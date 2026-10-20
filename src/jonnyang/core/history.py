"""실행 기록과 되돌리기 로그."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from jonnyang.core.storage import Storage, iso


def _enc(o: Any) -> Any:
    if isinstance(o, datetime):
        return {"__dt": o.isoformat()}
    if isinstance(o, timedelta):
        return {"__td": o.total_seconds()}
    return str(o)


def _dec(d: dict) -> Any:
    if "__dt" in d:
        return datetime.fromisoformat(d["__dt"])
    if "__td" in d:
        return timedelta(seconds=d["__td"])
    return d


def dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=_enc)


def loads(s: str) -> Any:
    return json.loads(s, object_hook=_dec)


class History:
    def __init__(self, storage: Storage, clock):
        self.storage = storage
        self.clock = clock

    def record(self, skill: str, intent: str, label_key: str | None, label_data: dict[str, Any],
               undo: dict[str, Any]) -> int:
        cur = self.storage.execute(
            "INSERT INTO history(ts, skill, intent, label_key, label_data, undo) VALUES(?, ?, ?, ?, ?, ?)",
            (iso(self.clock()), skill, intent, label_key, dumps(label_data), dumps(undo)))
        return cur.lastrowid

    def last_undoable(self) -> dict[str, Any] | None:
        rows = self.storage.query(
            "SELECT * FROM history WHERE undone = 0 AND undo IS NOT NULL ORDER BY id DESC LIMIT 1")
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "skill": r["skill"], "intent": r["intent"], "label_key": r["label_key"],
                "label_data": loads(r["label_data"] or "{}"), "undo": loads(r["undo"])}

    def mark_undone(self, hid: int) -> None:
        self.storage.execute("UPDATE history SET undone = 1 WHERE id = ?", (hid,))
