"""날씨·미세먼지 (Open-Meteo). 지역은 online.yaml places 표에서 먼저 찾고, 없으면 지오코딩 API로 찾는다."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from jonnyang.core.network import NetworkError
from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Result
from jonnyang.skills.online.common import OnlineSkill

PLACE_SUFFIX = re.compile(r"(?:특별자치시|특별자치도|특별시|광역시|시|군|도)$")
ADMIN_RE = re.compile(r"[가-힣]{1,6}(?:시|군|구|읍|면|동)$")
RAIN_RE = re.compile(r"비\s*(?:가|는|도)?\s*(?:와|오|올|온|내리|안\s*와|안\s*오)|우산|강수|소나기")
WEEK_RE = re.compile(r"이번\s*주|주간|일주일|한\s*주")
SHOW = {"SHOW": 0.2, "TELL": 0.2}


def pick_place(results: list[dict]) -> dict | None:
    """같은 이름이 여럿이면 인구가 가장 많은 곳. 첫 결과만 쓰면 '대구'가 북한의 같은 이름 마을,
    '인천'이 전남의 작은 마을로 잡혔다(CI 실측). 인구가 같으면 API 순서를 따른다."""
    if not results:
        return None
    return max(enumerate(results), key=lambda ir: (ir[1].get("population") or 0, -ir[0]))[1]


def geocode(network, url: str, name: str) -> dict | None:
    """지역 이름 → Open-Meteo 지오코딩 결과 하나.

    지오코딩은 2글자 이름을 정확히 일치로만 찾아서 "수원"으로는 "수원시"가 안 나오고 같은 이름의 작은 마을만
    나온다(CI 실측: 수원 → 전남 마을, 고양 → 충남 마을). 2글자면 시·군·구를 붙인 이름도 같이 찾아서
    한국 결과 중 인구가 가장 많은 곳을 고른다. 한국에 없으면 나라 제한 없이 찾는다(도쿄, 파리 등)."""
    names = [name] + ([name + s for s in ("시", "군", "구")] if len(name) == 2 else [])
    base = {"count": 10, "language": "ko", "format": "json"}
    found: list[dict] = []
    for n in names:
        data = network.get_json(url, {"name": n, **base, "countryCode": "KR"}, ttl=30 * 86400)
        found += data.get("results") or []
    if not found:
        found = network.get_json(url, {"name": name, **base}, ttl=30 * 86400).get("results") or []
    return pick_place(found)


def _weather_hint(req) -> float:
    return 0.4 if RAIN_RE.search(req.text) else 0.0


class WeatherSkill(OnlineSkill):
    name = "weather"
    section = "weather"
    service = "weather"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.intents = [
            Intent("weather.now", nouns={"날씨": 0.8, "기온": 0.7, "일기예보": 0.9, "예보": 0.5, "우산": 0.5,
                                         "기상": 0.5, "비": 0.4},
                   verbs=SHOW, hint=_weather_hint, avoid={"SET": 0.3, "CANCEL": 0.5, "ADD": 0.4},
                   examples=("오늘 날씨 어때", "내일 부산 날씨 알려줘", "내일 비 와?")),
            Intent("air.now", nouns={"미세먼지": 0.9, "초미세먼지": 0.9, "대기질": 0.9, "황사": 0.7, "먼지": 0.6,
                                     "공기": 0.5},
                   verbs=SHOW, avoid={"SET": 0.3, "CANCEL": 0.5}, examples=("미세먼지 어때", "서울 공기 어때")),
            Intent("weather.set_home", nouns={"동네": 0.5, "지역": 0.4, "위치": 0.4, "사는": 0.2},
                   verbs={"SET": 0.3}, extras={"기본": 0.1, "우리": 0.1, "날씨": 0.1, "바꾸": 0.2, "변경": 0.2},
                   hint=lambda req: 0.3 if self.find_place(req) else 0.0,
                   avoid={"SHOW": 0.3, "CANCEL": 0.4}, required=("place",),
                   examples=("우리 동네 부산으로 설정해",)),
        ]
        places = self.ctx.online.get("places") or {}
        aliases = self.ctx.online.get("place_aliases") or {}
        self.places: dict[str, tuple[float, float]] = {str(k): (float(v[0]), float(v[1])) for k, v in places.items()}
        self.names: dict[str, str] = {**{n: n for n in self.places}, **{str(a): str(c) for a, c in aliases.items()}}

    def protected_words(self) -> set[str]:
        return set(self.names)

    # ── 지역 ──
    def find_place(self, req) -> str | None:
        """문장에서 지역 이름. 표에 있으면 표 이름, 없으면 지오코딩할 원래 단어."""
        for name in sorted(self.names, key=len, reverse=True):
            if name in req.compact:
                return self.names[name]
        for m in req.morphs:
            if m.tag == "NNP" and len(m.form) >= 2 and m.form not in ("존냥", "존냥이"):
                return m.form
        for word in req.text.split():
            word = re.sub(r"(?:의|에|은|는|도|에서)$", "", word)
            if ADMIN_RE.fullmatch(word) and word not in ("어떻게", "이번주"):
                return word
        return None

    def locate(self, name: str) -> tuple[str, float, float] | None:
        key = PLACE_SUFFIX.sub("", name) if PLACE_SUFFIX.sub("", name) in self.places else name
        if key in self.places:
            return key, *self.places[key]
        r = geocode(self.ctx.network, self.cfg["geocode_url"], name)
        if r is None:
            return None
        return str(r.get("name") or name), float(r["latitude"]), float(r["longitude"])

    def home(self) -> tuple[str, float, float]:
        saved = self.ctx.storage.get_setting("weather.home")
        if isinstance(saved, dict) and {"name", "lat", "lon"} <= set(saved):
            return saved["name"], float(saved["lat"]), float(saved["lon"])
        name = str(self.cfg.get("default_place", "서울"))
        lat, lon = self.places.get(name, (37.5665, 126.9780))
        return name, lat, lon

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        if payload.get("prev") is None:
            self.ctx.storage.execute("DELETE FROM settings WHERE key = ?", ("weather.home",))
        else:
            self.ctx.storage.set_setting("weather.home", payload["prev"])
        return Result("undo.done")

    def extract(self, intent: str, req) -> dict[str, Any]:
        place = self.find_place(req)
        return {"place": place} if place else {}

    # ── 실행 ──
    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        try:
            if slots.get("place"):
                loc = self.locate(slots["place"])
                if loc is None:
                    return Result("weather.place_unknown", {"place": slots["place"]}, core=("place",), ok=False)
            else:
                loc = self.home()
            if intent == "weather.set_home":
                name, lat, lon = loc
                prev = self.ctx.storage.get_setting("weather.home")
                self.ctx.storage.set_setting("weather.home", {"name": name, "lat": lat, "lon": lon})
                return Result("weather.home_set", {"place": name}, core=("place",),
                              undo={"op": "home", "prev": prev}, undo_label="weather.home")
            if intent == "air.now":
                return self._air(loc)
            return self._weather(loc, req)
        except NetworkError as exc:
            return self.fail(exc)
        except (KeyError, IndexError, TypeError, ValueError):
            return self.fail(NetworkError("bad_data"))

    def _day_offset(self, req) -> int:
        t = req.time
        if t.at is not None:
            return (t.at.date() - req.now.date()).days
        return 0

    def _weather(self, loc: tuple[str, float, float], req) -> Result:
        name, lat, lon = loc
        data = self.ctx.network.get_json(self.cfg["forecast_url"], {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto", "forecast_days": 7}, ttl=self.ttl(10))
        daily = data["daily"]
        days = [date.fromisoformat(d) for d in daily["time"]]
        rows = [self._row(daily, i) for i in range(len(days))]
        if WEEK_RE.search(req.text):
            items = [{"day": days[i], **rows[i]} for i in range(len(days))]
            return Result("weather.week", {"place": name}, core=("place",), items=items, item_key="weather.week_item")
        today = req.now.date()
        offset = self._day_offset(req)
        target = today + timedelta(days=offset)
        if target not in days:
            return Result("weather.out_of_range", {"days": len(days)}, ok=False)
        row = rows[days.index(target)]
        rain_q = bool(RAIN_RE.search(req.text))
        follow = self._tips(row, rain_q)
        if target == today:
            cur = data["current"]
            res = Result("weather.rain" if rain_q else "weather.now", {
                "place": name, "day": self._day_label(0), "desc": self._desc(cur["weather_code"]),
                "temp": round(float(cur["temperature_2m"]), 1), "feels": round(float(cur["apparent_temperature"]), 1),
                "humidity": round(float(cur["relative_humidity_2m"])), **row},
                core=("place", "temp", "rain") if rain_q else ("place", "desc", "temp"))
        else:
            res = Result("weather.rain" if rain_q else "weather.day",
                         {"place": name, "day": self._day_label(offset, target), **row},
                         core=("place", "day", "rain") if rain_q else ("place", "day", "desc", "high", "low"))
        res.follow = follow
        return res

    def _row(self, daily: dict, i: int) -> dict[str, Any]:
        rain = daily.get("precipitation_probability_max", [None] * (i + 1))[i]
        return {"desc": self._desc(daily["weather_code"][i]), "code": int(daily["weather_code"][i]),
                "high": round(float(daily["temperature_2m_max"][i])),
                "low": round(float(daily["temperature_2m_min"][i])),
                "rain_pct": None if rain is None else int(rain),
                "rain": "-" if rain is None else f"{int(rain)}%"}

    def _desc(self, code) -> str:
        codes = self.cfg.get("codes") or {}
        return str(codes.get(int(code), codes.get(str(code), f"코드 {code}")))

    @staticmethod
    def _day_label(offset: int, d: date | None = None) -> Any:
        return {0: "오늘", 1: "내일", 2: "모레"}.get(offset, d)

    def _tips(self, row: dict[str, Any], rain_q: bool) -> list[Result]:
        tips = []
        rain = row["rain_pct"]
        wet = row["code"] in (self.cfg.get("rain_codes") or [])
        if (isinstance(rain, int) and rain >= int(self.cfg.get("umbrella_percent", 50))) or wet:
            tips.append(Result("weather.tip_umbrella"))
        elif rain_q:
            tips.append(Result("weather.tip_no_umbrella"))
        if row["code"] in (self.cfg.get("snow_codes") or []):
            tips.append(Result("weather.tip_snow"))
        if row["low"] <= 0:
            tips.append(Result("weather.tip_cold"))
        elif row["high"] >= 30:
            tips.append(Result("weather.tip_hot"))
        return tips

    def _air(self, loc: tuple[str, float, float]) -> Result:
        name, lat, lon = loc
        data = self.ctx.network.get_json(self.cfg["air_url"], {
            "latitude": lat, "longitude": lon, "current": "pm10,pm2_5", "timezone": "auto"}, ttl=self.ttl(10))
        cur = data["current"]
        pm10, pm25 = round(float(cur["pm10"])), round(float(cur["pm2_5"]))
        g10, g25 = self._grade("pm10", pm10), self._grade("pm2_5", pm25)
        order = ["좋음", "보통", "나쁨", "매우나쁨"]
        worst = max(g10, g25, key=lambda g: order.index(g) if g in order else 0)
        res = Result("air.now", {"place": name, "pm10": pm10, "pm10_grade": g10, "pm25": pm25, "pm25_grade": g25,
                                 "grade": worst}, core=("place", "pm10", "pm25"))
        if worst in ("나쁨", "매우나쁨"):
            res.follow = [Result("air.tip_mask")]
        return res

    def _grade(self, kind: str, value: float) -> str:
        for limit, label in (self.ctx.online.get("air_grades") or {}).get(kind, []):
            if value <= float(limit):
                return str(label)
        return "-"
