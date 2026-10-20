"""kiwipiepy 형태소 분석 → 내용어 어근 + 대표형 그룹."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# 의미를 담는 품사만 남긴다. 조사(J*), 어미(E*), 기호(S* 중 SL/SN 제외)는 버린다.
CONTENT_TAGS = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "VX", "XR", "SL", "SH", "MAG", "MM", "IC")
AUX_VERBS = {"주", "보", "있", "드리"}   # "맞춰 줘", "켜 봐"의 보조용언


@dataclass(frozen=True)
class Morph:
    form: str
    tag: str
    start: int
    end: int


class Lexicon:
    def __init__(self, data: dict):
        self.user_words: list[tuple[str, str]] = [tuple(w) for w in data.get("user_words", [])]
        self.lemma_groups: dict[str, set[str]] = {}
        self.surface_groups: list[tuple[re.Pattern, str]] = []
        self.group_names: set[str] = set((data.get("groups") or {}).keys())
        for group, spec in (data.get("groups") or {}).items():
            for lemma in spec.get("lemmas", []):
                self.lemma_groups.setdefault(lemma, set()).add(group)
            for surf in spec.get("surface", []):
                self.surface_groups.append((re.compile(rf"(?:^|\s){re.escape(surf)}"), group))

    def groups_for(self, lemmas: Iterable[str], text: str) -> set[str]:
        groups: set[str] = set()
        for lemma in lemmas:
            groups |= self.lemma_groups.get(lemma, set())
        for pat, group in self.surface_groups:
            if pat.search(text):
                groups.add(group)
        return groups


class Analyzer:
    """Kiwi 로딩이 몇 초 걸리므로 프로그램 전체에서 하나만 만든다."""

    def __init__(self, lexicon: Lexicon, extra_words: Iterable[str] = ()):
        from kiwipiepy import Kiwi

        self.kiwi = Kiwi()
        self.lexicon = lexicon
        for word, tag in lexicon.user_words:
            self.kiwi.add_user_word(word, tag, 0)
        for word in extra_words:
            self.add_word(word)

    def add_word(self, word: str) -> None:
        if word and " " not in word and re.fullmatch(r"[가-힣]+", word):
            self.kiwi.add_user_word(word, "NNP", 0)

    def tokenize(self, text: str) -> list[Morph]:
        if not text:
            return []
        return [Morph(t.form, t.tag, t.start, t.end) for t in self.kiwi.tokenize(text)]


def content_lemmas(morphs: list[Morph], skip_spans: list[tuple[int, int]] = ()) -> list[str]:
    out = []
    for m in morphs:
        if not m.tag.startswith(CONTENT_TAGS):
            continue
        if m.tag.startswith("VX") and m.form in AUX_VERBS | {"말"}:
            continue
        if any(s <= m.start < e for s, e in skip_spans):
            continue
        out.append(m.form.lower() if m.tag == "SL" else m.form)
    return out
