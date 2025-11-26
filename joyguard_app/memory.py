"""Helpers for chat/user memory handling."""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections import deque
from typing import Any

from aiogram import types

from .database import db
from .openrouter import call_openrouter
from .settings import (
    CHAT_HISTORY_CHAR_LIMIT,
    CHAT_HISTORY_LIMIT,
    CHAT_MEMORY_CONTEXT_LIMIT,
    CHAT_MEMORY_MESSAGE_CHAR_LIMIT,
    CUSTOM_STYLE_PROMPT_LIMIT,
    OPENROUTER_API_KEY,
    MAX_MEMORY_FACTS,
    MEMORY_CAPTURE_PROBABILITY,
    MEMORY_MIN_RECENT_SHARE,
    MEMORY_SUMMARY_PROMPT,
    USER_MEMORY_CONTEXT_LIMIT,
    chat_histories,
    logger,
    WORD_PATTERN,
)


def store_chat_history(message: types.Message) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        return
    if not message.from_user:
        return
    content = message.text or message.caption
    if not content:
        content = f"<{message.content_type}>"
    author = (
        message.from_user.full_name
        or (f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id))
    )
    entry = f"{author}: {content}"
    history = chat_histories.setdefault(message.chat.id, deque(maxlen=CHAT_HISTORY_LIMIT))
    history.append(entry)


async def should_capture_memory(message: types.Message) -> bool:
    text = (message.text or message.caption or "").strip()
    if not text or text.startswith("/"):
        return False
    if message.from_user and message.from_user.is_bot:
        return False
    return random.random() <= MEMORY_CAPTURE_PROBABILITY


def get_chat_history_entries(chat_id: int) -> list[str]:
    history = chat_histories.get(chat_id)
    if not history:
        return []
    return list(history)


def get_display_name(user: types.User | None) -> str:
    if not user:
        return "Неизвестный"
    if user.full_name:
        return user.full_name
    if user.username:
        return f"@{user.username}"
    return f"ID{user.id}"


def build_user_memory_context(chat_id: int, targets: list[dict]) -> list[str]:
    context_lines: list[str] = []
    for target in targets:
        target_id = target.get("user_id")
        if not target_id:
            continue
        notes = db.get_user_memories(chat_id, target_id, USER_MEMORY_CONTEXT_LIMIT)
        if not notes:
            continue
        name = target.get("name") or (
            f"@{target.get('username')}" if target.get("username") else f"ID{target_id}"
        )
        sampled_notes = choose_varied_entries(notes, max(1, USER_MEMORY_CONTEXT_LIMIT // 2))
        for note in sampled_notes:
            context_lines.append(f"{name}: {note}")
    return context_lines


def serialize_targets_for_prompt(targets: list[dict]) -> list[dict[str, Any]]:
    serialized = []
    for target in targets:
        if not target.get("user_id"):
            continue
        serialized.append(
            {
                "user_id": target["user_id"],
                "name": target.get("name"),
                "username": target.get("username"),
            }
        )
    return serialized


def choose_varied_entries(entries: list[str], limit: int) -> list[str]:
    if limit <= 0 or len(entries) <= limit:
        return entries
    recent_keep = entries[: max(MEMORY_MIN_RECENT_SHARE, min(limit // 2, len(entries)))]
    remaining = entries[len(recent_keep) :]
    to_pick = limit - len(recent_keep)
    if remaining and to_pick > 0:
        sampled = random.sample(remaining, min(to_pick, len(remaining)))
        recent_keep += sampled
    return recent_keep


def summarize_message_text(message: types.Message) -> str:
    text = (message.text or message.caption or "").strip()
    if text:
        return text[:CHAT_MEMORY_MESSAGE_CHAR_LIMIT]
    return f"<{message.content_type}>"


def normalize_message_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized.lower() if normalized else None


async def extract_memory_facts(
    message: types.Message, targets: list[dict]
) -> tuple[list[str], dict[int, list[str]]]:
    text = message.text or message.caption
    if not text or not OPENROUTER_API_KEY:
        return [], {}

    target_payload = serialize_targets_for_prompt(targets)
    payload = {
        "role": "user",
        "content": json.dumps(
            {
                "chat_id": message.chat.id,
                "author_id": message.from_user.id if message.from_user else None,
                "author_name": get_display_name(message.from_user),
                "text": text,
                "targets": target_payload,
            },
            ensure_ascii=False,
        ),
    }
    response = await call_openrouter(
        [
            {"role": "system", "content": MEMORY_SUMMARY_PROMPT},
            payload,
        ],
        temperature=0.2,
        max_tokens=300,
    )
    if not response:
        return [], {}
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return [], {}

    chat_facts = []
    if isinstance(parsed, dict):
        for fact in (parsed.get("chat_facts") or [])[:MAX_MEMORY_FACTS]:
            if isinstance(fact, str) and fact.strip():
                chat_facts.append(fact.strip())
    user_facts: dict[int, list[str]] = {}
    for entry in parsed.get("user_facts") or []:
        if not isinstance(entry, dict):
            continue
        uid = entry.get("user_id")
        note = entry.get("note")
        if isinstance(uid, int) and isinstance(note, str) and note.strip():
            user_facts.setdefault(uid, []).append(note.strip())
    return chat_facts, user_facts


async def store_structured_memories(message: types.Message, targets: list[dict]) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        return
    summary = summarize_message_text(message)
    author_id = message.from_user.id if message.from_user else None
    author_name = get_display_name(message.from_user)
    db.add_chat_memory(message.chat.id, message.message_id, author_id, author_name, summary)

    chat_facts, user_facts = await extract_memory_facts(message, targets)
    for fact in chat_facts:
        db.add_chat_memory(message.chat.id, None, author_id, author_name, fact)

    for subject_id, notes in user_facts.items():
        for note in notes[:MAX_MEMORY_FACTS]:
            db.add_user_memory(message.chat.id, subject_id, author_id, note)

    if not chat_facts and not user_facts and targets and (message.text or message.caption):
        for target in targets:
            target_id = target.get("user_id")
            if not target_id:
                continue
            target_name = target.get("name") or (
                f"@{target.get('username')}" if target.get("username") else "этот пользователь"
            )
            note = f"{author_name} обычно заводит тему '{summary}' когда общается с {target_name}"
            db.add_user_memory(message.chat.id, target_id, author_id, note)


async def schedule_memory_capture(message: types.Message, targets: list[dict]) -> None:
    if not await should_capture_memory(message):
        return

    cloned_targets = [target.copy() for target in targets]

    async def _runner() -> None:
        try:
            await store_structured_memories(message, cloned_targets)
        except Exception as exc:
            logger.warning("Memory capture failed: %s", exc)

    asyncio.create_task(_runner())
