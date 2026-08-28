# Langfuse 점수 적재 테스트 — 모의 클라이언트로 트레이스·점수 호출을 검증한다
from __future__ import annotations

from judge_mcp.langfuse_sink import push_scorecard


class FakeTrace:
    """score 호출을 기록하는 모의 트레이스."""

    def __init__(self) -> None:
        """점수 기록 저장소를 초기화한다."""
        self.scores: list[dict] = []

    def score(self, name, value, comment=None):
        """점수 하나를 기록한다."""
        self.scores.append({"name": name, "value": value, "comment": comment})


class FakeLangfuse:
    """trace·flush 호출을 기록하는 모의 Langfuse 클라이언트."""

    def __init__(self) -> None:
        """트레이스 저장소와 flush 카운터를 초기화한다."""
        self.traces: list[dict] = []
        self.flushed = 0
        self.last_trace: FakeTrace | None = None

    def trace(self, name, input, output):
        """트레이스 생성을 기록하고 모의 트레이스를 돌려준다."""
        self.traces.append({"name": name, "input": input, "output": output})
        self.last_trace = FakeTrace()
        return self.last_trace

    def flush(self):
        """flush 호출을 센다."""
        self.flushed += 1


CARD = {
    "n_items": 2, "accuracy": 0.5, "model": "sonnet", "backend": "claude-cli",
    "buckets": {"good_fix": {"n": 1, "correct": 1, "accuracy": 1.0},
                "missed": {"n": 1, "correct": 0, "accuracy": 0.0}},
}
DETAILS = [
    {"id": "g01", "label": "good_fix", "total": 8.6, "verdict": "good"},
    {"id": "m01", "label": "missed", "total": 8.4, "verdict": "good"},
]


def test_push_creates_one_trace_with_run_metadata():
    """실행 1회가 트레이스 1건으로 적재되고 모델·백엔드·정확도가 실린다."""
    client = FakeLangfuse()
    push_scorecard(CARD, DETAILS, client)
    assert len(client.traces) == 1
    t = client.traces[0]
    assert t["name"] == "judge-golden-run"
    assert t["input"]["model"] == "sonnet" and t["output"]["accuracy"] == 0.5


def test_push_records_overall_bucket_and_item_scores():
    """전체 정확도 1개 + 버킷 2개 + 문항 2개 = 점수 5개가 적재된다."""
    client = FakeLangfuse()
    push_scorecard(CARD, DETAILS, client)
    names = [s["name"] for s in client.last_trace.scores]
    assert names == ["golden_accuracy", "golden:good_fix", "golden:missed", "item:g01", "item:m01"]
    assert client.last_trace.scores[0]["value"] == 0.5


def test_push_flushes_before_exit():
    """단명 CLI에서 이벤트가 유실되지 않도록 flush가 호출된다."""
    client = FakeLangfuse()
    push_scorecard(CARD, DETAILS, client)
    assert client.flushed == 1
