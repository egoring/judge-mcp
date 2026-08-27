# judge-mcp

[![CI](https://github.com/egoring/judge-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/egoring/judge-mcp/actions/workflows/ci.yml)

> English: [README.en.md](README.en.md)

**LLM-as-Judge 텍스트 품질 평가를 MCP 서버로.**

원문·수정문 쌍을 다축 가중 루브릭으로 채점하고, 사람 라벨 골든셋으로 채점기 모델을 시험하며("학습이 아니라 시험"), 두 채점기의 일치율을 교차 검증합니다. 전부 [MCP](https://modelcontextprotocol.io) 도구로 노출되므로 Claude Desktop·Claude Code 등 어떤 MCP 클라이언트에서든 대화로 평가를 돌릴 수 있습니다.

## 왜 만들었나

교정·리라이팅·요약에는 단일 정답이 없어서 LLM 채점기를 쓰는 팀이 늘고 있습니다. 그런데 검증 안 된 채점기는 또 하나의 의견일 뿐입니다. 이 서버는 실서비스 로그 분석 프로젝트에서 검증한 방법론을 도구로 일반화한 것입니다.

1. **다축 가중 루브릭** — 의미 보존·자연스러움·개선 여부·과교정 절제. 불투명한 단일 점수 대신 축별로 잽니다.
2. **골든셋 시험** — 채점기 후보를 사람 라벨(잘 고침/방치/과교정)로 *시험*합니다. 학습에는 절대 쓰지 않아 골든셋이 시험지로 유지되고, 루브릭이 바뀔 때마다 회귀 시험으로 재사용됩니다.
3. **이중 채점 교차 검증** — 같은 문항을 두 채점기로 채점해 일치율을 재고, 결론이 채점기 선택에 강건한지 실증합니다.
4. **결정적 프리필터** — 무변경 쌍은 LLM 없이 코드가 채점합니다. 싸고, 항상 같은 답입니다.

## 도구

| 도구 | 기능 |
|---|---|
| `judge_score_text` | 원문·수정문 한 쌍 채점 → 축별 점수·가중 종합·good/fair/poor 판정·근거 |
| `judge_run_golden_set` | 골든셋으로 채점기 시험 → 전체·버킷별 정확도 성적표 |
| `judge_compare_models` | 두 모델 이중 채점 → ±1점 일치율·저품질 판정 일치율·평균 차 |
| `judge_list_rubrics` | 루브릭 목록과 축·가중치 조회 |

한국어 교정 합성 골든셋 24문항(3버킷)이 내장돼 있고, `golden_path`로 자체 골든셋(JSONL: `id`, `original`, `revised`, `label`)을 쓸 수 있습니다.

## 설치·설정

OpenAI 호환 백엔드면 모두 동작합니다 — OpenAI, 로컬 vLLM, Ollama, LM Studio.

```bash
pip install -e .

export JUDGE_API_BASE="https://api.openai.com/v1"   # vLLM이면 http://localhost:8000/v1
export JUDGE_API_KEY="sk-..."                        # 로컬 서버는 아무 값
export JUDGE_MODEL="gpt-4o-mini"                     # 또는 Qwen/Qwen2.5-7B-Instruct-AWQ
```

Claude Desktop 설정 예시는 [examples/](examples/claude_desktop_config.json)에 있습니다. 설정 후 이렇게 물으면 됩니다.

- "이 교정 채점해줘: 원문 '오늘 회의 몇시에 시작하나요', 수정 '몇 시에 시작하나요?'"
- "gpt-4o-mini로 골든셋 돌리고 성적표 보여줘"
- "gpt-4o-mini랑 로컬 Qwen이 채점기로서 서로 일치하는지 비교해줘"

## 실측 결과

내장 골든셋 24문항을 **Claude Sonnet**(`claude-cli` 백엔드)으로 시험한 결과:

| 버킷 | 정확도 |
|---|---|
| 잘 고침(good_fix) | **8/8** |
| 방치(missed) | **7/8** |
| 과교정(overcorrected) | 5/8 |
| **전체** | **83.3%** |

직접 재현: `python scripts/run_golden.py --backend claude-cli` (OpenAI 호환 API는 `--backend api`).

### 케이스 스터디: 골든셋이 설계 결함을 잡아냈다

첫 실행은 **62.5% — 방치 버킷이 0/8**이었다. 원인은 채점기가 아니라 판정 설계였다. 방치된 수정은 의미를 보존하고 과교정도 없어서 가중치가 큰 두 축(0.40+0.35)이 만점이 되고, 개선 축이 1점이어도 종합이 8~9점이 된다. 종합 점수로 방치를 잡는 건 수학적으로 불가능했다.

수정: 방치 버킷 판정을 종합 점수 대신 **개선(improvement) 축 ≤ 4**로 변경. 재시험 결과 62.5% → **83.3%**, 방치 0/8 → 7/8. 골든셋 회귀 루프가 존재하는 이유가 바로 이것이다 — 조용히 숨어 있던 평가 설계 결함을 실측으로 드러내고, 고치고, 회귀 테스트로 잠갔다. (남은 격차: 과교정 버킷은 LLM 채점의 실행 간 변동이 관찰됨 — Few-shot 앵커 보강 후보이며, 같은 회귀 루프로 개선을 검증할 수 있다.)

## 설계 노트

- **채점기 검증이 핵심입니다.** 채점기 모델들은 기본 상태에서 성향이 극과 극이라, 시험 없이 고르는 건 추측입니다. 정확도는 방향으로 판정합니다 — 잘 고친 수정은 높게(≥7), 방치·과교정은 낮게(≤5). 회색 지대(5~7)는 의도적으로 오답 처리합니다.
- **재현성 우선.** temperature 0, JSON 강제 출력 + 코드펜스·잡담 내성 파싱, 점수 범위 클램프, 그리고 모델이 필요 없는 케이스(무변경)는 코드 경로로.
- **행동 가능한 에러.** 연결·스키마 실패는 스택트레이스가 아니라 "무엇을 고치면 되는지"를 담은 메시지로 돌려줍니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest   # 21건, 네트워크 불필요 (모의 LLM)
```

## 라이선스

MIT
