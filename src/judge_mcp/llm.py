# OpenAI 호환 API를 호출하는 최소 LLM 클라이언트 (vLLM·Ollama·OpenAI 모두 지원)
from __future__ import annotations

import os

import httpx

DEFAULT_TIMEOUT = 60.0


class LLMError(RuntimeError):
    """LLM 호출 실패 — 도구 응답에서 원인과 해결책을 안내하기 위한 예외."""


class LLMClient:
    """OpenAI 호환 /chat/completions 엔드포인트 클라이언트.

    환경 변수:
      JUDGE_API_BASE  기본 https://api.openai.com/v1  (vLLM: http://localhost:8000/v1)
      JUDGE_API_KEY   API 키 (로컬 vLLM이면 아무 값이나 가능)
      JUDGE_MODEL     기본 모델명 (예: gpt-4o-mini, Qwen/Qwen2.5-7B-Instruct-AWQ)
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """인자가 없으면 JUDGE_* 환경 변수에서 설정을 읽는다."""
        self.api_base = (api_base or os.environ.get("JUDGE_API_BASE", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("JUDGE_API_KEY", "")
        self.model = model or os.environ.get("JUDGE_MODEL", "gpt-4o-mini")

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """단일 user 메시지로 채점 응답 텍스트를 받는다. temperature 0 = 재현성 우선."""
        if not self.api_key and "api.openai.com" in self.api_base:
            raise LLMError(
                "JUDGE_API_KEY가 설정되지 않았습니다. "
                "OpenAI 키를 넣거나, JUDGE_API_BASE를 로컬 vLLM 주소(예: http://localhost:8000/v1)로 바꾸세요."
            )
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key or 'local'}"},
                json={
                    "model": model or self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"LLM API가 {e.response.status_code}를 반환했습니다: {e.response.text[:200]}. "
                f"JUDGE_API_BASE({self.api_base})와 모델명({model or self.model})을 확인하세요."
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(
                f"LLM API({self.api_base})에 연결할 수 없습니다: {e}. "
                "서버가 떠 있는지, 주소가 맞는지 확인하세요."
            ) from e
