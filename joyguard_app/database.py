"""Database layer for JoyGuard."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from typing import Any

from .settings import CHAT_MEMORY_DB_LIMIT, CHAT_MEMORY_MESSAGE_CHAR_LIMIT


class Database:
    def __init__(self, db_name: str = "joyguard.db") -> None:
        self.db_name = db_name
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_name)

    def init_db(self) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                blocker_id INTEGER NOT NULL,
                blocked_id INTEGER NOT NULL,
                personal_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, blocker_id, blocked_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS global_autoresponders (
                user_id INTEGER PRIMARY KEY,
                message TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS support_bans (
                user_id INTEGER PRIMARY KEY,
                block_media INTEGER NOT NULL DEFAULT 0,
                block_all INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS global_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                blocker_id INTEGER NOT NULL,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, blocker_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS global_block_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                blocker_id INTEGER NOT NULL,
                allowed_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, blocker_id, allowed_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS last_support_time (
                user_id INTEGER PRIMARY KEY,
                last_message_time INTEGER NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                username_lower TEXT UNIQUE,
                first_name TEXT,
                last_name TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS swear_stats (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                author_id INTEGER,
                author_name TEXT,
                summary TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                subject_user_id INTEGER NOT NULL,
                source_user_id INTEGER,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, key)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, key)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                subject_user_id INTEGER NOT NULL,
                source_user_id INTEGER,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_styles (
                user_id INTEGER PRIMARY KEY,
                style TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
        conn.close()

    # Settings helpers -----------------------------------------------------
    def get_chat_setting(self, chat_id: int, key: str) -> str | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM chat_settings WHERE chat_id = ? AND key = ?",
            (chat_id, key),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def set_chat_setting(self, chat_id: int, key: str, value: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_settings (chat_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, key, value),
        )
        conn.commit()
        conn.close()

    def get_user_setting(self, user_id: int, key: str) -> str | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def set_user_setting(self, user_id: int, key: str, value: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, key, value),
        )
        conn.commit()
        conn.close()

    def delete_user_setting(self, user_id: int, key: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        conn.commit()
        conn.close()

    # Saved styles ---------------------------------------------------------
    def get_saved_styles(self, user_id: int) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, prompt, created_at FROM saved_styles WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {"id": row[0], "name": row[1], "prompt": row[2], "created_at": row[3]}
            for row in rows
        ]

    def get_saved_style(self, user_id: int, style_id: int) -> dict[str, Any] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, prompt, created_at FROM saved_styles WHERE user_id = ? AND id = ?",
            (user_id, style_id),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "prompt": row[2], "created_at": row[3]}

    def add_saved_style(self, user_id: int, name: str, prompt: str) -> dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO saved_styles (user_id, name, prompt) VALUES (?, ?, ?)",
            (user_id, name, prompt),
        )
        style_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"id": style_id, "name": name, "prompt": prompt}

    def delete_saved_style(self, user_id: int, style_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM saved_styles WHERE user_id = ? AND id = ?",
            (user_id, style_id),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    # Memories -------------------------------------------------------------
    def add_chat_memory(
        self,
        chat_id: int,
        message_id: int | None,
        author_id: int | None,
        author_name: str | None,
        summary: str,
    ) -> None:
        if not summary:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_memories (chat_id, message_id, author_id, author_name, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, message_id, author_id, author_name, summary[:CHAT_MEMORY_MESSAGE_CHAR_LIMIT]),
        )
        cursor.execute(
            """
            DELETE FROM chat_memories
            WHERE id NOT IN (
                SELECT id FROM chat_memories WHERE chat_id = ? ORDER BY id DESC LIMIT ?
            ) AND chat_id = ?
            """,
            (chat_id, CHAT_MEMORY_DB_LIMIT, chat_id),
        )
        conn.commit()
        conn.close()

    def get_chat_memories(self, chat_id: int, limit: int) -> list[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT summary FROM chat_memories WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def add_user_memory(
        self,
        chat_id: int,
        subject_user_id: int,
        source_user_id: int | None,
        note: str,
    ) -> None:
        if not note:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_memories (chat_id, subject_user_id, source_user_id, note)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, subject_user_id, source_user_id, note[:CHAT_MEMORY_MESSAGE_CHAR_LIMIT]),
        )
        conn.commit()
        conn.close()

    def get_user_memories(self, chat_id: int, user_id: int, limit: int) -> list[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT note FROM user_memories
            WHERE chat_id = ? AND subject_user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (chat_id, user_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    # Blocks ---------------------------------------------------------------
    def toggle_block(
        self,
        chat_id: int,
        blocker_id: int,
        blocked_id: int,
        personal_message: str | None = None,
    ) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM blocks
            WHERE chat_id = ? AND blocker_id = ? AND blocked_id = ?
            """,
            (chat_id, blocker_id, blocked_id),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                DELETE FROM blocks
                WHERE chat_id = ? AND blocker_id = ? AND blocked_id = ?
                """,
                (chat_id, blocker_id, blocked_id),
            )
            conn.commit()
            conn.close()
            return False

        cursor.execute(
            """
            INSERT INTO blocks (chat_id, blocker_id, blocked_id, personal_message)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, blocker_id, blocked_id, personal_message),
        )
        conn.commit()
        conn.close()
        return True

    def is_blocked(self, chat_id: int, blocker_id: int, blocked_id: int) -> tuple[bool, str | None]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT personal_message FROM blocks
            WHERE chat_id = ? AND blocker_id = ? AND blocked_id = ?
            """,
            (chat_id, blocker_id, blocked_id),
        )
        result = cursor.fetchone()
        conn.close()
        if result:
            return True, result[0]
        return False, None

    def get_chat_blocks(self, chat_id: int) -> list[tuple[int, int]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT blocker_id, blocked_id FROM blocks WHERE chat_id = ?",
            (chat_id,),
        )
        results = cursor.fetchall()
        conn.close()
        return results

    def get_blocks_by_blocker(self, chat_id: int, blocker_id: int) -> list[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT blocked_id FROM blocks WHERE chat_id = ? AND blocker_id = ?",
            (chat_id, blocker_id),
        )
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def toggle_global_block(self, chat_id: int, blocker_id: int, message: str | None = None) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM global_blocks WHERE chat_id = ? AND blocker_id = ?",
            (chat_id, blocker_id),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "DELETE FROM global_blocks WHERE chat_id = ? AND blocker_id = ?",
                (chat_id, blocker_id),
            )
            conn.commit()
            conn.close()
            return False

        cursor.execute(
            "INSERT INTO global_blocks (chat_id, blocker_id, message) VALUES (?, ?, ?)",
            (chat_id, blocker_id, message),
        )
        cursor.execute(
            "DELETE FROM global_block_exceptions WHERE chat_id = ? AND blocker_id = ?",
            (chat_id, blocker_id),
        )
        conn.commit()
        conn.close()
        return True

    def get_global_block(self, chat_id: int, blocker_id: int) -> tuple[bool, str | None]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT message FROM global_blocks WHERE chat_id = ? AND blocker_id = ?",
            (chat_id, blocker_id),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return False, None
        return True, row[0]

    def toggle_global_block_exception(self, chat_id: int, blocker_id: int, allowed_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM global_block_exceptions
            WHERE chat_id = ? AND blocker_id = ? AND allowed_id = ?
            """,
            (chat_id, blocker_id, allowed_id),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                """
                DELETE FROM global_block_exceptions
                WHERE chat_id = ? AND blocker_id = ? AND allowed_id = ?
                """,
                (chat_id, blocker_id, allowed_id),
            )
            conn.commit()
            conn.close()
            return False

        cursor.execute(
            """
            INSERT INTO global_block_exceptions (chat_id, blocker_id, allowed_id)
            VALUES (?, ?, ?)
            """,
            (chat_id, blocker_id, allowed_id),
        )
        conn.commit()
        conn.close()
        return True

    def is_global_block_exception(self, chat_id: int, blocker_id: int, allowed_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM global_block_exceptions
            WHERE chat_id = ? AND blocker_id = ? AND allowed_id = ?
            """,
            (chat_id, blocker_id, allowed_id),
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None

    # Profiles -------------------------------------------------------------
    def upsert_user_profile(self, user: Any) -> None:
        if user is None:
            return
        user_id = getattr(user, "id", None)
        if user_id is None:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        username = getattr(user, "username", None)
        username_lower = username.lower() if username else None
        first_name = getattr(user, "first_name", None)
        last_name = getattr(user, "last_name", None)
        cursor.execute(
            """
            INSERT INTO user_profiles (user_id, username, username_lower, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                username_lower = excluded.username_lower,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, username, username_lower, first_name, last_name),
        )
        conn.commit()
        conn.close()

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        if not username:
            return None
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, first_name, username FROM user_profiles WHERE username_lower = ?",
            (username.lower(),),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"user_id": row[0], "first_name": row[1], "username": row[2]}
        return None

    # Support --------------------------------------------------------------
    def can_send_support_message(self, user_id: int, cooldown_seconds: int = 30) -> tuple[bool, int]:
        conn = self.get_connection()
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute(
            "SELECT last_message_time FROM last_support_time WHERE user_id = ?",
            (user_id,),
        )
        result = cursor.fetchone()

        if result:
            last_time = result[0]
            time_passed = current_time - last_time
            if time_passed < cooldown_seconds:
                conn.close()
                return False, cooldown_seconds - time_passed

        cursor.execute(
            "INSERT OR REPLACE INTO last_support_time (user_id, last_message_time) VALUES (?, ?)",
            (user_id, current_time),
        )
        conn.commit()
        conn.close()
        return True, 0

    def save_support_message(self, user_id: int, message: str) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO support_messages (user_id, message) VALUES (?, ?)",
            (user_id, message),
        )
        conn.commit()
        conn.close()

    def get_support_ban(self, user_id: int) -> dict[str, bool] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT block_media, block_all FROM support_bans WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {"block_media": bool(row[0]), "block_all": bool(row[1])}

    def _upsert_support_ban(self, user_id: int, block_media: int, block_all: int) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_bans (user_id, block_media, block_all)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                block_media = excluded.block_media,
                block_all = excluded.block_all,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, block_media, block_all),
        )
        conn.commit()
        conn.close()

    def set_support_ban(
        self,
        user_id: int,
        *,
        block_media: bool | None = None,
        block_all: bool | None = None,
    ) -> dict[str, bool]:
        current = self.get_support_ban(user_id) or {"block_media": False, "block_all": False}
        new_media = block_media if block_media is not None else current["block_media"]
        new_all = block_all if block_all is not None else current["block_all"]
        self._upsert_support_ban(user_id, int(new_media), int(new_all))
        return {"block_media": new_media, "block_all": new_all}

    def toggle_support_media_ban(self, user_id: int) -> bool:
        current = self.get_support_ban(user_id) or {"block_media": False, "block_all": False}
        new_state = not current["block_media"]
        self._upsert_support_ban(user_id, int(new_state), int(current["block_all"]))
        return new_state

    def toggle_support_full_ban(self, user_id: int) -> bool:
        current = self.get_support_ban(user_id) or {"block_media": False, "block_all": False}
        new_state = not current["block_all"]
        self._upsert_support_ban(user_id, int(current["block_media"]), int(new_state))
        return new_state

    # Stats ----------------------------------------------------------------
    def increment_swear(self, chat_id: int, user_id: int, amount: int = 1) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO swear_stats (chat_id, user_id, count)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                count = count + excluded.count
            """,
            (chat_id, user_id, amount),
        )
        conn.commit()
        conn.close()

    def get_swear_ranking(self, chat_id: int, limit: int) -> list[tuple[int, int]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, count FROM swear_stats
            WHERE chat_id = ?
            ORDER BY count DESC, user_id ASC
            LIMIT ?
            """,
            (chat_id, limit),
        )
        results = cursor.fetchall()
        conn.close()
        return results


db = Database()
