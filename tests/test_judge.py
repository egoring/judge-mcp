# 채점 로직 단위 테스트 — LLM 없이 모의 클라이언트로 검증한다
from __future__ import annotations

import pytest

from judge_mcp.judge import parse_judge_output, score_pair
from judge_mcp.rubric import CORRECTION, RUBRICS, build_prompt


class MockClient:
    """정해진 응답을 돌려주는 모의 LLM 클라이언트."""

    def __init__(self, response: str) -> None:
        """항상 돌려줄 응답 문자열을 받는다."""
        self.response = response
        self.calls: list[str] = []

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """호출 프롬프트를 기록하고 고정 응답을 돌려준다."""
        self.calls.append(prompt)
        return self.response


GOOD_JSON = '{"scores": {"meaning": 10, "naturalness": 9, "improvement": 9, "restraint": 10}, "rationale": "잘 고침"}'


def test_parse_clean_json():
    out = parse_judge_output(GOOD_JSON, CORRECTION)
    assert out["scores"]["meaning"] == 10.0
    assert out["rationale"] == "잘 고침"


def test_parse_json_with_code_fence_and_chatter():
    raw = f"채점 결과입니다.\n```json\n{GOOD_JSON}\n```"
    out = parse_judge_output(raw, CORRECTION)
    assert out["scores"]["restraint"] == 10.0


def test_parse_missing_axis_raises():
    with pytest.raises(ValueError, match="누락"):
        parse_judge_output('{"scores": {"meaning": 10}}', CORRECTION)


def test_parse_no_json_raises():
    with pytest.raises(ValueError, match="JSON"):
        parse_judge_output("점수를 매길 수 없습니다.", CORRECTION)


def test_scores_clamped_to_range():
    raw = '{"scores": {"meaning": 15, "naturalness": 0, "improvement": "abc", "restraint": 7}}'
    out = parse_judge_output(raw, CORRECTION)
    assert out["scores"]["meaning"] == 10.0   # 상한 클램프
    assert out["scores"]["naturalness"] == 1.0  # 하한 클램프
    assert out["scores"]["improvement"] == 1.0  # 비수치 -> 최저점


def test_score_pair_good_fix():
    client = MockClient(GOOD_JSON)
    result = score_pair(client, "몇시에 시작하나요", "몇 시에 시작하나요?")
    assert result["verdict"] == "good"
    assert result["total"] >= 7.0
    assert not result["prefiltered"]
    assert len(client.calls) == 1


def test_prefilter_no_change_skips_llm():
    client = MockClient(GOOD_JSON)
    result = score_pair(client, "같은 문장", "같은 문장")
    assert result["prefiltered"] is True
    assert result["scores"]["improvement"] == 1.0
    assert client.calls == []  # LLM 호출 없음 — 결정적 처리


def test_prefilter_total_reflects_low_improvement():
    client = MockClient(GOOD_JSON)
    result = score_pair(client, "같은 문장", "같은 문장")
    # improvement(가중 0.10)만 1점 -> 종합 = 0.9*10 + 0.1*1 = 9.1
    assert result["total"] == pytest.approx(9.1)


def test_unknown_rubric_raises():
    with pytest.raises(ValueError, match="루브릭"):
        score_pair(MockClient(GOOD_JSON), "a", "b", rubric_name="없는루브릭")


def test_weighted_total_matches_weights():
    scores = {"meaning": 10, "naturalness": 10, "improvement": 10, "restraint": 2}
    # 0.4*10 + 0.15*10 + 0.1*10 + 0.35*2 = 7.2
    assert CORRECTION.weighted_total(scores) == pytest.approx(7.2)


def test_build_prompt_contains_axes_and_texts():
    prompt = build_prompt(CORRECTION, "원문A", "수정B")
    for axis in CORRECTION.axes:
        assert axis in prompt
    assert "원문A" in prompt and "수정B" in prompt
    assert "JSON" in prompt


def test_rubric_weights_sum_to_one():
    for rubric in RUBRICS.values():
        assert sum(rubric.axes.values()) == pytest.approx(1.0)
