
import json
import sqlite3
from datetime import datetime

from mntu_app.config import DB_FILE

ANNOUNCEMENT_V2_PREFIX = "__ANNOUNCEMENT_V2__:"
DEFAULT_ADMIN_EMAIL = "n.biloshickii@istu.edu.ua"

SETTINGS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    notifications_enabled INTEGER,
    notify_minutes INTEGER,
    notify_group TEXT
)
"""


def _ensure_settings_column(c: sqlite3.Cursor, column_name: str, column_def: str):
    c.execute("PRAGMA table_info(settings)")
    cols = {row[1] for row in c.fetchall()}
    if column_name not in cols:
        c.execute(f"ALTER TABLE settings ADD COLUMN {column_name} {column_def}")


def _ensure_table_column(c: sqlite3.Cursor, table_name: str, column_name: str, column_def: str):
    c.execute(f"PRAGMA table_info({table_name})")
    cols = {row[1] for row in c.fetchall()}
    if column_name not in cols:
        c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(SETTINGS_TABLE_SCHEMA)
    _ensure_settings_column(c, "theme", "TEXT DEFAULT 'green'")
    _ensure_settings_column(c, "custom_accent", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "user_role", "TEXT DEFAULT 'Студент'")
    _ensure_settings_column(c, "last_seen_announcement_id", "INTEGER DEFAULT 0")
    _ensure_settings_column(c, "telegram_enabled", "INTEGER DEFAULT 0")
    _ensure_settings_column(c, "telegram_bot_token", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "telegram_chat_id", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "auth_required", "INTEGER DEFAULT 1")
    _ensure_settings_column(c, "tg_auth_verified", "INTEGER DEFAULT 0")
    _ensure_settings_column(c, "first_name", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "last_name", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "middle_name", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "tg_login_code", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "tg_login_code_expires_at", "TEXT DEFAULT ''")
    _ensure_settings_column(c, "email", "TEXT DEFAULT ''")
    conn.commit()
    c.execute("UPDATE settings SET last_seen_announcement_id = 0 WHERE last_seen_announcement_id IS NULL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_json TEXT NOT NULL,
            group_options TEXT NOT NULL,
            week_options TEXT NOT NULL,
            week_dates TEXT NOT NULL,
            saved_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS shown_notifications (
            date_str TEXT NOT NULL,
            time_str TEXT NOT NULL,
            subject TEXT NOT NULL,
            notification_date TEXT DEFAULT (date('now','localtime')),
            PRIMARY KEY (date_str, time_str, subject, notification_date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            items_json TEXT NOT NULL,
            saved_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            last_name TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            middle_name TEXT DEFAULT '',
            role TEXT DEFAULT 'Студент',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    _ensure_table_column(c, "users", "email", "TEXT DEFAULT ''")
    _ensure_table_column(c, "users", "last_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "users", "first_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "users", "middle_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "users", "role", "TEXT DEFAULT 'Студент'")
    _ensure_table_column(c, "users", "created_at", "TEXT DEFAULT ''")
    _ensure_table_column(c, "users", "updated_at", "TEXT DEFAULT ''")
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS role_change_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            last_name TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            middle_name TEXT DEFAULT '',
            current_role TEXT DEFAULT 'Студент',
            requested_role TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            reviewed_at TEXT DEFAULT '',
            reviewed_by TEXT DEFAULT '',
            review_comment TEXT DEFAULT ''
        )
        """
    )
    _ensure_table_column(c, "role_change_requests", "email", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "last_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "first_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "middle_name", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "current_role", "TEXT DEFAULT 'Студент'")
    _ensure_table_column(c, "role_change_requests", "requested_role", "TEXT DEFAULT 'Викладач'")
    _ensure_table_column(c, "role_change_requests", "status", "TEXT DEFAULT 'pending'")
    _ensure_table_column(c, "role_change_requests", "created_at", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "reviewed_at", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "reviewed_by", "TEXT DEFAULT ''")
    _ensure_table_column(c, "role_change_requests", "review_comment", "TEXT DEFAULT ''")
    c.execute("UPDATE users SET created_at = datetime('now','localtime') WHERE COALESCE(created_at, '') = ''")
    c.execute("UPDATE users SET updated_at = datetime('now','localtime') WHERE COALESCE(updated_at, '') = ''")
    c.execute("UPDATE role_change_requests SET created_at = datetime('now','localtime') WHERE COALESCE(created_at, '') = ''")
    c.execute("UPDATE settings SET theme = 'green' WHERE theme IS NULL")
    c.execute("UPDATE settings SET user_role = 'Студент' WHERE user_role IS NULL")
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO settings (notifications_enabled, notify_minutes, notify_group, theme, user_role) VALUES (?, ?, ?, ?, ?)",
            (1, 10, "", "green", "Студент"),
        )
    conn.commit()
    conn.close()


