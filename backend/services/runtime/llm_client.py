from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


class LLMConfigurationError(RuntimeError):
    """Raised when the runtime LLM client is unavailable or misconfigured."""


def _openrouter_config() -> tuple[str, str, str, dict[str, str]]:
    api_key = str(os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise LLMConfigurationError("OPENROUTER_API_KEY is not set.")

    base_url = str(os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
    model = str(os.getenv("AGENTIC_MODEL") or "openai/gpt-4.1-mini").strip()
    referer = str(os.getenv("OPENROUTER_SITE_URL") or "http://localhost").strip()
    title = str(os.getenv("OPENROUTER_SITE_NAME") or "market-research").strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-OpenRouter-Title": title,
    }
    return base_url, model, f"{base_url}/chat/completions", headers


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response does not include choices.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("LLM response does not include message payload.")
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        joined = "\n".join(parts).strip()
        if joined:
            return joined
    raise RuntimeError("LLM response content is empty.")


def _parse_json_content(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Empty JSON payload.")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, dict):
            return parsed

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No JSON object found in response.")


async def complete_json(*, system_prompt: str, user_payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    base_url, model, endpoint, headers = _openrouter_config()

    max_tokens = int(kwargs.get("max_tokens") or 900)
    temperature_raw = kwargs.get("temperature")
    temperature = float(0.2 if temperature_raw is None else temperature_raw)
    timeout_seconds = float(kwargs.get("timeout_seconds") or 20.0)
    context = str(kwargs.get("context") or "LLM request")
    response_schema = kwargs.get("response_schema") if isinstance(kwargs.get("response_schema"), dict) else None
    reasoning_enabled = bool(kwargs.get("reasoning_enabled", False))

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_schema:
        payload["response_format"] = {"type": "json_schema", "json_schema": response_schema}
    else:
        payload["response_format"] = {"type": "json_object"}
    if reasoning_enabled:
        payload["reasoning"] = {"enabled": True}

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{context} request failed: {exc.__class__.__name__}: {exc}") from exc

    if response.status_code >= 400:
        detail = ""
        try:
            detail_payload = response.json()
            detail = str(detail_payload.get("error") or detail_payload)
        except Exception:
            detail = response.text
        raise RuntimeError(f"{context} request failed with status {response.status_code}: {detail}")

    response_payload = response.json()
    content = _extract_content(response_payload)
    try:
        return _parse_json_content(content)
    except Exception as exc:
        raise RuntimeError(f"{context} returned invalid JSON: {exc}") from exc
