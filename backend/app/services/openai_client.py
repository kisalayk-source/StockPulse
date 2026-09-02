from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("app.services.openai_client")


async def call_openai_chat(
    settings: Any,
    *,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.2,
    log_key: str = "openai_chat_failed",
) -> str | None:
    if not settings.research_llm_enabled or not settings.openai_api_key:
        return None
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning(log_key, extra={"error_type": type(exc).__name__})
        return None
