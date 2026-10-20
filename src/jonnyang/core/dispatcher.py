"""입력 → 의도 판정 → 스킬 실행 → 말투 입히기. 되묻기/확인 대기 상태도 여기서 관리한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from jonnyang.core.context import AppContext
from jonnyang.nlu.matcher import Candidate, Intent, Matcher
from jonnyang.nlu.pipeline import NLU, Request
from jonnyang.nlu.preprocess import clean
from jonnyang.skills.base import Confirm, Result

YES_WORDS = ["응+", "어+", "ㅇㅇ+", "ㅇ", "그래", "그래요", "네", "예", "좋아", "오케이", "ok", "okay",
             "웅", "엉", "yes", "y", "해", "해줘", "해 줘", "그렇게 해", "ㄱㄱ", "고고", "ㄱ", "맞아", "부탁해"]
NO_WORDS = ["아니", "아니야", "아니요", "아뇨", "ㄴㄴ+", "ㄴ", "싫어", "취소", "취소해", "됐어", "no", "n",
            "안 해", "하지 마", "노", "놉", "그만", "말아", "아냐"]
YES_RE = re.compile(rf"^(?:{'|'.join(YES_WORDS)})$", re.I)
NO_RE = re.compile(rf"^(?:{'|'.join(NO_WORDS)})$", re.I)
CHOICE_RE = [(re.compile(r"^(?:1|1번|첫\s*번째|첫째|앞에\s*거|앞에꺼|위에\s*거)$"), 0),
             (re.compile(r"^(?:2|2번|두\s*번째|둘째|뒤에\s*거|뒤에꺼|아래\s*거)$"), 1)]


@dataclass
class Interpretation:
    # execute | ask_slot | clarify | fallback | negated | time_error | wake | empty | ignored
    kind: str
    req: Request
    intent: Intent | None = None
    candidates: list[Candidate] = field(default_factory=list)
    slots: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    options: list[Intent] = field(default_factory=list)


@dataclass
class Pending:
    kind: str                       # confirm | choice | slot
    created: datetime
    confirm: Confirm | None = None
    skill: str = ""
    intent: str = ""
    options: list[Intent] = field(default_factory=list)
    raw: str = ""


class Dispatcher:
    def __init__(self, ctx: AppContext, skills: list):
        self.ctx = ctx
        intents: list[Intent] = []
        for skill in skills:
            ctx.skills[skill.name] = skill
            for it in skill.intents:
                it.skill = skill.name
                intents.append(it)
        self.intents = intents
        self.matcher = Matcher(intents, ctx.analyzer.lexicon.group_names, self._protected)
        self.nlu = NLU(ctx.analyzer, ctx.settings.get("default_reminder_hour", 9))
        th = ctx.settings.get("thresholds", {})
        self.exec_th = th.get("execute", 0.7)
        self.margin = th.get("margin", 0.15)
        self.clarify_th = th.get("clarify", 0.4)
        self.pending_ttl = timedelta(seconds=ctx.settings.get("pending_timeout_sec", 60))
        self.pending: Pending | None = None

    def _protected(self) -> set[str]:
        return set().union(*(s.protected_words() for s in self.ctx.skills.values()))

    # ── 판정 (실행 없음, 테스트에서 직접 사용) ──
    def interpret(self, raw: str, now: datetime | None = None, forced: Intent | None = None) -> Interpretation:
        now = now or self.ctx.clock()
        req = self.nlu.parse(raw, now)
        if not req.text:
            return Interpretation("wake" if req.woke else "empty", req)
        if self.ctx.wake_required and not req.woke and forced is None:
            return Interpretation("ignored", req)
        if req.negated:
            return Interpretation("negated", req)
        cands = self.matcher.rank(req)
        if forced is not None:
            intent = forced
        else:
            top = cands[0]
            second = cands[1].score if len(cands) > 1 else 0.0
            if top.score >= self.exec_th and top.score - second >= self.margin:
                intent = top.intent
            elif top.score >= self.clarify_th:
                options = [c.intent for c in cands[:2] if c.score >= self.clarify_th]
                return Interpretation("clarify", req, candidates=cands, options=options)
            else:
                return Interpretation("fallback", req, candidates=cands)
        return self._prepare(intent, req, cands)

    def _prepare(self, intent: Intent, req: Request, cands: list[Candidate]) -> Interpretation:
        skill = self.ctx.skills[intent.skill]
        time_needed = {"at", "duration"} & set(intent.required)
        if time_needed and req.time.error:
            return Interpretation("time_error", req, intent, cands)
        slots = skill.extract(intent.name, req)
        missing = [s for s in intent.required if s not in slots]
        kind = "ask_slot" if missing else "execute"
        return Interpretation(kind, req, intent, cands, slots, missing)

    # ── 실행 ──
    def handle(self, raw: str) -> list[str]:
        now = self.ctx.clock()
        if self.pending and now - self.pending.created > self.pending_ttl:
            self.pending = None
        if self.pending:
            out = self._handle_pending(raw, now)
            if out is not None:
                return out
        return self._run(self.interpret(raw, now), now)

    def _say(self, r: Result | Confirm, now: datetime) -> list[str]:
        return [self.ctx.persona.render(r, now)]

    def _run(self, it: Interpretation, now: datetime) -> list[str]:
        p = self.ctx.persona
        if it.kind == "empty":
            return []
        if it.kind == "wake":
            return self._say(Result("wake"), now)
        if it.kind == "ignored":
            return self._say(Result("ignored"), now)
        if it.kind == "negated":
            return self._say(Result("negated"), now)
        if it.kind == "time_error":
            return self._say(Result(f"time.{it.req.time.error}"), now)
        if it.kind == "fallback":
            if it.req.excluded:
                return self._say(Result("excluded_only", {"excluded": sorted(it.req.excluded)},
                                        core=("excluded",)), now)
            return self._say(Result("fallback", {"examples": self._examples(3)}, core=("examples",)), now)
        if it.kind == "clarify":
            self.pending = Pending("choice", now, options=it.options, raw=it.req.raw)
            items = [{"no": i, "label": p.label(f"intent.{o.name}")} for i, o in enumerate(it.options, 1)]
            key = "clarify" if len(items) > 1 else "clarify_one"
            return self._say(Result(key, {"label": items[0]["label"]}, items=items, item_key="clarify.item"), now)
        if it.kind == "ask_slot":
            self.pending = Pending("slot", now, skill=it.intent.skill, intent=it.intent.name, raw=it.req.raw)
            return self._say(Result(f"ask.{it.missing[0]}"), now)
        return self._execute(it.intent, it.req, it.slots, now)

    def _execute(self, intent: Intent, req: Request, slots: dict[str, Any], now: datetime) -> list[str]:
        skill = self.ctx.skills[intent.skill]
        out = skill.handle(intent.name, req, slots)
        if isinstance(out, Confirm):
            self.pending = Pending("confirm", now, confirm=out, skill=skill.name, intent=intent.name)
            return self._say(out, now)
        return self._finish(skill.name, intent.name, out, now)

    def _finish(self, skill: str, intent: str, res: Result, now: datetime) -> list[str]:
        if isinstance(res, Confirm):   # 되돌리기처럼 확인을 한 번 더 요구하는 경우
            self.pending = Pending("confirm", now, confirm=res, skill=skill, intent=intent)
            return self._say(res, now)
        if res.undo is not None and res.ok:
            self.ctx.history.record(skill, intent, res.undo_label, res.data, res.undo)
        return self._say(res, now)

    def _handle_pending(self, raw: str, now: datetime) -> list[str] | None:
        pend = self.pending
        answer = re.sub(r"[?!.~\s]+$", "", clean(raw)).lower()
        if pend.kind == "confirm":
            if YES_RE.match(answer):
                self.pending = None
                return self._finish(pend.skill, pend.intent, pend.confirm.action(), now)
            if NO_RE.match(answer):
                self.pending = None
                return self._say(Result("cancelled"), now)
            self.pending = None
            return None
        if pend.kind == "choice":
            idx = None
            for pat, i in CHOICE_RE:
                if pat.match(answer):
                    idx = i
            if idx is None and YES_RE.match(answer):
                idx = 0
            if idx is not None and idx < len(pend.options):
                self.pending = None
                it = self.interpret(pend.raw, now, forced=pend.options[idx])
                return self._run(it, now)
            if NO_RE.match(answer):
                self.pending = None
                return self._say(Result("cancelled"), now)
            self.pending = None
            return None
        if pend.kind == "slot":
            if NO_RE.match(answer):
                self.pending = None
                return self._say(Result("cancelled"), now)
            intent = next(i for i in self.intents if i.name == pend.intent)
            it = self.interpret(f"{pend.raw} {raw}", now, forced=intent)
            self.pending = None
            if it.kind == "execute" or it.kind == "time_error":
                return self._run(it, now)
            return None
        self.pending = None
        return None

    def _examples(self, n: int) -> list[str]:
        pool = [ex for it in self.intents for ex in it.examples[:1] if not it.name.startswith(("chat.", "persona."))]
        return self.ctx.persona.rng.sample(pool, min(n, len(pool)))

    # ── 시작 ──
    def startup(self) -> list[str]:
        now = self.ctx.clock()
        h = now.hour
        part = "morning" if 5 <= h < 11 else "afternoon" if h < 17 else "evening" if h < 22 else "night"
        lines = self._say(Result(f"greet.{part}"), now)
        for skill in self.ctx.skills.values():
            for r in skill.on_start():
                lines += self._say(r, now)
        return lines
