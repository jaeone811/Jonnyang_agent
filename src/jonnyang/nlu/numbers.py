"""한글 수사를 아라비아 숫자로 바꾼다.

"삼십 분" → "30분", "한 시간 반" → "1시간 반", "3만 2천원" → "32000원".
뒤에 단위가 붙은 경우에만 바꾼다. 단위 없는 "이", "한" 같은 글자는 일반 단어일 가능성이
높아서 건드리지 않는다.
"""

from __future__ import annotations

import re

SINO_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
BIG_UNITS = {"만": 10_000, "억": 100_000_000, "조": 1_000_000_000_000}
NUMERAL_CHARS = set(SINO_DIGITS) | set(SMALL_UNITS) | set(BIG_UNITS)

NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50,
               "예순": 60, "일흔": 70, "여든": 80, "아흔": 90}
NATIVE_ONES = {"하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "석": 3, "넷": 4, "네": 4,
               "넉": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}

# 긴 것부터 검사해야 "시간"이 "시"보다 먼저 잡힌다.
SINO_UNITS = sorted(
    ["시간", "개월", "주일", "퍼센트", "프로", "킬로그램", "킬로미터", "킬로", "미터", "센티미터", "센티",
     "밀리리터", "밀리미터", "밀리", "리터", "그램", "제곱미터", "평", "인분", "마리", "초", "분", "시",
     "일", "주", "년", "월", "개", "명", "살", "잔", "병", "장", "권", "원", "배", "층", "도", "%"],
    key=len, reverse=True,
)
# "이번", "이달"을 숫자로 바꾸지 않으려고 한자어 수사 단위에서 "번", "달"은 뺐다.
NATIVE_UNITS = sorted(
    ["시간", "마리", "시", "개", "명", "번", "살", "잔", "병", "장", "권", "달", "주", "분", "초"],
    key=len, reverse=True,
)
# 단위 바로 뒤에 와도 되는 글자(조사, 시간 표현). 그 외 한글이 붙으면 다른 단어로 본다("육개장").
AFTER_UNIT_OK = set("뒤후에이가을를도만씩짜까반동쯤째간부마의으로와과랑하야요엔")

_HANGUL = re.compile(r"[가-힣]")


def _is_hangul(ch: str) -> bool:
    return bool(_HANGUL.match(ch))


def parse_sino(s: str) -> float | None:
    """'삼십이', '3만2천', '이천이십육', '2.5만' 같은 문자열을 숫자로. 실패하면 None."""
    s = s.replace(" ", "")
    if not s:
        return None
    total = 0.0
    section = 0.0
    current: float | None = None
    i = 0
    while i < len(s):
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            if current is not None:
                return None
            current = float(m.group())
            i += len(m.group())
            continue
        ch = s[i]
        if ch in SINO_DIGITS:
            if current is not None:
                return None
            current = SINO_DIGITS[ch]
        elif ch in SMALL_UNITS:
            section += (current if current is not None else 1) * SMALL_UNITS[ch]
            current = None
        elif ch in BIG_UNITS:
            chunk = section + (current or 0)
            total += (chunk if chunk else 1) * BIG_UNITS[ch]
            section, current = 0.0, None
        else:
            return None
        i += 1
    return total + section + (current or 0)


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)


def _unit_at(text: str, pos: int, units: list[str]) -> tuple[str, int] | None:
    """pos에서 (공백 하나 허용 후) 단위가 시작하고 뒤 경계가 맞으면 (단위, 공백포함 길이)."""
    space = 1 if pos < len(text) and text[pos] == " " else 0
    start = pos + space
    for u in units:
        if text.startswith(u, start):
            end = start + len(u)
            if end >= len(text) or not _is_hangul(text[end]) or text[end] in AFTER_UNIT_OK:
                return u, space
    return None


