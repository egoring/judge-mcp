# 골든셋 시험을 CLI로 실행해 성적표 JSON을 출력한다 (MCP 클라이언트 없이 빠른 검증용)
# 백엔드 2종: api(OpenAI 호환 HTTP) / claude-cli(Claude Code 구독 인증으로 `claude -p` 호출)
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from judge_mcp.judge import score_pair  # noqa: E402
from judge_mcp.langfuse_sink import client_from_env, push_scorecard  # noqa: E402
from judge_mcp.llm import LLMClient, LLMError  # noqa: E402
from judge_mcp.scorecard import build_scorecard, load_golden_set  # noqa: E402


class ClaudeCLIClient:
    """Claude Code CLI(`claude -p`)를 채점 백엔드로 쓰는 클라이언트.

    API 키 없이 Claude 구독(Pro/Max) 인증으로 동작한다. Claude Code 설치·로그인 필요:
    https://docs.claude.com/en/docs/claude-code
    """

    def __init__(self, model: str | None = None) -> None:
        """claude 실행 파일을 찾고 기본 모델(sonnet)을 설정한다. 없으면 설치 안내와 함께 실패."""
        self.model = model or "sonnet"
        self._bin = shutil.which("claude")
        if not self._bin:
            raise LLMError(
                "claude 명령을 찾을 수 없습니다. Claude Code를 설치하고 로그인하세요: "
                "npm install -g @anthropic-ai/claude-code && claude"
            )

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """`claude -p`를 호출해 응답 텍스트를 받는다.

        프롬프트는 stdin으로 전달한다 — Windows에서 인자로 넘기면 줄바꿈·따옴표가 깨진다.
        (temperature는 CLI가 지원하지 않아 무시된다.)
        """
        try:
            proc = subprocess.run(
                [self._bin, "-p", "--model", model or self.model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError("claude CLI 호출이 180초를 넘어 중단됐습니다.") from e
        if proc.returncode != 0:
            raise LLMError(
                f"claude CLI가 실패했습니다 (exit {proc.returncode}): {proc.stderr.strip()[:200]}. "
                "claude 명령을 단독 실행해 로그인 상태를 확인하세요."
            )
        return proc.stdout.strip()


def main() -> None:
    """골든셋을 로드해 선택한 백엔드로 전 문항을 채점하고 성적표 JSON을 stdout에 쓴다."""
    parser = argparse.ArgumentParser(description="골든셋으로 채점기 모델을 시험한다.")
    parser.add_argument(
        "--backend",
        choices=["api", "claude-cli"],
        default="api",
        help="api=OpenAI 호환 HTTP(JUDGE_* 환경 변수) / claude-cli=Claude 구독으로 `claude -p` 호출",
    )
    parser.add_argument("--model", default=None, help="모델명 (api: JUDGE_MODEL 기본 / claude-cli: sonnet 기본)")
    parser.add_argument(
        "--langfuse",
        action="store_true",
        help="성적표를 Langfuse에 점수로 적재한다 (LANGFUSE_* 환경 변수 필요)",
    )
    parser.add_argument("--limit", type=int, default=0, help="문항 수 상한 (0=전체 24문항)")
    parser.add_argument(
        "--golden",
        default=str(Path(__file__).resolve().parents[1] / "data" / "golden_set.jsonl"),
        help="골든셋 JSONL 경로",
    )
    args = parser.parse_args()

    items = load_golden_set(args.golden)
    if args.limit > 0:
        items = items[: args.limit]

    try:
        if args.backend == "claude-cli":
            client = ClaudeCLIClient(model=args.model)
            model = client.model
            where = "claude CLI (구독 인증)"
        else:
            client = LLMClient()
            model = args.model or client.model
            where = client.api_base
    except LLMError as e:
        print(f"[중단] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[judge-mcp] 모델 '{model}' · {len(items)}문항 시험 시작 ({where})", file=sys.stderr)

    results, details = [], []
    for i, item in enumerate(items, 1):
        try:
            scored = score_pair(client, item["original"], item["revised"], model=args.model)
        except (LLMError, ValueError) as e:
            print(f"\n[중단] {e}", file=sys.stderr)
            sys.exit(1)
        results.append({"label": item["label"], "total": scored["total"], "improvement": scored["scores"].get("improvement")})
        details.append({"id": item["id"], "label": item["label"], "total": scored["total"], "verdict": scored["verdict"]})
        print(f"  {i:>2}/{len(items)} {item['id']} [{item['label']:<13}] total={scored['total']:>5} {scored['verdict']}", file=sys.stderr)

    card = build_scorecard(results)
    card["model"] = model
    card["backend"] = args.backend
    print(json.dumps(card, ensure_ascii=False, indent=2))

    if args.langfuse:
        try:
            push_scorecard(card, details, client_from_env())
            print("[judge-mcp] Langfuse에 성적표를 적재했습니다.", file=sys.stderr)
        except RuntimeError as e:
            print(f"[경고] Langfuse 적재 실패: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
