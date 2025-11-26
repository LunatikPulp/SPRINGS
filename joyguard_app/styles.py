"""Helpers for managing AI styles and prompts."""

from __future__ import annotations

from typing import Any

from .database import db
from .settings import (
    AI_STYLE_PRESETS,
    CUSTOM_STYLE_KEY,
    CUSTOM_STYLE_MIN_LENGTH,
    CUSTOM_STYLE_MIN_WORDS,
    CUSTOM_STYLE_NAME_MAX_LENGTH,
    CUSTOM_STYLE_NAME_MIN_LENGTH,
    CUSTOM_STYLE_PROMPT_LIMIT,
    SAVED_STYLE_PREFIX,
    WORD_PATTERN,
    active_saved_style_cache,
    saved_styles_cache,
    user_custom_prompt_cache,
    user_style_cache,
)


def is_saved_style_key(style_key: str | None) -> bool:
    return isinstance(style_key, str) and style_key.startswith(SAVED_STYLE_PREFIX)


def extract_saved_style_id(style_key: str | None) -> int | None:
    if not is_saved_style_key(style_key):
        return None
    try:
        return int(style_key.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return None


def get_user_style(user_id: int | None) -> str | None:
    if not user_id:
        return None
    cached = user_style_cache.get(user_id)
    if cached in AI_STYLE_PRESETS or cached == CUSTOM_STYLE_KEY or is_saved_style_key(cached):
        return cached
    stored = db.get_user_setting(user_id, "ai_style")
    if stored in AI_STYLE_PRESETS or stored == CUSTOM_STYLE_KEY or is_saved_style_key(stored):
        user_style_cache[user_id] = stored
        return stored
    user_style_cache[user_id] = None
    return None


def set_active_saved_style(user_id: int, style_id: int | None) -> None:
    active_saved_style_cache[user_id] = style_id
    if style_id is None:
        db.delete_user_setting(user_id, "ai_style_saved_id")
    else:
        db.set_user_setting(user_id, "ai_style_saved_id", str(style_id))


def get_active_saved_style_id(user_id: int | None) -> int | None:
    if not user_id:
        return None
    if user_id in active_saved_style_cache:
        return active_saved_style_cache[user_id]
    stored = db.get_user_setting(user_id, "ai_style_saved_id")
    if stored is None:
        active_saved_style_cache[user_id] = None
        return None
    try:
        value = int(stored)
    except (TypeError, ValueError):
        value = None
    active_saved_style_cache[user_id] = value
    return value


def set_user_style(user_id: int, style_key: str, *, saved_style_id: int | None = None) -> None:
    user_style_cache[user_id] = style_key
    db.set_user_setting(user_id, "ai_style", style_key)
    set_active_saved_style(user_id, saved_style_id)


def reset_user_style(user_id: int) -> None:
    user_style_cache[user_id] = None
    user_custom_prompt_cache[user_id] = None
    db.delete_user_setting(user_id, "ai_style")
    db.delete_user_setting(user_id, "ai_style_custom_prompt")
    set_active_saved_style(user_id, None)


def get_user_custom_prompt(user_id: int | None) -> str | None:
    if not user_id:
        return None
    if user_id in user_custom_prompt_cache:
        return user_custom_prompt_cache[user_id]
    value = db.get_user_setting(user_id, "ai_style_custom_prompt")
    user_custom_prompt_cache[user_id] = value
    return value


def set_user_custom_prompt(user_id: int, prompt: str) -> None:
    cleaned = prompt.strip()
    trimmed = cleaned[:CUSTOM_STYLE_PROMPT_LIMIT]
    user_custom_prompt_cache[user_id] = trimmed
    db.set_user_setting(user_id, "ai_style_custom_prompt", trimmed)


def invalidate_saved_styles_cache(user_id: int) -> None:
    saved_styles_cache.pop(user_id, None)


def get_saved_styles(user_id: int) -> list[dict[str, Any]]:
    cached = saved_styles_cache.get(user_id)
    if cached is not None:
        return cached
    styles = db.get_saved_styles(user_id)
    saved_styles_cache[user_id] = styles
    return styles


def get_saved_style(user_id: int, style_id: int | None) -> dict[str, Any] | None:
    if style_id is None:
        return None
    for style in get_saved_styles(user_id):
        if style["id"] == style_id:
            return style
    style = db.get_saved_style(user_id, style_id)
    if style:
        invalidate_saved_styles_cache(user_id)
        saved_styles_cache[user_id] = db.get_saved_styles(user_id)
    return style


def add_saved_style(user_id: int, name: str, prompt: str) -> dict[str, Any]:
    style = db.add_saved_style(user_id, name, prompt)
    invalidate_saved_styles_cache(user_id)
    return style


def delete_saved_style(user_id: int, style_id: int) -> bool:
    deleted = db.delete_saved_style(user_id, style_id)
    if deleted:
        invalidate_saved_styles_cache(user_id)
    return deleted


def get_effective_ai_style(user_id: int | None, *, default: str) -> str:
    personal = get_user_style(user_id)
    if personal == CUSTOM_STYLE_KEY:
        return CUSTOM_STYLE_KEY
    if is_saved_style_key(personal):
        return personal
    if personal in AI_STYLE_PRESETS:
        return personal  # type: ignore[arg-type]
    return default


def validate_saved_style_name(name: str, user_id: int) -> tuple[bool, str | None]:
    text = (name or "").strip()
    if not text:
        return False, "Нужна осмысленная кличка для стиля."
    if text.startswith("/"):
        return False, "Не используй команды — просто напиши название."
    if len(text) < CUSTOM_STYLE_NAME_MIN_LENGTH:
        return False, f"Название должно быть хоть {CUSTOM_STYLE_NAME_MIN_LENGTH} символа."
    if len(text) > CUSTOM_STYLE_NAME_MAX_LENGTH:
        return False, f"Сократи название до {CUSTOM_STYLE_NAME_MAX_LENGTH} символов."
    lowered = text.lower()
    for style in get_saved_styles(user_id):
        if style["name"].lower() == lowered:
            return False, "У тебя уже есть стиль с таким именем."
    return True, None


async def validate_custom_style_prompt(prompt: str) -> tuple[bool, str | None]:
    text = (prompt or "").strip()
    if not text:
        return False, "Опиши характер словами, пустое сообщение не подойдёт."
    if text.startswith("/"):
        return False, "Не используй команды — просто опиши стиль общения."
    if len(text) < CUSTOM_STYLE_MIN_LENGTH:
        return False, f"Нужно минимум {CUSTOM_STYLE_MIN_LENGTH} символов. Сейчас вышло {len(text)}."
    if len(text) > CUSTOM_STYLE_PROMPT_LIMIT:
        return False, f"Ты превысил лимит {CUSTOM_STYLE_PROMPT_LIMIT} символов. Сократи описание."
    words = WORD_PATTERN.findall(text)
    if len(words) < CUSTOM_STYLE_MIN_WORDS:
        return False, f"Опиши стиль понятнее — нужно хотя бы {CUSTOM_STYLE_MIN_WORDS} слова."
    return True, None
