"""스킬 인터페이스. 스킬은 순수 결과 데이터(Result)만 돌려주고 말투는 persona가 입힌다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from jonnyang.nlu.matcher import Intent

if TYPE_CHECKING:
    from jonnyang.core.context import AppContext
    from jonnyang.nlu.pipeline import Request


@dataclass
class Result:
    key: str                                  # persona 템플릿 키
    data: dict[str, Any] = field(default_factory=dict)
    core: tuple[str, ...] = ()                # 말투가 뭐든 반드시 출력에 나와야 하는 data 키
    items: list[dict[str, Any]] | None = None
    item_key: str | None = None               # items 각 줄을 그릴 템플릿 키
    undo: dict[str, Any] | None = None        # 있으면 history에 기록 → skill.undo(payload)
    undo_label: str | None = None             # persona.undo_labels 키
    ok: bool = True


@dataclass
class Confirm:
    """파괴적 작업 확인. 사용자가 '응' 하면 action()을 실행한다."""
    key: str
    action: Callable[[], Result]
    data: dict[str, Any] = field(default_factory=dict)
    core: tuple[str, ...] = ()
    items: list[dict[str, Any]] | None = None
    item_key: str | None = None


class Skill:
    name: str = ""
    requires_network: bool = False
    intents: list[Intent] = []

    def __init__(self, ctx: "AppContext"):
        self.ctx = ctx

    def extract(self, intent: str, req: "Request") -> dict[str, Any]:
        """스킬 전용 슬롯 추출. 필수 슬롯이 없으면 키를 빼고 돌려준다."""
        return {}

    def handle(self, intent: str, req: "Request", slots: dict[str, Any]) -> Result | Confirm:
        raise NotImplementedError

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        return Result("undo.unsupported", ok=False)

    def status(self, now: datetime) -> list[tuple[datetime, Result]]:
        """지금 진행 중인 일 (말풍선 표시용). (다음 이벤트 시각, 결과) 목록."""
        return []

    def protected_words(self) -> set[str]:
        """이 스킬이 의미를 아는 단어. 다른 의도의 키워드로 오타 보정되지 않게 보호한다."""
        return set()

    def on_start(self) -> list[Result]:
        """프로그램 시작 시 할 일(예약 복구, 놓친 알림)."""
        return []
