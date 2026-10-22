"""persona.yaml 무결성 + 핵심 정보 보장."""

import random
import string
from datetime import datetime, timedelta

import pytest

from jonnyang.app import SKILLS
from jonnyang.core.config import load_yaml
from jonnyang.persona.cat import Persona
from jonnyang.skills.base import Result

DATA = load_yaml("persona.yaml")
PROFILES = DATA["profiles"]
NOW = datetime(2026, 10, 20, 14, 0)


def placeholders(t) -> set[str]:
    texts = t if isinstance(t, list) else [t]
    return {f for s in texts for _, f, _, _ in string.Formatter().parse(str(s)) if f}


def persona(settings=None):
    settings = settings or {}
    return Persona(DATA, lambda k, d=None: settings.get(k, d), random.Random(0))


def test_soft_and_plain_are_complete_and_aligned():
    soft, plain = PROFILES["soft"]["templates"], PROFILES["plain"]["templates"]
    assert set(soft) == set(plain), set(soft) ^ set(plain)


@pytest.mark.parametrize("name", [p for p in PROFILES if p not in ("soft", "plain")])
def test_partial_profiles_only_override_known_keys(name):
    soft = PROFILES["soft"]["templates"]
    for key, t in PROFILES[name]["templates"].items():
        assert key in soft, f"{name}: 모르는 키 {key}"
        assert placeholders(t) <= placeholders(soft[key]) | {"note"}, f"{name}.{key}: 오타 난 자리표시자"


@pytest.mark.parametrize("name", list(PROFILES))
def test_same_placeholders_as_soft(name):
    """프로필끼리 자리표시자 집합이 다르면 오타일 가능성이 높다 (soft 기준 부분집합이어야 함)."""
    soft = PROFILES["soft"]["templates"]
    for key, t in PROFILES[name]["templates"].items():
        assert placeholders(t) <= placeholders(soft[key]) | {"note"}, f"{name}.{key}"


def test_labels_cover_every_intent_and_skill():
    labels = DATA["labels"]

    class Dummy:
        def __getattr__(self, item):
            raise AttributeError(item)

    for cls in SKILLS:
        intents = cls.intents if isinstance(cls.__dict__.get("intents"), list) else None
        if intents is None:   # AppSkill은 __init__에서 의도를 만든다
            intents = [type("I", (), {"name": "app.open"})()]
        for it in intents:
            assert f"intent.{it.name}" in labels, it.name
        assert f"skill.{cls.name}" in labels, cls.name


def test_core_value_is_never_hidden():
    data = {**DATA, "profiles": {"soft": {"templates": {"timer.set": "알았다냥!"}}, "plain": {"templates": {}}}}
    p = Persona(data, lambda k, d=None: d, random.Random(0))
    out = p.render(Result("timer.set", {"duration": timedelta(minutes=3), "end": NOW + timedelta(minutes=3)},
                          core=("duration", "end")), NOW)
    assert "3분" in out and "오후 2:03" in out


def test_nyang_off_uses_plain():
    out = persona({"persona.nyang": False}).render(
        Result("volume.set", {"level": 50, "before": 40}, core=("level",)), NOW)
    assert "냥" not in out and "50" in out


def test_emoji_off_strips_only_emoji():
    out = persona({"persona.emoji": False}).render(
        Result("volume.up", {"level": 50, "before": 40}, core=("level",)), NOW)
    assert "🔊" not in out and "40 → 50" in out


def test_assumed_note_is_shown():
    out = persona().render(Result("alarm.set", {"at": NOW + timedelta(hours=1), "assumed": ["pm"]}, core=("at",)),
                           NOW)
    assert "오후로 알아들음" in out


@pytest.mark.parametrize("profile", [p for p in PROFILES if p != "plain"])
def test_every_template_renders(profile):
    """모든 템플릿이 예외 없이 그려지고 넘긴 값이 그대로 나온다."""
    p = persona({"persona.profile": profile})
    for key, t in PROFILES["soft"]["templates"].items():
        fields = placeholders(t) - {"items", "note"}
        data = {f: f"<{f}>" for f in fields}
        out = p.say(key, data, NOW, core=tuple(fields))
        for f in fields:
            assert f"<{f}>" in out, (profile, key, f)


@pytest.mark.parametrize("name", ["persona.yaml", "settings.yaml", "aliases.yaml", "lexicon.yaml"])
def test_yaml_keys_are_strings(name):
    """YAML 1.1은 yes/no/on/off 키를 true/false로 읽는다. 그런 키가 섞이면 조용히 기능이 깨진다."""
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                assert isinstance(k, str), f"{name}: {path}의 키 {k!r}가 문자열이 아님 (따옴표로 감싸라)"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(load_yaml(name), name)


def test_pose_rules():
    p = persona()
    assert p.pose_for("timer.done") == "alert"
    assert p.pose_for("confirm.list_clear") == "ask"
    assert p.pose_for("fallback", ok=False) == "confused"
    assert p.pose_for("timer.set") == "happy"
    assert p.pose_for("calc.zero", ok=False) == "confused"
    assert p.ui("answer_yes") == "응"
