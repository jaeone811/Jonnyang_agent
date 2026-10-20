"""값 표시 형식. 말투와 상관없이 숫자·시간·경로가 또렷하게 나오게 한다."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

WEEKDAY_KO = "월화수목금토일"


class Bytes(int):
    """바이트 수. 표시할 때 GB 같은 단위로 바꾼다."""


def duration(td: timedelta) -> str:
    total = int(round(td.total_seconds()))
    if total <= 0:
        return "0초"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    if seconds:
        parts.append(f"{seconds}초")
    return " ".join(parts)


def clock(dt: datetime) -> str:
    ampm = "오전" if dt.hour < 12 else "오후"
    h = dt.hour % 12
    if dt.hour == 12:
        h = 12
    return f"{ampm} {h}:{dt.minute:02d}"


def when(dt: datetime, now: datetime) -> str:
    """'오늘 오후 3:00', '내일 10/21(수) 오전 7:00', '2027/10/01(금) 오전 9:00'"""
    d, today = dt.date(), now.date()
    wd = WEEKDAY_KO[dt.weekday()]
    if d == today:
        return f"오늘 {clock(dt)}"
    if d.year != today.year:
        return f"{d.year}/{d.month}/{d.day}({wd}) {clock(dt)}"
    prefix = {1: "내일 ", 2: "모레 "}.get((d - today).days, "")
    return f"{prefix}{d.month}/{d.day}({wd}) {clock(dt)}"


def number(v: int | float) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int) or float(v).is_integer():
        return f"{int(v):,}"
    s = f"{v:,.6f}".rstrip("0").rstrip(".")
    return s


def size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return str(n)


def value(key: str, v: Any, now: datetime) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return when(v, now)
    if isinstance(v, date):
        return f"{v.month}/{v.day}({WEEKDAY_KO[v.weekday()]})"
    if isinstance(v, timedelta):
        return duration(v)
    if isinstance(v, (list, tuple)):
        return ", ".join(value(key, x, now) for x in v)
    if isinstance(v, Bytes):
        return size(int(v))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return number(v)
    return str(v)
