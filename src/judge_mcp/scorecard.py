# 골든셋 성적표와 두 채점기 일치율을 계산하는 순수 로직 (LLM 비의존 — 단위 테스트 대상)
from __future__ import annotations

import json
from pathlib import Path

from .judge import GOOD_QUALITY_CUT, LOW_QUALITY_CUT

# 라벨별 기대 방향 — good_fix는 높은 점수가 정답, 나머지는 낮은 점수가 정답
EXPECT_HIGH = {"good_fix"}
EXPECT_LOW = {"missed", "overcorrected"}
VALID_LABELS = EXPECT_HIGH | EXPECT_LOW


def load_golden_set(path: str | Path) -> list[dict]:
    """JSONL 골든셋을 읽고 스키마를 검증한다. 항목: id, original, revised, label."""
    items: list[dict] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        for key in ("id", "original", "revised", "label"):
            if key not in item:
                raise ValueError(f"골든셋 {line_no}행에 '{key}' 필드가 없습니다.")
        if item["label"] not in VALID_LABELS:
            raise ValueError(
                f"골든셋 {line_no}행 라벨 '{item['label']}'은 유효하지 않습니다. 허용: {sorted(VALID_LABELS)}"
            )
        items.append(item)
    if not items:
        raise ValueError(f"골든셋이 비어 있습니다: {path}")
    return items


# missed 판정용 개선 축 컷 — 오류를 방치한 수정은 improvement가 낮아야 정답
MISSED_IMPROVEMENT_CUT = 4.0


def is_correct(label: str, total: float, improvement: float | None = None) -> bool:
    """채점 점수가 사람 라벨과 같은 방향인지 판정한다.

    - good_fix: 종합 점수가 높아야 정답
    - overcorrected: 종합 점수가 낮아야 정답 (절제 축 가중치가 커서 종합에 반영됨)
    - missed: **개선 여부 축**이 낮아야 정답 — 방치된 수정은 의미 보존·절제가 만점이라
      종합 점수로는 잡히지 않는다 (골든셋 회귀 시험이 실측으로 잡아낸 설계 교훈)
    """
    if label in EXPECT_HIGH:
        return total >= GOOD_QUALITY_CUT
    if label == "missed" and improvement is not None:
        return improvement <= MISSED_IMPROVEMENT_CUT
    return total <= LOW_QUALITY_CUT


def build_scorecard(results: list[dict]) -> dict:
    """항목별 (label, total) 결과를 버킷별·전체 정확도 성적표로 집계한다."""
    buckets: dict[str, dict[str, int]] = {}
    correct_total = 0
    for r in results:
        b = buckets.setdefault(r["label"], {"n": 0, "correct": 0})
        b["n"] += 1
        if is_correct(r["label"], r["total"], r.get("improvement")):
            b["correct"] += 1
            correct_total += 1
    n = len(results)
    return {
        "n_items": n,
        "accuracy": round(correct_total / n, 4) if n else 0.0,
        "buckets": {
            label: {
                "n": b["n"],
                "correct": b["correct"],
                "accuracy": round(b["correct"] / b["n"], 4),
            }
            for label, b in sorted(buckets.items())
        },
        "thresholds": {"good": GOOD_QUALITY_CUT, "poor": LOW_QUALITY_CUT},
    }


def agreement(results_a: list[float], results_b: list[float], tolerance: float = 1.0) -> dict:
    """두 채점기의 종합 점수 목록으로 일치율을 계산한다.

    - within_tolerance: 점수 차이가 tolerance(기본 ±1) 이내인 비율
    - verdict_agreement: 저품질(poor) 판정이 서로 같은 비율
    """
    if len(results_a) != len(results_b):
        raise ValueError("두 결과 목록의 길이가 다릅니다.")
    n = len(results_a)
    if n == 0:
        raise ValueError("빈 결과로는 일치율을 계산할 수 없습니다.")
    within = sum(1 for a, b in zip(results_a, results_b) if abs(a - b) <= tolerance)
    verdict_same = sum(
        1
        for a, b in zip(results_a, results_b)
        if (a <= LOW_QUALITY_CUT) == (b <= LOW_QUALITY_CUT)
    )
    return {
        "n_items": n,
        "within_tolerance": round(within / n, 4),
        "tolerance": tolerance,
        "verdict_agreement": round(verdict_same / n, 4),
        "mean_abs_diff": round(sum(abs(a - b) for a, b in zip(results_a, results_b)) / n, 3),
    }
