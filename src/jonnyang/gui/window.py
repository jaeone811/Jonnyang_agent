"""데스크톱 펫 창: 바탕화면 위에 떠 있는 고양이 + 말풍선 + 입력창.

- 테두리 없는 투명 창, 항상 위. 고양이를 끌어서 옮긴다(끄는 동안 둥실 뜬 자세). 투명한 부분은 클릭이 뒤로 통과한다.
- 고양이는 그림(sprite.py, 스프라이트 애니메이션)으로 그리고, 그림 파일이 없으면 도형(painter.py)으로 그린다.
- 말풍선: 평소엔 지금 하는 일(타이머 남은 시간, 다음 알람, 대답 대기)을 보여주고,
  명령을 처리하면 응답을 잠깐 보여준 뒤 다시 상태 표시로 돌아간다. 알림(타이머 끝 등)은 확인할 때까지 남는다.
- 스케줄러 스레드의 알림은 Signal로 GUI 스레드에 넘긴다 (Qt 위젯은 GUI 스레드에서만 만진다).
- 잔상 방지: Windows의 투명 창은 알파 0 픽셀을 원래 클릭이 통과하므로 setMask를 쓰지 않는다
  (레이어드 창 + 창 영역을 같이 쓰면 지난 말풍선 글자가 남아 겹쳐 보일 수 있다). 말풍선 그림자도 QGraphicsEffect 대신
  직접 그리고, 말풍선이 바뀔 때마다 창 전체를 다시 그린다.
- 대사·문구·색·표정 규칙은 전부 persona.yaml에서 온다.
"""

from __future__ import annotations

import math
import random
import sys
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from jonnyang.core.config import sprite_dir
from jonnyang.core.reply import Reply
from jonnyang.gui.painter import CatFrame, CatPainter
from jonnyang.gui.sprite import SpritePainter, make_painter
from jonnyang.persona.cat import Persona

FONT_FAMILIES = ["Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans CJK KR",
                 "WenQuanYi Zen Hei", "Segoe UI Emoji", "sans-serif"]
WIN_W, WIN_H = 340, 480
CAT_W, CAT_H = 190, 170
INPUT_H = 36
BUBBLE_MAX_W = 310
BUBBLE_MAX_TEXT_H = 220
IDLE_BUBBLE_SEC = 6.0          # 할 일 없을 때 대기 문구를 보여주는 시간
REPLY_MIN_SEC, REPLY_MAX_SEC = 4.0, 25.0
REPLY_SEC_PER_CHAR = 0.07      # 한국어 읽는 속도 대략 초당 14자
HOVER_GRACE_SEC = 2.0          # 말풍선에서 마우스를 뗀 뒤 조금 더 보여준다
USE_MASK = sys.platform != "win32"   # Windows는 투명 픽셀이 원래 클릭을 통과시킨다
SLEEP_AFTER_SEC = 10 * 60      # 이만큼 조용하면 잠든다
DRAG_THRESHOLD = 4


