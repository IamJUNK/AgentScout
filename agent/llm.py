from __future__ import annotations
import json
from typing import Any
import httpx

class OpenAICompatibleClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None, timeout: float = 30.0):
        from config import load_settings
        settings = load_settings() if None in (base_url, api_key, model) else None
        self.base_url = (base_url if base_url is not None else settings.llm_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model if model is not None else settings.llm_model
        self.timeout = timeout
    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model)
    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 1800) -> tuple[str, int | None]:
        if not self.available:
            raise RuntimeError("LLM_API_KEY and LLM_MODEL must be configured to use the cloud model")
        response = httpx.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}, timeout=self.timeout)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        text = payload["choices"][0]["message"].get("content", "")
        tokens = payload.get("usage", {}).get("total_tokens")
        return text, int(tokens) if tokens is not None else None

def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM did not return a JSON object")
    return json.loads(cleaned[start:end + 1])
