"""데스크톱 펫 실행 진입점."""

from __future__ import annotations

import sys


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
