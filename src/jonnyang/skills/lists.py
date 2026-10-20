"""목록 관리 (쇼핑 목록, 할 일 목록 등)."""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz, process

from jonnyang.core.storage import iso
from jonnyang.nlu.matcher import Intent
from jonnyang.nlu.preprocess import jamo
from jonnyang.skills.base import Confirm, Result, Skill

DEFAULT_LIST = "쇼핑"
LIST_SYNONYMS = {"장보기": "쇼핑", "장": "쇼핑", "장볼": "쇼핑", "살": "쇼핑", "구매": "쇼핑",
                 "할일": "할 일", "투두": "할 일", "todo": "할 일"}
LIST_PHRASE = re.compile(r"(?:(?P<name>[가-힣A-Za-z]+(?:\s일)?)\s*)?(?:목록|리스트)(?:에서|에다가?|에|을|를|은|는)?")
ADD_TAIL = re.compile(r"\s*(?:을|를)?\s*(?:좀\s*)?(?:추가|넣어|넣|담아|담|적어|적)[가-힣]*(?:\s+[가-힣]+)?\s*$")
REMOVE_TAIL = re.compile(r"\s*(?:을|를|은|는)?\s*(?:좀\s*)?(?:빼|지워|지우|삭제|제거|없애)[가-힣]*(?:\s+[가-힣]+)?\s*$")


class ListSkill(Skill):
    name = "lists"
    intents = [
        Intent("list.add", nouns={"목록": 0.6, "리스트": 0.6, "장보기": 0.5}, verbs={"ADD": 0.4},
               avoid={"CANCEL": 0.4, "SHOW": 0.3},
               hint=lambda req: 0.3 if "ADD" in req.groups else 0.0,
               examples=("쇼핑 목록에 우유랑 계란 추가해", "할 일 목록에 보고서 쓰기 추가")),
        Intent("list.show", nouns={"목록": 0.6, "리스트": 0.6, "장보기": 0.5}, verbs={"SHOW": 0.4, "TELL": 0.3},
               avoid={"ADD": 0.4, "CANCEL": 0.4}, examples=("쇼핑 목록 보여줘", "장보기 목록에 뭐 있어")),
        Intent("list.remove", nouns={"목록": 0.6, "리스트": 0.6, "장보기": 0.5}, verbs={"CANCEL": 0.4},
               avoid={"ALL": 0.4, "EMPTY": 0.4}, examples=("쇼핑 목록에서 우유 빼줘",)),
        Intent("list.clear", nouns={"목록": 0.6, "리스트": 0.6, "장보기": 0.5}, verbs={"EMPTY": 0.4, "CANCEL": 0.2},
               extras={"ALL": 0.2}, examples=("쇼핑 목록 비워줘",)),
    ]

    # ── 파싱 ──
    @staticmethod
    def list_name(text: str) -> str:
        m = LIST_PHRASE.search(text)
        name = (m.group("name") or "").strip() if m else ""
        name = LIST_SYNONYMS.get(name.replace(" ", ""), name)
        return name or DEFAULT_LIST

    def _items_from(self, text: str, tail: re.Pattern) -> list[str]:
        body = LIST_PHRASE.sub(" ", text, count=1)
        body = tail.sub("", body).strip()
        if not body:
            return []
        morphs = self.ctx.analyzer.tokenize(body)
        items: list[str] = []
        start = 0
        last_end = 0
        for m in morphs:
            if m.tag == "JC" or m.form in (",", "&"):
                items.append(body[start:last_end])
                start = m.end
            elif m.tag.startswith("J") or m.tag in ("SF", "SP"):
                continue
            else:
                last_end = m.end
        items.append(body[start:last_end])
        return [re.sub(r"\s+", " ", i).strip(" ,") for i in items if i.strip(" ,")]

    def extract(self, intent: str, req) -> dict[str, Any]:
        slots: dict[str, Any] = {"list": self.list_name(req.text)}
        if intent == "list.add":
            items = req.quoted or self._items_from(req.text, ADD_TAIL)
            if items:
                slots["items"] = items
        elif intent == "list.remove":
            items = req.quoted or self._items_from(req.text, REMOVE_TAIL)
            if items:
                slots["items"] = items
        return slots

    def _rows(self, name: str):
        return self.ctx.storage.query("SELECT * FROM list_items WHERE list_name = ? ORDER BY id", (name,))

    def _add(self, name: str, items: list[str], now) -> list[int]:
        ids = []
        for item in items:
            cur = self.ctx.storage.execute("INSERT INTO list_items(list_name, item, created) VALUES(?, ?, ?)",
                                           (name, item, iso(now)))
            ids.append(cur.lastrowid)
        return ids

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result | Confirm:
        name = slots["list"]
        if intent == "list.add":
            items = slots.get("items")
            if not items:
                return Result("ask.items", {"list": name}, core=("list",))
            ids = self._add(name, items, req.now)
            return Result("list.add", {"list": name, "items": items, "count": len(self._rows(name))},
                          core=("list", "items"), undo={"op": "delete", "ids": ids}, undo_label="list.add")

        rows = self._rows(name)
        if intent == "list.show":
            if not rows:
                return Result("list.empty", {"list": name}, core=("list",))
            return Result("list.show", {"list": name, "count": len(rows)}, core=("list", "count"),
                          items=[{"no": i, "item": r["item"]} for i, r in enumerate(rows, 1)], item_key="list.item")

        if intent == "list.remove":
            wanted = slots.get("items")
            if not wanted:
                return Result("ask.items", {"list": name}, core=("list",))
            if not rows:
                return Result("list.empty", {"list": name}, core=("list",))
            names = [r["item"] for r in rows]
            removed, missing = [], []
            for w in wanted:
                # 오타 허용("게란" → 계란). 실제로 지운 항목 이름을 응답에 보여주고 undo도 된다.
                hit = process.extractOne(jamo(w), [jamo(n) for n in names], scorer=fuzz.ratio, score_cutoff=80)
                if hit is None:
                    missing.append(w)
                    continue
                row = rows[hit[2]]
                self.ctx.storage.execute("DELETE FROM list_items WHERE id = ?", (row["id"],))
                removed.append(row["item"])
                rows = rows[:hit[2]] + rows[hit[2] + 1:]
                names = [r["item"] for r in rows]
            if not removed:
                return Result("list.not_found", {"list": name, "items": missing}, core=("list", "items"), ok=False)
            return Result("list.remove", {"list": name, "items": removed, "missing": missing},
                          core=("list", "items"), undo={"op": "add", "list": name, "items": removed},
                          undo_label="list.remove")

        if intent == "list.clear":
            if not rows:
                return Result("list.empty", {"list": name}, core=("list",))

            def do_clear() -> Result:
                current = [r["item"] for r in self._rows(name)]
                self.ctx.storage.execute("DELETE FROM list_items WHERE list_name = ?", (name,))
                return Result("list.clear", {"list": name, "count": len(current)}, core=("list", "count"),
                              undo={"op": "add", "list": name, "items": current}, undo_label="list.clear")
            return Confirm("confirm.list_clear", do_clear, {"list": name, "count": len(rows)},
                           core=("list", "count"), items=[{"no": i, "item": r["item"]} for i, r in enumerate(rows, 1)],
                           item_key="list.item")
        raise ValueError(intent)

    def undo(self, intent: str, payload: dict[str, Any]) -> Result:
        if payload["op"] == "delete":
            for rid in payload["ids"]:
                self.ctx.storage.execute("DELETE FROM list_items WHERE id = ?", (rid,))
        else:
            self._add(payload["list"], payload["items"], self.ctx.clock())
        return Result("undo.done")
