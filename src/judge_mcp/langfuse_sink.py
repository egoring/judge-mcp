# Langfuse 점수 적재 (선택 기능) — 골든셋 성적표를 관측 플랫폼에 쌓아 추이를 본다
from __future__ import annotations


def client_from_env():
    """환경 변수(LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST)로 Langfuse 클라이언트를 만든다.

    SDK 미설치면 설치 방법을 담은 에러로 안내한다 — 관측은 선택 기능이므로
    이 함수는 --langfuse 플래그를 켰을 때만 호출된다.
    """
    try:
        from langfuse import Langfuse
    except ImportError as e:
        raise RuntimeError(
            "langfuse 패키지가 없습니다. 점수 적재를 쓰려면 `pip install langfuse>=2,<3`로 설치하세요."
        ) from e
    return Langfuse()


def push_scorecard(card: dict, details: list[dict], client) -> None:
    """골든셋 성적표 한 번의 실행을 Langfuse 트레이스 + 점수로 적재한다.

    - 트레이스 1건: 모델·백엔드·전체 정확도
    - 트레이스 점수: 전체 정확도(golden_accuracy)와 버킷별 정확도(golden:<버킷>)
    - 문항별 점수: 각 항목의 종합 점수(item:<id>) — 회귀 비교의 최소 단위

    client는 주입받는다 — 테스트에서는 모의 클라이언트로 검증한다.
    """
    trace = client.trace(
        name="judge-golden-run",
        input={"model": card.get("model"), "backend": card.get("backend"), "n_items": card["n_items"]},
        output={"accuracy": card["accuracy"]},
    )
    trace.score(name="golden_accuracy", value=card["accuracy"])
    for label, b in card["buckets"].items():
        trace.score(name=f"golden:{label}", value=b["accuracy"])
    for d in details:
        trace.score(name=f"item:{d['id']}", value=d["total"], comment=f"{d['label']} -> {d['verdict']}")
    client.flush()
