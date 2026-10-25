"""온라인 스킬 공통 부분: 설정 읽기, 네트워크 실패 → 안내 결과."""

from __future__ import annotations

from typing import Any

from jonnyang.core.network import NetworkError
from jonnyang.skills.base import Result, Skill


class OnlineSkill(Skill):
    requires_network = True
    section = ""          # online.yaml 안의 설정 이름
    service = ""          # 실패 안내에 들어갈 서비스 이름 (persona labels: service.*)

    @property
    def cfg(self) -> dict[str, Any]:
        return self.ctx.online.get(self.section) or {}

    def ttl(self, default_min: float) -> float:
        return float(self.cfg.get("cache_min", default_min)) * 60

    def fail(self, exc: NetworkError) -> Result:
        """인터넷 문제는 이 기능만 못 한다고 알린다. 원인 종류는 핵심 정보라 그대로 보여준다."""
        service = self.ctx.persona.label(f"service.{self.service}")
        return Result(f"online.{exc.kind}", {"service": service, "detail": exc.detail}, core=("service",),
                      ok=False)

    def loading_key(self, intent: str) -> str:
        return "online.loading"
