# judge-mcp 서버 본체 — LLM-as-Judge 채점을 MCP 도구로 노출한다
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .judge import score_pair
from .llm import LLMClient, LLMError
from .rubric import RUBRICS
from .scorecard import agreement, build_scorecard, load_golden_set

mcp = FastMCP(
    "judge-mcp",
    instructions=(
        "LLM-as-Judge 텍스트 품질 평가 서버. 원문·수정문 쌍을 루브릭으로 채점하고, "
        "사람 라벨 골든셋으로 채점기(모델)를 시험하며, 두 모델의 채점 일치율을 비교한다. "
        "채점 백엔드는 JUDGE_API_BASE/JUDGE_API_KEY/JUDGE_MODEL 환경 변수로 설정한다 "
        "(OpenAI 호환 API — vLLM·Ollama 포함)."
    ),
)

_DEFAULT_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_set.jsonl"


def _client() -> LLMClient:
    """도구 호출 시점에 환경 변수를 읽어 클라이언트를 만든다 (설정 변경 즉시 반영)."""
    return LLMClient()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def judge_score_text(
    original: Annotated[str, Field(description="수정 전 원문")],
    revised: Annotated[str, Field(description="수정 후 문장")],
    rubric: Annotated[str, Field(description="루브릭 이름 (judge_list_rubrics로 조회)")] = "correction",
) -> dict:
    """원문·수정문 쌍을 4축 루브릭으로 채점한다.

    반환: 축별 점수(1~10), 가중 종합 점수, good/fair/poor 판정, 한 문장 근거.
    무변경 쌍은 LLM 호출 없이 프리필터로 결정적으로 처리된다.
    """
    try:
        return score_pair(_client(), original, revised, rubric_name=rubric)
    except (LLMError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def judge_run_golden_set(
    model: Annotated[str, Field(description="시험할 채점기 모델명 (비우면 JUDGE_MODEL)")] = "",
    golden_path: Annotated[str, Field(description="골든셋 JSONL 경로 (비우면 내장 합성 골든셋)")] = "",
    limit: Annotated[int, Field(ge=0, description="시험 문항 수 상한 (0=전체)")] = 0,
) -> dict:
    """사람 라벨 골든셋으로 채점기 모델을 시험해 성적표를 만든다.

    골든셋 라벨: good_fix(잘 고침 — 높은 점수가 정답) / missed(방치) / overcorrected(과교정 — 낮은 점수가 정답).
    반환: 전체·버킷별 정확도와 항목별 상세. '학습 없이 시험만'으로 채점기를 검증하는 도구다.
    """
    try:
        items = load_golden_set(golden_path or _DEFAULT_GOLDEN)
    except (OSError, ValueError) as e:
        return {"error": f"골든셋을 읽지 못했습니다: {e}"}
    if limit > 0:
        items = items[:limit]

    client = _client()
    results, details = [], []
    for item in items:
        try:
            scored = score_pair(client, item["original"], item["revised"], model=model or None)
        except (LLMError, ValueError) as e:
            return {"error": str(e), "completed_items": len(results)}
        results.append({"label": item["label"], "total": scored["total"], "improvement": scored["scores"].get("improvement")})
        details.append({"id": item["id"], "label": item["label"], "total": scored["total"], "verdict": scored["verdict"]})

    card = build_scorecard(results)
    card["model"] = model or client.model
    card["details"] = details
    return card


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def judge_compare_models(
    model_a: Annotated[str, Field(description="채점기 후보 A 모델명")],
    model_b: Annotated[str, Field(description="채점기 후보 B 모델명")],
    golden_path: Annotated[str, Field(description="골든셋 JSONL 경로 (비우면 내장 골든셋)")] = "",
    limit: Annotated[int, Field(ge=0, description="비교 문항 수 상한 (0=전체)")] = 0,
) -> dict:
    """같은 문항을 두 모델로 이중 채점해 일치율을 계산한다.

    반환: ±1점 이내 일치율, 저품질 판정 일치율, 평균 점수 차 — 결론이 채점기 선택에
    강건한지(robustness)를 실증하는 도구다.
    """
    try:
        items = load_golden_set(golden_path or _DEFAULT_GOLDEN)
    except (OSError, ValueError) as e:
        return {"error": f"골든셋을 읽지 못했습니다: {e}"}
    if limit > 0:
        items = items[:limit]

    client = _client()
    totals_a, totals_b = [], []
    for item in items:
        try:
            totals_a.append(score_pair(client, item["original"], item["revised"], model=model_a)["total"])
            totals_b.append(score_pair(client, item["original"], item["revised"], model=model_b)["total"])
        except (LLMError, ValueError) as e:
            return {"error": str(e), "completed_items": len(totals_b)}

    result = agreement(totals_a, totals_b)
    result.update({"model_a": model_a, "model_b": model_b})
    return result


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def judge_list_rubrics() -> dict:
    """사용 가능한 루브릭 목록과 축·가중치 구성을 반환한다."""
    return {
        name: {"description": r.description, "axes": r.axes, "guides": r.axis_guides}
        for name, r in RUBRICS.items()
    }


def main() -> None:
    """stdio 트랜스포트로 서버를 실행한다 (Claude Desktop 등 로컬 클라이언트용)."""
    mcp.run()


if __name__ == "__main__":
    main()
