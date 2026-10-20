"""의도 점수 계산: 키워드 점수 + 자모 퍼지 보정 + 슬롯/힌트 보너스.

점수 = max(명사 적중) + max(동사 적중) + Σ(추가 적중) + Σ(슬롯 보너스) + 힌트 − Σ(감점), 0~1로 자른다.
가중치는 "평범하게 완전한 명령"이 1.0 근처가 되도록 각 의도에서 정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from rapidfuzz import fuzz, process

from jonnyang.nlu.preprocess import jamo

if TYPE_CHECKING:
    from jonnyang.nlu.pipeline import Request

FUZZY_CUTOFF = 80
EOJEOL_STRICT_CUTOFF = 83
FUZZY_TAGS = ("NNG", "NNP", "SL", "XR")


@dataclass
class Intent:
    name: str
    nouns: dict[str, float] = field(default_factory=dict)
    verbs: dict[str, float] = field(default_factory=dict)
    extras: dict[str, float] = field(default_factory=dict)
    avoid: dict[str, float] = field(default_factory=dict)
    slots: dict[str, float] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    hint: Callable[["Request"], float] | None = None
    skill: str = ""


@dataclass
class Candidate:
    intent: Intent
    score: float


class Matcher:
    def __init__(self, intents: list[Intent], groups: set[str], protected: Callable[[], set[str]] = set):
        self.intents = intents
        self.groups = groups
        self.protected = protected   # 다른 스킬이 아는 진짜 단어(단위, 별칭). 오타로 보고 고치지 않는다.
        vocab = {k for it in intents for k in it.nouns if k not in groups}
        self.vocab = sorted(vocab)
        self.vocab_jamo = [jamo(v) for v in self.vocab]

    def _fuzzy(self, req: "Request") -> dict[str, float]:
        """사전에 없는 명사를 자모 유사도로 사전 단어에 붙인다. {사전단어: 유사도(0~1)}"""
        protected = self.protected()
        known = set(self.vocab) | protected
        out: dict[str, float] = {}
        for m in req.morphs:
            word = m.form.lower() if m.tag == "SL" else m.form
            if not m.tag.startswith(FUZZY_TAGS) or len(word) < 2 or word in known or word in req.excluded:
                continue
            self._fuzzy_one(word, out)
        # 형태소 분석이 오타 단어를 엉뚱하게 쪼갠 경우("배터랴" → 배터/이/랴)를 위해 어절 단위로도 본다.
        for eojeol in req.text.split():
            cands = {eojeol, eojeol[:-1], eojeol[:-2]}
            if not re.fullmatch(r"[가-힣]{2,}", eojeol) or cands & known or eojeol in req.excluded:
                continue
            for cand in cands:
                if len(cand) >= 2 and cand not in known:
                    self._fuzzy_one(cand, out, strict=True)
        return out

    def _fuzzy_one(self, word: str, out: dict[str, float], strict: bool = False) -> None:
        hit = process.extractOne(jamo(word), self.vocab_jamo, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF)
        if not hit:
            return
        target = self.vocab[hit[2]]
        # 어절 단위 비교는 잡음이 많다("버리라" ≈ "배터리"). 첫 음절이 같거나 꽤 비슷할 때만 인정한다.
        if strict and word[0] != target[0] and hit[1] < EOJEOL_STRICT_CUTOFF:
            return
        out[target] = max(out.get(target, 0.0), hit[1] / 100)

    def _hit(self, key: str, req: "Request", fuzzy: dict[str, float] | None) -> float:
        if key in self.groups:
            return 1.0 if key in req.groups else 0.0
        if key in req.lemma_set or (len(key) >= 2 and key.replace(" ", "") in req.compact):
            return 1.0
        if fuzzy is not None:
            return fuzzy.get(key, 0.0)
        return 0.0

    def score(self, intent: Intent, req: "Request", fuzzy: dict[str, float]) -> float:
        n = max((w * self._hit(k, req, fuzzy) for k, w in intent.nouns.items()), default=0.0)
        v = max((w * self._hit(k, req, None) for k, w in intent.verbs.items()), default=0.0)
        e = sum(w * self._hit(k, req, None) for k, w in intent.extras.items())
        s = sum(w for k, w in intent.slots.items() if req.has_slot(k))
        h = intent.hint(req) if intent.hint else 0.0
        p = sum(w * self._hit(k, req, None) for k, w in intent.avoid.items())
        return max(0.0, min(1.0, n + v + e + s + h - p))

    def rank(self, req: "Request") -> list[Candidate]:
        fuzzy = self._fuzzy(req)
        cands = [Candidate(it, round(self.score(it, req, fuzzy), 3)) for it in self.intents]
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands
