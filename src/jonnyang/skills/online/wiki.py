"""위키백과 요약 (한국어판, MediaWiki Action API + TextExtracts).

가져온 글은 화면에 보여주기만 한다. 요약 안에 "타이머 맞춰" 같은 말이 있어도 절대 명령으로 처리하지 않는다.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from jonnyang.core.network import NetworkError
from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Result
from jonnyang.skills.online.common import OnlineSkill

ASK_RE = re.compile(r"(?:이|가|은|는)?\s*(?:누구|뭐|무엇|뭔데|뭔지|어떤\s*거|어떤\s*사람)"
                    r"(?:야|니|지|예요|에요|인가요?|임|냐)?\s*(?:\?|$)"
                    r"|(?:에\s*대해서?|에\s*관해서?)\s*(?:좀\s*)?(?:알려|설명|말해|찾아)"
                    r"|(?:뜻|의미)(?:가|이)?\s*(?:뭐|알려)")
CUE_RE = re.compile(r"(?:위키\s*백과|위키피디아|위키|백과사전)(?:에서|에|로|으로)?")
TRAIL_RE = re.compile(
    r"(?:에서|에|으로|로)?\s*(?:좀\s*)?(?:검색|찾아|찾|알려|설명|말해)\s*(?:해)?\s*(?:줘|주세요|줄래|봐|줘요)?\s*$")
PARTICLE_RE = re.compile(r"(?:이란|란|이라는|라는|이|가|은|는|을|를|의)$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def topic_of(text: str, quoted: list[str], morphs=None) -> str:
    if quoted:
        return quoted[0].strip()
    t = ASK_RE.sub(" ", text)
    t = CUE_RE.sub(" ", t)
    t = TRAIL_RE.sub(" ", t.strip())
    t = re.sub(r"(?:에\s*대해서?|에\s*관해서?)\s*$", "", t.strip())
    t = re.sub(r"\s*(?:좀|줘|주세요|줄래|봐)\s*$", "", t.strip())
    t = " ".join(t.split()).strip(" ?!.,")
    if not t:
        return ""
    if morphs:
        # 끝에 붙은 조사만 뗀다 ("광합성이" → 광합성, "고양이"는 그대로). 형태소 분석 결과로 판단한다.
        start = text.find(t)
        if start >= 0:
            inside = [m for m in morphs if m.start >= start and m.end <= start + len(t)]
            while inside and inside[-1].tag.startswith(("J", "E", "VCP", "XSN")):
                inside.pop()
            if inside:
                return text[inside[0].start:inside[-1].end].strip()
    return PARTICLE_RE.sub("", t) if len(t) > 3 else t


def _hint(req) -> float:
    if ASK_RE.search(req.text) and topic_of(req.text, req.quoted, req.morphs):
        return 0.75
    return 0.0


class WikiSkill(OnlineSkill):
    name = "wiki"
    section = "wiki"
    service = "wiki"
    intents = [
        Intent("wiki.search", nouns={"위키": 0.9, "위키백과": 1.0, "위키피디아": 1.0, "백과사전": 0.9, "검색": 0.3},
               verbs={"SHOW": 0.1, "TELL": 0.2}, extras={"찾": 0.2}, hint=_hint,
               avoid={"SET": 0.4, "CANCEL": 0.5, "ADD": 0.4, "OPEN": 0.3, "UP": 0.4, "DOWN": 0.4},
               examples=("아인슈타인이 누구야", "광합성이 뭐야", "위키에서 고양이 찾아줘")),
    ]

    def extract(self, intent: str, req) -> dict[str, Any]:
        topic = topic_of(req.text, req.quoted, req.morphs)
        return {"topic": topic} if topic else {}

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        topic = slots.get("topic")
        if not topic:
            return Result("ask.topic")
        url = self.cfg["url"]
        base = {"action": "query", "format": "json", "formatversion": 2, "prop": "extracts", "exintro": 1,
                "explaintext": 1, "redirects": 1}
        try:
            data = self.ctx.network.get_json(url, {**base, "titles": topic}, ttl=self.ttl(1440))
            page = (data.get("query", {}).get("pages") or [{}])[0]
            if page.get("missing") or page.get("invalid") or not page.get("extract"):
                data = self.ctx.network.get_json(url, {**base, "generator": "search", "gsrsearch": topic,
                                                       "gsrlimit": 1}, ttl=self.ttl(1440))
                pages = data.get("query", {}).get("pages") or []
                page = pages[0] if pages else {}
        except NetworkError as exc:
            return self.fail(exc)
        except (AttributeError, IndexError, TypeError):
            return self.fail(NetworkError("bad_data"))
        extract = CONTROL_RE.sub("", str(page.get("extract") or "")).strip()
        if not extract:
            return Result("wiki.not_found", {"topic": topic}, core=("topic",), ok=False)
        title = str(page.get("title") or topic)
        link = "https://ko.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        return Result("wiki.summary", {"title": title, "summary": self._cut(extract), "url": link},
                      core=("title", "summary"))

    def _cut(self, text: str) -> str:
        limit = int(self.cfg.get("max_chars", 300))
        text = text.split("\n")[0].strip() if len(text.split("\n")[0]) > 40 else " ".join(text.split())
        if len(text) <= limit:
            return text
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind("다."))
        return (cut[:end + 2] if end > limit * 0.5 else cut).rstrip() + ("" if end > limit * 0.5 else "…")
