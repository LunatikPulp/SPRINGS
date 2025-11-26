"""Auto-debate helpers for spotting nonsense and triggering AI replies."""

from __future__ import annotations

import json
import time
from typing import Any, Iterable

from aiogram import types

from .openrouter import call_openrouter
from .memory import get_chat_history_entries, serialize_targets_for_prompt
from .settings import (
    AUTO_DEBATE_CONFIDENCE_THRESHOLD,
    AUTO_DEBATE_COOLDOWN,
    AUTO_DEBATE_HISTORY_LIMIT,
    AUTO_DEBATE_ENABLED,
    AUTO_DEBATE_MIN_TEXT_LENGTH,
    AUTO_DEBATE_REASON_MAX_CHARS,
    auto_debate_last_reply,
    logger,
)

DEBATE_SYSTEM_PROMPT = (
    "Ты язвительный хулиган, который мониторит чат и врезает словом каждый раз,"
    " когда кто-то несёт чушь, врёт или истерит. Тебе дадут последние реплики"
    " (формат 'Автор: текст') и текущее сообщение."
    " Отвечай строго JSON {\"should_reply\": bool, \"confidence\": float, \"reason\": str}."
    " should_reply=true только если видишь тупую ложь, бред, токсичный наезд или жалкий плач,"
    " на который надо ответить ядом. reason — короткий список тезисов в свободной форме"
    " (каждая строка начинается с тире), где ты объясняешь, почему автор заслуживает оскорбительный ответ."
    " После списка добавь едкое резюме в одном предложении. confidence — число 0..1."
    " Не зови правила, не оправдывайся — тебе достаточно видеть идиотизм."
)


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _build_dialogue_context(chat_id: int) -> list[str]:
    history = get_chat_history_entries(chat_id)
    return history[-AUTO_DEBATE_HISTORY_LIMIT:]


async def should_trigger_auto_debate(
    message: types.Message,
    targets: Iterable[dict] | None = None,
) -> tuple[bool, str | None]:
    """Return decision and reason for automatic debate reply."""

    if not AUTO_DEBATE_ENABLED:
        return False, None

    if not message.from_user or message.from_user.is_bot:
        return False, None

    text = (message.text or message.caption or "").strip()
    if len(text) < AUTO_DEBATE_MIN_TEXT_LENGTH:
        return False, None

    now = time.time()
    last_reply = auto_debate_last_reply.get(message.chat.id)
    if last_reply and now - last_reply < AUTO_DEBATE_COOLDOWN:
        return False, None

    dialogue = _build_dialogue_context(message.chat.id)
    serialized_targets = serialize_targets_for_prompt(list(targets or []))

    payload = [
        {"role": "system", "content": DEBATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "chat_id": message.chat.id,
                    "user_id": message.from_user.id,
                    "text": text,
                    "dialogue": dialogue,
                    "targets": serialized_targets,
                },
                ensure_ascii=False,
            ),
        },
    ]

    response = await call_openrouter(payload, temperature=0.2, max_tokens=140)
    if not response:
        return False, None

    parsed = _parse_json_response(response)
    if not parsed:
        lowered = response.lower()
        should_reply = "true" in lowered or "yes" in lowered
        confidence = 1.0 if should_reply else 0.0
        reason = response.strip() if should_reply else None
    else:
        should_reply = bool(parsed.get("should_reply"))
        try:
            confidence = float(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = parsed.get("reason") if isinstance(parsed, dict) else None

    if reason:
        reason = reason.strip()
        if len(reason) > AUTO_DEBATE_REASON_MAX_CHARS:
            reason = reason[: AUTO_DEBATE_REASON_MAX_CHARS].rstrip() + "…"

    if should_reply and confidence >= AUTO_DEBATE_CONFIDENCE_THRESHOLD:
        logger.info(
            "Auto-debate trigger: chat=%s user=%s confidence=%.2f reason=%s",
            message.chat.id,
            message.from_user.id if message.from_user else None,
            confidence,
            reason,
        )
        return True, reason

    return False, None


def mark_auto_debate_reply(chat_id: int) -> None:
    """Remember when the bot last auto-replied in this chat."""

    auto_debate_last_reply[chat_id] = time.time()
