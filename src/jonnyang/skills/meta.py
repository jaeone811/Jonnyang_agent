"""도움말, 되돌리기, 별칭 등록, 말투 설정, 잡담."""

from __future__ import annotations

import os
import re
from typing import Any

from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Confirm, Result, Skill

ALIAS_PATTERNS = [
    # "메모장을 노트라고 불러", "C:\work 폴더를 작업실이라고 부를게"
    re.compile(r"^(?P<target>.+?)\s*(?:폴더)?\s*(?:을|를)\s*(?P<alias>[^\s]+?)(?:이)?라고\s*"
               r"(?:불러|부를|부르|할게|해|등록)"),
    # "노트를 메모장 별칭으로 등록해"
    re.compile(r"^(?P<alias>[^\s]+?)\s*(?:을|를)\s*(?P<target>.+?)(?:의)?\s*별칭으로"),
    # "별칭 등록 노트 = 메모장"
    re.compile(r"별칭\s*(?:등록|추가)?\s*[:,]?\s*(?P<alias>[^\s=]+)\s*=\s*(?P<target>.+)$"),
]
PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|~|%[A-Za-z_]+%|\\\\)")
SETTING_ON = ("OPEN",)
SETTING_OFF = ("CLOSE", "CANCEL")


def _alias_hint(req) -> float:
    return 0.8 if any(p.search(req.text) for p in ALIAS_PATTERNS) else 0.0


HELP_RE = re.compile(r"뭐\s*(?:할|하)\s*(?:수|줄\s*수)\s*있|뭘?\s*할\s*줄\s*알|뭘\s*할\s*수|어떻게\s*써|기능\s*뭐")


def _help_hint(req) -> float:
    return 1.0 if HELP_RE.search(req.text) else 0.0


def _undo_hint(req) -> float:
    return 0.9 if re.search(r"(?:방금|아까|직전|마지막).*(?:취소|되돌|원래대로|없던\s*일)|실행\s*취소|없던\s*일로",
                            req.text) else 0.0


def _onoff(req) -> bool | None:
    if re.search(r"없이|안\s*써|빼", req.text):
        return False
    if any(g in req.groups for g in SETTING_OFF):
        return False
    if any(g in req.groups for g in SETTING_ON) or re.search(r"써\s*줘|쓰자|써$|살려|다시", req.text):
        return True
    return None


