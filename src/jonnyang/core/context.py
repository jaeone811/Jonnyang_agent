"""프로그램 전체가 공유하는 객체 묶음."""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Callable

from jonnyang.core.aliases import AliasBook
from jonnyang.core.config import load_yaml
from jonnyang.core.history import History
from jonnyang.core.reply import Reply
from jonnyang.core.scheduler import Scheduler
from jonnyang.core.storage import Storage
from jonnyang.nlu.normalize import Analyzer
from jonnyang.persona.cat import Persona
from jonnyang.platform.base import Platform
from jonnyang.skills.base import Confirm, Result, Skill


class AppContext:
    def __init__(self, *, storage: Storage, platform: Platform, analyzer: Analyzer,
                 clock: Callable[[], datetime] = datetime.now, config_dir=None,
                 sink: Callable[[list[str]], None] | None = None, rng: random.Random | None = None,
                 beep_gap: float = 0.3):
        self.settings = load_yaml("settings.yaml", config_dir)
        self.storage = storage
        self.platform = platform
        self.analyzer = analyzer
        self.clock = clock
        self.scheduler = Scheduler(clock)
        self.history = History(storage, clock)
        self.aliases = AliasBook(storage, load_yaml("aliases.yaml", config_dir), clock)
        self.persona = Persona(load_yaml("persona.yaml", config_dir), storage.get_setting, rng)
        self.sink = sink or (lambda lines: None)
        self.reply_sink: Callable[[list[Reply]], None] | None = None   # GUI용 (스케줄러 스레드에서 불림)
        self.skills: dict[str, Skill] = {}
        self.beep_gap = beep_gap
        for name in self.aliases.names():
            analyzer.add_word(name)

    @property
    def wake_required(self) -> bool:
        return bool(self.storage.get_setting("wake.required", self.settings.get("wake_required", False)))

    def notify(self, results: list[Result], beeps: int = 0) -> None:
        """스케줄러 스레드에서 부르는 알림 출력."""
        now = self.clock()
        replies = [Reply(self.persona.render(r, now), r.key, r.ok, alert=True) for r in results]
        self.sink([r.text for r in replies])
        if self.reply_sink:
            self.reply_sink(replies)
        for i in range(beeps):
            try:
                self.platform.beeper.beep()
            except Exception:
                break
            if i < beeps - 1 and self.beep_gap:
                time.sleep(self.beep_gap)

    def undo_last(self) -> Result | Confirm:
        last = self.history.last_undoable()
        if last is None:
            return Result("undo.nothing")
        skill = self.skills.get(last["skill"])
        if skill is None:
            return Result("undo.unsupported", ok=False)
        label_key = last["label_key"] or last["intent"]
        template = self.persona.label(f"undo.{label_key}")
        action_text = self.persona.say_label(template, last["label_data"], self.clock())

        def do_undo() -> Result:
            res = skill.undo(last["intent"], last["undo"])
            if res.ok:
                self.history.mark_undone(last["id"])
            if res.key == "undo.done":
                res.data = {"action": action_text}
                res.core = ("action",)
            return res
        return Confirm("confirm.undo", do_undo, {"action": action_text}, core=("action",))
