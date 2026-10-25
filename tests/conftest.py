import random
from datetime import datetime

import pytest

from jonnyang.app import build_app, make_analyzer
from jonnyang.core.network import FakeNetwork
from jonnyang.core.storage import Storage
from jonnyang.platform.fake import fake_platform

# 데이터셋 공통 기준 시각: 2026-10-20(화) 14:00
NOW = datetime(2026, 10, 20, 14, 0)


@pytest.fixture(scope="session")
def analyzer():
    return make_analyzer()


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class App:
    def __init__(self, analyzer, storage=None, now=NOW, files_root=None, routes=None):
        self.clock = Clock(now)
        self.notes: list[str] = []
        self.platform = fake_platform(files_root)
        self.net = FakeNetwork(routes or {})        # 실제 인터넷은 안 쓴다. 경로가 없으면 '오프라인'
        self.ctx, self.d = build_app(platform=self.platform, analyzer=analyzer,
                                     storage=storage or Storage(":memory:"), clock=self.clock,
                                     sink=self.notes.extend, rng=random.Random(0), beep_gap=0, network=self.net)

    def say(self, text: str) -> str:
        return "\n".join(self.d.handle(text))

    def tick(self, **delta) -> list[str]:
        from datetime import timedelta
        self.clock.now += timedelta(**delta)
        self.ctx.scheduler.run_pending()
        out, self.notes[:] = list(self.notes), []
        return out


@pytest.fixture
def app(analyzer):
    return App(analyzer)


@pytest.fixture
def make_app(analyzer):
    def factory(**kw):
        return App(analyzer, **kw)
    return factory
