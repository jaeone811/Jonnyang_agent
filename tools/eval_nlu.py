"""의도 데이터셋 정확도 리포트 + 임계값 스윕.

사용법: python tools/eval_nlu.py [--sweep]
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jonnyang.app import build_app  # noqa: E402
from jonnyang.core.storage import Storage  # noqa: E402
from jonnyang.platform.fake import fake_platform  # noqa: E402

NOW = datetime(2026, 10, 20, 14, 0)


def load():
    for path in sorted((ROOT / "tests" / "data" / "intents").glob("*.yaml")):
        yield from yaml.safe_load(path.read_text(encoding="utf-8"))


def judge(d, case):
    it = d.interpret(case["text"], NOW)
    expect = case.get("expect", "execute")
    ok = it.kind == expect
    if ok and "intent" in case and expect != "clarify":
        ok = it.intent is not None and it.intent.name == case["intent"]
    got = f"{it.kind}:{it.intent.name if it.intent else '-'}"
    want = f"{expect}:{case.get('intent', '-')}"
    return ok, got, want


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="실행 임계값/차이 조합별 정확도")
    args = ap.parse_args()
    _, d = build_app(platform=fake_platform(), storage=Storage(":memory:"), clock=lambda: NOW, rng=random.Random(0))
    cases = list(load())

    by_tag: dict[str, list[bool]] = defaultdict(list)
    confusion: Counter = Counter()
    for case in cases:
        ok, got, want = judge(d, case)
        for tag in case.get("tags", ["-"]):
            by_tag[tag].append(ok)
        if not ok:
            confusion[(want, got)] += 1
            print(f"  ✗ {case['text']!r}: want {want}, got {got}")
    total = sum(ok for v in by_tag.values() for ok in v) / max(1, sum(len(v) for v in by_tag.values()))
    print(f"\n전체 {len(cases)}문장")
    for tag, oks in sorted(by_tag.items()):
        print(f"  {tag:10} {sum(oks)}/{len(oks)}  {100 * sum(oks) / len(oks):.0f}%")
    if confusion:
        print("\n혼동 top 10")
        for (want, got), n in confusion.most_common(10):
            print(f"  {n}× {want} → {got}")
    print(f"\n태그 가중 정확도 {100 * total:.1f}%")

    if args.sweep:
        print("\nexecute  margin  정확도")
        for ex in (0.6, 0.65, 0.7, 0.75, 0.8):
            for mg in (0.1, 0.15, 0.2):
                d.exec_th, d.margin = ex, mg
                acc = sum(judge(d, c)[0] for c in cases) / len(cases)
                print(f"  {ex:.2f}    {mg:.2f}   {100 * acc:.1f}%")


if __name__ == "__main__":
    main()
