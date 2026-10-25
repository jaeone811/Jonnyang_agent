from datetime import datetime
from pathlib import Path

import pytest
import yaml

from jonnyang.nlu.numbers import normalize_numbers
from jonnyang.nlu.timeparse import parse

NOW = datetime(2026, 10, 20, 14, 0)
CASES = yaml.safe_load((Path(__file__).parent / "data" / "time_cases.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["text"] for c in CASES])
def test_time(case):
    r = parse(normalize_numbers(case["text"]), NOW)
    detail = f"at={r.at} duration={r.duration} rel={r.relative} err={r.error} assumed={r.assumed}"
    if case.get("none"):
        assert not r.found, detail
        return
    assert r.error == case.get("error"), detail
    if "at" in case:
        assert r.at is not None and r.at.isoformat(timespec="minutes") == case["at"], detail
    if "duration" in case:
        assert r.duration is not None and r.duration.total_seconds() == case["duration"], detail
    if "relative" in case:
        assert r.relative == case["relative"], detail
    for a in case.get("assumed", []):
        assert a in r.assumed, detail
    if "repeat" in case:
        assert r.repeat is not None, detail
        for k, v in case["repeat"].items():
            got = getattr(r.repeat, k)
            assert (list(got) if isinstance(got, tuple) else got) == v, f"{k}: {r.repeat}"
    else:
        assert r.repeat is None, detail


@pytest.mark.parametrize("now,text,want", [
    (datetime(2026, 10, 20, 23, 59), "1분 뒤", "2026-10-21T00:00"),      # 자정 넘김
    (datetime(2026, 10, 25, 10, 0), "화요일", "2026-10-27T09:00"),        # 일요일 기준
    (datetime(2026, 10, 25, 8, 0), "주말", "2026-10-25T09:00"),           # 일요일 아침엔 오늘
    (datetime(2026, 10, 25, 10, 0), "주말", "2026-10-31T09:00"),          # 일요일 9시 지남 → 다음 토요일
    (datetime(2026, 10, 24, 10, 0), "주말 오후 3시", "2026-10-24T15:00"),  # 토요일엔 오늘
    (datetime(2026, 1, 31, 12, 0), "한 달 뒤", "2026-02-28T12:00"),       # 월말 보정
    (datetime(2026, 12, 31, 20, 0), "내일 10시", "2027-01-01T10:00"),      # 연말
    (datetime(2026, 10, 20, 9, 0), "화요일 10시", "2026-10-20T10:00"),     # 오늘이 화요일이고 아직 안 지남
    (datetime(2026, 10, 20, 11, 0), "화요일 10시", "2026-10-27T10:00"),    # 오늘이 화요일인데 지남 → 다음주
])
def test_edges(now, text, want):
    r = parse(normalize_numbers(text), now)
    assert r.error is None and r.at is not None and r.at.isoformat(timespec="minutes") == want, (r.at, r.error)
