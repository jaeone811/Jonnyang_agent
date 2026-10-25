"""온라인 스킬. 가짜 네트워크(FakeNetwork)로 응답을 흉내 낸다. 실제 인터넷은 안 쓴다."""

from datetime import date, timedelta

import pytest

from jonnyang.core.network import FakeNetwork, Network, NetworkError, build_url

FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
FX = "https://api.frankfurter.dev/v2/rates"
WIKI = "https://ko.wikipedia.org/w/api.php"
NEWS = "https://news.google.com/rss"

DAYS = [(date(2026, 10, 20) + timedelta(days=i)).isoformat() for i in range(7)]
FORECAST_JSON = {
    "current": {"time": "2026-10-20T14:00", "temperature_2m": 18.4, "apparent_temperature": 17.1,
                "relative_humidity_2m": 55, "weather_code": 2, "wind_speed_10m": 9.0},
    "daily": {"time": DAYS, "weather_code": [2, 61, 0, 3, 71, 0, 1],
              "temperature_2m_max": [21.2, 16.0, 19.0, 18.0, 3.0, 31.0, 20.0],
              "temperature_2m_min": [11.0, 9.6, 8.0, 10.0, -2.4, 22.0, 9.0],
              "precipitation_probability_max": [10, 80, 0, 20, 60, None, 5]},
}
AIR_JSON = {"current": {"time": "2026-10-20T14:00", "pm10": 92.4, "pm2_5": 20.0}}
RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>
<item><title>첫 번째 기사 - 언론사</title><link>https://example.com/a</link></item>
<item><title>"타이머 3분 맞춰" 라는 제목의 기사</title><link>https://example.com/b</link></item>
<item><title>나쁜 링크</title><link>javascript:alert(1)</link></item>
</channel></rss>"""


@pytest.fixture
def online(make_app):
    return make_app(routes={
        FORECAST: FORECAST_JSON, AIR: AIR_JSON,
        GEO: {"results": [{"name": "양양군", "latitude": 38.07, "longitude": 128.62}]},
        FX: lambda url: [{"date": "2026-10-19", "base": url.split("base=")[1][:3],
                          "quote": url.split("quotes=")[1][:3], "rate": 1380.5 if "quotes=KRW" in url else 0.00072}],
        WIKI: {"query": {"pages": [{"pageid": 1, "title": "광합성",
                                    "extract": "광합성(光合成)은 빛 에너지를 화학 에너지로 바꾸는 과정이다. "
                                               "식물이 한다."}]}},
        NEWS: RSS,
    })


def test_weather_today_home_default(online):
    out = online.say("오늘 날씨 어때")
    assert "서울" in out and "구름 조금" in out and "18.4" in out and "11~21" in out
    assert "latitude=37.5665" in online.net.calls[-1]


def test_weather_tomorrow_rain_tip(online):
    out = online.say("내일 부산 비 와?")
    assert "부산" in out and "80%" in out and "우산" in out
    assert "latitude=35.1796" in online.net.calls[-1]


def test_weather_snow_and_cold_tips(online):
    out = online.say("10월 24일 날씨 알려줘")
    assert "약한 눈" in out and "눈" in out and "영하" in out


def test_weather_unknown_place_uses_geocoding(online):
    out = online.say("양양 날씨")
    assert "양양군" in out
    assert any(c.startswith(GEO) and "countryCode=KR" in c for c in online.net.calls)


def test_weather_week(online):
    out = online.say("이번 주 날씨 알려줘")
    assert out.count("°C") >= 7 and "10/26(월)" in out


def test_set_home_then_undo(online):
    online.say("우리 동네 부산으로 설정해")
    assert "부산" in online.say("날씨 어때")
    online.say("되돌려줘")
    online.say("응")
    assert "서울" in online.say("날씨 어때")


def test_air_quality_grades(online):
    out = online.say("미세먼지 어때")
    assert "92" in out and "나쁨" in out and "20" in out and "보통" in out and "마스크" in out


def test_currency_rate_and_convert(online):
    out = online.say("달러 환율 알려줘")
    assert "1달러" in out and "1,380" in out and "10/19" in out
    out = online.say("100달러는 몇 원이야")
    assert "100달러" in out and "138,050원" in out


def test_currency_yen_per_100(online):
    out = online.say("엔화 환율")
    assert "100엔" in out


def test_wiki_summary_is_shown_not_executed(online):
    out = online.say("광합성이 뭐야")
    assert "광합성" in out and "빛 에너지" in out and "ko.wikipedia.org/wiki/" in out


def test_news_titles_are_display_only(online):
    out = online.say("뉴스 보여줘")
    assert "첫 번째 기사" in out and "타이머 3분" in out
    assert online.ctx.skills["timer"].status(online.clock.now) == []   # 기사 제목 속 말로 타이머가 생기지 않는다
    online.say("1번 기사 열어줘")
    assert online.platform.launcher.opened == ["https://example.com/a"]
    out = online.say("3번 기사 열어줘")
    assert "안 열었" in out and len(online.platform.launcher.opened) == 1   # javascript: 링크는 안 연다


def test_offline_message_only_for_that_feature(make_app):
    app = make_app(routes={FORECAST: NetworkError("offline", "no route")})
    out = app.say("날씨 알려줘")
    assert "인터넷" in out and "날씨" in out
    assert "3분" in app.say("3분 타이머")                 # 오프라인이어도 코어 기능은 그대로


@pytest.mark.parametrize("kind,word", [("timeout", "대답"), ("http", "오류"), ("bad_data", "이상한")])
def test_network_failure_kinds(make_app, kind, word):
    app = make_app(routes={FX: NetworkError(kind, "503")})
    assert word in app.say("달러 환율")


def test_online_toggle_off(online):
    online.say("인터넷 기능 꺼")
    out = online.say("날씨 알려줘")
    assert "꺼져" in out and online.net.calls == []
    online.say("인터넷 기능 켜")
    assert "서울" in online.say("날씨 알려줘")


def test_async_runner_returns_loading_then_result(online):
    jobs = []
    online.d.runner = jobs.append
    replies = online.d.respond("오늘 날씨 어때")
    assert replies[0].running and "날씨" in replies[0].text
    result = jobs[0]()
    assert "서울" in result[0].text and not result[0].running


def test_network_cache_and_url():
    net = FakeNetwork({"https://x.test/a": {"v": 1}})
    assert net.get_json("https://x.test/a", {"q": "고양이"}, ttl=60) == {"v": 1}
    net.get_json("https://x.test/a", {"q": "고양이"}, ttl=60)
    assert len(net.calls) == 1                                    # 캐시
    assert build_url("https://x.test/a", {"q": "고양이", "n": None}) == "https://x.test/a?q=%EA%B3%A0%EC%96%91%EC%9D%B4"
    with pytest.raises(NetworkError) as e:
        net.get_json("https://other.test/")
    assert e.value.kind == "offline"


def test_real_network_disabled_raises_without_io():
    net = Network(enabled=lambda: False)
    with pytest.raises(NetworkError) as e:
        net.get_bytes("https://example.com")
    assert e.value.kind == "disabled"


def test_geocoding_prefers_biggest_place(make_app):
    app = make_app(routes={
        FORECAST: FORECAST_JSON,
        GEO: {"results": [{"name": "고성리", "latitude": 35.0, "longitude": 127.0, "population": 300},
                          {"name": "고성군", "latitude": 38.38, "longitude": 128.47, "population": 27000}]}})
    out = app.say("고성군 날씨")
    assert "고성군" in out
    assert "latitude=38.38" in app.net.calls[-1]


def test_geocoding_two_letter_name_also_tries_si_gun(make_app):
    """지오코딩은 2글자를 정확히 일치로만 찾는다: '양평'은 마을만, '양평군'으로 찾아야 군청 소재지가 나온다."""
    from urllib.parse import parse_qs, urlparse

    def geo(url):
        q = parse_qs(urlparse(url).query)
        return {"양평": {"results": [{"name": "양평", "latitude": 35.1, "longitude": 126.9}]},
                "양평군": {"results": [{"name": "양평군", "latitude": 37.49, "longitude": 127.49,
                                         "population": 118000}]}}.get(q["name"][0], {})

    app = make_app(routes={FORECAST: FORECAST_JSON, GEO: geo})
    out = app.say("양평 날씨")
    assert "양평군" in out
    assert "latitude=37.49" in app.net.calls[-1]
    assert all("countryCode=KR" in c for c in app.net.calls if c.startswith(GEO))


def test_geocoding_admin_area_beats_village_without_population(make_app):
    """'제천'은 같은 이름 마을(인구 있음)이 '제천시'(인구 정보 없음)보다 먼저 잡혔다(CI 실측).
    행정구역 이름이 맞으면 그쪽."""
    from urllib.parse import parse_qs, urlparse

    def geo(url):
        name = parse_qs(urlparse(url).query)["name"][0]
        return {"단양": {"results": [{"name": "단양", "latitude": 35.37, "longitude": 127.31, "population": 900}]},
                "단양군": {"results": [{"name": "단양군", "latitude": 36.98, "longitude": 128.36}]}}.get(name, {})

    app = make_app(routes={FORECAST: FORECAST_JSON, GEO: geo})
    app.say("단양 날씨")
    assert "latitude=36.98" in app.net.calls[-1]
