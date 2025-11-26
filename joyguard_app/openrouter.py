"""OpenRouter API helpers."""

from __future__ import annotations

import json

import aiohttp

from .settings import (
    AIOHTTP_TIMEOUT,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_MODEL,
    logger,
)


async def call_openrouter(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.9,
    max_tokens: int = 400,
) -> str | None:
    if not OPENROUTER_API_KEY:
        logger.error(
            "OPENROUTER_API_KEY/GROK_API_KEY not provided. Set a valid key in your environment before enabling AI replies."
        )
        return None

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "SpringtrapSilent",
    }
    try:
        async with aiohttp.ClientSession(timeout=AIOHTTP_TIMEOUT) as session:
            async with session.post(OPENROUTER_API_URL, json=payload, headers=headers) as response:
                response_text = await response.text()
                if response.status != 200:
                    if response.status == 401:
                        logger.error(
                            "OpenRouter API error 401 (unauthorized). Make sure OPENROUTER_API_KEY/GROK_API_KEY contains a valid OpenRouter token registered to your account. Response: %s",
                            response_text,
                        )
                    else:
                        logger.error("OpenRouter API error %s: %s", response.status, response_text)
                    return None
                data = json.loads(response_text)
    except Exception as exc:  # pragma: no cover - network
        logger.error("OpenRouter request failed: %s", exc)
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message", {})
    content = message.get("content")
    return content.strip() if content else None
