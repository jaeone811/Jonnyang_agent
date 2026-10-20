"""계산: 사칙연산, 퍼센트, 할인, 더치페이. eval() 대신 ast로 안전하게 계산한다."""

from __future__ import annotations

import ast
import operator
import re
from fractions import Fraction
from typing import Any

from jonnyang.nlu.matcher import Intent
from jonnyang.skills.base import Result, Skill

WORD_OPS = [
    (r"더하기|플러스|더해서|\+", "+"), (r"빼기|마이너스|−", "-"), (r"곱하기|곱|×|\*", "*"),
    (r"나누기|÷", "/"),
]
PERCENT_OF = re.compile(r"(\d+(?:\.\d+)?)\s*(?:원)?\s*의\s*(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)")
DISCOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*원?\s*(?:에서|의)?\s*(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)\s*할인")
DUTCH_WORDS = re.compile(r"나눠|나누|더치|엔빵|n빵|N빵|1/n|각자|인당|명당")
PEOPLE = re.compile(r"(\d+)\s*명")
WON = re.compile(r"(\d+(?:\.\d+)?)\s*원")
EXPR = re.compile(r"[\d.()\s+\-*/^]+")

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.Mod: operator.mod}


class CalcError(Exception):
    pass


def safe_eval(expr: str) -> Fraction:
    def ev(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow):
                if right.denominator != 1 or abs(right) > 100 or abs(left) > 10**6:
                    raise CalcError("too_big")
                return left ** int(right)
            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
                raise CalcError("zero")
            return OPS[type(node.op)](left, right)
        raise CalcError("syntax")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError("syntax") from exc
    return ev(tree)


def pretty(expr: str) -> str:
    s = expr.replace("**", "^").replace("*", "×").replace("/", "÷")
    s = re.sub(r"\s*([+\-×÷^])\s*", r" \1 ", s)
    return re.sub(r"\s+", " ", s).replace("( ", "(").replace(" )", ")").strip()


def to_number(v: Fraction) -> int | float:
    return int(v) if v.denominator == 1 else float(v)


def find_expression(text: str) -> str | None:
    t = PERCENT_OF.sub(lambda m: f"({m.group(1)}*{m.group(2)}/100)", text)
    for pat, op in WORD_OPS:
        t = re.sub(pat, f" {op} ", t)
    t = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", " * ", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*의\s*제곱", r"(\1)^2", t)
    best = None
    for m in EXPR.finditer(t):
        cand = m.group().strip()
        if re.search(r"\d", cand) and (re.search(r"\d\s*[+\-*/^]\s*[\d(]", cand) or cand.startswith("(")):
            if best is None or len(cand) > len(best):
                best = cand
    return best.replace("^", "**") if best else None


def _calc_hint(req) -> float:
    if DISCOUNT.search(req.text) or find_expression(req.text):
        return 1.0
    if DUTCH_WORDS.search(req.text) and PEOPLE.search(req.text) and len(req.numbers) >= 2:
        return 1.0
    return 0.0


class CalcSkill(Skill):
    name = "calc"
    intents = [
        Intent("calc.eval", nouns={"계산": 0.5, "더치페이": 0.6, "엔빵": 0.6}, hint=_calc_hint,
               examples=("40의 15%는?", "3만 2천원 4명이서 나눠", "12 곱하기 7", "5만원에서 20% 할인")),
    ]

    def handle(self, intent: str, req, slots: dict[str, Any]) -> Result:
        text = req.text
        m = DISCOUNT.search(text)
        if m:
            price, pct = Fraction(m.group(1)), Fraction(m.group(2))
            final = price * (1 - pct / 100)
            return Result("calc.discount", {"price": to_number(price), "percent": to_number(pct),
                                            "value": to_number(final), "saved": to_number(price - final)},
                          core=("value",))

        people = PEOPLE.search(text)
        if DUTCH_WORDS.search(text) and people:
            n = int(people.group(1))
            won = WON.search(text)
            others = [x for x in req.numbers if x != n]
            total = Fraction(won.group(1)) if won else (Fraction(str(others[0])) if others else None)
            if total is None or n <= 0:
                return Result("calc.error", {"expr": text}, ok=False)
            if total.denominator == 1:
                per, rem = divmod(int(total), n)
                key = "calc.dutch_rem" if rem else "calc.dutch"
                return Result(key, {"total": int(total), "people": n, "per": per, "rem": rem, "per_plus": per + 1},
                              core=("per",))
            return Result("calc.dutch", {"total": to_number(total), "people": n, "per": to_number(total / n),
                                         "rem": 0, "per_plus": 0}, core=("per",))

        expr = find_expression(text)
        if not expr:
            return Result("calc.error", {"expr": text}, ok=False)
        try:
            value = safe_eval(expr)
        except CalcError as exc:
            return Result(f"calc.{exc.args[0]}", {"expr": pretty(expr)}, ok=False)
        return Result("calc.result", {"expr": pretty(expr), "value": to_number(value)}, core=("value",))
