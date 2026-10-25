import pytest

from jonnyang.core.storage import Storage
from jonnyang.platform.base import Platform
from jonnyang.platform.fake import FakeBeeper, FakeLauncher, FakeSysInfo
from jonnyang.platform.system import UnsupportedVolume
from jonnyang.skills.calc import CalcError, safe_eval
from jonnyang.skills.reminder import extract_message


# ── 타이머 ──
def test_timer_fires_and_beeps(app):
    app.say("10초 타이머")
    assert app.tick(seconds=5) == []
    notes = app.tick(seconds=6)
    assert len(notes) == 1 and "10초" in notes[0]
    assert app.platform.beeper.count == 2
    assert "없다" in app.say("타이머 얼마나 남았어")


def test_timer_cancel_by_index_and_undo(app):
    app.say("3분 타이머")
    app.say("라면 타이머 5분")
    out = app.say("2번 타이머 취소")
    assert "라면" in out and "5분" in out
    app.say("되돌려줘")
    app.say("응")
    assert "타이머 2개" in app.say("타이머 얼마나 남았어")


def test_timer_cancel_ambiguous_lists(app):
    app.say("3분 타이머")
    app.say("5분 타이머")
    out = app.say("타이머 취소해")
    assert "2번 타이머 취소" in out and "1." in out


# ── 알람 / 리마인더 ──
def test_alarm_fires_three_beeps(app):
    app.say("30분 뒤에 깨워줘")
    notes = app.tick(minutes=31)
    assert notes and "오후 2:30" in notes[0]
    assert app.platform.beeper.count == 3


def test_reminder_message_and_fire(app):
    out = app.say("10분 뒤에 빨래 꺼내라고 알려줘")
    assert "빨래 꺼내기" in out and "오후 2:10" in out
    notes = app.tick(minutes=10)
    assert notes and "빨래 꺼내기" in notes[0]


def test_reminder_persists_and_reports_missed(make_app, tmp_path):
    db = tmp_path / "j.db"
    a = make_app(storage=Storage(db))
    a.say("10분 뒤에 빨래 꺼내라고 알려줘")
    a.say("내일 오후 3시에 병원 가라고 알려줘")
    a.ctx.storage.close()

    from datetime import datetime
    b = make_app(storage=Storage(db), now=datetime(2026, 10, 20, 15, 0))
    lines = "\n".join(b.d.startup())
    assert "놓친" in lines or "지나간" in lines
    assert "빨래 꺼내기" in lines
    out = b.say("리마인더 뭐 있어")
    assert "병원 가기" in out and "빨래" not in out
    notes = b.tick(days=1)
    assert notes and "병원 가기" in notes[0]


def test_reminder_cancel_by_keyword(app):
    app.say("내일 오후 3시에 병원 가라고 알려줘")
    app.say("금요일에 보고서 제출 리마인더 등록")
    out = app.say("병원 리마인더 취소")
    assert "병원 가기" in out
    assert "보고서" in app.say("리마인더 뭐 있어")


def test_time_error_message(app):
    assert "매달" in app.say("매달 1일 월세 내라고 알려줘")      # 지원 안 하는 반복은 무엇이 되는지 안내
    assert "지났다" in app.say("오늘 1시 알람")


# ── 반복 리마인더 / 알람 ──
def test_repeat_reminder_fires_and_reschedules(app):
    out = app.say("매일 아침 8시에 약 먹으라고 알려줘")
    assert "매일 오전 8:00" in out and "약 먹기" in out
    fired = app.tick(hours=18)                                              # 10/21 08:00
    assert len(fired) == 1 and "약 먹기" in fired[0]
    assert "10/22(목) 오전 8:00" in app.say("리마인더 뭐 있어")          # 다음 날로 넘어감
    assert len(app.tick(days=1)) == 1                                       # 10/22 08:00 또 울림


