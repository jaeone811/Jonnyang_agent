"""리마인더와 알람. 둘 다 SQLite에 저장되고 프로그램이 켜져 있을 때 울린다.

꺼져 있는 동안 시간이 지난 것은 다음 시작 때 '놓친 알림'으로 알려준다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from jonnyang.core.storage import iso
from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Confirm, Result, Skill

NO_RE = re.compile(r"(\d+)\s*번")
# 리마인더 내용에서 떼어낼 명령 꼬리
TRAILER_RE = re.compile(
    r"\s*(?:좀\s*)?(?:나한테\s*|저한테\s*)?"
    r"(?:알려\s*줘|알려\s*주세요|알려\s*줄래|알려|말해\s*줘|말해|리마인드\s*해\s*줘|리마인드|상기시켜\s*줘|상기시켜|"
    r"알림\s*(?:줘|해\s*줘|설정해\s*줘|설정|등록)?|리마인더\s*(?:등록|추가|설정|맞춰)?\s*(?:해\s*줘|해)?)\s*$")
LEAD_RE = re.compile(r"^\s*(?:에는|에|쯤에?|까지|부터)?\s*(?:리마인더|알림)?\s*(?:등록|추가|설정)?\s*[:,]?\s*")
FORGET_RE = re.compile(r"\s*(?:거\s*)?잊지\s*(?:않게|말라고|말게|말고)\s*$")


def extract_message(text: str, spans: list[tuple[int, int]]) -> str:
    buf = list(text)
    for s, e in spans:
        for i in range(s, min(e, len(buf))):
            buf[i] = " "
    msg = " ".join("".join(buf).split())
    msg = TRAILER_RE.sub("", msg)
    msg = FORGET_RE.sub("", msg)
    msg = LEAD_RE.sub("", msg)
    msg = re.sub(r"(?:으)?라고$", "기", msg)          # "병원 가라고" → "병원 가기"
    msg = re.sub(r"다고$", "다", msg)                 # "회의 있다고" → "회의 있다"
    msg = re.sub(r"(?:이)?라는\s*거$", "", msg)
    return msg.strip(" ,.")


TELL_ME_RE = re.compile(r"(?:으)?라고\s*(?:좀\s*)?해\s*(?:줘|주세요|줄래)")


def _reminder_hint(req) -> float:
    score = 0.0 if req.has_slot("at") else -0.2
    if "TELL" not in req.groups and TELL_ME_RE.search(req.text):   # "쓰레기 버리라고 해줘"
        score += 0.4
    return score


class _Scheduled(Skill):
    """reminders 테이블을 kind별로 다루는 공통 부분."""

    kind = ""

    def _rows(self) -> list:
        return self.ctx.storage.query(
            "SELECT * FROM reminders WHERE kind = ? AND delivered = 0 ORDER BY at", (self.kind,))

    def _items(self, rows) -> list[dict[str, Any]]:
        return [{"no": i, "at": datetime.fromisoformat(r["at"]), "message": r["message"]}
                for i, r in enumerate(rows, start=1)]

    def _insert(self, at: datetime, message: str, created: datetime) -> int:
        cur = self.ctx.storage.execute(
            "INSERT INTO reminders(kind, at, message, created) VALUES(?, ?, ?, ?)",
            (self.kind, iso(at), message, iso(created)))
        rid = cur.lastrowid
        self._arm(rid, at)
        return rid

    def _arm(self, rid: int, at: datetime) -> None:
        self.jobs[rid] = self.ctx.scheduler.schedule(at, lambda: self._fire(rid))

    def _delete(self, rid: int) -> None:
        self.ctx.storage.execute("DELETE FROM reminders WHERE id = ?", (rid,))
        job = self.jobs.pop(rid, None)
        if job:
            self.ctx.scheduler.cancel(job)

    def _fire(self, rid: int) -> None:
        rows = self.ctx.storage.query("SELECT * FROM reminders WHERE id = ? AND delivered = 0", (rid,))
        if not rows:
            return
        self.ctx.storage.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (rid,))
        self.jobs.pop(rid, None)
        r = rows[0]
        self.ctx.notify([Result(f"{self.kind}.done", {"at": datetime.fromisoformat(r["at"]),
                                                      "message": r["message"]}, core=("message",))],
                        beeps=3 if self.kind == "alarm" else 1)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.jobs: dict[int, int] = {}

    def on_start(self) -> list[Result]:
        now = self.ctx.clock()
        missed = []
        for r in self._rows():
            at = datetime.fromisoformat(r["at"])
            if at <= now:
                missed.append({"at": at, "message": r["message"]})
                self.ctx.storage.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (r["id"],))
            else:
                self._arm(r["id"], at)
        if not missed:
            return []
        return [Result(f"{self.kind}.missed", {"count": len(missed)}, core=("count",), items=missed,
                       item_key=f"{self.kind}.missed_item")]

    def _list(self) -> Result:
        rows = self._rows()
        if not rows:
            return Result(f"{self.kind}.none")
        return Result(f"{self.kind}.list", {"count": len(rows)}, core=("count",), items=self._items(rows),
                      item_key=f"{self.kind}.item")

    def _cancel(self, req, slots) -> Result:
        rows = self._rows()
        if not rows:
            return Result(f"{self.kind}.none")
        target = None
        if "index" in slots and 1 <= slots["index"] <= len(rows):
            target = rows[slots["index"] - 1]
        elif req.time.at is not None:
            same = [r for r in rows if datetime.fromisoformat(r["at"]) == req.time.at]
            target = same[0] if len(same) == 1 else None
        if target is None:
            words = [w for w in req.lemmas if len(w) >= 2]
            same = [r for r in rows if any(w in r["message"] for w in words)]
            if len(same) == 1:
                target = same[0]
        if target is None and len(rows) == 1:
            target = rows[0]
        if target is None:
            return Result(f"{self.kind}.which", {"count": len(rows)}, items=self._items(rows),
                          item_key=f"{self.kind}.item")
        at = datetime.fromisoformat(target["at"])
        self._delete(target["id"])
        return Result(f"{self.kind}.cancel", {"at": at, "message": target["message"]}, core=("at", "message"),
                      undo={"op": "restore", "rows": [{"at": target["at"], "message": target["message"]}]},
                      undo_label=f"{self.kind}.cancel")

    def _clear(self) -> Result | Confirm:
        rows = self._rows()
        if not rows:
            return Result(f"{self.kind}.none")

        def do_clear() -> Result:
            current = self._rows()
            for r in current:
                self._delete(r["id"])
            return Result(f"{self.kind}.clear", {"count": len(current)}, core=("count",),
                          undo={"op": "restore", "rows": [{"at": r["at"], "message": r["message"]} for r in current]},
                          undo_label=f"{self.kind}.clear")
        return Confirm(f"confirm.{self.kind}_clear", do_clear, {"count": len(rows)}, core=("count",),
                       items=self._items(rows), item_key=f"{self.kind}.item")

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        now = self.ctx.clock()
        if payload["op"] == "delete":
            self._delete(payload["id"])
            return Result("undo.done")
        skipped = 0
        for r in payload["rows"]:
            at = datetime.fromisoformat(r["at"])
            if at <= now:
                skipped += 1
                continue
            self._insert(at, r["message"], now)
        if skipped and skipped == len(payload["rows"]):
            return Result("undo.expired", ok=False)
        return Result("undo.done")

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        if req.time.at is not None and req.time.error is None:
            slots["at"] = req.time.at
        m = NO_RE.search(req.text)
        if m:
            slots["index"] = int(m.group(1))
        return slots


class ReminderSkill(_Scheduled):
    name = "reminder"
    kind = "reminder"
    intents = [
        Intent("reminder.set", nouns={"리마인더": 0.6, "리마인드": 0.6, "알림": 0.5},
               verbs={"TELL": 0.4, "SET": 0.3, "ADD": 0.3}, slots={"at": 0.35},
               extras={"잊": 0.1}, avoid={"CANCEL": 0.5, "SHOW": 0.4, "ALL": 0.3},
               hint=_reminder_hint, required=("at",),
               examples=("내일 오후 3시에 병원 가라고 알려줘", "10분 뒤에 빨래 꺼내라고 알려줘")),
        Intent("reminder.list", nouns={"리마인더": 0.7, "리마인드": 0.7, "알림": 0.6, "일정": 0.5},
               verbs={"SHOW": 0.4, "TELL": 0.3}, extras={"목록": 0.3, "리스트": 0.3},
               avoid={"CANCEL": 0.5, "SET": 0.3, "ADD": 0.3}, examples=("리마인더 뭐 있어",)),
        Intent("reminder.cancel", nouns={"리마인더": 0.7, "리마인드": 0.7, "알림": 0.6},
               verbs={"CANCEL": 0.3}, avoid={"ALL": 0.4, "SET": 0.4, "ADD": 0.4}, examples=("병원 리마인더 취소",)),
        Intent("reminder.clear", nouns={"리마인더": 0.6, "리마인드": 0.6, "알림": 0.5},
               verbs={"CANCEL": 0.2}, extras={"ALL": 0.3}, avoid={"SET": 0.4, "ADD": 0.4},
               examples=("리마인더 전부 지워",)),
    ]

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots = super().extract(intent, req)
        if intent == "reminder.set":
            msg = req.quoted[0] if req.quoted else extract_message(req.text, req.time.spans)
            slots["message"] = msg
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        if intent == "reminder.set":
            at: datetime = slots["at"]
            message = slots.get("message") or ""
            rid = self._insert(at, message, req.now)
            return Result("reminder.set", {"at": at, "message": message, "assumed": req.time.assumed},
                          core=("at", "message"), undo={"op": "delete", "id": rid}, undo_label="reminder.set")
        if intent == "reminder.list":
            return self._list()
        if intent == "reminder.cancel":
            return self._cancel(req, slots)
        if intent == "reminder.clear":
            return self._clear()
        raise ValueError(intent)


ALARM_AVOID = {"CANCEL": 0.5, "CLOSE": 0.5, "SHOW": 0.4, "ALL": 0.3}


class AlarmSkill(_Scheduled):
    name = "alarm"
    kind = "alarm"
    intents = [
        Intent("alarm.set", nouns={"알람": 0.7, "모닝콜": 0.7}, verbs={"SET": 0.3, "OPEN": 0.2, "깨우": 0.5},
               slots={"at": 0.3}, avoid=ALARM_AVOID, required=("at",),
               examples=("내일 아침 7시 알람 맞춰줘", "30분 뒤에 깨워줘")),
        Intent("alarm.list", nouns={"알람": 0.7, "모닝콜": 0.7}, verbs={"SHOW": 0.3, "TELL": 0.2},
               extras={"목록": 0.3, "리스트": 0.3},
               avoid={"CANCEL": 0.5, "CLOSE": 0.5, "SET": 0.3}, examples=("알람 뭐 있어",)),
        Intent("alarm.cancel", nouns={"알람": 0.7, "모닝콜": 0.7}, verbs={"CANCEL": 0.3, "CLOSE": 0.3},
               avoid={"ALL": 0.4, "SET": 0.4}, examples=("7시 알람 꺼줘",)),
        Intent("alarm.clear", nouns={"알람": 0.6, "모닝콜": 0.6}, verbs={"CANCEL": 0.2, "CLOSE": 0.2},
               extras={"ALL": 0.3}, avoid={"SET": 0.4}, examples=("알람 다 꺼줘",)),
    ]

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        if intent == "alarm.set":
            at: datetime = slots["at"]
            rid = self._insert(at, "", req.now)
            return Result("alarm.set", {"at": at, "assumed": req.time.assumed}, core=("at",),
                          undo={"op": "delete", "id": rid}, undo_label="alarm.set")
        if intent == "alarm.list":
            return self._list()
        if intent == "alarm.cancel":
            return self._cancel(req, slots)
        if intent == "alarm.clear":
            return self._clear()
        raise ValueError(intent)
