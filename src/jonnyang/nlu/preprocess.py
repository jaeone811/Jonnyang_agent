"""형태소 분석 전 전처리: 유니코드 정규화, 호출어 제거, 숫자 정규화."""

from __future__ import annotations

import re
import unicodedata

from jonnyang.nlu.numbers import normalize_numbers

WAKE_RE = re.compile(r"^\s*(?:야\s*)?존냥(?:아|이|님|이야)?(?![가-힣])[\s,!~.]*")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_wake(text: str) -> tuple[str, bool]:
    m = WAKE_RE.match(text)
    if not m:
        return text, False
    return text[m.end():].strip(), True


def preprocess(raw: str) -> tuple[str, bool]:
    """(정규화된 문장, 호출어가 있었는지)"""
    text, woke = strip_wake(clean(raw))
    text = re.sub(r"[?!.~]+$", "", text).strip()
    return normalize_numbers(text), woke


def jamo(s: str) -> str:
    """한글 음절을 자모로 분해. '볼룸'과 '볼륨'처럼 글자 하나 다른 오타의 유사도를 높인다."""
    return unicodedata.normalize("NFD", s)
