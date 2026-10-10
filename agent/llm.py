from __future__ import annotations
import json
from typing import Any
import httpx


class IncompleteResponse(RuntimeError):
    def __init__(self, message, tokens=None):
        super().__init__(message)
        self.tokens = tokens


class OpenAICompatibleClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=30.0):
        from config import load_settings
        settings = load_settings() if None in (base_url, api_key, model) else None
        self.base_url = (base_url if base_url is not None else settings.llm_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model if model is not None else settings.llm_model
        self.timeout = timeout

    @property
    def available(self):
        return bool(self.api_key and self.model)

    def chat(self, messages, temperature=.2, max_tokens=1800):
        if not self.available:
            raise RuntimeError("LLM_API_KEY and LLM_MODEL must be configured")
        response = httpx.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        choice = payload["choices"][0]
        tokens = payload.get("usage", {}).get("total_tokens")
        tokens = int(tokens) if tokens is not None else None
        if choice.get("finish_reason") not in {"stop", None}:
            raise IncompleteResponse("Model output incomplete: " + str(choice.get("finish_reason")), tokens)
        text = choice.get("message", {}).get("content")
        if not isinstance(text, str) or not text.strip():
            raise IncompleteResponse("Model returned empty content", tokens)
        return text, tokens


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = cleaned.strip(chr(96))
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM did not return a JSON object")
    return json.loads(cleaned[start:end + 1])