def test_repeat_weekdays_skips_weekend(make_app):
    from datetime import datetime
    app = make_app(now=datetime(2026, 10, 23, 12, 0))                       # 금요일 낮
    app.say("평일마다 7시 알람 맞춰줘")
    assert "10/26(월) 오전 7:00" in app.say("알람 목록")


def test_repeat_interval(app):
    app.say("30분마다 물 마시라고 알려줘")
    assert len(app.tick(minutes=30)) == 1
    assert len(app.tick(minutes=30)) == 1
    assert "물 마시기" in app.say("리마인더 뭐 있어")


def test_repeat_missed_while_off_is_reported_once_then_moves_on(make_app, tmp_path):
    from datetime import datetime
    db = tmp_path / "j.db"
    a = make_app(storage=Storage(db))
    a.say("매일 아침 8시에 약 먹으라고 알려줘")
    a.ctx.storage.close()
    b = make_app(storage=Storage(db), now=datetime(2026, 10, 23, 9, 0))      # 3일 꺼져 있었음
    out = "\n".join(b.d.startup())
    assert "약 먹기" in out
    assert "10/24(토) 오전 8:00" in b.say("리마인더 뭐 있어")              # 다음 회차로 넘어가 있음
    c = make_app(storage=Storage(db), now=datetime(2026, 10, 23, 9, 30))
    assert "놓친" not in "\n".join(c.d.startup())                         # 같은 걸 두 번 알리지 않음


def test_repeat_cancel_and_undo(app):
    app.say("평일마다 9시에 출근하라고 알려줘")
    app.say("출근 리마인더 취소")
    assert "없다" in app.say("리마인더 뭐 있어")
    app.say("되돌려줘")
    app.say("응")
    assert "평일 오전 9:00" in app.say("리마인더 뭐 있어")


def test_repeat_without_time_asks(app):
    out = app.say("매일 약 먹으라고 알려줘")
    assert "언제" in out
    out = app.say("저녁 9시")
    assert "매일 오후 9:00" in out and "약 먹기" in out


@pytest.mark.parametrize("text,spans_text,want", [
    ("내일 오후 3시에 병원 가라고 알려줘", "내일 오후 3시", "병원 가기"),
    ("10분 뒤에 빨래 꺼내라고 알려줘", "10분 뒤", "빨래 꺼내기"),
    ("저녁 8시에 약 먹으라고 말해줘", "저녁 8시", "약 먹기"),
    ("금요일에 보고서 제출 리마인더 등록", "금요일", "보고서 제출"),
    ("3시에 회의 있다고 알려줘", "3시", "회의 있다"),
])
def test_extract_message(text, spans_text, want):
    start = text.index(spans_text)
    assert extract_message(text, [(start, start + len(spans_text))]) == want


# ── 목록 ──
def test_list_remove_fuzzy(app):
    app.say("쇼핑 목록에 우유랑 계란 추가해")
    out = app.say("쇼핑 목록에서 게란 빼줘")
    assert "계란" in out
    assert "계란" not in app.say("쇼핑 목록 보여줘")


def test_list_remove_missing(app):
    app.say("쇼핑 목록에 우유 추가해")
    assert "없다" in app.say("쇼핑 목록에서 수박 빼줘")


def test_lists_are_separate(app):
    app.say("쇼핑 목록에 우유 추가해")
    app.say("할 일 목록에 보고서 쓰기 추가")
    out = app.say("할 일 목록 보여줘")
    assert "보고서 쓰기" in out and "우유" not in out


# ── 계산 / 단위 ──
@pytest.mark.parametrize("text,want", [
    ("40의 15%는?", "= 6"),
    ("3+4*2", "= 11"),
    ("12 곱하기 7", "= 84"),
    ("1 나누기 3", "0.333333"),
    ("삼십 더하기 십오", "= 45"),
    ("2의 제곱 계산해줘", "= 4"),
    ("3만 2천원 4명이서 나눠", "8,000원"),
    ("5만원에서 20% 할인", "40,000원"),
])
def test_calc(app, text, want):
    assert want in app.say(text)


