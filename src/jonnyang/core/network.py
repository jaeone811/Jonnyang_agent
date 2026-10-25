"""네트워크 호출은 전부 여기로만 한다: 타임아웃, 예외 정리, 메모리 캐시.

- 표준 라이브러리 urllib만 쓴다. Windows에서는 시스템 프록시 설정과 인증서 저장소를 그대로 쓴다.
- 실패는 `NetworkError(kind)` 하나로 바꿔서 던진다. kind: offline | timeout | http | bad_data | disabled
- 테스트는 `FakeNetwork`로 미리 준비한 응답을 돌려준다(실제 인터넷 안 씀).
- 외부에서 받은 글은 표시만 한다. 여기서도 스킬에서도 명령으로 해석하지 않는다.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

USER_AGENT = "Jonnyang/0.2 (rule-based desktop assistant; +https://github.com/jaeone811/Jonnyang_agent)"
MAX_BYTES = 2 * 1024 * 1024


class NetworkError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


def build_url(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None}
    return f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(clean, doseq=True)}"


class Network:
    def __init__(self, timeout: float = 6.0, enabled: Callable[[], bool] = lambda: True,
                 clock: Callable[[], float] = time.monotonic):
        self.timeout = timeout
        self.enabled = enabled
        self.clock = clock
        self._cache: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    # ── 공개 API ──
    def get_bytes(self, url: str, params: dict[str, Any] | None = None, ttl: float = 0) -> bytes:
        if not self.enabled():
            raise NetworkError("disabled")
        full = build_url(url, params)
        now = self.clock()
        with self._lock:
            hit = self._cache.get(full)
            if hit and hit[0] > now:
                return hit[1]
        data = self._fetch(full)
        if ttl > 0:
            with self._lock:
                self._cache[full] = (now + ttl, data)
        return data

    def get_json(self, url: str, params: dict[str, Any] | None = None, ttl: float = 0) -> Any:
        data = self.get_bytes(url, params, ttl)
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            with self._lock:
                self._cache.pop(build_url(url, params), None)
            raise NetworkError("bad_data", str(exc)) from exc

    # ── 실제 요청 ──
    def _fetch(self, full_url: str) -> bytes:
        req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (https 고정 URL만)
                data = resp.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise NetworkError("http", str(exc.code)) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise NetworkError("timeout") from exc
            raise NetworkError("offline", str(exc.reason)) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkError("timeout") from exc
        except (OSError, ValueError) as exc:     # 연결 끊김, 잘못된 응답 등
            raise NetworkError("offline", str(exc)) from exc
        if len(data) > MAX_BYTES:
            raise NetworkError("bad_data", "response too large")
        return data


class FakeNetwork(Network):
    """테스트용. URL 앞부분 → 응답(bytes/str/dict/list) 또는 던질 예외. 가장 긴 앞부분이 이긴다."""

    def __init__(self, routes: dict[str, Any] | None = None, **kw):
        super().__init__(**kw)
        self.routes: dict[str, Any] = dict(routes or {})
        self.calls: list[str] = []

    def _fetch(self, full_url: str) -> bytes:
        self.calls.append(full_url)
        matches = [p for p in self.routes if full_url.startswith(p)]
        if not matches:
            raise NetworkError("offline", "no fake route")
        value = self.routes[max(matches, key=len)]
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(full_url)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False).encode("utf-8")
        if isinstance(value, str):
            return value.encode("utf-8")
        return value
