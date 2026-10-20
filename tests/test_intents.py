"""명령 예시 데이터셋 테스트 (tests/data/intents/*.yaml).

각 항목: text, intent, slots(부분 일치), expect(기본 execute), tags.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from conftest import NOW

DATA = Path(__file__).parent / "data" / "intents"


def load_cases():
    cases = []
    for path in sorted(DATA.glob("*.yaml")):
        for i, case in enumerate(yaml.safe_load(path.read_text(encoding="utf-8"))):
            cases.append(pytest.param(case, id=f"{path.stem}:{i}:{case['text']}"))
    return cases


def normalize_slot(key, value):
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return value


@pytest.mark.parametrize("case", load_cases())
def test_intent(app, case):
    it = app.d.interpret(case["text"], NOW)
    expect = case.get("expect", "execute")
    detail = f"kind={it.kind} intent={it.intent.name if it.intent else None} " \
             f"top={[(c.intent.name, c.score) for c in it.candidates[:3]]} slots={it.slots}"
    assert it.kind == expect, detail
    if "intent" in case:
        if expect == "clarify":
            assert case["intent"] in [o.name for o in it.options], detail
        else:
            assert it.intent is not None and it.intent.name == case["intent"], detail
    for key, want in (case.get("slots") or {}).items():
        if key == "duration_sec":
            got = it.slots.get("duration")
            assert got is not None and got.total_seconds() == want, detail
        else:
            assert normalize_slot(key, it.slots.get(key)) == want, f"slot {key}: {detail}"
