"""되묻기 / 확인 / 슬롯 보충 / 되돌리기 / 호출어 흐름."""


def test_confirm_yes_clears_list(app):
    app.say("쇼핑 목록에 우유랑 계란 추가해")
    out = app.say("쇼핑 목록 비워줘")
    assert "우유" in out and "계란" in out and "(응/아니)" in out   # 무엇을 지우는지 반드시 보여준다
    assert "비웠다" in app.say("응")
    assert "비어 있다" in app.say("쇼핑 목록 보여줘")


def test_confirm_no_keeps_list(app):
    app.say("쇼핑 목록에 우유 추가해")
    app.say("쇼핑 목록 비워줘")
    app.say("아니")
    assert "우유" in app.say("쇼핑 목록 보여줘")


def test_confirm_dropped_by_new_command(app):
    app.say("쇼핑 목록에 우유 추가해")
    app.say("쇼핑 목록 비워줘")
    out = app.say("볼륨 올려줘")          # 확인 대신 다른 명령 → 대기 취소하고 새 명령 실행
    assert "50" in out
    assert "우유" in app.say("쇼핑 목록 보여줘")


def test_clarify_then_slot(app):
    out = app.say("타이머")
    assert "1." in out and "2." in out
    assert "몇 분" in app.say("1")
    out = app.say("3분")
    assert "3분" in out and "오후 2:03" in out


def test_slot_followup_for_alarm(app):
    assert "언제" in app.say("알람 맞춰")
    out = app.say("내일 7시")
    assert "10/21" in out and "오전 7:00" in out


def test_pending_expires(app):
    app.say("알람 맞춰")
    app.clock.now = app.clock.now.replace(minute=2)
    app.say("내일 7시")
    assert "없다" in app.say("알람 뭐 있어")


def test_undo_with_confirmation(app):
    assert "없다" in app.say("되돌려줘")
    app.say("쇼핑 목록에 우유 추가해")
    out = app.say("되돌려줘")
    assert "우유" in out and "(응/아니)" in out
    assert "되돌렸다" in app.say("응")
    assert "비어 있다" in app.say("쇼핑 목록 보여줘")
    assert "없다" in app.say("되돌려줘")


def test_undo_restores_cleared_list(app):
    app.say("쇼핑 목록에 우유랑 계란 추가해")
    app.say("쇼핑 목록 비워줘")
    app.say("응")
    app.say("방금 거 취소해")
    app.say("응")
    out = app.say("쇼핑 목록 보여줘")
    assert "우유" in out and "계란" in out


def test_negation_does_nothing(app):
    app.say("볼륨 올리지 마")
    assert app.platform.volume.level == 40


def test_exclusion_runs_other(app):
    out = app.say("타이머 말고 내일 7시 알람")
    assert "알람" in out and "오전 7:00" in out
    assert "없다" in app.say("타이머 얼마나 남았어")


def test_wake_word_required(app):
    app.say("호출어 켜")
    app.say("볼륨 올려")
    assert app.platform.volume.level == 40
    app.say("존냥아 볼륨 올려")
    assert app.platform.volume.level == 50
    app.say("존냥아 호출어 꺼")
    app.say("볼륨 올려")
    assert app.platform.volume.level == 60


def test_wake_only_greets(app):
    assert app.say("존냥아")


def test_fallback_shows_examples(app):
    out = app.say("배고프다")
    assert "할 수 있다" in out
