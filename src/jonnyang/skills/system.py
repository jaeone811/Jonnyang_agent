"""볼륨, 앱 실행, 시스템 상태. 실제 OS 호출은 platform 어댑터가 한다."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from rapidfuzz import fuzz, process

from jonnyang.nlu.matcher import Intent
from jonnyang.nlu.preprocess import jamo
from jonnyang.persona.fmt import Bytes
from jonnyang.platform.base import Unsupported
from jonnyang.skills.base import Result, Skill

VOL = {"볼륨": 0.6, "소리": 0.6, "음량": 0.6, "사운드": 0.6}
LEVEL_RE = re.compile(r"(\d+)\s*(?:%|퍼센트|프로)?")


def _level_hint(req) -> float:
    return 0.4 if LEVEL_RE.search(req.text) or re.search(r"최대|최소|맥스|반으로", req.text) else 0.0


class VolumeSkill(Skill):
    name = "volume"
    intents = [
        Intent("volume.up", nouns=VOL, verbs={"UP": 0.4}, examples=("볼륨 올려줘", "소리 20 키워")),
        Intent("volume.down", nouns=VOL, verbs={"DOWN": 0.4}, examples=("소리 좀 줄여",)),
        Intent("volume.set", nouns=VOL, verbs={"SET": 0.1}, hint=_level_hint,
               avoid={"UP": 0.5, "DOWN": 0.5}, examples=("볼륨 50으로 해줘", "볼륨 최대로")),
        Intent("volume.mute", nouns={"음소거": 1.0, "소리": 0.6, "볼륨": 0.5}, verbs={"CLOSE": 0.4},
               avoid={"RELEASE": 0.6, "OPEN": 0.6, "UP": 0.5, "DOWN": 0.5}, examples=("음소거", "소리 꺼")),
        Intent("volume.unmute", nouns={"음소거": 0.6, "소리": 0.6, "볼륨": 0.5}, verbs={"RELEASE": 0.4, "OPEN": 0.4},
               avoid={"CLOSE": 0.5}, examples=("음소거 해제", "소리 켜")),
        Intent("volume.get", nouns=VOL, verbs={"SHOW": 0.4}, avoid={"UP": 0.4, "DOWN": 0.4},
               examples=("볼륨 몇이야",)),
    ]

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        m = LEVEL_RE.search(req.text)
        if m:
            slots["amount"] = int(m.group(1))
        if re.search(r"최대|맥스", req.text):
            slots["amount"] = 100
        elif re.search(r"최소", req.text):
            slots["amount"] = 0
        elif re.search(r"반으로", req.text):
            slots["amount"] = 50
        if re.search(r"조금|살짝|약간", req.text):
            slots["step"] = 5
        elif re.search(r"많이|확", req.text):
            slots["step"] = 20
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        vol = self.ctx.platform.volume
        try:
            before = {"level": vol.get(), "muted": vol.is_muted()}
            undo = {"op": "restore", **before}
            if intent == "volume.get":
                return Result("volume.get", {"level": before["level"], "muted": before["muted"]}, core=("level",))
            if intent == "volume.mute":
                vol.set_mute(True)
                return Result("volume.mute", undo=undo, undo_label="volume")
            if intent == "volume.unmute":
                vol.set_mute(False)
                return Result("volume.unmute", {"level": before["level"]}, core=("level",), undo=undo,
                              undo_label="volume")
            if intent == "volume.set":
                if "amount" not in slots:
                    return Result("ask.level")
                level = max(0, min(100, slots["amount"]))
            else:
                step = slots.get("amount", slots.get("step", 10))
                level = before["level"] + (step if intent == "volume.up" else -step)
                level = max(0, min(100, level))
            vol.set(level)
            if before["muted"] and level > 0:
                vol.set_mute(False)
            return Result(intent if intent != "volume.set" else "volume.set",
                          {"level": level, "before": before["level"]}, core=("level",), undo=undo,
                          undo_label="volume")
        except Unsupported:
            return Result("error.unsupported", ok=False)

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        vol = self.ctx.platform.volume
        try:
            vol.set(payload["level"])
            vol.set_mute(payload["muted"])
        except Unsupported:
            return Result("error.unsupported", ok=False)
        return Result("undo.done")


class AppSkill(Skill):
    """별칭 사전(config/aliases.yaml + 등록 별칭)에 있는 것만 연다. 사용자 문장으로 명령을 조립하지 않는다."""

    name = "apps"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.intents = [
            Intent("app.open", nouns={"앱": 0.2, "프로그램": 0.2, "폴더": 0.2}, verbs={"OPEN": 0.4},
                   avoid={"CLOSE": 0.5, "CANCEL": 0.5}, hint=lambda req: 0.6 * self.find(req)[1],
                   examples=("메모장 켜줘", "다운로드 폴더 열어", "계산기 실행")),
        ]

    def find(self, req) -> tuple[str | None, float]:
        names = self.ctx.aliases.names()
        if not names:
            return None, 0.0
        compact = req.compact
        exact = [n for n in names if n.replace(" ", "") in compact]
        if exact:
            return max(exact, key=len), 1.0
        best: tuple[str | None, float] = (None, 0.0)
        jamo_names = [jamo(n) for n in names]
        for m in req.morphs:
            if m.tag.startswith(("NN", "SL")) and len(m.form) >= 2:
                hit = process.extractOne(jamo(m.form.lower()), jamo_names, scorer=fuzz.ratio, score_cutoff=85)
                if hit and hit[1] / 100 > best[1]:
                    best = (names[hit[2]], hit[1] / 100)
        return best

    def extract(self, intent: str, req) -> dict[str, Any]:
        name, _ = self.find(req)
        return {"target": name} if name else {}

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        name = slots.get("target")
        if not name:
            return Result("app.not_found", {"text": req.text}, ok=False)
        kind, target = self.ctx.aliases.resolve(name)
        try:
            self.ctx.platform.launcher.open(target)
        except Unsupported:
            return Result("error.unsupported", ok=False)
        except OSError as exc:
            return Result("app.error", {"name": name, "target": target, "reason": str(exc)},
                          core=("name", "target", "reason"), ok=False)
        return Result("folder.open" if kind == "folder" else "app.open", {"name": name, "target": target},
                      core=("name",))


SHOW = {"SHOW": 0.2, "TELL": 0.2}


class SysInfoSkill(Skill):
    name = "sysinfo"
    intents = [
        Intent("sys.cpu", nouns={"cpu": 0.8, "씨피유": 0.8, "프로세서": 0.8}, verbs=SHOW,
               examples=("CPU 얼마나 써",)),
        Intent("sys.memory", nouns={"메모리": 0.8, "램": 0.8, "ram": 0.8}, verbs=SHOW,
               examples=("메모리 사용량 알려줘",)),
        Intent("sys.disk", nouns={"디스크": 0.8, "저장공간": 0.8, "드라이브": 0.8, "하드": 0.6, "용량": 0.5},
               verbs=SHOW, examples=("디스크 용량 얼마나 남았어",)),
        Intent("sys.battery", nouns={"배터리": 0.8, "충전": 0.6, "밧데리": 0.8}, verbs=SHOW,
               examples=("배터리 얼마나 남았어",)),
        Intent("sys.overview", nouns={"시스템": 0.8, "컴퓨터": 0.6, "pc": 0.6}, verbs=SHOW,
               avoid={"CLOSE": 0.5}, examples=("시스템 상태 알려줘",)),
    ]

    def _cpu(self) -> dict[str, Any]:
        return {"cpu": round(self.ctx.platform.sysinfo.cpu_percent(), 1)}

    def _mem(self) -> dict[str, Any]:
        used, total, pct = self.ctx.platform.sysinfo.memory()
        return {"mem_used": Bytes(used), "mem_total": Bytes(total), "mem_percent": round(pct, 1)}

    def _disk_items(self) -> list[dict[str, Any]]:
        return [{"mount": d.mount, "used": Bytes(d.used), "total": Bytes(d.total), "free": Bytes(d.total - d.used),
                 "percent": round(d.percent, 1)} for d in self.ctx.platform.sysinfo.disks()]

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        si = self.ctx.platform.sysinfo
        if intent == "sys.cpu":
            return Result("sys.cpu", self._cpu(), core=("cpu",))
        if intent == "sys.memory":
            return Result("sys.memory", self._mem(), core=("mem_used", "mem_total", "mem_percent"))
        if intent == "sys.disk":
            return Result("sys.disk", items=self._disk_items(), item_key="sys.disk_item")
        if intent == "sys.battery":
            b = si.battery()
            if b is None:
                return Result("sys.no_battery")
            key = "sys.battery_plugged" if b.plugged else ("sys.battery" if b.secs_left else "sys.battery_nolife")
            left = timedelta(seconds=b.secs_left) if b.secs_left else None
            return Result(key, {"percent": round(b.percent), "left": left}, core=("percent",))
        if intent == "sys.overview":
            data = {**self._cpu(), **self._mem()}
            b = si.battery()
            data["battery"] = f"{round(b.percent)}%" if b else "-"
            return Result("sys.overview", data, core=("cpu", "mem_percent"),
                          items=self._disk_items(), item_key="sys.disk_item")
        raise ValueError(intent)