def _collect_sino(text: str, i: int) -> int:
    """i부터 숫자/한자어 수사가 이어지는 끝 위치. '3만 2천'처럼 큰 단위 뒤 공백 + 천/백/십 묶음은 이어 붙인다."""
    j = i
    n = len(text)
    while j < n and (text[j].isdigit() or text[j] == "." or text[j] in NUMERAL_CHARS):
        j += 1
    while j < n - 1 and text[j] == " " and text[j - 1] in BIG_UNITS:
        k = j + 1
        while k < n and (text[k].isdigit() or text[k] in NUMERAL_CHARS):
            k += 1
        seg = text[j + 1:k]
        if seg and any(c in SMALL_UNITS for c in seg):
            j = k
        else:
            break
    return j


def _try_sino(text: str, i: int) -> tuple[int, str] | None:
    end = _collect_sino(text, i)
    for e in range(end, i, -1):
        cand = text[i:e]
        if cand[-1] == " " or not any(c in NUMERAL_CHARS for c in cand):
            continue  # 순수 아라비아 숫자는 그대로 둔다
        hit = _unit_at(text, e, SINO_UNITS)
        if not hit:
            continue
        unit, space = hit
        # 한 글자 수사("삼", "오")는 "구분", "엔진 오일"과 헷갈리니 띄어 쓴 경우만 인정.
        # 예외: "삼월", "삼일 뒤"처럼 뒤에 기간 표현이 오는 경우.
        if len(cand) == 1 and cand in SINO_DIGITS and not space:
            after = text[e + len(unit):].lstrip()
            if not (unit == "월" or (unit == "일" and re.match(r"(뒤|후|동안|간|있다가|지나)", after))):
                continue
        value = parse_sino(cand)
        if value is None:
            continue
        return e + space, _fmt(value)
    # 단위가 없어도 "3만", "2천5백"처럼 아라비아 숫자 + 자릿수 단위면 숫자로 본다 (계산식용).
    cand = text[i:end].rstrip()
    e = i + len(cand)
    if any(c.isdigit() for c in cand) and any(c in SMALL_UNITS or c in BIG_UNITS for c in cand):
        if e >= len(text) or not _is_hangul(text[e]) or text[e] in AFTER_UNIT_OK:
            value = parse_sino(cand)
            if value is not None:
                return e, _fmt(value)
    return None


def _try_native(text: str, i: int) -> tuple[int, str] | None:
    rest = text[i:]
    value = 0
    length = 0
    for word in sorted(NATIVE_TENS, key=len, reverse=True):
        if rest.startswith(word):
            value, length = NATIVE_TENS[word], len(word)
            break
    if value != 20 or not rest.startswith("스무"):  # "스무" 뒤에는 일의 자리가 안 붙는다
        for word in sorted(NATIVE_ONES, key=len, reverse=True):
            if rest.startswith(word, length):
                value += NATIVE_ONES[word]
                length += len(word)
                break
    if not length:
        return None
    hit = _unit_at(text, i + length, NATIVE_UNITS)
    if hit:
        return i + length + hit[1], str(value)
    return None


def normalize_numbers(text: str) -> str:
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)  # 32,000 → 32000
    text = re.sub(r"(?<![가-힣])시월", "10월", text)
    text = re.sub(r"(?<![가-힣])유월", "6월", text)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        left_ok = i == 0 or not (_is_hangul(text[i - 1]) or text[i - 1].isdigit() or text[i - 1] == ".")
        if left_ok:
            if text[i].isdigit() or text[i] in NUMERAL_CHARS:
                hit = _try_sino(text, i)
                if hit:
                    out.append(hit[1])
                    i = hit[0]
                    continue
            hit = _try_native(text, i)
            if hit:
                out.append(hit[1])
                i = hit[0]
                continue
            if text[i].isdigit():  # 순수 숫자는 통째로 넘겨서 중간부터 다시 검사하지 않게
                j = i
                while j < n and (text[j].isdigit() or text[j] == "."):
                    j += 1
                out.append(text[i:j])
                i = j
                continue
        out.append(text[i])
        i += 1
    result = "".join(out)
    # "3월 사일"처럼 월 뒤에 오는 한 글자 날짜
    return re.sub(r"(\d+월\s*)([일이삼사오육칠팔구])일",
                  lambda m: f"{m.group(1)}{SINO_DIGITS[m.group(2)]}일", result)
