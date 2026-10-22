"""타이머 (메모리에만 있음, 프로그램을 끄면 사라진다)."""

from __future__ import annotations

import itertools
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Confirm, Result, Skill

NO_RE = re.compile(r"(\d+)\s*번")
LABEL_RE = re.compile(r"^(.*?)\s*타이머")


@dataclass
class Timer:
    id: int
    end: datetime
    duration: timedelta
    label: str
    job: int


AVOID_SET = {"CANCEL": 0.5, "CLOSE": 0.5, "SHOW": 0.4, "ALL": 0.3}


class TimerSkill(Skill):
    name = "timer"
    intents = [
        Intent("timer.set", nouns={"타이머": 0.7}, verbs={"SET": 0.3, "OPEN": 0.2, "재": 0.5}, slots={"duration": 0.3},
               avoid=AVOID_SET, required=("duration",),
               examples=("3분 타이머 맞춰줘", "라면 타이머 4분", "1시간 반 타이머")),
        Intent("timer.list", nouns={"타이머": 0.7}, verbs={"SHOW": 0.3, "TELL": 0.2}, extras={"목록": 0.3},
               avoid={"CANCEL": 0.5, "CLOSE": 0.5, "SET": 0.3}, examples=("타이머 얼마나 남았어",)),
        Intent("timer.cancel", nouns={"타이머": 0.7}, verbs={"CANCEL": 0.3, "CLOSE": 0.3},
               avoid={"ALL": 0.4, "SET": 0.4}, examples=("타이머 취소해", "2번 타이머 꺼")),
        Intent("timer.clear", nouns={"타이머": 0.6}, verbs={"CANCEL": 0.2, "CLOSE": 0.2}, extras={"ALL": 0.3},
               avoid={"SET": 0.4},
               examples=("타이머 전부 꺼",)),
    ]

    def __init__(self, ctx):
        super().__init__(ctx)
        self.timers: dict[int, Timer] = {}
        self._ids = itertools.count(1)
        self.lock = threading.RLock()

    # ── helpers ──
    def _sorted(self) -> list[Timer]:
        with self.lock:
            return sorted(self.timers.values(), key=lambda t: t.end)

    def _items(self, now: datetime) -> list[dict[str, Any]]:
        return [{"no": i, "duration": t.duration, "remaining": max(t.end - now, timedelta()), "label": t.label}
                for i, t in enumerate(self._sorted(), start=1)]

    def _start(self, duration: timedelta, label: str, now: datetime) -> Timer:
        with self.lock:
            tid = next(self._ids)
            end = now + duration
            t = Timer(tid, end, duration, label, 0)
            t.job = self.ctx.scheduler.schedule(end, lambda: self._fire(tid))
            self.timers[tid] = t
            return t

    def _fire(self, tid: int) -> None:
        with self.lock:
            t = self.timers.pop(tid, None)
        if t is None:
            return
        self.ctx.notify([Result("timer.done", {"duration": t.duration, "label": t.label}, core=("duration",))],
                        beeps=2)

    def _stop(self, t: Timer) -> None:
        with self.lock:
            self.timers.pop(t.id, None)
            self.ctx.scheduler.cancel(t.job)

    # ── Skill ──
    def status(self, now: datetime) -> list[tuple[datetime, Result]]:
        return [(t.end, Result("status.timer", {"label": t.label, "remaining": max(t.end - now, timedelta()),
                                                "duration": t.duration}, core=("remaining",)))
                for t in self._sorted()]

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        if req.time.duration and req.time.error is None:
            slots["duration"] = req.time.duration
        m = LABEL_RE.search(req.text)
        if m:
            label = re.sub(r"[\d.]+\s*(시간|분|초|번)(\s*반)?|짜리|용|으로|로", "", m.group(1)).strip()
            if label:
                slots["label"] = label
        m = NO_RE.search(req.text)
        if m:
            slots["index"] = int(m.group(1))
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        now = req.now
        if intent == "timer.set":
            dur: timedelta = slots["duration"]
            if dur.total_seconds() <= 0 or dur > timedelta(days=7):
                return Result("timer.bad_duration", {"duration": dur}, core=("duration",), ok=False)
            t = self._start(dur, slots.get("label", ""), now)
            return Result("timer.set", {"duration": dur, "end": t.end, "label": t.label}, core=("duration", "end"),
                          undo={"op": "cancel", "id": t.id}, undo_label="timer.set")

        timers = self._sorted()
        if not timers:
            return Result("timer.none")

        if intent == "timer.list":
            return Result("timer.list", {"count": len(timers)}, core=("count",),
                          items=self._items(now), item_key="timer.item")

        if intent == "timer.cancel":
            target = self._pick(timers, slots)
            if target is None:
                return Result("timer.which", {"count": len(timers)}, items=self._items(now), item_key="timer.item")
            remaining = max(target.end - now, timedelta())
            self._stop(target)
            return Result("timer.cancel", {"duration": target.duration, "remaining": remaining,
                                           "label": target.label}, core=("duration",),
                          undo={"op": "restore", "timers": [self._dump(target, now)]}, undo_label="timer.cancel")

        if intent == "timer.clear":
            def do_clear() -> Result:
                current = self._sorted()
                dumped = [self._dump(t, self.ctx.clock()) for t in current]
                for t in current:
                    self._stop(t)
                return Result("timer.clear", {"count": len(current)}, core=("count",),
                              undo={"op": "restore", "timers": dumped}, undo_label="timer.clear")
            return Confirm("confirm.timer_clear", do_clear, {"count": len(timers)}, core=("count",),
                           items=self._items(now), item_key="timer.item")
        raise ValueError(intent)

    def _pick(self, timers: list[Timer], slots: dict[str, Any]) -> Timer | None:
        if "index" in slots and 1 <= slots["index"] <= len(timers):
            return timers[slots["index"] - 1]
        if "duration" in slots:
            same = [t for t in timers if t.duration == slots["duration"]]
            if len(same) == 1:
                return same[0]
        if slots.get("label"):
            same = [t for t in timers if t.label and t.label in slots["label"]]
            if len(same) == 1:
                return same[0]
        return timers[0] if len(timers) == 1 else None

    @staticmethod
    def _dump(t: Timer, now: datetime) -> dict[str, Any]:
        return {"remaining": max((t.end - now).total_seconds(), 1), "duration": t.duration.total_seconds(),
                "label": t.label}

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        now = self.ctx.clock()
        if payload["op"] == "cancel":
            t = self.timers.get(payload["id"])
            if t is None:
                return Result("undo.expired", ok=False)
            self._stop(t)
            return Result("undo.done")
        for d in payload["timers"]:
            t = self._start(timedelta(seconds=d["remaining"]), d["label"], now)
            t.duration = timedelta(seconds=d["duration"])
        return Result("undo.done")
