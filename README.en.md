# judge-mcp

[![CI](https://github.com/egoring/judge-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/egoring/judge-mcp/actions/workflows/ci.yml)

**LLM-as-Judge text quality evaluation as an MCP server.**

Score original/revised text pairs with a weighted multi-axis rubric, benchmark judge models against a human-labeled golden set ("exam, not training"), and cross-check two judges for agreement — all exposed as [Model Context Protocol](https://modelcontextprotocol.io) tools, so any MCP client (Claude Desktop, Claude Code, custom agents) can run evaluations conversationally.

> 한국어 문서: [README.md](README.md)

## Why

Text revision (proofreading, rewriting, summarizing) has no single ground truth, so teams increasingly use LLM judges to score quality. But an unvalidated judge is just another opinion. This server packages a methodology proven in a production log analysis project:

1. **Multi-axis weighted rubric** — meaning preservation, naturalness, actual improvement, and over-correction restraint, instead of one opaque score.
2. **Golden-set exam** — judge candidates are *tested* against human labels (good fix / missed / over-corrected), never trained on them, so the golden set stays a valid exam and can be reused as a regression test whenever the rubric changes.
3. **Dual-scoring cross-check** — score the same items with two judges and measure agreement, proving conclusions are robust to judge choice.
4. **Deterministic pre-filter** — identical input/output pairs are scored by code, not by the LLM: cheaper, and always reproducible.

## Tools

| Tool | What it does |
|---|---|
| `judge_score_text` | Score one original/revised pair on a rubric → per-axis scores, weighted total, good/fair/poor verdict, one-line rationale |
| `judge_run_golden_set` | Run a judge model through the golden set → overall & per-bucket accuracy scorecard |
| `judge_compare_models` | Dual-score the golden set with two models → ±1 agreement rate, low-quality verdict agreement, mean diff |
| `judge_list_rubrics` | List available rubrics with axes and weights |

A synthetic Korean proofreading golden set (24 items, 3 buckets) is bundled. Bring your own via `golden_path` — one JSON object per line with `id`, `original`, `revised`, `label`.

## Setup

Works with any OpenAI-compatible backend — OpenAI, local vLLM, Ollama, LM Studio.

```bash
pip install -e .

export JUDGE_API_BASE="https://api.openai.com/v1"   # or http://localhost:8000/v1 (vLLM)
export JUDGE_API_KEY="sk-..."                        # any value for local servers
export JUDGE_MODEL="gpt-4o-mini"                     # or Qwen/Qwen2.5-7B-Instruct-AWQ
```

### Claude Desktop

Add to `claude_desktop_config.json` (see [examples/](examples/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "judge-mcp": {
      "command": "judge-mcp",
      "env": {
        "JUDGE_API_BASE": "http://localhost:8000/v1",
        "JUDGE_API_KEY": "local",
        "JUDGE_MODEL": "Qwen/Qwen2.5-7B-Instruct-AWQ"
      }
    }
  }
}
```

Then ask Claude things like:

- *"Score this revision: original '오늘 회의 몇시에 시작하나요', revised '몇 시에 시작하나요?'"*
- *"Run the golden set against gpt-4o-mini and show me the scorecard."*
- *"Compare gpt-4o-mini and my local Qwen as judges — do they agree?"*

## Measured results

Golden set (24 items) judged by **Claude Sonnet** via the `claude-cli` backend:

| Bucket | Accuracy |
|---|---|
| good_fix | **8/8** |
| missed | **7/8** |
| overcorrected | 5/8 |
| **Overall** | **83.3%** |

Run it yourself: `python scripts/run_golden.py --backend claude-cli` (or `--backend api` with any OpenAI-compatible endpoint).

### Case study: the golden set caught a design flaw

The first run scored **62.5% — with the `missed` bucket at 0/8**. Root cause: a *missed* revision preserves meaning and over-corrects nothing, so the two heaviest axes (0.40 + 0.35) max out and the weighted total lands around 8-9 even when `improvement` is 1. Detecting misses through the total was mathematically impossible.

Fix: the `missed` bucket is now judged on the **improvement axis** (<= 4) instead of the total. Rerun: 62.5% -> **83.3%**, missed 0/8 -> 7/8. This is exactly what the golden-set regression loop exists for — it turned a silent evaluation-design flaw into a measured, fixed, and regression-tested lesson. (Remaining gap: `overcorrected` shows run-to-run variance of the LLM judge — a candidate for few-shot anchor tuning, verifiable by the same regression loop.)

## Design notes

- **Judge validation is the point.** `judge_run_golden_set` exists because judge models disagree wildly out of the box; picking one without an exam is guessing. Accuracy is directional: a *good fix* must score high (≥7), a *missed* or *over-corrected* revision must score low (≤5) — the gray zone counts as wrong, on purpose.
- **Reproducibility over cleverness.** Temperature 0, JSON-forced output with fence/chatter-tolerant parsing, clamped score ranges, and a code path (pre-filter) for the one case that needs no model at all.
- **Actionable errors.** Connection and schema failures come back as messages that tell the agent what to fix (`JUDGE_API_BASE`? model name? golden set field?), not stack traces.

## Test

```bash
pip install -e ".[dev]"
pytest   # 21 tests, no network required (mocked LLM)
```

## License

MIT
