"""Optional, pluggable LLM adapters (Anthropic and any OpenAI-compatible endpoint, e.g. Ollama)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ...infrastructure.repositories import Settings


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient(LLMClient):
    def __init__(self, key: str, model: str):
        self.key, self.model = key, model or "claude-haiku-5-5"

    def complete(self, system: str, user: str) -> str:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=20,
                       headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                       json={"model": self.model, "max_tokens": 400, "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["content"][0]["text"]


class OpenAICompatClient(LLMClient):
    def __init__(self, key: str, model: str, base_url: str):
        self.key, self.model = key, model or "gpt-4o-mini"
        self.base = (base_url or "https://api.openai.com/v1").rstrip("/")

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(f"{self.base}/chat/completions", timeout=30,
                       headers={"Authorization": f"Bearer {self.key or 'none'}"},
                       json={"model": self.model, "messages": [{"role": "system", "content": system},
                                                               {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def build_llm(s: Settings) -> LLMClient | None:
    """None means 'no LLM configured' → the rules engine answers."""
    kind = s.get("llm_provider")
    if kind == "anthropic" and s.get("anthropic_api_key"):
        return AnthropicClient(s.get("anthropic_api_key"), s.get("llm_model"))
    if kind == "openai" and (s.get("openai_api_key") or s.get("llm_base_url")):
        return OpenAICompatClient(s.get("openai_api_key"), s.get("llm_model"), s.get("llm_base_url"))
    return None
