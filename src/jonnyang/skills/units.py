"""단위 변환. 계수는 국제 정의값(인치 0.0254m, 파운드 0.45359237kg, 미국 갤런 3.785411784L, 1평 400/121㎡)."""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Result, Skill

# (표시 이름, 분류, 기준 단위로의 계수). 온도는 따로 처리.
UNITS: dict[str, tuple[str, str, Fraction]] = {}


def _add(names: list[str], display: str, cat: str, factor) -> None:
    for n in names:
        UNITS[n.lower()] = (display, cat, Fraction(factor))


# 길이 (기준: m)
_add(["mm", "밀리미터", "밀리"], "mm", "length", "0.001")
_add(["cm", "센티미터", "센티", "센치"], "cm", "length", "0.01")
_add(["m", "미터"], "m", "length", 1)
_add(["km", "킬로미터"], "km", "length", 1000)
_add(["in", "inch", "인치"], "인치", "length", "0.0254")
_add(["ft", "피트"], "피트", "length", "0.3048")
_add(["yd", "야드"], "야드", "length", "0.9144")
_add(["mi", "mile", "마일"], "마일", "length", "1609.344")
# 무게 (기준: g)
_add(["mg", "밀리그램"], "mg", "mass", "0.001")
_add(["g", "그램"], "g", "mass", 1)
_add(["kg", "킬로그램"], "kg", "mass", 1000)
_add(["t", "톤"], "톤", "mass", 1_000_000)
_add(["oz", "온스"], "온스", "mass", "28.349523125")
_add(["lb", "lbs", "파운드"], "파운드", "mass", "453.59237")
_add(["근"], "근", "mass", 600)
# 부피 (기준: L)
_add(["ml", "밀리리터"], "mL", "volume", "0.001")
_add(["l", "리터"], "L", "volume", 1)
_add(["gal", "갤런"], "갤런", "volume", "3.785411784")
# 넓이 (기준: ㎡)
_add(["㎡", "m2", "m²", "제곱미터", "평방미터"], "㎡", "area", 1)
_add(["평"], "평", "area", Fraction(400, 121))
_add(["㎢", "km2", "제곱킬로미터"], "㎢", "area", 1_000_000)
_add(["ha", "헥타르"], "ha", "area", 10_000)

TEMPS = {"섭씨": "C", "°c": "C", "℃": "C", "화씨": "F", "°f": "F", "℉": "F", "켈빈": "K"}
TEMP_DISPLAY = {"C": "°C", "F": "°F", "K": "K"}
AMBIGUOUS = {"킬로": ("km", "kg")}   # 상대 단위의 분류로 결정

_ALL = sorted(list(UNITS) + list(TEMPS) + list(AMBIGUOUS), key=len, reverse=True)
_UNIT_RE = "|".join(re.escape(u) for u in _ALL)
PAIR = re.compile(rf"(-?\d+(?:\.\d+)?)\s*({_UNIT_RE})(?:\s*도)?.*?(?:몇\s*)?({_UNIT_RE})", re.IGNORECASE)
TEMP_PREFIX = re.compile(r"(섭씨|화씨|켈빈)\s*(-?\d+(?:\.\d+)?)\s*도?.*?(섭씨|화씨|켈빈)")


def _resolve(a: str, b: str) -> tuple[str, str] | None:
    a, b = a.lower(), b.lower()
    if a in AMBIGUOUS and b in AMBIGUOUS:
        return None
    if a in AMBIGUOUS:
        cat = UNITS.get(b, (None, None))[1]
        a = next((x for x in AMBIGUOUS[a] if UNITS[x][1] == cat), None)
    if b in AMBIGUOUS:
        cat = UNITS.get(a, (None, None))[1]
        b = next((x for x in AMBIGUOUS[b] if UNITS[x][1] == cat), None)
    return (a, b) if a and b else None


def _temp(v: Fraction, src: str, dst: str) -> Fraction:
    c = v if src == "C" else (v - 32) * Fraction(5, 9) if src == "F" else v - Fraction("273.15")
    return c if dst == "C" else c * Fraction(9, 5) + 32 if dst == "F" else c + Fraction("273.15")


def parse(text: str) -> tuple[Fraction, str, str] | None:
    m = TEMP_PREFIX.search(text)
    if m:
        return Fraction(m.group(2)), m.group(1), m.group(3)
    m = PAIR.search(text)
    if not m:
        return None
    return Fraction(m.group(1)), m.group(2), m.group(3)


def convert(value: Fraction, src: str, dst: str) -> tuple[Fraction, str, str] | None:
    s, d = src.lower(), dst.lower()
    if s in TEMPS or d in TEMPS:
        if s in TEMPS and d in TEMPS and TEMPS[s] != TEMPS[d]:
            return _temp(value, TEMPS[s], TEMPS[d]), TEMP_DISPLAY[TEMPS[s]], TEMP_DISPLAY[TEMPS[d]]
        return None
    pair = _resolve(s, d)
    if not pair:
        return None
    s, d = pair
    (sd, sc, sf), (dd, dc, df) = UNITS[s], UNITS[d]
    if sc != dc or s == d:
        return None
    return value * sf / df, sd, dd


def _round(v: Fraction) -> int | float:
    f = round(float(v), 4)
    return int(f) if f == int(f) else f


class UnitSkill(Skill):
    name = "units"
    intents = [
        Intent("units.convert", nouns={"변환": 0.4, "환산": 0.4, "단위": 0.3},
               hint=lambda req: 1.0 if (p := parse(req.text)) and convert(*p) else 0.0,
               examples=("5평은 몇 제곱미터야", "10마일을 킬로미터로", "화씨 100도는 섭씨로")),
    ]

    def protected_words(self) -> set[str]:
        return set(UNITS) | set(TEMPS) | set(AMBIGUOUS)

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        p = parse(req.text)
        out = convert(*p) if p else None
        if not out:
            return Result("units.error", {"text": req.text}, ok=False)
        value, src, dst = out
        return Result("units.result", {"value": _round(p[0]), "src": src, "result": _round(value), "dst": dst},
                      core=("value", "result", "dst"))
