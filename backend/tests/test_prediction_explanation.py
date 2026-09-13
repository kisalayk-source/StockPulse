"""MVP-7 grounded prediction explanation enrichment."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.prediction_explanation import enrich_prediction_explanation
from ml.explanation import explain_prediction


def _result() -> dict:
    structured = {
        "ticker": "MSFT",
        "signal": "HOLD",
        "probability": 0.51,
        "horizon": "5d",
        "risk_score": 0.4,
    }
    return {
        "ticker": "MSFT",
        "signal": "HOLD",
        "explanation": explain_prediction(structured),
    }


def test_enrich_keeps_template_when_llm_disabled() -> None:
    settings = SimpleNamespace(research_llm_enabled=True, openai_api_key="x")
    user = SimpleNamespace(research_llm_enabled=True)
    out = asyncio.run(
        enrich_prediction_explanation(settings, user, _result(), llm_config_enabled=False)
    )
    assert out["explanation"]["provider"] == "template"


def test_enrich_keeps_template_when_user_opted_out() -> None:
    settings = SimpleNamespace(research_llm_enabled=True, openai_api_key="x")
    user = SimpleNamespace(research_llm_enabled=False)
    out = asyncio.run(
        enrich_prediction_explanation(settings, user, _result(), llm_config_enabled=True)
    )
    assert out["explanation"]["provider"] == "template"


def test_enrich_uses_llm_when_active(monkeypatch) -> None:
    settings = SimpleNamespace(
        research_llm_enabled=True,
        openai_api_key="x",
        openai_base_url=None,
        openai_model="gpt-4o-mini",
    )
    user = SimpleNamespace(research_llm_enabled=True)

    async def fake_chat(*args, **kwargs):
        return "MSFT is HOLD at 51% over 5d using only the provided JSON."

    monkeypatch.setattr("app.services.openai_client.call_openai_chat", fake_chat)
    out = asyncio.run(
        enrich_prediction_explanation(settings, user, _result(), llm_config_enabled=True)
    )
    assert out["explanation"]["provider"] == "llm"
    assert "MSFT is HOLD" in out["explanation"]["text"]
    assert out["explanation"]["template_text"]
