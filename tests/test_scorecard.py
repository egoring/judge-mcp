# 성적표·일치율 계산과 골든셋 로더 테스트
from __future__ import annotations

from pathlib import Path

import pytest

from judge_mcp.scorecard import agreement, build_scorecard, is_correct, load_golden_set

GOLDEN = Path(__file__).resolve().parents[1] / "data" / "golden_set.jsonl"


def test_load_bundled_golden_set():
    items = load_golden_set(GOLDEN)
    assert len(items) == 24
    labels = {i["label"] for i in items}
    assert labels == {"good_fix", "missed", "overcorrected"}


def test_load_rejects_bad_label(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "x", "original": "a", "revised": "b", "label": "unknown"}', encoding="utf-8")
    with pytest.raises(ValueError, match="라벨"):
        load_golden_set(p)


def test_load_rejects_missing_field(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "x", "original": "a", "label": "missed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="revised"):
        load_golden_set(p)


def test_is_correct_direction():
    assert is_correct("good_fix", 8.5)          # 잘 고침 -> 높은 점수가 정답
    assert not is_correct("good_fix", 4.0)
    assert is_correct("missed", 3.0)            # 방치 -> 낮은 점수가 정답
    assert is_correct("overcorrected", 4.9)
    assert not is_correct("overcorrected", 8.0)


def test_missed_judged_by_improvement_axis():
    # 방치는 의미 보존·절제가 만점이라 종합이 높게 나온다 — improvement 축으로 판정해야 한다
    assert is_correct("missed", 8.4, improvement=2.0)       # 종합은 높아도 개선 축이 낮으면 정답
    assert not is_correct("missed", 8.4, improvement=9.0)   # 개선 축까지 높으면 오답
    assert is_correct("missed", 9.1, improvement=1.0)       # 무변경 프리필터 케이스(9.1)도 정답 처리


def test_missed_falls_back_to_total_without_improvement():
    assert is_correct("missed", 3.0)
    assert not is_correct("missed", 8.0)


def test_is_correct_fair_zone_counts_as_wrong():
    # 판정 회색 지대(5~7 사이)는 어느 라벨에서도 정답이 아니다 — 보수적 채점
    assert not is_correct("good_fix", 6.0)
    assert not is_correct("missed", 6.0)


def test_build_scorecard_accuracy():
    results = [
        {"label": "good_fix", "total": 9.0},       # 정답
        {"label": "good_fix", "total": 4.0},       # 오답
        {"label": "missed", "total": 3.0},         # 정답
        {"label": "overcorrected", "total": 4.5},  # 정답
    ]
    card = build_scorecard(results)
    assert card["n_items"] == 4
    assert card["accuracy"] == pytest.approx(0.75)
    assert card["buckets"]["good_fix"]["accuracy"] == pytest.approx(0.5)
    assert card["buckets"]["missed"]["accuracy"] == 1.0


def test_agreement_within_tolerance():
    a = [8.0, 3.0, 5.0, 9.0]
    b = [7.5, 4.5, 5.0, 6.0]
    out = agreement(a, b)
    assert out["within_tolerance"] == pytest.approx(0.5)  # 8/7.5, 5/5만 ±1 이내
    # 저품질(<=5) 판정: (F,F), (T,T), (T,T), (F,F) -> 전부 일치
    assert out["verdict_agreement"] == 1.0


def test_agreement_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        agreement([1.0], [1.0, 2.0])


def test_agreement_rejects_empty():
    with pytest.raises(ValueError):
        agreement([], [])
