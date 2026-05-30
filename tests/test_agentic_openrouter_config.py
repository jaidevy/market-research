from __future__ import annotations

import pytest

from market_research.agentic.service import AgenticResearchService
from market_research.config.settings import Settings


def test_openrouter_provider_maps_to_openai_with_headers_and_reasoning(tmp_path) -> None:
    settings = Settings(
        agentic_skills_dir=str(tmp_path / "skills"),
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_site_url="http://localhost",
        openrouter_site_name="market-research",
        openrouter_reasoning_enabled=True,
    )
    service = AgenticResearchService(settings=settings, engine=object())

    provider, kwargs = service._resolve_model_runtime_config()

    assert provider == "openai"
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert kwargs["max_tokens"] == 4096
    assert kwargs["default_headers"] == {
        "HTTP-Referer": "http://localhost",
        "X-OpenRouter-Title": "market-research",
    }
    assert kwargs["extra_body"] == {"reasoning": {"enabled": True}}


def test_openrouter_provider_requires_api_key(tmp_path) -> None:
    settings = Settings(
        agentic_skills_dir=str(tmp_path / "skills"),
        openrouter_api_key="",
    )
    service = AgenticResearchService(settings=settings, engine=object())

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is required"):
        service._resolve_model_runtime_config()
