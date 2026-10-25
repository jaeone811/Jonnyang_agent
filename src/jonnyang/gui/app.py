"""데스크톱 펫 실행 진입점.

exe(콘솔 없음)로 돌 때는 오류가 화면에 안 보이므로, 죽으면 data 폴더의 crash.log에 남기고 대화상자로 알린다.
`--selftest 결과파일`은 빌드된 exe가 제대로 묶였는지 CI에서 확인하는 용도다 (창 없이 돌고 사용자 데이터는 안 건드림).
"""

from __future__ import annotations

import sys
import traceback


def _crash_log(exc: BaseException) -> str:
    from datetime import datetime

    from jonnyang.core.config import data_dir

    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / "crash.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n{text}")
        return f"{text}\n\n로그: {path}"
    except OSError:
        return text


def selftest(out_path: str) -> int:
    """exe 안에 kiwi 모델·설정·Qt 플러그인이 다 들어갔는지 확인. 결과를 텍스트 파일로 남긴다."""
    import os
    import random

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines: list[str] = []
    ok = True
    try:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtWidgets import QApplication

        from jonnyang.app import build_app
        from jonnyang.core.config import config_dir, frozen, load_yaml
        from jonnyang.core.storage import Storage
        from jonnyang.gui.painter import CatFrame, CatPainter
        from jonnyang.platform.system import resolve_folder, system_platform

        app = QApplication.instance() or QApplication(sys.argv[:1])
        lines.append(f"frozen={frozen()} config_dir={config_dir()} persona_keys={len(load_yaml('persona.yaml'))}"
                     f" online={bool(load_yaml('online.yaml'))} files={bool(load_yaml('files.yaml'))}")
        _, d = build_app(platform=system_platform(), storage=Storage(":memory:"), rng=random.Random(0))
        checks = {"3분 타이머": "3분", "40의 15%는?": "6", "쇼핑 목록에 우유 추가해": "우유", "CPU 얼마나 써": "%",
                  "매일 아침 8시에 약 먹으라고 알려줘": "매일", "인터넷 기능 꺼": "껐", "날씨 어때": "꺼져"}
        for text, want in checks.items():
            out = "\n".join(d.handle(text))
            good = want in out
            ok &= good
            lines.append(f"{'OK ' if good else 'BAD'} {text} -> {out}")
        import feedparser
        from send2trash import send2trash  # noqa: F401  (exe에 묶였는지만 본다)

        feed = feedparser.parse(b"<rss version='2.0'><channel><item><title>t1</title></item></channel></rss>")
        good = len(feed.entries) == 1
        ok &= good
        lines.append(f"{'OK ' if good else 'BAD'} feedparser {feedparser.__version__}, send2trash import")
        lines.append(f"    Downloads folder -> {resolve_folder('known:Downloads')}")
        img = QImage(200, 180, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        CatPainter().paint(p, QRectF(0, 0, 200, 180), CatFrame(pose="search"))
        p.end()
        drawn = img.pixelColor(100, 80).alpha() > 0
        ok &= drawn
        lines.append(f"{'OK ' if drawn else 'BAD'} cat painted, qt platform={app.platformName()}")
    except BaseException as exc:
        ok = False
        lines.append(traceback.format_exc())
        del exc
    lines.append("SELFTEST PASS" if ok else "SELFTEST FAIL")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def run() -> int:
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox

    from jonnyang.app import build_app
    from jonnyang.core.config import data_dir, load_yaml
    from jonnyang.core.storage import Storage
    from jonnyang.gui.window import PetWindow
    from jonnyang.persona.cat import Persona
    from jonnyang.platform.system import system_platform

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)    # 창을 숨겨도(트레이) 계속 돈다
    app.setApplicationName("Jonnyang")

    data = data_dir()
    data.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / "jonnyang.lock"))
    persona_data = load_yaml("persona.yaml")
    if not lock.tryLock(100):
        # 고양이 둘이 같은 DB로 리마인더를 두 번 울리지 않게 한 번만 실행
        QMessageBox.information(None, "Jonnyang", Persona(persona_data, lambda k, d=None: d).ui("already_running"))
        return 1

    storage = Storage(data / "jonnyang.db")
    win = PetWindow(Persona(persona_data, storage.get_setting), storage)
    win.show()
    win.start_backend(lambda: build_app(platform=system_platform(), storage=storage))
    try:
        return app.exec()
    finally:
        win.shutdown()
        storage.close()
        lock.unlock()


def main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--selftest":
        return selftest(args[1])
    try:
        return run()
    except Exception as exc:  # 콘솔 없는 exe에서 조용히 죽지 않게
        detail = _crash_log(exc)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            QApplication.instance() or QApplication(sys.argv[:1])
            QMessageBox.critical(None, "Jonnyang", detail)
        except Exception:
            print(detail, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
