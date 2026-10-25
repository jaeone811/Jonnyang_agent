"""부정과 제외 탐지.

- 부정: 문장의 마지막 서술어에 "-지 마", "안/못 ~"이 걸리거나 "안 ~어도 돼" → 실행하지 않는다.
  "잊지 말라고 알려줘"처럼 부정이 앞쪽 서술어에만 걸리면 부정이 아니다.
- 제외: "타이머 말고 알람" → '타이머'를 후보에서 뺀다. "끄지 말고 줄여" → '끄'를 뺀다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jonnyang.nlu.normalize import AUX_VERBS, Morph

PRED_TAGS = ("VV", "VA", "XSV", "XSA", "VCP")
# 명령이 될 수 없는 상태 서술어. "내일 비 안 와?", "밖에 안 추워?"는 부정 명령이 아니라 질문이다.
STATE_VERBS = {"오", "내리", "춥", "덥", "좋", "나쁘", "괜찮", "맑", "흐리", "불"}


@dataclass
class Polarity:
    negated: bool = False
    excluded: set[str] = field(default_factory=set)
    excluded_spans: list[tuple[int, int]] = field(default_factory=list)


def _is_permission(morphs: list[Morph], i: int) -> bool:
    """'-어도 되'의 '되'. 새 서술어가 아니라 앞 서술어에 붙은 허락 표현이다."""
    return morphs[i].form == "되" and i > 0 and morphs[i - 1].form in ("어도", "아도", "도", "여도")


def detect(morphs: list[Morph]) -> Polarity:
    pol = Polarity()
    preds = []
    for i, m in enumerate(morphs):
        if m.tag.startswith("VX"):
            if m.form == "말":
                preds.append(i)
            continue
        if m.tag.startswith(PRED_TAGS) and m.form not in AUX_VERBS and not _is_permission(morphs, i):
            preds.append(i)
    last = preds[-1] if preds else None

    for i, m in enumerate(morphs):
        nxt = morphs[i + 1] if i + 1 < len(morphs) else None
        if m.form == "말" and m.tag.startswith("VX") and i > 0 and morphs[i - 1].form == "지":
            if i == last:
                pol.negated = True
            elif nxt is not None and nxt.form == "고" and i >= 2:
                verb = morphs[i - 2]
                pol.excluded.add(verb.form)
                pol.excluded_spans.append((verb.start, nxt.end))
        elif m.form == "말" and m.tag.startswith("VV") and nxt is not None and nxt.form == "고":
            j = i - 1
            while j >= 0 and morphs[j].tag.startswith("J"):
                j -= 1
            if j >= 0 and morphs[j].tag.startswith(("NN", "SL", "NP")):
                pol.excluded.add(morphs[j].form)
                pol.excluded_spans.append((morphs[j].start, nxt.end))
        elif m.form in ("안", "못") and m.tag.startswith("MAG"):
            after = [k for k in preds if k > i]
            if after and after[0] == last and morphs[last].form not in STATE_VERBS:
                pol.negated = True
            if any(_is_permission(morphs, k) for k in range(i + 1, len(morphs))):
                pol.negated = True
    return pol
