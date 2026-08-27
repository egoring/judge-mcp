# 채점 루브릭 정의와 채점 프롬프트를 구성하는 모듈
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rubric:
    """4축 루브릭 한 벌 — 축 이름, 가중치, 축별 설명."""

    name: str
    description: str
    axes: dict[str, float]  # 축 이름 -> 가중치 (합계 1.0)
    axis_guides: dict[str, str] = field(default_factory=dict)

    def weighted_total(self, scores: dict[str, float]) -> float:
        """축별 점수(1~10)를 가중 평균해 종합 점수를 낸다."""
        total = sum(self.axes[a] * scores[a] for a in self.axes)
        return round(total, 2)


# 기본 루브릭: 문장 교정 품질 (캡스톤 방법론의 일반화 버전)
CORRECTION = Rubric(
    name="correction",
    description="원문 대비 수정문이 '얼마나 잘 고쳐졌는가'를 평가하는 교정 품질 루브릭",
    axes={
        "meaning": 0.40,        # 의미 보존
        "naturalness": 0.15,    # 자연스러움
        "improvement": 0.10,    # 개선 여부
        "restraint": 0.35,      # 과교정 절제 (높을수록 불필요한 변경이 없음)
    },
    axis_guides={
        "meaning": "원문의 의미가 보존되었는가. 의미가 바뀌었으면 낮게.",
        "naturalness": "수정문이 문법적으로 자연스러운가.",
        "improvement": "원문의 오류가 실제로 고쳐졌는가. 오류가 남아 있으면 낮게.",
        "restraint": "불필요한 변경(어투·표현 바꾸기)이 없는가. 과하게 고쳤으면 낮게.",
    },
)

# 요약 품질 루브릭 — 확장 예시 (루브릭 추가가 쉬움을 보이는 용도)
SUMMARY = Rubric(
    name="summary",
    description="원문 대비 요약문의 충실성·간결성을 평가하는 요약 품질 루브릭",
    axes={
        "faithfulness": 0.45,   # 원문 사실 왜곡 없음
        "coverage": 0.25,       # 핵심 내용 포함
        "conciseness": 0.15,    # 간결성
        "fluency": 0.15,        # 문장 완성도
    },
    axis_guides={
        "faithfulness": "원문에 없는 내용을 지어내지 않았는가.",
        "coverage": "원문의 핵심 정보가 요약에 담겼는가.",
        "conciseness": "군더더기 없이 짧게 정리되었는가.",
        "fluency": "요약문 자체가 읽기 자연스러운가.",
    },
)

RUBRICS: dict[str, Rubric] = {r.name: r for r in (CORRECTION, SUMMARY)}

# Few-shot 앵커 — 점수 척도를 고정하기 위한 기준 예시
_ANCHORS = """
채점 기준 예시 (교정 루브릭):
- 원문 "오늘 회의 몇시에 시작하나요" -> 수정 "오늘 회의 몇 시에 시작하나요?"
  => meaning 10, naturalness 10, improvement 9, restraint 10  (잘 고침)
- 원문 "오늘 회의 몇시에 시작하나요" -> 수정 "오늘 회의 몇시에 시작하나요"
  => meaning 10, naturalness 5, improvement 2, restraint 10  (오류 방치)
- 원문 "오늘 회의 몇시에 시작하나요" -> 수정 "회의 시작 시각을 알려주시기 바랍니다."
  => meaning 5, naturalness 9, improvement 6, restraint 2  (과교정: 어투까지 변경)
""".strip()


def build_prompt(rubric: Rubric, original: str, revised: str) -> str:
    """루브릭·앵커·대상 문장으로 채점 프롬프트를 만든다. 출력은 JSON을 강제한다."""
    axis_lines = "\n".join(
        f'- "{axis}" (가중치 {w:.2f}): {rubric.axis_guides.get(axis, "")}'
        for axis, w in rubric.axes.items()
    )
    score_fields = ", ".join(f'"{a}": <1-10>' for a in rubric.axes)
    return (
        f"당신은 텍스트 품질 채점관이다. 아래 루브릭으로 수정문을 1~10점 채점하라.\n\n"
        f"[루브릭: {rubric.name}] {rubric.description}\n{axis_lines}\n\n"
        f"{_ANCHORS}\n\n"
        f"[원문]\n{original}\n\n[수정문]\n{revised}\n\n"
        f"반드시 아래 형식의 JSON만 출력하라. 다른 텍스트 금지.\n"
        f'{{"scores": {{{score_fields}}}, "rationale": "<한 문장 근거>"}}'
    )
