"""데스크톱 펫 GUI (화면 없이 offscreen으로 돈다)."""

import os
from datetime import timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from jonnyang.gui.painter import POSES, CatFrame, CatPainter  # noqa: E402
from jonnyang.gui.window import PetWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Mono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def pet(qapp, app):
    win = PetWindow(app.ctx.persona, app.ctx.storage, tray=False)
    mono = Mono()
    win.mono = win.cat.mono = mono
    win.show()
    win.attach(app.ctx, app.d)
    win.mono_fake = mono
    yield win, app
    win.shutdown()
    win.close()


def test_every_pose_paints(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    img = QImage(200, 180, QImage.Format.Format_ARGB32)
    for pose in POSES:
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        CatPainter().paint(p, QRectF(0, 0, 200, 180), CatFrame(pose=pose, t=2.0, pose_t=0.5, heart_t=0.2))
        p.end()
        assert img.pixelColor(100, 80).alpha() > 0, pose      # 머리가 그려졌다


def _paint(painter, pose, **kw):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    img = QImage(190, 170, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    painter.paint(p, QRectF(0, 0, 190, 170), CatFrame(pose=pose, **kw))
    p.end()
    return img


def _opaque(img) -> int:
    return sum(img.pixelColor(x, y).alpha() > 128 for x in range(0, img.width(), 4) for y in range(0, img.height(), 4))


def test_sprites_cover_every_pose(qapp, app):
    from jonnyang.core.config import sprite_dir
    from jonnyang.gui.sprite import SpritePainter, SpriteSheet
    sheet = SpriteSheet(sprite_dir())
    assert sheet.available
    for name, n in sheet.counts.items():
        assert len(sheet.frames(name)) == n, name          # 그림 파일이 manifest와 맞다
    spec = app.ctx.persona.sprites
    painter = SpritePainter(sheet, spec)
    for pose in (*POSES, "drag"):
        name, _ = painter.anim_for(CatFrame(pose=pose, pose_t=1.0))
        assert sheet.has(name) and name == painter.poses[pose]["anim"], pose   # 모든 표정에 그림이 있다
        assert _opaque(_paint(painter, pose, t=2.0, pose_t=0.5, heart_t=0.2)) > 300, pose


def _bbox(img):
    pts = [(x, y) for x in range(0, img.width(), 2) for y in range(0, img.height(), 2)
           if img.pixelColor(x, y).alpha() > 128]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    return min(xs), min(ys), max(xs), max(ys)


def test_sprite_stays_still_and_click_only_squashes(qapp, app):
    from jonnyang.core.config import sprite_dir
    from jonnyang.gui.sprite import SpritePainter, SpriteSheet
    painter = SpritePainter(SpriteSheet(sprite_dir()), app.ctx.persona.sprites)
    for pose in (*POSES, "drag"):
        name, spec = painter.anim_for(CatFrame(pose=pose))
        idx = {painter.frame_index(CatFrame(pose=pose, t=t, pose_t=t), name, spec) for t in (0, 0.4, 1.3, 7.7, 30)}
        assert idx == {0}, pose                                   # 그림은 넘기지 않고 가만히
    assert len({painter.anim_for(CatFrame(pose=p))[0] for p in ("idle", "happy", "ask", "alert", "love")}) == 1
    calm = _bbox(_paint(painter, "idle", t=0.0, pose_t=10.0))
    poked = _bbox(_paint(painter, "idle", t=0.0, pose_t=10.0, heart_t=0.15))     # 클릭 직후: 옆으로 퍼진다
    assert poked[2] - poked[0] > calm[2] - calm[0]
    assert poked[1] > calm[1] or poked[3] - poked[1] < calm[3] - calm[1]
    done = _bbox(_paint(painter, "idle", t=0.0, pose_t=10.0, heart_t=5.0))       # 다 끝나면 원래대로
    assert done == calm


def test_sprite_fallback_to_shapes(qapp, tmp_path):
    from jonnyang.gui.sprite import SpritePainter, SpriteSheet, make_painter
    assert isinstance(make_painter(tmp_path), CatPainter)            # 그림 폴더가 비면 도형 고양이
    assert isinstance(make_painter(tmp_path, {"enabled": False}), CatPainter)
    broken = SpritePainter(SpriteSheet(tmp_path))
    assert not broken.available
    assert _opaque(_paint(broken, "idle", t=1.0)) > 300                # 그려지긴 한다 (도형으로)


def test_startup_greets_and_enables_input(pet):
    win, _ = pet
    assert win.input.isEnabled()
    assert win.bubble.isVisibleTo(win) and win.bubble.text()


def test_command_reply_then_status_countdown(pet):
    win, app = pet
    win.submit("라면 타이머 4분")
    assert "라면" in win.bubble.text() and "4분" in win.bubble.text()
    assert win.bubble.state == "ready"
    assert win.cat.pose == "happy"
    win.mono_fake.t += 60                        # 응답 보여주는 시간이 지남
    app.clock.now += timedelta(seconds=30)
    win.tick()
    assert win.mode == "status" and win.bubble.state == "running"
    assert "3분 30초" in win.bubble.text()       # 남은 시간이 말풍선에 보인다


def test_confirm_has_buttons_and_sticks(pet):
    win, _ = pet
    win.submit("쇼핑 목록에 우유 추가해")
    win.submit("쇼핑 목록 비워줘")
    assert win.bubble.state == "needs_input"
    labels = [win.bubble.buttons_layout.itemAt(i).widget().text()
              for i in range(win.bubble.buttons_layout.count()) if win.bubble.buttons_layout.itemAt(i).widget()]
    assert labels == ["응", "아니"]
    win.mono_fake.t += 600
    win.tick()
    assert win.mode == "reply"                   # 대답할 때까지 안 사라진다
    win.bubble.choice.emit("응")
    assert "비웠다" in win.bubble.text()


def test_clarify_buttons_answer_by_number(pet):
    win, _ = pet
    win.submit("타이머")
    answers = [b for b in win.bubble.findChildren(QtWidgets.QPushButton)]
    assert len(answers) == 2
    win.submit("1")
    assert "몇 분" in win.bubble.text()


def test_scheduler_alert_from_other_thread(pet, qapp):
    import threading
    win, app = pet
    win.submit("10초 타이머")
    app.clock.now += timedelta(seconds=11)
    t = threading.Thread(target=app.ctx.scheduler.run_pending)
    t.start()
    t.join()
    qapp.processEvents()                          # Signal이 GUI 스레드로 넘어와 처리됨
    assert "10초" in win.bubble.text() and win.bubble.state == "alert"
    assert win.cat.pose == "alert"
    win.mono_fake.t += 600
    win.tick()
    assert win.mode == "reply"                   # 알림은 확인할 때까지 유지
    win.on_cat_clicked()
    assert win.mode != "reply"


def test_idle_bubble_hides_then_sleeps(pet):
    win, _ = pet
    win.mono_fake.t += 60
    win.tick()                                   # 인사 만료 → 할 일 없음 → 대기 문구
    assert win.mode == "idle"
    win.mono_fake.t += 10
    win.tick()
    assert win.mode == "hidden" and not win.bubble.isVisibleTo(win)
    win.mono_fake.t += 11 * 60
    win.tick()
    assert win.cat.base_pose == "sleep"
    win.on_cat_clicked()                          # 쓰다듬으면 깬다
    assert win.cat.base_pose != "sleep"
    win.mono_fake.t += 11 * 60
    win.mode = "hidden"
    win.tick()
    assert win.cat.base_pose == "sleep"
    win.input.textEdited.emit("타")                # 타자 치기 시작해도 깬다
    assert win.cat.base_pose != "sleep"


def test_toggle_input_and_drag(pet):
    from PySide6.QtCore import QPoint
    win, app = pet
    win.toggle_input()
    assert win.input.isHidden()
    win.toggle_input()
    assert not win.input.isHidden()
    win.cat.dragged.emit(QPoint(123, 45))
    win.cat.drag_finished.emit()
    assert app.ctx.storage.get_setting("gui.pos") == [123, 45]


def test_bubble_is_plain_text(pet):
    win, _ = pet
    win.submit('쇼핑 목록에 "<b>굵게</b>" 추가해')
    assert "<b>굵게</b>" in win.bubble.body.text()   # HTML로 해석하지 않고 그대로 보여준다
    from PySide6.QtCore import Qt
    assert win.bubble.body.textFormat() == Qt.TextFormat.PlainText


def _fire(app, qapp, seconds):
    import threading
    app.clock.now += timedelta(seconds=seconds)
    t = threading.Thread(target=app.ctx.scheduler.run_pending)
    t.start()
    t.join()
    qapp.processEvents()


def test_alerts_back_to_back_are_merged_not_overwritten(pet, qapp):
    win, app = pet
    win.submit("라면 타이머 10초")
    win.submit("계란 타이머 12초")
    _fire(app, qapp, 11)
    _fire(app, qapp, 2)
    text = win.bubble.text()
    assert "라면" in text and "계란" in text          # 첫 알림이 두 번째에 덮여 사라지지 않는다


def test_alert_during_confirm_restores_question(pet, qapp):
    win, app = pet
    win.submit("10초 타이머")
    win.submit("쇼핑 목록에 우유 추가해")
    win.submit("쇼핑 목록 비워줘")
    question = win.bubble.text()
    _fire(app, qapp, 11)
    assert win.bubble.state == "alert"
    win.on_cat_clicked()                              # 알림 확인
    assert win.bubble.state == "needs_input" and win.bubble.text() == question
    win.bubble.choice.emit("응")
    assert "비웠다" in win.bubble.text()


def test_reply_time_scales_with_length(pet):
    win, _ = pet
    assert win.reply_seconds("짧음") == 4.0
    assert 4.0 < win.reply_seconds("가" * 100) < 25.0
    assert win.reply_seconds("가" * 2000) == 25.0


def test_hover_keeps_reply_then_grace(pet):
    win, _ = pet
    win.submit("3 더하기 4")
    win.bubble.hovering = True
    win.mono_fake.t += 60
    win.tick()
    assert win.mode == "reply"
    win.bubble.hovering = False
    win.tick()
    assert win.mode == "reply"                       # 마우스를 뗀 직후엔 조금 더 보여준다
    win.mono_fake.t += 3
    win.tick()
    assert win.mode != "reply"


def test_online_reply_runs_in_background(qapp, make_app):
    import time as _time

    from test_online import FORECAST, FORECAST_JSON
    app = make_app(routes={FORECAST: FORECAST_JSON})
    win = PetWindow(app.ctx.persona, app.ctx.storage, tray=False)
    mono = Mono()
    win.mono = win.cat.mono = mono
    win.show()
    win.attach(app.ctx, app.d)
    try:
        win.submit("오늘 날씨 어때")
        assert win.bubble.state == "running" and win.cat.pose == "search"   # 기다리는 동안 홀로그램 창 보는 표정
        deadline = _time.monotonic() + 5
        while "서울" not in win.bubble.text() and _time.monotonic() < deadline:
            qapp.processEvents()
            _time.sleep(0.01)
        assert "서울" in win.bubble.text() and win.bubble.state == "ready"
    finally:
        win.shutdown()
        win.close()


def test_drag_floats_then_restores_pose(pet):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    win, _ = pet
    win.submit("쇼핑 목록 비워줘")
    before = win.cat.pose                           # 대답 기다리는 표정
    cat = win.cat

    def ev(kind, x):
        pos = QPointF(40 + x, 40)
        glob = QPointF(cat.mapToGlobal(QPoint(40 + x, 40)))
        btns = Qt.MouseButton.NoButton if kind == QMouseEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
        return QMouseEvent(kind, pos, glob, Qt.MouseButton.LeftButton, btns, Qt.KeyboardModifier.NoModifier)

    cat.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, 0))
    cat.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, 30))
    assert cat.pose == "drag"                       # 끌려가는 동안 둥실
    cat.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, 30))
    assert cat.pose == before
