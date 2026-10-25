"""뉴스 헤드라인 (RSS + feedparser). 제목만 보여주고, 번호로 말하면 그 기사를 브라우저로 연다.

기사 제목은 외부 텍스트라 표시만 한다. 제목 안의 말은 명령으로 해석하지 않는다.
"""

from __future__ import annotations

import re
from typing import Any

from jonnyang.core.network import NetworkError
from jonnyang.nlu.matcher import Intent
from jonnyang.platform.base import Unsupported
from jonnyang.skills.base import Result
from jonnyang.skills.online.common import OnlineSkill

NO_RE = re.compile(r"(\d+)\s*번")
STOP = {"오늘", "최신", "요즘", "주요", "최근", "지금", "새로운", "새", "실시간", "뉴스", "기사", "헤드라인", "소식",
        "존냥", "존냥이", "좀", "거", "것"}
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class NewsSkill(OnlineSkill):
    name = "news"
    section = "news"
    service = "news"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.last: list[dict[str, str]] = []
        self.intents = [
            Intent("news.headlines", nouns={"뉴스": 1.0, "헤드라인": 0.9, "기사": 0.6, "소식": 0.4},
                   verbs={"SHOW": 0.1, "TELL": 0.1}, hint=self._topic_hint,
                   avoid={"SET": 0.4, "CANCEL": 0.5, "ADD": 0.4, "OPEN": 0.3},
                   examples=("오늘 뉴스 보여줘", "IT 뉴스 알려줘", "축구 뉴스")),
            Intent("news.open", nouns={"뉴스": 0.5, "기사": 0.6}, verbs={"OPEN": 0.3, "SHOW": 0.1},
                   hint=self._open_hint, avoid={"CANCEL": 0.5}, required=("index",), examples=("2번 기사 열어줘",)),
        ]

    def _topic_hint(self, req) -> float:
        words = {str(k).lower() for k in (self.cfg.get("topic_words") or {})}
        has_news_word = any(w in req.lemma_set for w in ("소식", "기사", "뉴스", "헤드라인"))
        return 0.3 if has_news_word and any(lm.lower() in words for lm in req.lemmas) else 0.0

    def _open_hint(self, req) -> float:
        if NO_RE.search(req.text) and self.last and self.ctx.storage.get_setting("recent.list") == "news":
            return 0.4
        return 0.2 if NO_RE.search(req.text) else -0.3

    def runs_async(self, intent: str) -> bool:
        return intent != "news.open"       # 브라우저 열기는 GUI 스레드에서 (네트워크 안 씀)

    def protected_words(self) -> set[str]:
        return {str(k) for k in (self.cfg.get("topic_words") or {})}

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        m = NO_RE.search(req.text)
        if m:
            slots["index"] = int(m.group(1))
        if intent == "news.headlines":
            topic_words = {str(k).lower(): str(v) for k, v in (self.cfg.get("topic_words") or {}).items()}
            for lemma in req.lemmas:
                if lemma.lower() in topic_words:
                    slots["topic"] = topic_words[lemma.lower()]
                    return slots
            if req.quoted:
                slots["query"] = req.quoted[0]
                return slots
            words = [lm for lm in req.lemmas
                     if lm not in STOP and len(lm) >= 2 and re.fullmatch(r"[가-힣A-Za-z0-9]+", lm)]
            if words and "뉴스" in req.text:
                head = req.text.split("뉴스")[0]
                words = [w for w in words if w in head]
                if words:
                    slots["query"] = " ".join(words[:3])
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        if intent == "news.open":
            return self._open(slots)
        feeds = self.cfg.get("feeds") or {}
        if slots.get("topic") in feeds:
            label, url, params = slots["topic"], feeds[slots["topic"]], None
        elif slots.get("query"):
            label, url, params = slots["query"], self.cfg["search_url"], {"q": slots["query"]}
        else:
            label, url, params = "주요", feeds.get("주요"), None
        try:
            raw = self.ctx.network.get_bytes(url, params, ttl=self.ttl(10))
        except NetworkError as exc:
            return self.fail(exc)
        import feedparser  # 필요할 때만 불러온다 (시작 시간 단축)

        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries[: int(self.cfg.get("max_items", 5))]:
            title = CONTROL_RE.sub("", " ".join(str(entry.get("title", "")).split()))
            link = str(entry.get("link", ""))
            if title:
                items.append({"no": len(items) + 1, "title": title, "link": link})
        if not items:
            return Result("news.empty", {"topic": label}, core=("topic",), ok=False)
        self.last = items
        self.ctx.storage.set_setting("recent.list", "news")
        return Result("news.list", {"topic": label, "count": len(items)}, core=("topic",), items=items,
                      item_key="news.item")

    def _open(self, slots: dict[str, Any]) -> Result:
        if not self.last:
            return Result("news.no_list", ok=False)
        i = slots.get("index", 0)
        if not 1 <= i <= len(self.last):
            return Result("news.bad_index", {"count": len(self.last)}, core=("count",), ok=False)
        item = self.last[i - 1]
        link = item["link"]
        if not re.match(r"^https?://", link):       # 피드에서 온 주소라 http(s)만 연다
            return Result("news.bad_link", {"title": item["title"]}, ok=False)
        try:
            self.ctx.platform.launcher.open(link)
        except Unsupported:
            return Result("error.unsupported", ok=False)
        except OSError as exc:
            return Result("app.error", {"name": item["title"], "target": link, "reason": str(exc)},
                          core=("name", "reason"), ok=False)
        return Result("news.opened", {"no": i, "title": item["title"]}, core=("title",))
