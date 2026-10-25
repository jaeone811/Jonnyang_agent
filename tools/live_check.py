"""실제 인터넷으로 온라인 기능을 한 번씩 돌려본다 (CI용 점검, 테스트는 가짜 네트워크로 따로 돈다).

- 날씨·미세먼지·환율·위키·뉴스 명령을 실제 서버에 보내고 응답 문장을 출력한다.
- online.yaml의 지역 좌표를 Open-Meteo 지오코딩 결과와 비교해서 많이 다르면 알려준다.
- 외부 서버 상태에 따라 실패할 수 있으므로 CI에서는 실패해도 빌드를 막지 않는다(continue-on-error).

사용법: python tools/live_check.py
"""

from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jonnyang.app import build_app  # noqa: E402
from jonnyang.core.network import Network, NetworkError  # noqa: E402
from jonnyang.core.storage import Storage  # noqa: E402
from jonnyang.platform.fake import fake_platform  # noqa: E402
from jonnyang.skills.online.weather import geocode  # noqa: E402

COMMANDS = ["오늘 날씨 어때", "내일 부산 비 와?", "양양 날씨", "이번 주 날씨 알려줘", "미세먼지 어때",
            "달러 환율 알려줘", "엔화 환율", "100유로는 몇 원이야", "5만원은 몇 달러야",
            "광합성이 뭐야", "아인슈타인이 누구야", "위키에서 고양이 찾아줘",
            "뉴스 보여줘", "IT 뉴스 알려줘", "'인공지능' 뉴스 보여줘"]
FAIL_KEYS = ("online.", "error.", "weather.place_unknown", "currency.unsupported", "wiki.not_found", "news.empty")


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class Slow:
    """연달아 너무 빨리 부르면 서버가 연결을 끊는다(WinError 10054). 부를 때마다 조금 쉰다."""

    def __init__(self, net: Network):
        self.net = net

    def get_json(self, url, params=None, ttl=0):
        for attempt in range(3):
            time.sleep(0.4 + attempt)
            try:
                return self.net.get_json(url, params, ttl=ttl)
            except NetworkError as exc:
                if exc.kind != "offline" or attempt == 2:
                    raise
        return {}


def main() -> int:
    net = Network(timeout=15)
    ctx, d = build_app(platform=fake_platform(), storage=Storage(":memory:"), rng=random.Random(0), network=net)
    bad = 0
    for text in COMMANDS:
        replies = d.respond(text)
        failed = any(r.key.startswith(FAIL_KEYS) for r in replies)
        bad += failed
        print(f"{'FAIL' if failed else 'OK  '} > {text}")
        for r in replies:
            print("      " + r.text.replace("\n", "\n      "))
    print("\n== 지역 좌표 점검 (좌표표에 없는 지역을 찾는 방법(geocode)과 15km 넘게 차이 나면 표시) ==")
    geo = ctx.online["weather"]["geocode_url"]
    slow = Slow(net)
    for name, (lat, lon) in (ctx.online.get("places") or {}).items():
        try:
            r = geocode(slow, geo, name)
        except NetworkError as exc:
            print(f"  ?? {name}: {exc}")
            continue
        if r is None:
            print(f"  ?? {name}: 지오코딩 결과 없음")
            continue
        dist = km((lat, lon), (r["latitude"], r["longitude"]))
        mark = "!!" if dist > 15 else "ok"
        print(f"  {mark} {name}: 표 ({lat}, {lon}) / API {r.get('name')} ({r['latitude']}, {r['longitude']}, "
              f"{r.get('country_code')}) 차이 {dist:.1f}km")
    print(f"\n실패한 명령 {bad}개 / {len(COMMANDS)}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
