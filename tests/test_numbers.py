import pytest

from jonnyang.nlu.numbers import normalize_numbers, parse_sino


@pytest.mark.parametrize("text,want", [
    ("삼십 분 뒤", "30분 뒤"),
    ("한 시간 반 뒤", "1시간 반 뒤"),
    ("한시간 뒤", "1시간 뒤"),
    ("3만 2천원 4명이서 나눠", "32000원 4명이서 나눠"),
    ("32,000원", "32000원"),
    ("삼 분 타이머", "3분 타이머"),
    ("열두 시", "12시"),
    ("스물다섯 살", "25살"),
    ("만원", "10000원"),
    ("삼월 사일", "3월 4일"),
    ("시월 3일", "10월 3일"),
    ("10월 이십일", "10월 20일"),
    ("이십분", "20분"),
    ("삼일 뒤", "3일 뒤"),
    ("십일 분", "11분"),
    ("사과 두 개", "사과 2개"),
    ("5천만원", "50000000원"),
    ("2.5만", "25000"),
    ("이천이십육년", "2026년"),
])
def test_converts(text, want):
    assert normalize_numbers(text) == want


@pytest.mark.parametrize("text", [
    "오분",            # 붙여 쓴 한 글자 수사는 "구분"과 헷갈려서 안 바꾼다
    "구분해줘", "육개장 추가", "이번주 화요일", "이달", "열어줘", "천천히", "네 알겠어", "두부",
    "오이 3개", "사이다", "엄마 오시는 날", "일시정지", "엔진 오일 추가", "하나 추가",
])
def test_leaves_words_alone(text):
    assert normalize_numbers(text) == text


@pytest.mark.parametrize("s,want", [("삼십이", 32), ("3만2천", 32000), ("이천이십육", 2026), ("만", 10000),
                                    ("1억2천만", 120_000_000), ("abc", None)])
def test_parse_sino(s, want):
    assert parse_sino(s) == want
