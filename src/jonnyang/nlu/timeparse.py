"""한국어 시간 표현 파서.

입력은 `normalize_numbers`를 거친 문장(숫자가 아라비아 숫자)이다. `now`를 받아서 순수 함수로 동작한다.
지원 범위와 해석 규칙은 docs/PLAN.md 3장 참고.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
DAY_WORDS = [("내일\\s*모레", 2), ("오늘", 0), ("금일", 0), ("내일", 1), ("낼(?![가-힣])", 1), ("명일", 1),
             ("모레", 2), ("글피", 3)]
# "낮춰", "밤새" 같은 단어 안의 글자를 시간대로 오인하지 않게 뒤에 올 수 있는 것을 제한한다.
WORD_END = r"(?=$|[^가-힣]|에|쯤|부터|까지|엔|중|이나)"
DAY_COUNT_WORDS = {"하루": 1, "이틀": 2, "사흘": 3, "나흘": 4, "닷새": 5, "엿새": 6, "이레": 7, "열흘": 10}
PERIOD_DEFAULT_HOUR = {"새벽": 6, "아침": 8, "오전": 9, "점심": 12, "낮": 13, "오후": 15, "저녁": 19, "밤": 21}
RELATIVE_MARK = r"\s*(?:뒤|후|있다가|이따가?|지나서|지나고)"

ERR_PAST_TODAY = "past_today"
ERR_PAST_DATE = "past_date"
ERR_MULTIPLE = "multiple"
ERR_VAGUE = "vague"
ERR_RECURRING = "recurring"
ERR_INVALID = "invalid"


@dataclass
class TimeResult:
    duration: timedelta | None = None   # "3분", "1시간 반" 같은 기간
    relative: bool = False              # 기간 뒤에 "뒤/후"가 붙었는지
    at: datetime | None = None          # 최종 절대 시각 (상대 표현도 여기로 환산)
    spans: list[tuple[int, int]] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)  # persona가 되읽어 줄 가정들
    error: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.spans) or self.error is not None


def add_months(d: datetime, months: int) -> datetime:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


class _Scanner:
    """패턴을 찾으면 그 구간을 공백으로 지워서 다른 패턴이 같은 글자를 다시 먹지 않게 한다."""

    def __init__(self, text: str):
        self.buf = list(text)
        self.spans: list[tuple[int, int]] = []

    @property
    def text(self) -> str:
        return "".join(self.buf)

    def take(self, pattern: str, flags: int = 0) -> list[re.Match]:
        found = list(re.finditer(pattern, self.text, flags))
        for m in found:
            self.mask(m.start(), m.end())
        return found

    def mask(self, start: int, end: int) -> None:
        for i in range(start, end):
            self.buf[i] = " "
        self.spans.append((start, end))


def _duration_from(match_text: str) -> tuple[timedelta, int]:
    """기간 문자열 → (timedelta, 개월 수). 개월은 달력 계산이 필요해서 따로 돌려준다."""
    td = timedelta()
    months = 0
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(시간|분|초|주일|주|일|개월|달)(\s*반)?", match_text):
        n = float(m.group(1))
        unit = m.group(2)
        half = bool(m.group(3))
        if unit == "시간":
            td += timedelta(hours=n + (0.5 if half else 0))
        elif unit == "분":
            td += timedelta(minutes=n + (0.5 if half else 0))
        elif unit == "초":
            td += timedelta(seconds=n)
        elif unit in ("주", "주일"):
            td += timedelta(weeks=n)
        elif unit == "일":
            td += timedelta(days=n)
        else:
            months += int(n)
    for word, days in DAY_COUNT_WORDS.items():
        if word in match_text:
            td += timedelta(days=days)
    if re.search(r"일주일", match_text):
        td += timedelta(weeks=1)
    if re.search(r"(?<!\d\s)(?<!\d)반\s*시간", match_text):
        td += timedelta(minutes=30)
    return td, months


def parse(text: str, now: datetime, default_hour: int = 9) -> TimeResult:
    sc = _Scanner(text)
    res = TimeResult()

    if re.search(r"매일|매주|매달|매월|마다|평일에는|주말마다", text):
        res.error = ERR_RECURRING
        return res

    # 1) 시각: "3시 15분", "3시 반", "15:30", 정오/자정. 기간의 "15분"과 헷갈리지 않게 먼저 지운다.
    clocks = sc.take(r"(?<!\d)(\d{1,2})\s*시(?!간)(?:\s*(\d{1,2})\s*분|\s*(반))?|(?<!\d)(\d{1,2}):(\d{2})")
    specials = sc.take(r"정오|자정")

    # 2) 기간 + "뒤/후"
    unit = r"\d+(?:\.\d+)?\s*(?:시간|분|초)(?:\s*반)?"
    long_unit = r"\d+(?:\.\d+)?\s*(?:주일|주|일|개월|달)"
    count_word = "|".join(DAY_COUNT_WORDS) + r"|일주일|반\s*시간"
    rel = sc.take(rf"(?:(?:{unit}|{long_unit}|{count_word})\s*)+{RELATIVE_MARK}")
    plain = sc.take(rf"(?:(?:{unit}|반\s*시간)\s*)+")

    # 3) 날짜
    day_words: list[int] = []
    for pat, off in DAY_WORDS:
        for _ in sc.take(pat):
            day_words.append(off)
    week_days = sc.take(r"(이번\s*주|금주|다음\s*주|담주|차주|다다음\s*주)?\s*([월화수목금토일])요일")
    weekends = sc.take(r"(이번\s*주|다음\s*주|담주)?\s*주말")
    full_dates = sc.take(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")
    month_rel = sc.take(r"(이번\s*달|다음\s*달|담달)\s*(\d{1,2})\s*일")
    day_only = sc.take(r"(?<!\d)(\d{1,2})\s*일(?!\s*(?:뒤|후|동안|간|있다가))")

    # 4) 하루 중 구간
    periods = sc.take(rf"(?:오전|오후|새벽|아침|점심|저녁|밤|낮){WORD_END}")

    res.spans = sorted(sc.spans)

    # ── 기간 ──
    if rel or plain:
        if len(rel) + len(plain) > 1:
            res.error = ERR_MULTIPLE
            return res
        m = (rel or plain)[0]
        td, months = _duration_from(m.group())
        if rel:
            res.relative = True
            base = add_months(now, months) if months else now
            res.duration = td if not months else None
            res.at = (base + td).replace(microsecond=0)
        else:
            res.duration = td
        if clocks or specials or day_words or week_days or full_dates or month_rel or day_only:
            res.error = ERR_MULTIPLE
        return res

    has_date = bool(day_words or week_days or weekends or full_dates or month_rel or day_only)
    if not (clocks or specials or has_date or periods):
        if re.search(r"이따가?|조만간|나중에|언젠가|좀\s*있다가|잠시\s*후", text):
            res.error = ERR_VAGUE
        return res

    if len(clocks) + len(specials) > 1 or len(day_words) + len(week_days) + len(weekends) + len(full_dates) \
            + len(month_rel) + len(day_only) > 1 or len(periods) > 1:
        res.error = ERR_MULTIPLE
        return res

    # ── 날짜 결정 ──
    today = now.date()
    target: date | None = None
    explicit_today = False
    strict_past = False   # 지났으면 넘기지 말고 에러
    weekday_floating = False
    weekend_floating: date | None = None   # "주말"이 지났을 때 넘어갈 다음 토요일
    try:
        if day_words:
            target = today + timedelta(days=day_words[0])
            explicit_today = day_words[0] == 0
        elif week_days:
            m = week_days[0]
            wd = WEEKDAYS[m.group(2)]
            prefix = re.sub(r"\s", "", m.group(1) or "")
            monday = today - timedelta(days=today.weekday())
            if prefix in ("이번주", "금주"):
                target = monday + timedelta(days=wd)
                strict_past = True
            elif prefix in ("다음주", "담주", "차주"):
                target = monday + timedelta(days=7 + wd)
            elif prefix == "다다음주":
                target = monday + timedelta(days=14 + wd)
            else:
                target = today + timedelta(days=(wd - today.weekday()) % 7)
                weekday_floating = True
        elif weekends:
            prefix = re.sub(r"\s", "", weekends[0].group(1) or "")
            monday = today - timedelta(days=today.weekday())
            sat = monday + timedelta(days=5 + (7 if prefix in ("다음주", "담주") else 0))
            target = today if today.weekday() == 6 and not prefix else sat
            if target < today:
                target = sat + timedelta(days=7)
            if not prefix:
                weekend_floating = sat + timedelta(days=7) if today.weekday() >= 5 else sat
        elif full_dates:
            m = full_dates[0]
            year = int(m.group(1)) if m.group(1) else today.year
            target = date(year, int(m.group(2)), int(m.group(3)))
            if not m.group(1) and target < today:
                target = date(year + 1, target.month, target.day)
                res.assumed.append("next_year")
            elif m.group(1):
                strict_past = True
        elif month_rel:
            m = month_rel[0]
            base = today.replace(day=1)
            if re.sub(r"\s", "", m.group(1)) != "이번달":
                base = add_months(datetime.combine(base, time()), 1).date()
            target = base.replace(day=int(m.group(2)))
            strict_past = True
        elif day_only:
            d = int(day_only[0].group(1))
            target = today.replace(day=d) if d >= today.day else None
            if target is None:
                nxt = add_months(datetime.combine(today.replace(day=1), time()), 1).date()
                target = nxt.replace(day=d)
                res.assumed.append("next_month")
    except ValueError:
        res.error = ERR_INVALID
        return res

    # ── 시각 결정 ──
    period = periods[0].group() if periods else None
    hour: int | None = None
    minute = 0
    next_day_shift = 0
    if specials:
        if specials[0].group() == "정오":
            hour = 12
        else:
            hour, next_day_shift = 0, 1
    elif clocks:
        m = clocks[0]
        if m.group(4):
            hour, minute = int(m.group(4)), int(m.group(5))
        else:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else (30 if m.group(3) else 0)
        if hour > 24 or minute > 59:
            res.error = ERR_INVALID
            return res
        if hour == 24:
            hour, next_day_shift = 0, 1
        elif period in ("오전", "새벽", "아침"):
            if hour == 12:
                hour = 0
        elif period in ("오후", "저녁", "점심", "낮"):
            if hour < 12:
                hour += 12
        elif period == "밤":
            if hour == 12:
                hour, next_day_shift = 0, 1
            elif 1 <= hour <= 5:
                next_day_shift = 1      # "밤 1시" = 다음날 새벽 1시
            elif hour < 12:
                hour += 12
        elif 1 <= hour <= 12 and target is not None:
            # 날짜는 있는데 오전/오후가 없음: 1~6시는 오후, 7~11시는 오전으로 추정
            if hour <= 6:
                hour += 12
                res.assumed.append("pm")
            elif hour < 12:
                res.assumed.append("am")
    elif period:
        hour = PERIOD_DEFAULT_HOUR[period]
        res.assumed.append("period_default")
    else:
        hour = default_hour
        res.assumed.append("default_time")

    tod = time(hour % 24, minute)

    if target is None:
        # 날짜 없이 시각만: 오전/오후 미지정이면 가장 가까운 미래
        candidates = [datetime.combine(today, tod) + timedelta(days=next_day_shift)]
        if clocks and not period and 1 <= hour <= 11:
            candidates.append(datetime.combine(today, time(hour + 12, minute)))
            res.assumed.append("nearest")
        elif clocks and not period and hour == 12:
            candidates.append(datetime.combine(today + timedelta(days=1), time(0, minute)))
            res.assumed.append("nearest")
        future = [c for c in candidates if c > now]
        if future:
            res.at = min(future)
        else:
            res.at = min(candidates) + timedelta(days=1)
            res.assumed.append("rolled_tomorrow")
        return res

    at = datetime.combine(target, tod) + timedelta(days=next_day_shift)
    if at <= now:
        if weekday_floating:
            at += timedelta(days=7)
        elif weekend_floating is not None:
            at = datetime.combine(weekend_floating, tod) + timedelta(days=next_day_shift)
        elif explicit_today:
            res.error = ERR_PAST_TODAY
        else:
            res.error = ERR_PAST_DATE
    if strict_past and target < today:
        res.error = ERR_PAST_DATE
    res.at = at
    return res
