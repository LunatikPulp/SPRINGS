"""Chat rules management for JoyGuard."""

from __future__ import annotations

RULES_LAST_REQUEST_KEY = "rules_last_request"

import re
import time
from typing import Any

from .database import db
from .settings import (
    RULES_AUTO_REQUEST_COOLDOWN,
    RULES_CAPTURE_TIMEOUT,
    chat_rules_cache,
    logger,
    pending_rules_requests,
)

RULE_LINE_RE = re.compile(r"^\s*(\d+(?:\.\d+)*|[•\*-])\s*[\).\:-]?\s*(.+)$")


def parse_rules_text(raw_text: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    if not raw_text:
        return rules

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = RULE_LINE_RE.match(stripped)
        if match:
            number = match.group(1)
            body = match.group(2).strip() or stripped
            rules.append({"id": number, "text": body})
        elif rules:
            rules[-1]["text"] = f"{rules[-1]['text']} {stripped}".strip()
        else:
            rules.append({"id": f"R{len(rules) + 1}", "text": stripped})
    return rules


def _set_cache(chat_id: int, raw_text: str, parsed_rules: list[dict[str, str]]) -> None:
    chat_rules_cache[chat_id] = {
        "raw_text": raw_text,
        "parsed": parsed_rules,
        "cached_at": time.time(),
    }


def get_cached_rules(chat_id: int) -> dict[str, Any] | None:
    return chat_rules_cache.get(chat_id)


def load_rules(chat_id: int) -> dict[str, Any] | None:
    cached = get_cached_rules(chat_id)
    if cached:
        return cached
    stored = db.get_chat_rules(chat_id)
    if not stored:
        return None
    parsed = stored.get("parsed") or []
    raw = stored.get("raw_text") or ""
    _set_cache(chat_id, raw, parsed)
    return chat_rules_cache.get(chat_id)


def start_rules_capture(chat_id: int, requested_by: int | None = None) -> None:
    pending_rules_requests[chat_id] = {"ts": time.time(), "by": requested_by}


def is_rules_capture_active(chat_id: int) -> bool:
    data = pending_rules_requests.get(chat_id)
    if not data:
        return False
    if time.time() - data.get("ts", 0) > RULES_CAPTURE_TIMEOUT:
        pending_rules_requests.pop(chat_id, None)
        logger.info("Rules capture for chat %s expired due to timeout", chat_id)
        return False
    return True


def cancel_rules_capture(chat_id: int) -> None:
    pending_rules_requests.pop(chat_id, None)


def capture_rules_text(chat_id: int, raw_text: str) -> list[dict[str, str]]:
    parsed = parse_rules_text(raw_text)
    db.save_chat_rules(chat_id, raw_text, parsed)
    _set_cache(chat_id, raw_text, parsed)
    cancel_rules_capture(chat_id)
    logger.info("Stored %s rules for chat %s", len(parsed), chat_id)
    return parsed


def get_rules_excerpt(chat_id: int, limit: int = 6) -> str | None:
    entry = load_rules(chat_id)
    if not entry:
        return None
    parsed: list[dict[str, str]] = entry.get("parsed", [])
    if not parsed:
        raw_text = entry.get("raw_text", "").strip()
        return raw_text[:400] if raw_text else None
    lines = []
    for rule in parsed[:limit]:
        rid = rule.get("id") or "•"
        text = rule.get("text") or ""
        lines.append(f"{rid}. {text}")
    return "\n".join(lines)


def get_rules_for_debate(chat_id: int, limit: int = 8) -> list[dict[str, str]]:
    entry = load_rules(chat_id)
    if not entry:
        return []
    parsed: list[dict[str, str]] = entry.get("parsed", [])
    return parsed[:limit]


def has_rules(chat_id: int) -> bool:
    entry = load_rules(chat_id)
    return bool(entry and (entry.get("parsed") or entry.get("raw_text")))


def _get_last_request_ts(chat_id: int) -> int | None:
    value = db.get_chat_setting(chat_id, RULES_LAST_REQUEST_KEY)
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mark_rules_request(chat_id: int) -> None:
    db.set_chat_setting(chat_id, RULES_LAST_REQUEST_KEY, str(int(time.time())))


def should_request_rules(chat_id: int) -> bool:
    if is_rules_capture_active(chat_id):
        return False
    if has_rules(chat_id):
        return False
    last_ts = _get_last_request_ts(chat_id)
    if last_ts and time.time() - last_ts < RULES_AUTO_REQUEST_COOLDOWN:
        return False
    return True