def load_settings():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT notifications_enabled, notify_minutes, notify_group, "
        "COALESCE(theme, 'green'), COALESCE(custom_accent, ''), COALESCE(user_role, 'Студент'), "
        "COALESCE(telegram_enabled, 0), COALESCE(telegram_bot_token, ''), COALESCE(telegram_chat_id, ''), "
        "COALESCE(auth_required, 1), COALESCE(tg_auth_verified, 0), "
        "COALESCE(first_name, ''), COALESCE(last_name, ''), COALESCE(middle_name, ''), "
        "COALESCE(tg_login_code, ''), COALESCE(tg_login_code_expires_at, ''), "
        "COALESCE(email, '') "
        "FROM settings WHERE id = 1"
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "notifications_enabled": bool(row[0]),
            "notify_minutes": row[1],
            "notify_group": row[2],
            "theme": row[3] if len(row) > 3 else "green",
            "custom_accent": row[4] if len(row) > 4 else "",
            "user_role": row[5] if len(row) > 5 else "Студент",
            "telegram_enabled": bool(row[6]) if len(row) > 6 else False,
            "telegram_bot_token": row[7] if len(row) > 7 else "",
            "telegram_chat_id": row[8] if len(row) > 8 else "",
            "auth_required": bool(row[9]) if len(row) > 9 else True,
            "tg_auth_verified": bool(row[10]) if len(row) > 10 else False,
            "first_name": row[11] if len(row) > 11 else "",
            "last_name": row[12] if len(row) > 12 else "",
            "middle_name": row[13] if len(row) > 13 else "",
            "tg_login_code": row[14] if len(row) > 14 else "",
            "tg_login_code_expires_at": row[15] if len(row) > 15 else "",
            "email": row[16] if len(row) > 16 else "",
        }
    return {
        "notifications_enabled": True,
        "notify_minutes": 120,
        "notify_group": "",
        "theme": "green",
        "custom_accent": "",
        "user_role": "Студент",
        "telegram_enabled": False,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "auth_required": True,
        "tg_auth_verified": False,
        "first_name": "",
        "last_name": "",
        "middle_name": "",
        "tg_login_code": "",
        "tg_login_code_expires_at": "",
        "email": "",
    }


def clear_schedule_cache():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM schedule_data")
    conn.commit()
    conn.close()


def save_schedule_to_db(schedule_data: dict, group_options: list, week_options: list, week_dates: dict):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    schedule_json = json.dumps(schedule_data, ensure_ascii=False)
    group_options_json = json.dumps(group_options, ensure_ascii=False)
    week_options_json = json.dumps(week_options, ensure_ascii=False)
    week_dates_json = json.dumps(week_dates, ensure_ascii=False)
    c.execute("DELETE FROM schedule_data")
    c.execute(
        "INSERT INTO schedule_data (schedule_json, group_options, week_options, week_dates) VALUES (?, ?, ?, ?)",
        (schedule_json, group_options_json, week_options_json, week_dates_json),
    )
    conn.commit()
    conn.close()


def load_schedule_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT schedule_json, group_options, week_options, week_dates FROM schedule_data ORDER BY saved_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return (
                json.loads(row[0]),
                json.loads(row[1]),
                json.loads(row[2]),
                json.loads(row[3]),
            )
        except (json.JSONDecodeError, TypeError):
            return None, None, None, None
    return None, None, None, None


def save_settings_to_db(
    notifications_enabled: bool,
    notify_minutes: int,
    notify_group: str,
    theme: str = None,
    user_role: str = None,
):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if theme is not None and user_role is not None:
        c.execute(
            "UPDATE settings SET notifications_enabled = ?, notify_minutes = ?, notify_group = ?, theme = ?, user_role = ? WHERE id = 1",
            (1 if notifications_enabled else 0, notify_minutes, notify_group, theme, user_role),
        )
    elif theme is not None:
        c.execute(
            "UPDATE settings SET notifications_enabled = ?, notify_minutes = ?, notify_group = ?, theme = ? WHERE id = 1",
            (1 if notifications_enabled else 0, notify_minutes, notify_group, theme),
        )
    else:
        c.execute(
            "UPDATE settings SET notifications_enabled = ?, notify_minutes = ?, notify_group = ? WHERE id = 1",
            (1 if notifications_enabled else 0, notify_minutes, notify_group),
        )
    conn.commit()
    conn.close()


