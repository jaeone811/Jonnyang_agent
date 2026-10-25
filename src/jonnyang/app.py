"""구성 요소 조립."""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from typing import Callable

from jonnyang.core.config import config_dir as default_config_dir
from jonnyang.core.config import data_dir as default_data_dir
from jonnyang.core.config import load_yaml
from jonnyang.core.context import AppContext
from jonnyang.core.dispatcher import Dispatcher
from jonnyang.core.network import Network
from jonnyang.core.storage import Storage
from jonnyang.nlu.normalize import Analyzer, Lexicon
from jonnyang.platform.base import Platform
from jonnyang.skills.calc import CalcSkill
from jonnyang.skills.files import FileSkill
from jonnyang.skills.lists import ListSkill
from jonnyang.skills.meta import MetaSkill
from jonnyang.skills.online.currency import CurrencySkill
from jonnyang.skills.online.news import NewsSkill
from jonnyang.skills.online.weather import WeatherSkill
from jonnyang.skills.online.wiki import WikiSkill
from jonnyang.skills.reminder import AlarmSkill, ReminderSkill
from jonnyang.skills.system import AppSkill, SysInfoSkill, VolumeSkill
from jonnyang.skills.timer import TimerSkill
from jonnyang.skills.units import UnitSkill

SKILLS = [TimerSkill, AlarmSkill, ReminderSkill, ListSkill, CalcSkill, UnitSkill, VolumeSkill, AppSkill,
          SysInfoSkill, FileSkill, WeatherSkill, CurrencySkill, WikiSkill, NewsSkill, MetaSkill]


def make_analyzer(config_dir: Path | None = None) -> Analyzer:
    return Analyzer(Lexicon(load_yaml("lexicon.yaml", config_dir or default_config_dir())))


def build_app(*, platform: Platform, analyzer: Analyzer | None = None, config_dir: Path | None = None,
              data_dir: Path | None = None, storage: Storage | None = None,
              clock: Callable[[], datetime] = datetime.now, sink: Callable[[list[str]], None] | None = None,
              rng: random.Random | None = None, beep_gap: float = 0.3,
              network: Network | None = None) -> tuple[AppContext, Dispatcher]:
    config_dir = config_dir or default_config_dir()
    analyzer = analyzer or make_analyzer(config_dir)
    storage = storage or Storage((data_dir or default_data_dir()) / "jonnyang.db")
    ctx = AppContext(storage=storage, platform=platform, analyzer=analyzer, clock=clock, config_dir=config_dir,
                     sink=sink, rng=rng, beep_gap=beep_gap, network=network)
    dispatcher = Dispatcher(ctx, [cls(ctx) for cls in SKILLS])
    return ctx, dispatcher
