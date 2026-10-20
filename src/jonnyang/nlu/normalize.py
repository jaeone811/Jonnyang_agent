"""kiwipiepy 형태소 분석 → 내용어 어근 + 대표형 그룹."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# 의미를 담는 품사만 남긴다. 조사(J*), 어미(E*), 기호(S* 중 SL/SN 제외)는 버린다.
CONTENT_TAGS = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "VX", "XR", "SL", "SH", "MAG", "MM", "IC")
AUX_VERBS = {"주", "보", "있", "드리"}   # "맞춰 줘", "켜 봐"의 보조용언
OPPOSITES = [("UP", "DOWN"), ("OPEN", "CLOSE")]


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

    def groups_for(self, morphs: list["Morph"], text: str) -> set[str]:
        """대표형 그룹. 반대 뜻 그룹(올려/줄여 등)이 같이 나오면 문장에서 나중에 나온 쪽만 남긴다."""
        last: dict[str, int] = {}
        for m in morphs:
            for g in self.lemma_groups.get(m.form, ()):
                last[g] = max(last.get(g, -1), m.start)
        for pat, group in self.surface_groups:
            for hit in pat.finditer(text):
                last[group] = max(last.get(group, -1), hit.start())
        for a, b in OPPOSITES:
            if a in last and b in last:
                del last[a if last[a] < last[b] else b]
        return set(last)


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


def command_morphs(morphs: list[Morph], skip_spans: list[tuple[int, int]] = ()) -> list[Morph]:
    """명령 동사 후보. "방금 맞춘 타이머", "등록된 알림"처럼 관형형(ETM)으로 꾸미는 말은 뺀다."""
    out = []
    for i, m in enumerate(morphs):
        if any(s <= m.start < e for s, e in skip_spans):
            continue
        nxt = morphs[i + 1] if i + 1 < len(morphs) else None
        nxt2 = morphs[i + 2] if i + 2 < len(morphs) else None
        if nxt is not None and nxt.tag == "ETM" and m.tag.startswith(("VV", "VA", "XSV", "XSA")):
            continue
        if nxt is not None and nxt2 is not None and nxt.tag.startswith(("XSV", "XSA")) and nxt2.tag == "ETM":
            continue
        out.append(m)
    return out


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