def save_theme_to_db(theme: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET theme = ? WHERE id = 1", (theme,))
    conn.commit()
    conn.close()


def save_user_role_to_db(role: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET user_role = ? WHERE id = 1", (role,))
    conn.commit()
    conn.close()


def save_custom_accent(hex_color: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET theme = 'custom', custom_accent = ? WHERE id = 1", (hex_color,))
    conn.commit()
    conn.close()


def save_telegram_settings(enabled: bool, bot_token: str, chat_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "UPDATE settings SET telegram_enabled = ?, telegram_bot_token = ?, telegram_chat_id = ? WHERE id = 1",
        (1 if enabled else 0, (bot_token or "").strip(), (chat_id or "").strip()),
    )
    conn.commit()
    conn.close()


def save_telegram_auth_profile(
    *,
    auth_required: bool | None = None,
    verified: bool | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None,
    login_code: str | None = None,
    login_code_expires_at: str | None = None,
    email: str | None = None,
):
    fields = []
    values = []
    if auth_required is not None:
        fields.append("auth_required = ?")
        values.append(1 if auth_required else 0)
    if verified is not None:
        fields.append("tg_auth_verified = ?")
        values.append(1 if verified else 0)
    if first_name is not None:
        fields.append("first_name = ?")
        values.append((first_name or "").strip())
    if last_name is not None:
        fields.append("last_name = ?")
        values.append((last_name or "").strip())
    if middle_name is not None:
        fields.append("middle_name = ?")
        values.append((middle_name or "").strip())
    if login_code is not None:
        fields.append("tg_login_code = ?")
        values.append((login_code or "").strip())
    if login_code_expires_at is not None:
        fields.append("tg_login_code_expires_at = ?")
        values.append((login_code_expires_at or "").strip())
    if email is not None:
        fields.append("email = ?")
        values.append((email or "").strip().lower())
    if not fields:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"UPDATE settings SET {', '.join(fields)} WHERE id = 1", values)
    conn.commit()
    conn.close()


def _pack_announcement_payload(
    message: str,
    title: str = "",
    target_group: str = "",
    target_groups: list[str] | None = None,
    author_name: str = "",
    author_role: str = "",
    attachment_name: str = "",
    attachment_path: str = "",
) -> str:
    groups = [g.strip() for g in (target_groups or []) if (g or "").strip()]
    if not groups and (target_group or "").strip():
        groups = [(target_group or "").strip()]
    payload = {
        "title": (title or "").strip(),
        "text": (message or "").strip(),
        "target_group": (target_group or "").strip(),
        "target_groups": groups,
        "author_name": (author_name or "").strip(),
        "author_role": (author_role or "").strip(),
        "attachment_name": (attachment_name or "").strip(),
        "attachment_path": (attachment_path or "").strip(),
    }
    return ANNOUNCEMENT_V2_PREFIX + json.dumps(payload, ensure_ascii=False)


def _unpack_announcement_payload(raw_message: str) -> dict:
    msg = (raw_message or "").strip()
    if msg.startswith(ANNOUNCEMENT_V2_PREFIX):
        payload_raw = msg[len(ANNOUNCEMENT_V2_PREFIX) :]
        try:
            parsed = json.loads(payload_raw)
            return {
                "title": (parsed.get("title") or "").strip(),
                "text": (parsed.get("text") or "").strip(),
                "target_group": (parsed.get("target_group") or "").strip(),
                "target_groups": [g.strip() for g in (parsed.get("target_groups") or []) if (g or "").strip()],
                "author_name": (parsed.get("author_name") or "").strip(),
                "author_role": (parsed.get("author_role") or "").strip(),
                "attachment_name": (parsed.get("attachment_name") or "").strip(),
                "attachment_path": (parsed.get("attachment_path") or "").strip(),
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "title": "",
        "text": msg,
        "target_group": "",
        "target_groups": [],
        "author_name": "",
        "author_role": "",
        "attachment_name": "",
        "attachment_path": "",
    }


def _announcement_display_text(meta: dict) -> str:
    title = (meta.get("title") or "").strip()
    text = (meta.get("text") or "").strip()
    target_group = (meta.get("target_group") or "").strip()
    target_groups = [g.strip() for g in (meta.get("target_groups") or []) if (g or "").strip()]
    if not target_groups and target_group:
        target_groups = [target_group]
    author_name = (meta.get("author_name") or "").strip()
    author_role = (meta.get("author_role") or "").strip()
    attachment_name = (meta.get("attachment_name") or "").strip()
    parts = []
    if title:
        parts.append(title)
    if text:
        parts.append(text)
    if target_groups:
        if len(target_groups) == 1:
            parts.append(f"Група: {target_groups[0]}")
        else:
            parts.append(f"Групи: {', '.join(target_groups)}")
    if author_name:
        suffix = f" ({author_role})" if author_role else ""
        parts.append(f"Автор: {author_name}{suffix}")
    if attachment_name:
        parts.append(f"Файл: {attachment_name}")
    return "\n".join(parts).strip()


def _split_group_tokens(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _group_matches(selected_group: str, announcement_groups: list[str]) -> bool:
    sg = (selected_group or "").strip()
    if not sg:
        return True
    if not announcement_groups:
        return True
    if sg in announcement_groups:
        return True
    selected_tokens = _split_group_tokens(sg)
    ann_tokens: list[str] = []
    for g in announcement_groups:
        ann_tokens.extend(_split_group_tokens(g))
    if not selected_tokens:
        selected_tokens = [sg]
    if not ann_tokens:
        ann_tokens = list(announcement_groups)
    return any(t in ann_tokens for t in selected_tokens)


def save_announcement(
    message: str,
    title: str = "",
    target_group: str = "",
    target_groups: list[str] | None = None,
    author_name: str = "",
    author_role: str = "",
    attachment_name: str = "",
    attachment_path: str = "",
):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    packed = _pack_announcement_payload(
        message,
        title=title,
        target_group=target_group,
        target_groups=target_groups,
        author_name=author_name,
        author_role=author_role,
        attachment_name=attachment_name,
        attachment_path=attachment_path,
    )
    c.execute("INSERT INTO announcements (message) VALUES (?)", (packed,))
    conn.commit()
    conn.close()


def get_unread_announcements(target_group: str = "", include_meta: bool = False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COALESCE(last_seen_announcement_id, 0) FROM settings WHERE id = 1")
    row = c.fetchone()
    last_seen = row[0] if row else 0
    c.execute("SELECT id, message, created_at FROM announcements WHERE id > ? ORDER BY id ASC", (last_seen,))
    rows = c.fetchall()
    conn.close()
    out = []
    group = (target_group or "").strip()
    for aid, raw_message, created_at in rows:
        meta = _unpack_announcement_payload(raw_message or "")
        ann_groups = [g.strip() for g in (meta.get("target_groups") or []) if (g or "").strip()]
        ann_group = (meta.get("target_group") or "").strip()
        if not ann_groups and ann_group:
            ann_groups = [ann_group]
        if not _group_matches(group, ann_groups):
            continue
        display = _announcement_display_text(meta) or (raw_message or "").strip()
        if include_meta:
            out.append((aid, display, created_at, meta))
        else:
            out.append((aid, display, created_at))
    return out


def get_all_announcements(target_group: str = "", include_meta: bool = False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, message, created_at FROM announcements ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    out = []
    group = (target_group or "").strip()
    for aid, raw_message, created_at in rows:
        meta = _unpack_announcement_payload(raw_message or "")
        ann_groups = [g.strip() for g in (meta.get("target_groups") or []) if (g or "").strip()]
        ann_group = (meta.get("target_group") or "").strip()
        if not ann_groups and ann_group:
            ann_groups = [ann_group]
        if not _group_matches(group, ann_groups):
            continue
        display = _announcement_display_text(meta) or (raw_message or "").strip()
        if include_meta:
            out.append((aid, display, created_at, meta))
        else:
            out.append((aid, display, created_at))
    return out


def mark_announcements_seen(up_to_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET last_seen_announcement_id = ? WHERE id = 1", (up_to_id,))
    conn.commit()
    conn.close()


def get_shown_notifications_for_today():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    c.execute("SELECT date_str, time_str, subject FROM shown_notifications WHERE notification_date = ?", (today,))
    rows = c.fetchall()
    conn.close()
    return {(r[0], r[1], r[2]) for r in rows}


def mark_notification_shown(date_str: str, time_str: str, subject: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    try:
        c.execute(
            "INSERT OR IGNORE INTO shown_notifications (date_str, time_str, subject, notification_date) VALUES (?, ?, ?, ?)",
            (date_str, time_str, subject, today),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def clear_today_notifications():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    try:
        c.execute("DELETE FROM shown_notifications WHERE notification_date = ?", (today,))
        conn.commit()
        print("[NOTIFICATION] Очищено записи про показані сьогодні уведомлення")
    except Exception as e:
        print(f"[ERROR] Помилка очищення уведомлень: {e}")
    finally:
        conn.close()


def delete_announcements(announcement_ids: list[int]):
    if not announcement_ids:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    placeholders = ",".join("?" * len(announcement_ids))
    c.execute(f"DELETE FROM announcements WHERE id IN ({placeholders})", announcement_ids)
    conn.commit()
    conn.close()


def upsert_user_profile(email: str, last_name: str, first_name: str, middle_name: str, role: str = "Студент"):
    em = (email or "").strip().lower()
    if not em:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO users (email, last_name, first_name, middle_name, role, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(email) DO UPDATE SET
            last_name = excluded.last_name,
            first_name = excluded.first_name,
            middle_name = excluded.middle_name,
            role = excluded.role,
            updated_at = datetime('now','localtime')
        """,
        ((email or "").strip().lower(), (last_name or "").strip(), (first_name or "").strip(), (middle_name or "").strip(), (role or "Студент").strip()),
    )
    conn.commit()
    conn.close()


def create_role_change_request(
    *,
    email: str,
    last_name: str,
    first_name: str,
    middle_name: str,
    current_role: str,
    requested_role: str,
):
    em = (email or "").strip().lower()
    req = (requested_role or "").strip()
    if not em or not req:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO role_change_requests
        (email, last_name, first_name, middle_name, current_role, requested_role, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (em, (last_name or "").strip(), (first_name or "").strip(), (middle_name or "").strip(), (current_role or "Студент").strip(), req),
    )
    conn.commit()
    conn.close()


def get_pending_role_requests(limit: int = 20) -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, email, last_name, first_name, middle_name, current_role, requested_role, created_at
        FROM role_change_requests
        WHERE status = 'pending'
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "email": r[1],
            "last_name": r[2],
            "first_name": r[3],
            "middle_name": r[4],
            "current_role": r[5],
            "requested_role": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]


def review_role_request(request_id: int, approved: bool, reviewer_email: str = "", comment: str = "") -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, email, requested_role, status, last_name, first_name, middle_name
        FROM role_change_requests WHERE id = ?
        """,
        (int(request_id),),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    if row[3] != "pending":
        conn.close()
        return {"id": row[0], "email": row[1], "requested_role": row[2], "status": row[3]}
    new_status = "approved" if approved else "rejected"
    c.execute(
        """
        UPDATE role_change_requests
        SET status = ?, reviewed_at = datetime('now','localtime'), reviewed_by = ?, review_comment = ?
        WHERE id = ?
        """,
        (new_status, (reviewer_email or "").strip().lower(), (comment or "").strip(), int(request_id)),
    )
    if approved:
        c.execute(
            """
            INSERT INTO users (email, last_name, first_name, middle_name, role, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(email) DO UPDATE SET
                role = excluded.role,
                updated_at = datetime('now','localtime')
            """,
            (row[1], row[4], row[5], row[6], row[2]),
        )
    conn.commit()
    conn.close()
    return {"id": row[0], "email": row[1], "requested_role": row[2], "status": new_status}


def set_user_role_by_email(email: str, role: str) -> bool:
    em = (email or "").strip().lower()
    if not em:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO users (email, role, updated_at)
        VALUES (?, ?, datetime('now','localtime'))
        ON CONFLICT(email) DO UPDATE SET role = excluded.role, updated_at = datetime('now','localtime')
        """,
        (em, (role or "Студент").strip()),
    )
    conn.commit()
    conn.close()
    return True


def get_user_role_by_email(email: str) -> str | None:
    em = (email or "").strip().lower()
    if not em:
        return None
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE email = ? LIMIT 1", (em,))
    row = c.fetchone()
    conn.close()
    return (row[0] if row else None) or None
