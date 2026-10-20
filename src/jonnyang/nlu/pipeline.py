"""문장 하나를 스킬이 쓰기 좋은 Request로 만든다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from jonnyang.nlu import negation, timeparse
from jonnyang.nlu.normalize import Analyzer, Morph, content_lemmas
from jonnyang.nlu.preprocess import preprocess

QUOTE_RE = re.compile(r"[\"'“”‘’「『]([^\"'“”‘’」』]+)[\"'“”‘’」』]")


@dataclass
class Request:
    raw: str
    text: str                 # 정규화된 문장 (호출어 제거, 숫자는 아라비아 숫자)
    woke: bool
    now: datetime
    morphs: list[Morph] = field(default_factory=list)
    lemmas: list[str] = field(default_factory=list)
    groups: set[str] = field(default_factory=set)
    compact: str = ""         # 제외/시간 구간을 지우고 공백을 뺀 문장 (명사 부분 일치용)
    time: timeparse.TimeResult = field(default_factory=timeparse.TimeResult)
    negated: bool = False
    excluded: set[str] = field(default_factory=set)
    numbers: list[float] = field(default_factory=list)
    quoted: list[str] = field(default_factory=list)

    @property
    def lemma_set(self) -> set[str]:
        return set(self.lemmas)

    def has_slot(self, name: str) -> bool:
        if name == "duration":
            if self.time.error and self.time.error != "vague":
                return True   # 시간 표현은 있는데 문제가 있음 → 해당 의도로 가서 오류를 알려준다
            return self.time.duration is not None and not self.time.relative
        if name == "at":
            return self.time.at is not None or self.time.error is not None
        if name == "number":
            return bool(self.numbers)
        if name == "quoted":
            return bool(self.quoted)
        return False


class NLU:
    def __init__(self, analyzer: Analyzer, default_hour: int = 9):
        self.analyzer = analyzer
        self.default_hour = default_hour

    def parse(self, raw: str, now: datetime) -> Request:
        text, woke = preprocess(raw)
        req = Request(raw=raw, text=text, woke=woke, now=now)
        req.time = timeparse.parse(text, now, self.default_hour)
        req.morphs = self.analyzer.tokenize(text)
        pol = negation.detect(req.morphs)
        req.negated = pol.negated
        req.excluded = pol.excluded
        skip = pol.excluded_spans + req.time.spans
        req.lemmas = content_lemmas(req.morphs, skip)
        masked = list(text)
        for s, e in skip:
            for i in range(s, min(e, len(masked))):
                masked[i] = " "
        masked_text = "".join(masked)
        req.compact = re.sub(r"\s+", "", masked_text).lower()
        group_lemmas = content_lemmas(req.morphs, pol.excluded_spans)
        req.groups = self.analyzer.lexicon.groups_for(group_lemmas, " ".join(masked_text.split()))
        req.numbers = [float(x) for x in re.findall(r"(?<![\d.])\d+(?:\.\d+)?", text)]
        req.quoted = [q.strip() for q in QUOTE_RE.findall(raw) if q.strip()]
        return req