class MetaSkill(Skill):
    name = "meta"
    intents = [
        Intent("meta.help", nouns={"도움말": 1.0, "도움": 0.8, "명령어": 0.8, "사용법": 0.8, "기능": 0.6, "help": 1.0,
                                     "도와주": 0.9, "돕": 0.8},
               hint=_help_hint, examples=("뭐 할 수 있어?", "도움말")),
        Intent("meta.undo", nouns={"되돌리기": 1.0, "실행취소": 1.0, "undo": 1.0}, verbs={"UNDO": 0.8},
               hint=_undo_hint, avoid={"CALL": 0.5}, examples=("방금 거 취소해", "되돌려줘")),
        Intent("meta.alias", nouns={"별칭": 0.6, "별명": 0.6}, verbs={"CALL": 0.3, "SET": 0.2}, hint=_alias_hint,
               examples=("메모장을 노트라고 불러",)),
        Intent("persona.nyang", nouns={"냥체": 1.0, "냥냥체": 1.0}, examples=("냥체 꺼", "냥체 켜")),
        Intent("persona.emoji", nouns={"이모지": 1.0, "이모티콘": 0.9}, examples=("이모지 꺼",)),
        Intent("persona.profile", nouns={"말투": 0.7, "캐릭터": 0.5},
               hint=lambda req: 0.3 if re.search(r"순하|순한|시크|도도|기본|디시|원래", req.text) else 0.0,
               examples=("말투 시크하게", "말투 순하게")),
        Intent("wake.required", nouns={"호출어": 1.0}, examples=("호출어 꺼", "호출어 켜")),
        Intent("chat.greet", nouns={"안녕": 1.0, "하이": 0.9, "헬로": 0.9, "반갑": 0.9, "hi": 0.9, "hello": 0.9},
               examples=("안녕",)),
        Intent("chat.thanks", nouns={"고맙": 1.0, "고마워": 1.0, "감사": 1.0, "땡큐": 1.0, "thanks": 1.0}),
        Intent("chat.meow", nouns={"야옹": 1.0, "냐옹": 1.0, "츄르": 1.0, "심심": 0.9, "귀엽": 0.9, "귀여워": 0.9,
                                   "냥": 0.8, "놀아": 0.8}),
    ]

    # ── 별칭 ──
    def _parse_alias(self, req) -> tuple[str, str] | None:
        text = req.text
        for p in ALIAS_PATTERNS:
            m = p.search(text)
            if m:
                return m.group("alias").strip(" '\""), m.group("target").strip(" '\"")
        return None

    def _resolve_target(self, target: str) -> tuple[str, str] | None:
        known = self.ctx.aliases.get(target) or self.ctx.aliases.get(target.replace(" ", ""))
        if known:
            return known
        if PATH_RE.match(target):
            path = os.path.expandvars(os.path.expanduser(target))
            if os.path.isdir(path):
                return "folder", target
            if os.path.exists(path) or target.lower().endswith(".exe"):
                return "app", target
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) and not PATH_RE.match(target):
            return "app", target      # ms-settings: 같은 URI
        return None

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        if intent == "meta.alias":
            parsed = self._parse_alias(req)
            if parsed:
                slots["alias"], slots["target"] = parsed
        elif intent in ("persona.nyang", "persona.emoji", "wake.required"):
            on = _onoff(req)
            if on is not None:
                slots["enabled"] = on
        elif intent == "persona.profile":
            name = self.ctx.persona.find_profile(req.text)
            if name:
                slots["profile"] = name
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        if intent == "meta.help":
            return self._help()
        if intent == "meta.undo":
            return self.ctx.undo_last()
        if intent == "meta.alias":
            return self._alias(slots)
        if intent in ("persona.nyang", "persona.emoji", "wake.required"):
            return self._toggle(intent, slots)
        if intent == "persona.profile":
            name = slots.get("profile")
            if not name:
                return Result("persona.profile_unknown", {"profiles": self.ctx.persona.profile_names()},
                              core=("profiles",))
            prev = {"persona.profile": self.ctx.persona.profile, "persona.nyang": self.ctx.persona.nyang}
            self.ctx.storage.set_setting("persona.profile", name)
            self.ctx.storage.set_setting("persona.nyang", True)
            return Result("persona.profile", {"profile": self.ctx.persona.profile_title(name)}, core=("profile",),
                          undo={"settings": prev}, undo_label="setting")
        if intent.startswith("chat."):
            return Result(intent)
        raise ValueError(intent)

    def _help(self) -> Result:
        items = []
        for skill in self.ctx.skills.values():
            if skill.name == "meta":
                continue
            examples = [ex for it in skill.intents for ex in it.examples[:1]][:3]
            if examples:
                items.append({"skill": self.ctx.persona.label(f"skill.{skill.name}"),
                              "examples": " / ".join(f"\"{e}\"" for e in examples)})
        items.append({"skill": self.ctx.persona.label("skill.meta"),
                      "examples": "\"되돌려줘\" / \"메모장을 노트라고 불러\" / \"냥체 꺼\""})
        return Result("meta.help", items=items, item_key="meta.help_item")

    def _alias(self, slots: dict[str, Any]) -> Result | Confirm:
        if "alias" not in slots:
            return Result("ask.alias")
        alias, target = slots["alias"], slots["target"]
        resolved = self._resolve_target(target)
        if not resolved:
            return Result("alias.bad_target", {"target": target}, core=("target",), ok=False)
        kind, real = resolved
        prev = self.ctx.aliases.get(alias)

        def do_set() -> Result:
            self.ctx.aliases.set(alias, kind, real)
            self.ctx.analyzer.add_word(alias)
            return Result("alias.set", {"alias": alias, "target": real}, core=("alias", "target"),
                          undo={"alias": alias, "prev": list(prev) if prev else None}, undo_label="alias")
        if prev and prev != (kind, real):
            return Confirm("confirm.alias_overwrite", do_set, {"alias": alias, "old": prev[1], "target": real},
                           core=("alias", "old", "target"))
        return do_set()

    def _toggle(self, intent: str, slots: dict[str, Any]) -> Result:
        key = {"persona.nyang": "persona.nyang", "persona.emoji": "persona.emoji",
               "wake.required": "wake.required"}[intent]
        current = {"persona.nyang": self.ctx.persona.nyang, "persona.emoji": self.ctx.persona.emoji,
                   "wake.required": self.ctx.wake_required}[key]
        on = slots.get("enabled", not current)
        self.ctx.storage.set_setting(key, on)
        return Result(f"{intent}_{'on' if on else 'off'}", undo={"settings": {key: current}}, undo_label="setting")

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        if "settings" in payload:
            for k, v in payload["settings"].items():
                self.ctx.storage.set_setting(k, v)
            return Result("undo.done")
        if "alias" in payload:
            if payload["prev"]:
                self.ctx.aliases.set(payload["alias"], *payload["prev"])
            else:
                self.ctx.aliases.delete(payload["alias"])
            return Result("undo.done")
        return Result("undo.unsupported", ok=False)