def test_dutch_pay_remainder(app):
    out = app.say("1만원 3명이서 나눠")
    assert "3,333원" in out and "1명" in out and "3,334원" in out


def test_div_zero(app):
    assert "0으로" in app.say("10 나누기 0")


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "9**9**9", "[1]*10", "a+1"])
def test_safe_eval_rejects(expr):
    with pytest.raises(CalcError):
        safe_eval(expr)


@pytest.mark.parametrize("text,want", [
    ("5평은 몇 제곱미터야", "16.5289㎡"),
    ("10마일을 킬로미터로", "16.0934km"),
    ("화씨 100도는 섭씨로", "37.7778°C"),
    ("3파운드는 몇 킬로", "1.3608kg"),
    ("180cm는 몇 피트야", "5.9055피트"),
    ("2리터는 몇 갤런", "0.5283갤런"),
])
def test_units(app, text, want):
    assert want in app.say(text)


# ── 볼륨 ──
def test_volume_up_down_set_and_undo(app):
    app.say("볼륨 올려줘")
    assert app.platform.volume.level == 50
    app.say("소리 20 줄여")
    assert app.platform.volume.level == 30
    app.say("볼륨 최대로")
    assert app.platform.volume.level == 100
    app.say("되돌려줘")
    app.say("응")
    assert app.platform.volume.level == 30


def test_mute_unmute(app):
    app.say("음소거")
    assert app.platform.volume.muted
    app.say("음소거 해제")
    assert not app.platform.volume.muted


def test_volume_unsupported(analyzer):
    import random

    from jonnyang.app import build_app
    p = Platform(UnsupportedVolume(), FakeLauncher(), FakeSysInfo(), FakeBeeper())
    _, d = build_app(platform=p, analyzer=analyzer, storage=Storage(":memory:"), rng=random.Random(0))
    assert "Windows" in "\n".join(d.handle("볼륨 올려줘"))


# ── 앱 / 별칭 ──
def test_open_app_and_folder(app):
    app.say("메모장 켜줘")
    app.say("다운로드 폴더 열어")
    assert app.platform.launcher.opened == ["notepad.exe", "known:Downloads"]


def test_unknown_app_not_launched(app):
    app.say("포토샵 켜줘")
    assert app.platform.launcher.opened == []


def test_alias_register_use_undo(app):
    out = app.say("메모장을 노트라고 불러")
    assert "노트" in out and "notepad.exe" in out
    app.say("노트 열어")
    assert app.platform.launcher.opened == ["notepad.exe"]
    app.say("되돌려줘")
    app.say("응")
    assert app.ctx.aliases.get("노트") is None


def test_alias_overwrite_needs_confirm(app):
    out = app.say("계산기를 메모장이라고 불러")
    assert "(응/아니)" in out and "notepad.exe" in out and "calc.exe" in out
    app.say("아니")
    assert app.ctx.aliases.get("메모장") == ("app", "notepad.exe")


def test_alias_bad_target(app):
    assert "모르겠다" in app.say("없는앱을 뭐시기라고 불러")


# ── 시스템 정보 ──
def test_sysinfo(app):
    assert "12.5%" in app.say("CPU 얼마나 써")
    out = app.say("메모리 사용량 알려줘")
    assert "6.0GB" in out and "16.0GB" in out and "37.5%" in out
    assert "76%" in app.say("배터리 얼마나 남았어")
    assert "C:\\" in app.say("디스크 용량 얼마나 남았어")


def test_no_battery(app):
    app.platform.sysinfo._battery = None
    assert "배터리가 없다" in app.say("배터리 얼마나 남았어")


# ── 말투 설정 ──
def test_persona_switches_persist(app):
    app.say("냥체 꺼")
    out = app.say("3분 타이머")
    assert "냥" not in out and "3분" in out
    assert app.ctx.storage.get_setting("persona.nyang") is False
    app.say("냥체 켜")
    assert "냥" in app.say("5분 타이머")
    app.say("이모지 꺼")
    assert "🔊" not in app.say("볼륨 올려")
