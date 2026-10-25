"""환율 (Frankfurter v2: GET /v2/rates?base=USD&quotes=KRW → [{date, base, quote, rate}])."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from jonnyang.core.network import NetworkError
from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Result
from jonnyang.skills.online.common import OnlineSkill

# "원"은 다른 단어(공원, 원래, 회원)에 흔해서 돈 이야기로 보이는 자리만 원화로 본다
KRW_RE = re.compile(r"(?<=[\d만천억])\s*원|몇\s*원|원화|(?:^|\s)원(?:으로|에|은|이)?(?=\s|$)|한국\s*돈|우리\s*돈")
AMOUNT_RE = re.compile(r"((?:\d+(?:\.\d+)?\s*(?:억|만|천)?\s*)+)$")
UNIT = {"억": 100_000_000, "만": 10_000, "천": 1_000}


def parse_amount(s: str) -> float:
    """'5만' → 50000, '3만 5천' → 35000, '12.5' → 12.5"""
    total = 0.0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(억|만|천)?", s):
        total += float(num) * UNIT.get(unit, 1)
    return total
HOW_MUCH_RE = re.compile(r"얼마|몇|바꾸|바꿔|환전|로\s*(?:하면|치면)|으로")


class CurrencySkill(OnlineSkill):
    name = "currency"
    section = "currency"
    service = "currency"

    def __init__(self, ctx):
        super().__init__(ctx)
        names = self.cfg.get("names") or {}
        self.names: list[tuple[str, str]] = sorted(((str(k), str(v)) for k, v in names.items() if v != "KRW"),
                                                   key=lambda kv: len(kv[0]), reverse=True)
        self.intents = [
            Intent("currency.rate", nouns={"환율": 1.0, "환전": 0.8}, verbs={"SHOW": 0.2, "TELL": 0.2},
                   hint=self._hint, avoid={"SET": 0.3, "CANCEL": 0.5, "ADD": 0.4},
                   examples=("달러 환율 알려줘", "100달러는 몇 원이야", "엔화 환율")),
        ]

    def protected_words(self) -> set[str]:
        return {n.replace(" ", "") for n, _ in self.names} | {"원화", "환율"}

    def mentions(self, text: str) -> list[tuple[int, int, str]]:
        """(시작, 끝, 통화 코드) 문장 순서대로."""
        buf = text
        found: list[tuple[int, int, str]] = []
        for name, code in self.names:
            for m in re.finditer(re.escape(name), buf):
                found.append((m.start(), m.end(), code))
                buf = buf[:m.start()] + " " * len(name) + buf[m.end():]
        for m in KRW_RE.finditer(buf):
            found.append((m.start(), m.end(), "KRW"))
        return sorted(found)

    def _hint(self, req) -> float:
        ms = self.mentions(req.text)
        codes = {c for _, _, c in ms}
        if len(codes) >= 2:
            return 0.7
        if codes and codes != {"KRW"} and HOW_MUCH_RE.search(req.text):
            return 0.6
        return 0.3 if codes and codes != {"KRW"} else 0.0

    def extract(self, intent: str, req) -> dict[str, Any]:
        ms = self.mentions(req.text)
        if not ms:
            return {}
        src_i = 0
        amount = None
        for i, (start, _, _) in enumerate(ms):
            m = AMOUNT_RE.search(req.text[:start])
            if m and m.group(1).strip():
                src_i, amount = i, parse_amount(m.group(1))
                break
        src = ms[src_i][2]
        others = [c for _, _, c in ms if c != src]
        dst = others[0] if others else ("KRW" if src != "KRW" else "USD")
        slots: dict[str, Any] = {"src": src, "dst": dst}
        if amount is not None:
            slots["amount"] = amount
        return slots

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        src, dst = slots.get("src", "USD"), slots.get("dst", "KRW")
        try:
            rows = self.ctx.network.get_json(self.cfg["url"], {"base": src, "quotes": dst}, ttl=self.ttl(60))
            row = next(r for r in rows if r.get("quote") == dst)
            rate = float(row["rate"])
            day = date.fromisoformat(str(row["date"])[:10])
        except NetworkError as exc:
            return self.fail(exc)
        except (StopIteration, KeyError, TypeError, ValueError):
            return Result("currency.unsupported", {"src": self._name(src), "dst": self._name(dst)}, ok=False)
        if "amount" in slots:
            amount = slots["amount"]
            return Result("currency.convert", {"amount": self._num(amount, src), "src": self._name(src),
                                               "value": self._num(amount * rate, dst), "dst": self._name(dst),
                                               "date": day}, core=("amount", "value", "dst"))
        unit = 100 if src in (self.cfg.get("per_100") or []) else 1
        return Result("currency.rate", {"unit": unit, "src": self._name(src), "value": self._num(unit * rate, dst),
                                        "dst": self._name(dst), "date": day}, core=("value", "dst"))

    def _name(self, code: str) -> str:
        return str((self.cfg.get("display") or {}).get(code, code))

    @staticmethod
    def _num(v: float, code: str) -> int | float:
        if code in ("KRW", "JPY", "VND"):
            return int(round(v))
        return round(v, 2)
