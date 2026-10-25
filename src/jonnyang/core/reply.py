"""화면에 내보낼 응답 한 덩어리. CLI는 text만 쓰고, GUI는 나머지로 표정·말풍선 상태를 정한다."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Reply:
    text: str
    key: str                                  # persona 템플릿 키 (표정 규칙에 씀)
    ok: bool = True
    waiting: bool = False                     # 사용자 대답을 기다림 (확인/되묻기/슬롯)
    choices: list[tuple[str, str]] = field(default_factory=list)   # (버튼 글자, 보낼 말)
    alert: bool = False                       # 타이머 종료 같은 알림. 사용자가 볼 때까지 유지
    running: bool = False                     # 인터넷 응답 기다리는 중. 결과가 오면 바뀐다

    def __str__(self) -> str:
        return self.text