def ui_font(px: int = 13, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class Bridge(QObject):
    """다른 스레드 → GUI 스레드."""
    ready = Signal(object, object)       # ctx, dispatcher
    failed = Signal(str)
    notified = Signal(object)            # list[Reply]
    finished = Signal(object)            # list[Reply] 인터넷 스킬 결과 (작업 스레드에서)


# ───────────────────────── 고양이 ─────────────────────────
class CatWidget(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    dragged = Signal(QPoint)             # 새 창 위치
    drag_finished = Signal()
    menu_requested = Signal(QPoint)
    hovered = Signal()

    def __init__(self, painter: CatPainter | SpritePainter, parent: QWidget | None = None):
        super().__init__(parent)
        self.cat = painter
        self.setFixedSize(CAT_W, CAT_H)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)
        self.mono: Callable[[], float] = time.monotonic
        self.start = self.mono()
        self.base_pose = "sleep"
        self.transient: tuple[str, float | None] | None = None   # (표정, 끝나는 시각 / None=계속)
        self._pose = "sleep"
        self._pose_since = self.start
        self._next_blink = self.start + 2.0
        self._heart_since: float | None = None
        self._press: QPoint | None = None
        self._win_origin: QPoint | None = None
        self._dragging = False
        self._before_drag: tuple[str, float | None] | None = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    # 표정
    def set_base(self, pose: str) -> None:
        self.base_pose = pose

    def flash(self, pose: str, seconds: float | None = 2.5) -> None:
        """잠깐(또는 seconds=None이면 풀릴 때까지) 이 표정."""
        now = self.mono()
        self.transient = (pose, None if seconds is None else now + seconds)
        self._pose_since = now

    def clear_flash(self) -> None:
        self.transient = None

    def pet(self) -> None:
        """쓰다듬기: 그림은 그대로 두고 몸을 눌렀다 펴며 하트 (그리는 쪽이 heart_t로 처리)."""
        self._heart_since = self.mono()

    @property
    def pose(self) -> str:
        now = self.mono()
        if self.transient and (self.transient[1] is None or now < self.transient[1]):
            pose = self.transient[0]
        else:
            self.transient = None
            pose = self.base_pose
        if pose != self._pose:
            self._pose, self._pose_since = pose, now
        return pose

    def frame(self) -> CatFrame:
        now = self.mono()
        pose = self.pose
        if now >= self._next_blink:
            if now - self._next_blink > 0.16:
                self._next_blink = now + random.uniform(2.5, 6.0)
        blink = 1.0 if self._next_blink <= now <= self._next_blink + 0.16 else 0.0
        center = self.mapToGlobal(self.rect().center())
        cur = QCursor.pos()
        dx, dy = cur.x() - center.x(), cur.y() - center.y()
        dist = max(1.0, math.hypot(dx, dy))
        look = (dx / dist * min(1.0, dist / 200), dy / dist * min(1.0, dist / 200))
        heart = None if self._heart_since is None else now - self._heart_since
        return CatFrame(pose=pose, t=now - self.start, pose_t=now - self._pose_since, blink=blink, look=look,
                        heart_t=heart)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        self.cat.paint(p, QRectF(self.rect()), self.frame())
        p.end()

    # 마우스: 끌기 / 클릭 / 더블클릭 / 우클릭
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._win_origin = self.window().pos()
            self._dragging = False

    def mouseMoveEvent(self, e) -> None:
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._before_drag = self.transient
            self.flash("drag", None)          # 끌려가는 동안 둥실 떠 있는 자세
        if self._dragging:
            self.dragged.emit(self._win_origin + delta)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.transient = self._before_drag   # 끌기 전 표정(대답 기다리기 등)으로 돌아간다
            self._before_drag = None
            self.drag_finished.emit()
        else:
            self.clicked.emit()
        self._press = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def contextMenuEvent(self, e) -> None:
        self.menu_requested.emit(e.globalPos())

    def enterEvent(self, e) -> None:
        self.hovered.emit()


# ───────────────────────── 말풍선 ─────────────────────────
class Bubble(QWidget):
    choice = Signal(str)
    clicked = Signal()

    TAIL = 12
    PAD = 14
    SHADOW = 4

    def __init__(self, colors: dict, labels: Callable[[str], str], parent: QWidget | None = None):
        super().__init__(parent)
        self.colors = colors
        self.labels = labels
        self.hovering = False
        self.state: str | None = None
        self.tail_x = 0.5
        self._text = ""

        self.header = QLabel(self)
        self.header.setFont(ui_font(11, bold=True))
        self.body = QLabel(self)
        self.body.setTextFormat(Qt.TextFormat.PlainText)   # 목록 항목 등이 HTML로 해석되지 않게
        self.body.setWordWrap(True)
        self.body.setFont(ui_font(13))
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setStyleSheet(f"color: {colors.get('bubble_text', '#2B2622')}; background: transparent;")
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.buttons = QWidget(self)
        self.buttons_layout = QHBoxLayout(self.buttons)
        self.buttons_layout.setContentsMargins(0, 4, 0, 0)
        self.buttons_layout.setSpacing(6)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(self.PAD + self.SHADOW, 10 + self.SHADOW, self.PAD + self.SHADOW,
                               10 + self.TAIL + 2 * self.SHADOW)
        lay.setSpacing(4)
        lay.addWidget(self.header)
        lay.addWidget(self.scroll)
        lay.addWidget(self.buttons)
        self.hide()

    def text(self) -> str:
        return self._text

    def set_content(self, text: str, state: str | None = None, choices: list[tuple[str, str]] | None = None) -> None:
        self._text = text
        self.state = state
        self.body.setText(text)
        if state:
            dot = self.colors.get("state", {}).get(state, "#999999")
            self.header.setText(f"● {self.labels(f'state.{state}')}")
            self.header.setStyleSheet(f"color: {dot}; background: transparent;")
            self.header.show()
        else:
            self.header.hide()
        while self.buttons_layout.count():
            w = self.buttons_layout.takeAt(0).widget()
            if w:
                w.hide()              # deleteLater 전까지 옛 버튼이 새 글자 위에 남지 않게
                w.deleteLater()
        for label, answer in choices or []:
            b = QPushButton(label, self.buttons)
            b.setFont(ui_font(12, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            accent = self.colors.get("state", {}).get("needs_input", "#F5A524")
            b.setStyleSheet(
                f"QPushButton {{ background: #FFFFFF; color: #3A2E2E; border: 1.5px solid {accent};"
                f" border-radius: 11px; padding: 3px 10px; }}"
                f"QPushButton:hover {{ background: {accent}; color: white; }}")
            b.clicked.connect(lambda _=False, a=answer: self.choice.emit(a))
            self.buttons_layout.addWidget(b)
        self.buttons_layout.addStretch(1)
        self.buttons.setVisible(bool(choices))
        self._resize()
        self.scroll.verticalScrollBar().setValue(0)
        self.update()

    def _resize(self) -> None:
        fm = QFontMetrics(self.body.font())
        widest = max((fm.horizontalAdvance(line) for line in self._text.split("\n")), default=0)
        limit = BUBBLE_MAX_W - 2 * (self.PAD + self.SHADOW)
        inner = max(120, min(limit, widest + 8))
        if self.buttons.isVisible():
            inner = max(inner, min(limit, self.buttons.sizeHint().width()))
        self.body.setFixedWidth(inner - 2)
        text_h = self.body.heightForWidth(inner - 2)
        self.scroll.setFixedSize(inner, min(BUBBLE_MAX_TEXT_H, text_h + 2))
        policy = Qt.ScrollBarPolicy
        self.scroll.setVerticalScrollBarPolicy(
            policy.ScrollBarAsNeeded if text_h > BUBBLE_MAX_TEXT_H else policy.ScrollBarAlwaysOff)
        self.adjustSize()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sh = self.SHADOW
        r = QRectF(self.rect()).adjusted(1.5 + sh, 1.5 + sh, -1.5 - sh, -1.5 - self.TAIL - 2 * sh)
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        tx = max(r.left() + 24, min(r.right() - 24, self.width() * self.tail_x))
        tail = QPainterPath()
        tail.moveTo(tx - 10, r.bottom() - 1)
        tail.lineTo(tx + 2, r.bottom() + self.TAIL)
        tail.lineTo(tx + 10, r.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(Qt.PenStyle.NoPen)
        for i, alpha in enumerate((14, 18, 24)):     # 부드러운 그림자 (위젯 영역 안에서만)
            p.setBrush(QColor(40, 30, 90, alpha))
            p.drawPath(path.translated(0, 1 + i * 1.2))
        p.setPen(QPen(QColor(self.colors.get("bubble_border", "#EADBC6")), 1.5))
        p.setBrush(QColor(self.colors.get("bubble_bg", "#FFFDF8")))
        p.drawPath(path)
        p.end()

    def mousePressEvent(self, e) -> None:
        self.clicked.emit()

    def enterEvent(self, e) -> None:
        self.hovering = True

    def leaveEvent(self, e) -> None:
        self.hovering = False


# ───────────────────────── 입력창 ─────────────────────────
class InputBar(QLineEdit):
    focus_changed = Signal(bool)

    def __init__(self, colors: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.history: list[str] = []
        self._hist_i = 0
        self.setFont(ui_font(13))
        self.setFixedHeight(INPUT_H)
        bg = QColor(colors.get("bubble_bg", "#FFFDF8"))
        self.setStyleSheet(
            f"QLineEdit {{ background: rgba({bg.red()}, {bg.green()}, {bg.blue()}, 240);"
            f" color: {colors.get('bubble_text', '#2B2622')};"
            f" border: 1.5px solid {colors.get('bubble_border', '#EADBC6')};"
            " border-radius: 17px; padding: 0 14px; }"
            f"QLineEdit:focus {{ border: 1.5px solid {colors.get('input_focus', '#F0A04B')}; }}")

    def remember(self, text: str) -> None:
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self._hist_i = len(self.history)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Up and self.history:
            self._hist_i = max(0, self._hist_i - 1)
            self.setText(self.history[self._hist_i])
            return
        if e.key() == Qt.Key.Key_Down and self.history:
            self._hist_i = min(len(self.history), self._hist_i + 1)
            self.setText(self.history[self._hist_i] if self._hist_i < len(self.history) else "")
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        self.window().activateWindow()   # 항상 위 도구 창이라 직접 활성화해야 키 입력이 들어온다
        super().mousePressEvent(e)

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        self.focus_changed.emit(True)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.focus_changed.emit(False)


# ───────────────────────── 창 ─────────────────────────
class PetWindow(QWidget):
    def __init__(self, persona: Persona, storage=None, tray: bool = True):
        super().__init__(None)
        self.persona = persona
        self.storage = storage
        self.ctx = None
        self.dispatcher = None
        self.mono: Callable[[], float] = time.monotonic
        self.bridge = Bridge()
        self.bridge.ready.connect(self.attach)
        self.bridge.failed.connect(self._backend_failed)
        self.bridge.notified.connect(self.on_notify)
        self.bridge.finished.connect(self.on_finished)

        self.setWindowTitle(persona.ui("tray.tooltip"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIN_W, WIN_H)

        colors = persona.appearance
        self.cat = CatWidget(make_painter(sprite_dir(), persona.sprites, colors), self)
        self.bubble = Bubble(colors, persona.ui, self)
        self.input = InputBar(colors, self)
        self.input.setPlaceholderText(persona.ui("placeholder"))
        self.input.setEnabled(False)

        self.cat.clicked.connect(self.on_cat_clicked)
        self.cat.double_clicked.connect(self.toggle_input)
        self.cat.dragged.connect(self.move)
        self.cat.drag_finished.connect(self.save_position)
        self.cat.menu_requested.connect(self.show_menu)
        self.cat.hovered.connect(self.on_hover)
        self.bubble.choice.connect(self.submit)
        self.bubble.clicked.connect(self.acknowledge)
        self.input.returnPressed.connect(self._on_return)
        self.input.focus_changed.connect(self._on_input_focus)
        self.input.textEdited.connect(lambda _: self.touch())     # 타자 치기 시작하면 깬다

        # 말풍선 모드: reply(응답 보여주는 중) / status(진행 상태) / idle(대기 문구) / hidden
        self.mode = "hidden"
        self.sticky = False              # 대답 대기나 알림이면 확인할 때까지 유지
        self.deadline = 0.0
        self._was_hovering = False
        self._current_choices: list[tuple[str, str]] = []
        self._saved_question: tuple[str, list[tuple[str, str]]] | None = None   # 알림에 가려진 확인 질문
        self.last_activity = self.mono()

        self._layout()
        self._restore_position()
        self.tray = self._make_tray() if tray and QSystemTrayIcon.isSystemTrayAvailable() else None

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.tick)
        self.ticker.start(1000)
        self.show_bubble(persona.ui("loading"), None, [], hold=None)

    # ── 배치 ──
    def _layout(self) -> None:
        input_y = WIN_H - INPUT_H - 4
        self.input.setGeometry(18, input_y, WIN_W - 36, INPUT_H)
        cat_bottom = input_y - 2 if self.input.isVisibleTo(self) else WIN_H - 2
        self.cat.move((WIN_W - CAT_W) // 2, cat_bottom - CAT_H)
        self._place_bubble()

    def _place_bubble(self) -> None:
        b = self.bubble
        b.adjustSize()
        x = max(4, min(WIN_W - b.width() - 4, (WIN_W - b.width()) // 2))
        y = max(2, self.cat.y() + 22 - b.height())
        b.move(x, y)
        head_x = self.cat.x() + CAT_W / 2
        b.tail_x = (head_x - x) / max(1, b.width())
        b.update()
        self._update_mask()

    def _update_mask(self) -> None:
        if USE_MASK:
            region = QRegion(self.cat.geometry())
            if self.input.isVisibleTo(self):
                region = region.united(QRegion(self.input.geometry().adjusted(-2, -2, 2, 2)))
            if self.bubble.isVisibleTo(self):
                region = region.united(QRegion(self.bubble.geometry().adjusted(-4, -4, 4, 4)))
            self.setMask(region)
        self.update()                    # 부분 갱신만 하면 투명 창에 지난 말풍선이 남을 수 있다

    def _restore_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        pos = QPoint(avail.right() - WIN_W - 16, avail.bottom() - WIN_H - 8)
        saved = self.storage.get_setting("gui.pos") if self.storage else None
        if isinstance(saved, list) and len(saved) == 2:
            cand = QPoint(int(saved[0]), int(saved[1]))
            probe = cand + QPoint(WIN_W // 2, WIN_H - CAT_H // 2)
            if any(s.availableGeometry().contains(probe) for s in QGuiApplication.screens()):
                pos = cand
        self.move(pos)

    def save_position(self) -> None:
        if self.storage:
            self.storage.set_setting("gui.pos", [self.x(), self.y()])

    # ── 백엔드 연결 ──
    def start_backend(self, factory: Callable[[], tuple]) -> None:
        """형태소 사전 로딩(몇 초)을 다른 스레드에서. 그동안 고양이는 자고 있다."""
        def run() -> None:
            try:
                ctx, dispatcher = factory()
            except Exception as exc:  # 로딩 실패도 화면에 보여준다
                self.bridge.failed.emit(repr(exc))
                return
            self.bridge.ready.emit(ctx, dispatcher)
        threading.Thread(target=run, name="jonnyang-loader", daemon=True).start()

    def attach(self, ctx, dispatcher) -> None:
        self.ctx, self.dispatcher = ctx, dispatcher
        self.persona = ctx.persona
        ctx.reply_sink = self.bridge.notified.emit
        dispatcher.runner = self.run_async
        ctx.scheduler.on_error = lambda exc: self.bridge.notified.emit(
            [Reply(ctx.persona.say("error.internal", {"reason": repr(exc)}, core=("reason",)), "error.internal",
                   ok=False, alert=True)])
        self.input.setEnabled(True)
        self.cat.set_base("idle")
        self.last_activity = self.mono()
        self.show_replies(dispatcher.startup_replies())
        ctx.scheduler.start()

    def _backend_failed(self, reason: str) -> None:
        self.show_bubble(self.persona.say("error.internal", {"reason": reason}, core=("reason",)), "blocked", [],
                         hold=None)
        self.cat.flash("confused", None)

    # ── 입력 ──
    def _on_return(self) -> None:
        text = self.input.text().strip()
        self.input.clear()
        if text:
            self.input.remember(text)
            self.submit(text)

    def submit(self, text: str) -> None:
        if self.dispatcher is None:
            return
        self.touch()
        try:
            replies = self.dispatcher.respond(text)
        except Exception as exc:   # 한 명령의 오류로 펫이 죽지 않게
            replies = [Reply(self.persona.say("error.internal", {"reason": repr(exc)}, core=("reason",)),
                             "error.internal", ok=False)]
        self.show_replies(replies)

    def _on_input_focus(self, focused: bool) -> None:
        if focused:
            self.touch()
        self.cat.set_base("listen" if focused else "idle")

    def toggle_input(self) -> None:
        self.input.setVisible(self.input.isHidden())
        self._layout()
        if self.input.isVisibleTo(self):
            self.activateWindow()
            self.input.setFocus()

    # ── 말풍선 ──
    def show_bubble(self, text: str, state: str | None, choices: list[tuple[str, str]],
                    hold: float | None) -> None:
        """hold초 동안 보여준다. None이면 확인할 때까지."""
        if text != self.bubble.text() or state != self.bubble.state or choices:
            self.bubble.set_content(text, state, choices)
        self._current_choices = list(choices)
        self.bubble.show()
        self._place_bubble()
        self.sticky = hold is None
        self.deadline = self.mono() + (hold or 0)

    @staticmethod
    def reply_seconds(text: str) -> float:
        """응답을 보여줄 시간: 읽을 시간 + 여유. 너무 짧으면 못 읽고, 너무 길면 다음 응답과 섞여 보인다."""
        return max(REPLY_MIN_SEC, min(REPLY_MAX_SEC, 2.5 + len(text) * REPLY_SEC_PER_CHAR))

    def show_replies(self, replies: list[Reply]) -> None:
        if not replies:
            return
        last = replies[-1]
        text = "\n\n".join(r.text for r in replies if r.text)
        waiting = any(r.waiting for r in replies)
        alert = any(r.alert for r in replies)
        ok = all(r.ok for r in replies)
        choices = last.choices
        running = any(r.running for r in replies)
        showing_alert = self.mode == "reply" and self.sticky and self.bubble.state == "alert"
        if alert and not waiting and showing_alert:
            # 아직 확인 안 한 알림이 있으면 덮어쓰지 않고 이어 붙인다 (타이머 두 개가 연달아 끝난 경우 등)
            text = f"{self.bubble.text()}\n\n{text}"
        elif not waiting and self.mode == "reply" and self.bubble.state == "needs_input" \
                and self.dispatcher is not None and self.dispatcher.pending is not None:
            # 확인 질문 중에 알림이나 인터넷 결과가 오면 질문을 기억해 뒀다가 다 보면 다시 보여준다
            self._saved_question = (self.bubble.text(), self._current_choices)
        if waiting:
            self._saved_question = None
        state = ("needs_input" if waiting else "alert" if alert else "running" if running
                 else ("blocked" if not ok else "ready"))
        hold = None if (waiting or alert) else self.reply_seconds(text) + (30.0 if running else 0.0)
        self.mode = "reply"
        self.show_bubble(text, state, choices, hold)
        pose = self.persona.pose_for((next((r for r in replies if r.alert), last)).key, ok)
        self.cat.flash(pose, None if (waiting or alert or running) else 3.0)
        self.input.setPlaceholderText(self.persona.ui("placeholder_waiting" if waiting else "placeholder"))

    def run_async(self, job: Callable[[], list[Reply]]) -> None:
        """인터넷 스킬: 작업 스레드에서 돌리고 결과는 Signal로 GUI 스레드에 넘긴다."""
        def run() -> None:
            try:
                replies = job()
            except Exception as exc:  # job 안에서 이미 잡지만 혹시 몰라서
                replies = [Reply(self.persona.say("error.internal", {"reason": repr(exc)}, core=("reason",)),
                                 "error.internal", ok=False)]
            self.bridge.finished.emit(replies)
        threading.Thread(target=run, name="jonnyang-online", daemon=True).start()

    def on_finished(self, replies: list[Reply]) -> None:
        self.touch()
        self.show_replies(replies)

    def on_notify(self, replies: list[Reply]) -> None:
        """타이머 끝, 알람, 리마인더 (스케줄러 스레드에서 Signal로 넘어옴)."""
        self.touch()
        self.show_replies(replies)
        # 펫이 화면에 보이면 말풍선으로 충분하다. 트레이 알림까지 띄우면 같은 말이 화면 구석에 겹쳐 뜬다.
        hidden = not self.isVisible()
        if hidden and self.tray is not None:
            self.tray.showMessage(self.persona.ui("tray.tooltip"), "\n".join(r.text for r in replies),
                                  QSystemTrayIcon.MessageIcon.Information, 10_000)
        if hidden:
            self.show()
        self.raise_()

    def acknowledge(self) -> None:
        """알림·응답 말풍선 확인. 확인 질문에는 버튼이나 입력으로 답해야 하므로 그대로 둔다."""
        if self.mode != "reply" or self.dispatcher is None:
            return
        pending = self.dispatcher.pending is not None
        if self.bubble.state == "needs_input" and pending:
            return
        saved, self._saved_question = self._saved_question, None
        if saved and pending:            # 알림에 가려졌던 확인 질문으로 돌아간다
            self.show_bubble(saved[0], "needs_input", saved[1], hold=None)
            self.cat.flash("ask", None)
            self.input.setPlaceholderText(self.persona.ui("placeholder_waiting"))
            return
        self.sticky = False
        self.deadline = 0
        self.cat.clear_flash()
        self.input.setPlaceholderText(self.persona.ui("placeholder"))
        self.tick()

    def on_cat_clicked(self) -> None:
        self.touch()
        if self.mode == "reply" and self.sticky and self.bubble.state != "needs_input":
            self.acknowledge()
            return
        self.cat.pet()
        if self.dispatcher is not None and self.mode != "reply":
            self.mode = "idle"
            self.show_bubble(self.persona.say("chat.pet"), None, [], hold=3.0)

    def on_hover(self) -> None:
        if self.mode == "hidden" and self.dispatcher is not None:
            self.touch()
            self.tick()

    def touch(self) -> None:
        self.last_activity = self.mono()
        if self.cat.base_pose == "sleep" and self.dispatcher is not None:
            self.cat.set_base("listen" if self.input.hasFocus() else "idle")

    def tick(self) -> None:
        """1초마다: 응답 만료 → 상태 표시, 남은 시간 갱신, 졸음."""
        if self.dispatcher is None:
            return
        now = self.mono()
        if self.mode == "reply":
            if self.dispatcher.pending is None:
                self._saved_question = None
                if self.bubble.state == "needs_input":
                    self.sticky = False      # 대기 시간이 지나 dispatcher가 대기를 버림
            if self.bubble.hovering:         # 읽는 중이면 기다린다
                self._was_hovering = True
                return
            if self._was_hovering:
                self._was_hovering = False
                self.deadline = max(self.deadline, now + HOVER_GRACE_SEC)
            if self.sticky or now < self.deadline:
                return
            saved, self._saved_question = self._saved_question, None
            if saved and self.dispatcher.pending is not None:
                self.show_bubble(saved[0], "needs_input", saved[1], hold=None)
                self.cat.flash("ask", None)
                self.input.setPlaceholderText(self.persona.ui("placeholder_waiting"))
                return
            self.cat.clear_flash()
            self.input.setPlaceholderText(self.persona.ui("placeholder"))
            self.mode = "status"
        status = self.dispatcher.status()
        if status:
            kind, reply = status
            self.mode = "status"
            state = "needs_input" if kind == "waiting" else "running"
            self.show_bubble(reply.text, state, [], hold=0)
            self.sticky = False
            return
        if self.mode == "status":
            self.mode = "idle"
            sleepy = now - self.last_activity > SLEEP_AFTER_SEC
            self.show_bubble(self.persona.say("status.sleep" if sleepy else "status.idle"), None, [],
                             hold=IDLE_BUBBLE_SEC)
            return
        if self.mode == "idle" and (now >= self.deadline and not self.bubble.hovering):
            self.mode = "hidden"
            self.bubble.hide()
            self._update_mask()
        if self.mode == "hidden" and now - self.last_activity > SLEEP_AFTER_SEC:
            self.cat.set_base("sleep")

    # ── 메뉴 / 트레이 ──
    def _menu(self) -> QMenu:
        p = self.persona
        m = QMenu(self)
        m.setFont(ui_font(13))
        m.addAction(p.ui("menu.input"), self.toggle_input)
        m.addAction(p.ui("menu.help"), lambda: self.submit("뭐 할 수 있어?"))
        m.addSeparator()
        m.addAction(p.ui("menu.nyang_off" if p.nyang else "menu.nyang_on"),
                    lambda: self.submit("냥체 꺼" if self.persona.nyang else "냥체 켜"))
        m.addAction(p.ui("menu.emoji_off" if p.emoji else "menu.emoji_on"),
                    lambda: self.submit("이모지 꺼" if self.persona.emoji else "이모지 켜"))
        m.addSeparator()
        m.addAction(p.ui("menu.hide"), self.hide)
        m.addAction(p.ui("menu.quit"), QApplication.quit)
        return m

    def show_menu(self, global_pos: QPoint) -> None:
        self._menu().exec(global_pos)

    def _make_tray(self) -> QSystemTrayIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        self.cat.cat.paint_icon(p, QRectF(0, 0, 64, 64))
        p.end()
        tray = QSystemTrayIcon(QIcon(pix), self)
        tray.setToolTip(self.persona.ui("tray.tooltip"))
        menu = QMenu()
        show = QAction(self.persona.ui("menu.show"), menu)
        show.triggered.connect(self.bring_back)
        menu.addAction(show)
        menu.addAction(self.persona.ui("menu.quit"), QApplication.quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self.bring_back()
                               if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        self._tray_menu = menu
        return tray

    def bring_back(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def shutdown(self) -> None:
        self.save_position()
        if self.ctx is not None:
            self.ctx.scheduler.stop()
        if self.tray is not None:
            self.tray.hide()
