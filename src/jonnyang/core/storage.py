"""SQLite 저장소. 스케줄러 스레드도 쓰므로 연결 하나를 락으로 보호한다."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = [
    # version 1
    """
    CREATE TABLE list_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_name TEXT NOT NULL,
        item TEXT NOT NULL,
        created TEXT NOT NULL
    );
    CREATE TABLE reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,            -- 'reminder' | 'alarm'
        at TEXT NOT NULL,
        message TEXT NOT NULL,
        created TEXT NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE aliases (
        name TEXT PRIMARY KEY,
        kind TEXT NOT NULL,            -- 'app' | 'folder'
        target TEXT NOT NULL,
        created TEXT NOT NULL
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        skill TEXT NOT NULL,
        intent TEXT NOT NULL,
        label_key TEXT,
        label_data TEXT,
        undo TEXT,
        undone INTEGER NOT NULL DEFAULT 0
    );
    """,
    # version 2: 반복 리마인더/알람 ("매일 아침 8시"). JSON (nlu.timeparse.Repeat), 한 번짜리는 NULL
    """
    ALTER TABLE reminders ADD COLUMN repeat TEXT;
    """,
]


class Storage:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for i, script in enumerate(SCHEMA[version:], start=version + 1):
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version = {i}")
            self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    # ── settings ──
    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self.query("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: Any) -> None:
        self.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()
