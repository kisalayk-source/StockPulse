"""Grounded LLM enrichment for hybrid prediction explanations (MVP-7).

Reuses ``app.services.openai_client`` — same gates as research/SEC narration.
"""

from __future__ import annotations

from typing import Any

from ml.explanation import LLM_SYSTEM_PROMPT, build_llm_user_content, merge_llm_narration


async def enrich_prediction_explanation(
    settings: Any,
    user: Any | None,
    result: dict[str, Any],
    *,
    llm_config_enabled: bool,
) -> dict[str, Any]:
    """Optionally replace template text with grounded OpenAI narration.

    Falls back to the template when LLM is disabled, unavailable, or fails.
    """
    if not isinstance(result, dict):
        return result
    explanation = result.get("explanation")
    if not isinstance(explanation, dict):
        return result
    if not llm_config_enabled:
        result["explanation"] = merge_llm_narration(explanation, None)
        return result

    from app.services.openai_client import call_openai_chat, research_llm_active

    if not research_llm_active(settings, user):
        result["explanation"] = merge_llm_narration(explanation, None)
        return result

    structured = explanation.get("structured") or {}
    template_text = str(explanation.get("text") or "")
    narrative = await call_openai_chat(
        settings,
        system_prompt=LLM_SYSTEM_PROMPT,
        user_content=build_llm_user_content(structured, template_text=template_text),
        temperature=0.2,
        log_key="prediction_llm_failed",
        user=user,
    )
    result["explanation"] = merge_llm_narration(explanation, narrative)
    return result
