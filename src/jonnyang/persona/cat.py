"""존냥이 말투 계층. 캐릭터 관련 처리는 전부 여기서만 한다.

- 템플릿은 config/persona.yaml에서 읽는다 (코드에 대사 하드코딩 금지).
- 프로필 체인: 현재 프로필 → fallback → ... → plain. 냥체를 끄면 plain만 쓴다.
- 핵심 정보(Result.core)가 템플릿 때문에 빠지면 문장 끝에 덧붙여서라도 반드시 보여준다.
"""

from __future__ import annotations

import fnmatch
import random
import re
import string
from datetime import datetime
from typing import Any, Callable

from jonnyang.persona import fmt
from jonnyang.skills.base import Confirm, Result

EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002300-\U000023FF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D\U000020E3]+")


class _Keep(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class Persona:
    def __init__(self, data: dict, settings_get: Callable[[str, Any], Any], rng: random.Random | None = None):
        self.data = data
        self.profiles: dict[str, dict] = data.get("profiles", {})
        self.settings_get = settings_get
        self.rng = rng or random.Random()
        self.default_profile = data.get("default_profile", "soft")

    # ── 설정 ──
    @property
    def profile(self) -> str:
        p = self.settings_get("persona.profile", self.default_profile)
        return p if p in self.profiles else self.default_profile

    @property
    def nyang(self) -> bool:
        return bool(self.settings_get("persona.nyang", True))

    @property
    def emoji(self) -> bool:
        return bool(self.settings_get("persona.emoji", self.data.get("emoji_default", True)))

    def profile_names(self) -> list[str]:
        return [self.profile_title(p) for p in self.profiles if p != "plain"]

    def profile_title(self, name: str) -> str:
        return self.profiles.get(name, {}).get("title", name)

    def find_profile(self, text: str) -> str | None:
        for alias, name in (self.data.get("profile_aliases") or {}).items():
            if alias in text and name in self.profiles:
                return name
        return None

    def label(self, key: str) -> str:
        return str((self.data.get("labels") or {}).get(key, key))

    def ui(self, key: str) -> str:
        """GUI 문구 (입력창 안내, 메뉴 등)."""
        return str((self.data.get("ui") or {}).get(key, key))

    @property
    def appearance(self) -> dict[str, Any]:
        return dict(self.data.get("appearance") or {})

    def pose_for(self, key: str, ok: bool = True) -> str:
        """응답 키 → 고양이 표정. persona.yaml poses.rules에서 위부터 처음 맞는 것."""
        spec = self.data.get("poses") or {}
        for pattern, pose in spec.get("rules") or []:
            if fnmatch.fnmatchcase(key, pattern):
                return pose
        return spec.get("default", "happy") if ok else spec.get("error", "confused")

    # ── 템플릿 ──
    def _chain(self) -> list[str]:
        if not self.nyang:
            return ["plain"]
        chain, cur = [], self.profile
        while cur and cur not in chain and cur in self.profiles:
            chain.append(cur)
            cur = self.profiles[cur].get("fallback")
        if "plain" not in chain:
            chain.append("plain")
        return chain

    def template(self, key: str) -> str | None:
        for name in self._chain():
            t = (self.profiles.get(name, {}).get("templates") or {}).get(key)
            if t:
                return self.rng.choice(t) if isinstance(t, list) else str(t)
        return None

    def has_template(self, key: str) -> bool:
        return self.template(key) is not None

    def _fill(self, template: str, values: dict[str, str]) -> str:
        out = string.Formatter().vformat(template, (), _Keep(values))
        # 빈 값({label} 등) 때문에 생긴 이중 공백만 정리하고 줄 앞 들여쓰기는 둔다
        return "\n".join(re.sub(r"(?<=\S) {2,}", " ", line).rstrip() for line in out.split("\n"))

    def _format_data(self, data: dict[str, Any], now: datetime) -> dict[str, str]:
        return {k: fmt.value(k, v, now) for k, v in data.items()}

    def say(self, key: str, data: dict[str, Any] | None = None, now: datetime | None = None,
            core: tuple[str, ...] = (), items: list[dict] | None = None, item_key: str | None = None) -> str:
        now = now or datetime.now()
        data = dict(data or {})
        assumed = data.pop("assumed", None) or []
        values = self._format_data(data, now)
        notes = [self.label(f"assumed.{a}") for a in assumed if (self.data.get("labels") or {}).get(f"assumed.{a}")]
        values["note"] = f"({', '.join(notes)})" if notes else ""
        if items is not None:
            lines = []
            for it in items:
                t = self.template(item_key or "") or "- " + " ".join("{" + k + "}" for k in it)
                lines.append(self._fill(t, self._format_data(it, now)).rstrip())
            values["items"] = "\n".join(lines)
        t = self.template(key)
        if t is None:
            t = "[" + key + "] " + " ".join("{" + k + "}" for k in values if values[k])
        out = self._fill(t, values)
        # 핵심 정보 보장
        missing = [values[k] for k in core if values.get(k) and values[k] not in out]
        if missing:
            out += " (" + ", ".join(missing) + ")"
        if values["note"] and "{note}" not in t:
            out += " " + values["note"]
        if items is not None and "{items}" not in t and values["items"]:
            out += "\n" + values["items"]
        if not self.emoji:
            out = EMOJI_RE.sub("", out)
            out = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", out)).strip()
        return out.strip()

    def say_label(self, template: str, data: dict[str, Any], now: datetime) -> str:
        return self._fill(template, self._format_data(data, now))

    def render(self, r: Result | Confirm, now: datetime | None = None) -> str:
        text = self.say(r.key, r.data, now, r.core, r.items, r.item_key)
        for f in getattr(r, "follow", None) or []:
            extra = self.render(f, now)
            if extra:
                text += "\n" + extra
        return text
