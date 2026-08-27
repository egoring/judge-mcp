# LLM 응답을 채점 결과로 변환하는 핵심 로직 (프리필터·JSON 파싱·가중 합산)
from __future__ import annotations

import json
import re
from typing import Any

from .llm import LLMClient
from .rubric import RUBRICS, Rubric, build_prompt

# 저품질 판정 컷 — 종합 점수가 이 값 이하면 '문제 있는 수정'으로 본다
LOW_QUALITY_CUT = 5.0
# 고품질 판정 컷 — 이 값 이상이면 '잘 고친 수정'으로 본다
GOOD_QUALITY_CUT = 7.0

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _clamp(v: Any) -> float:
    """축 점수를 1~10 범위 float로 강제한다."""
    try:
        return min(10.0, max(1.0, float(v)))
    except (TypeError, ValueError):
        return 1.0


def parse_judge_output(raw: str, rubric: Rubric) -> dict:
    """LLM 원문 응답에서 JSON을 추출·검증한다. 코드펜스·잡담이 섞여도 복구한다."""
    match = _JSON_RE.search(raw)
    if not match:
        raise ValueError(f"채점 응답에서 JSON을 찾지 못했습니다: {raw[:120]!r}")
    data = json.loads(match.group(0))
    scores_in = data.get("scores", {})
    scores = {axis: _clamp(scores_in.get(axis)) for axis in rubric.axes}
    missing = [a for a in rubric.axes if a not in scores_in]
    if missing:
        raise ValueError(f"채점 응답에 누락된 축이 있습니다: {missing}")
    return {"scores": scores, "rationale": str(data.get("rationale", ""))[:300]}


def score_pair(
    client: LLMClient,
    original: str,
    revised: str,
    rubric_name: str = "correction",
    model: str | None = None,
) -> dict:
    """원문·수정문 한 쌍을 채점한다. 무변경 쌍은 LLM 없이 프리필터로 처리한다."""
    rubric = RUBRICS.get(rubric_name)
    if rubric is None:
        raise ValueError(f"알 수 없는 루브릭 '{rubric_name}'. 사용 가능: {sorted(RUBRICS)}")

    # 프리필터 — 수정문이 원문과 동일하면 채점 비용 없이 결정적으로 처리
    if original.strip() == revised.strip():
        scores = {a: 10.0 for a in rubric.axes}
        if "improvement" in scores:
            scores["improvement"] = 1.0
        total = rubric.weighted_total(scores)
        return {
            "rubric": rubric.name,
            "scores": scores,
            "total": total,
            "verdict": _verdict(total),
            "rationale": "무변경 응답 — 프리필터 처리 (원문과 수정문이 동일)",
            "prefiltered": True,
        }

    raw = client.chat(build_prompt(rubric, original, revised), model=model)
    parsed = parse_judge_output(raw, rubric)
    total = rubric.weighted_total(parsed["scores"])
    return {
        "rubric": rubric.name,
        "scores": parsed["scores"],
        "total": total,
        "verdict": _verdict(total),
        "rationale": parsed["rationale"],
        "prefiltered": False,
    }


def _verdict(total: float) -> str:
    """종합 점수를 3단계 판정으로 요약한다."""
    if total >= GOOD_QUALITY_CUT:
        return "good"
    if total <= LOW_QUALITY_CUT:
        return "poor"
    return "fair"
