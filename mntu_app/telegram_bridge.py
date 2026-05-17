
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

import requests
from mntu_app.database import DEFAULT_ADMIN_EMAIL, get_pending_role_requests, review_role_request


class TelegramBridge:
    def __init__(
        self,
        *,
        get_state: Callable[[], dict],
        apply_updates: Callable[[dict], None],
        get_groups: Callable[[], list[str]],
    ):
        self._get_state = get_state
        self._apply_updates = apply_updates
        self._get_groups = get_groups
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._offset = 0
        self._session = requests.Session()
        self._chat_state: dict[str, dict] = {}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def notify(self, message: str):
        state = self._get_state() or {}
        if not state.get("telegram_enabled"):
            return
        token = (state.get("telegram_bot_token") or "").strip()
        chat_id = (state.get("telegram_chat_id") or "").strip()
        if not token or not chat_id:
            return
        self._send_message(token, chat_id, message)

    def _api_url(self, token: str, method: str) -> str:
        return f"https://api.telegram.org/bot{token}/{method}"

    def _main_keyboard(self) -> dict:
        return {
            "keyboard": [
                [{"text": "📊 Статус"}, {"text": "👥 Групи"}],
                [{"text": "🔄 Змінити групу"}, {"text": "🕒 Змінити час"}],
                [{"text": "📢 Надіслати повідомлення"}],
                [{"text": "🔎 Парсинг груп"}],
                [{"text": "🛡 Заявки (адмін)"}],
                [{"text": "🔔 Сповіщення ON"}, {"text": "🔕 Сповіщення OFF"}],
                [{"text": "❓ Допомога"}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        }

    def _send_message(self, token: str, chat_id: str, text: str, reply_markup: dict | None = None):
        keyboard = {
            **(reply_markup or self._main_keyboard()),
        }
        try:
            self._session.post(
                self._api_url(token, "sendMessage"),
                json={"chat_id": chat_id, "text": text[:3900], "reply_markup": keyboard},
                timeout=10,
            )
        except Exception:
            pass

    def _send_group_picker(self, token: str, chat_id: str):
        groups = self._get_groups() or []
        if not groups:
            self._send_message(token, chat_id, "Список груп порожній. Спочатку завантажте розклад у додатку.")
            return
        rows = []
        for i in range(0, min(len(groups), 30), 2):
            row = [{"text": f"🎓 {groups[i]}"}]
            if i + 1 < min(len(groups), 30):
                row.append({"text": f"🎓 {groups[i + 1]}"})
            rows.append(row)
        rows.append([{"text": "↩️ Скасувати"}])
        self._chat_state.setdefault(chat_id, {})["awaiting_group"] = True
        self._send_message(
            token,
            chat_id,
            "Оберіть групу кнопкою нижче:",
            reply_markup={"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True},
        )

    def _send_time_picker(self, token: str, chat_id: str):
        self._chat_state.setdefault(chat_id, {})["awaiting_time"] = True
        self._send_message(
            token,
            chat_id,
            "Оберіть час нагадування:",
            reply_markup={
                "keyboard": [
                    [{"text": "⏱ 5 хв"}, {"text": "⏱ 10 хв"}, {"text": "⏱ 15 хв"}],
                    [{"text": "⏱ 30 хв"}, {"text": "⏱ 45 хв"}, {"text": "⏱ 60 хв"}],
                    [{"text": "✍️ Свій час"}],
                    [{"text": "↩️ Скасувати"}],
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    def _multi_group_keyboard(self) -> dict:
        groups = self._get_groups() or []
        rows = [[{"text": "✅ Завершити вибір"}, {"text": "👀 Обрано"}], [{"text": "↩️ Скасувати"}]]
        for i in range(0, min(len(groups), 40), 2):
            row = [{"text": f"🎓 {groups[i]}"}]
            if i + 1 < min(len(groups), 40):
                row.append({"text": f"🎓 {groups[i + 1]}"})
            rows.append(row)
        return {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True}

    def _poll_loop(self):
        while not self._stop_event.is_set():
            state = self._get_state() or {}
            if not state.get("telegram_enabled"):
                time.sleep(2)
                continue
            token = (state.get("telegram_bot_token") or "").strip()
            if not token:
                time.sleep(2)
                continue
            try:
                response = self._session.get(
                    self._api_url(token, "getUpdates"),
                    params={"timeout": 25, "offset": self._offset},
                    timeout=35,
                )
                data = response.json()
                if not data.get("ok"):
                    time.sleep(2)
                    continue
                for upd in data.get("result", []):
                    self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
                    self._handle_update(token, upd)
            except Exception:
                time.sleep(2)

    def _handle_update(self, token: str, update: dict):
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", "")).strip()
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            return

        state = self._get_state() or {}
        known_chat = (state.get("telegram_chat_id") or "").strip()
        if not known_chat:
            self._apply_updates({"telegram_chat_id": chat_id})
            known_chat = chat_id
            self._send_message(token, chat_id, "Чат прив'язано. Тепер можете керувати налаштуваннями через бота.")

        if known_chat != chat_id:
            self._send_message(token, chat_id, "Цей чат не прив'язаний до додатка.")
            return

        cmd = text.split()[0].lower()
        text_lower = text.lower()
        button_map = {
            "📊 статус": "/status",
            "👥 групи": "/groups",
            "🔄 змінити групу": "/group_pick",
            "🕒 змінити час": "/time_pick",
            "📢 надіслати повідомлення": "/announce_pick",
            "🔎 парсинг груп": "/parse_groups",
            "🛡 заявки (адмін)": "/requests",
            "🔔 сповіщення on": "/notify on",
            "🔕 сповіщення off": "/notify off",
            "❓ допомога": "/help",
        }
        if text_lower in button_map:
            mapped = button_map[text_lower]
            cmd = mapped.split()[0].lower()
            text = mapped
        role = (state.get("user_role") or "Студент").strip()
        user_email = (state.get("email") or "").strip().lower()
        is_admin = role == "Адміністратор" or user_email == DEFAULT_ADMIN_EMAIL
        is_teacher = role == "Викладач"

        def denied(required_role: str):
            self._send_message(token, chat_id, f"Недостатньо прав. Потрібна роль: {required_role}. Ваша роль: {role}.")

        def normalize_role(raw: str) -> str | None:
            value = (raw or "").strip().lower()
            mapping = {
                "student": "Студент",
                "студент": "Студент",
                "ученик": "Студент",
                "учень": "Студент",
                "teacher": "Викладач",
                "викладач": "Викладач",
                "преподаватель": "Викладач",
                "админ": "Адміністратор",
                "admin": "Адміністратор",
                "адміністратор": "Адміністратор",
            }
            return mapping.get(value)

        chat_flow = self._chat_state.get(chat_id, {})
        if chat_flow.get("awaiting_group"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_group"] = False
                self._send_message(token, chat_id, "Вибір групи скасовано.")
                return
            if text.startswith("🎓 "):
                selected = text[2:].strip()
                groups = self._get_groups() or []
                if groups and selected in groups:
                    self._chat_state[chat_id]["awaiting_group"] = False
                    self._apply_updates({"notify_group": selected})
                    self._send_message(token, chat_id, f"Групу оновлено: {selected}. Можна далі писати повідомлення.")
                else:
                    self._send_message(token, chat_id, "Такої групи немає в списку. Оберіть кнопку зі списку.")
                return
        if chat_flow.get("awaiting_time"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_time"] = False
                self._send_message(token, chat_id, "Вибір часу скасовано.")
                return
            if text_lower == "✍️ свій час":
                self._chat_state[chat_id]["awaiting_time"] = False
                self._chat_state.setdefault(chat_id, {})["awaiting_custom_time"] = True
                self._send_message(
                    token,
                    chat_id,
                    "Введіть свій час у хвилинах (1..180), наприклад: 25",
                    reply_markup={
                        "keyboard": [[{"text": "↩️ Скасувати"}]],
                        "resize_keyboard": True,
                        "one_time_keyboard": True,
                    },
                )
                return
            if text.startswith("⏱"):
                candidate = text.replace("⏱", "").replace("хв", "").strip()
                try:
                    minutes = max(1, min(180, int(candidate)))
                    self._chat_state[chat_id]["awaiting_time"] = False
                    self._apply_updates({"notify_minutes": minutes})
                    self._send_message(token, chat_id, f"Час нагадування змінено: {minutes} хв.")
                except (TypeError, ValueError):
                    self._send_message(token, chat_id, "Оберіть один із запропонованих варіантів.")
                return
        if chat_flow.get("awaiting_custom_time"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_custom_time"] = False
                self._send_message(token, chat_id, "Введення власного часу скасовано.")
                return
            try:
                minutes = max(1, min(180, int(text.strip())))
                self._chat_state[chat_id]["awaiting_custom_time"] = False
                self._apply_updates({"notify_minutes": minutes})
                self._send_message(token, chat_id, f"Час нагадування змінено: {minutes} хв.")
            except (TypeError, ValueError):
                self._send_message(token, chat_id, "Введіть число хвилин, наприклад: 25")
            return
        if chat_flow.get("awaiting_announce"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce"] = False
                self._send_message(token, chat_id, "Надсилання повідомлення скасовано.")
                return
            if not (is_teacher or is_admin):
                self._chat_state[chat_id]["awaiting_announce"] = False
                denied("Викладач або Адміністратор")
                return
            body = text.strip()
            if len(body) < 2:
                self._send_message(token, chat_id, "Текст занадто короткий. Введіть нормальне повідомлення.")
                return
            self._chat_state[chat_id]["awaiting_announce"] = False
            author_name = " ".join(
                [
                    (state.get("last_name") or "").strip(),
                    (state.get("first_name") or "").strip(),
                    (state.get("middle_name") or "").strip(),
                ]
            ).strip() or "Невідомий користувач"
            self._apply_updates(
                {
                    "announcement_payload": {
                        "title": "",
                        "text": body,
                        "target_groups": [],
                        "author_name": author_name,
                        "author_role": role,
                    }
                }
            )
            self._send_message(token, chat_id, "Оголошення опубліковано.")
            return
        if chat_flow.get("awaiting_announce_title"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce_title"] = False
                self._send_message(token, chat_id, "Створення повідомлення скасовано.")
                return
            title = text.strip()
            if len(title) < 2:
                self._send_message(token, chat_id, "Заголовок занадто короткий. Введіть заголовок ще раз.")
                return
            self._chat_state.setdefault(chat_id, {})["announce_title"] = title
            self._chat_state[chat_id]["awaiting_announce_title"] = False
            self._chat_state[chat_id]["awaiting_announce_text"] = True
            self._send_message(
                token,
                chat_id,
                "Тепер введіть основне сповіщення (текст повідомлення):",
                reply_markup={
                    "keyboard": [[{"text": "↩️ Скасувати"}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            )
            return
        if chat_flow.get("awaiting_announce_text"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce_text"] = False
                self._send_message(token, chat_id, "Створення повідомлення скасовано.")
                return
            body = text.strip()
            if len(body) < 2:
                self._send_message(token, chat_id, "Текст занадто короткий. Введіть основне сповіщення ще раз.")
                return
            self._chat_state.setdefault(chat_id, {})["announce_text"] = body
            self._chat_state[chat_id]["awaiting_announce_text"] = False
            self._chat_state[chat_id]["awaiting_announce_group_mode"] = True
            self._send_message(
                token,
                chat_id,
                "Оберіть режим відправки по групах:",
                reply_markup={
                    "keyboard": [
                        [{"text": "1️⃣ Одна група"}, {"text": "➕ Вибрати кілька груп"}],
                        [{"text": "👥 Для всіх груп"}],
                        [{"text": "↩️ Скасувати"}],
                    ],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            )
            return
        if chat_flow.get("awaiting_announce_group_mode"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce_group_mode"] = False
                self._send_message(token, chat_id, "Створення повідомлення скасовано.")
                return
            groups = self._get_groups() or []
            if text_lower == "👥 для всіх груп":
                title = (self._chat_state.get(chat_id, {}).get("announce_title") or "").strip()
                body = (self._chat_state.get(chat_id, {}).get("announce_text") or "").strip()
                author_name = " ".join(
                    [
                        (state.get("last_name") or "").strip(),
                        (state.get("first_name") or "").strip(),
                        (state.get("middle_name") or "").strip(),
                    ]
                ).strip() or "Невідомий користувач"
                self._chat_state[chat_id]["awaiting_announce_group_mode"] = False
                self._chat_state[chat_id]["announce_title"] = ""
                self._chat_state[chat_id]["announce_text"] = ""
                self._apply_updates(
                    {
                        "announcement_payload": {
                            "title": title,
                            "text": body,
                            "target_groups": [],
                            "author_name": author_name,
                            "author_role": role,
                        }
                    }
                )
                self._send_message(token, chat_id, "Оголошення опубліковано для всіх груп.")
                return
            if text_lower == "1️⃣ одна група":
                self._chat_state[chat_id]["awaiting_announce_group_mode"] = False
                self._chat_state[chat_id]["awaiting_announce_group_single"] = True
                rows = []
                for i in range(0, min(len(groups), 40), 2):
                    row = [{"text": f"🎓 {groups[i]}"}]
                    if i + 1 < min(len(groups), 40):
                        row.append({"text": f"🎓 {groups[i + 1]}"})
                    rows.append(row)
                rows.append([{"text": "↩️ Скасувати"}])
                self._send_message(token, chat_id, "Оберіть одну групу:", reply_markup={"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
                return
            if text_lower == "➕ вибрати кілька груп":
                self._chat_state[chat_id]["awaiting_announce_group_mode"] = False
                self._chat_state[chat_id]["awaiting_announce_group_multi"] = True
                self._chat_state[chat_id]["announce_groups_selected"] = []
                self._send_message(
                    token,
                    chat_id,
                    "Обирайте групи кнопками. Коли готово — натисніть «✅ Завершити вибір» "
                    "(або надішліть /done_groups).",
                    reply_markup=self._multi_group_keyboard(),
                )
                return
            self._send_message(token, chat_id, "Оберіть один із режимів кнопками нижче.")
            return
        if chat_flow.get("awaiting_announce_group_single"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce_group_single"] = False
                self._send_message(token, chat_id, "Створення повідомлення скасовано.")
                return
            if text.startswith("🎓 "):
                selected = text[2:].strip()
                groups = self._get_groups() or []
                if groups and selected not in groups:
                    self._send_message(token, chat_id, "Такої групи немає в актуальному списку. Оберіть зі списку кнопок.")
                    return
                title = (self._chat_state.get(chat_id, {}).get("announce_title") or "").strip()
                body = (self._chat_state.get(chat_id, {}).get("announce_text") or "").strip()
                author_name = " ".join(
                    [
                        (state.get("last_name") or "").strip(),
                        (state.get("first_name") or "").strip(),
                        (state.get("middle_name") or "").strip(),
                    ]
                ).strip() or "Невідомий користувач"
                self._chat_state[chat_id]["awaiting_announce_group_single"] = False
                self._chat_state[chat_id]["announce_title"] = ""
                self._chat_state[chat_id]["announce_text"] = ""
                self._apply_updates(
                    {
                        "announcement_payload": {
                            "title": title,
                            "text": body,
                            "target_groups": [selected],
                            "author_name": author_name,
                            "author_role": role,
                        }
                    }
                )
                self._send_message(token, chat_id, f"Оголошення опубліковано для групи: {selected}")
                return
            self._send_message(token, chat_id, "Оберіть групу кнопкою нижче.")
            return
        if chat_flow.get("awaiting_announce_group_multi"):
            if text_lower == "↩️ скасувати":
                self._chat_state[chat_id]["awaiting_announce_group_multi"] = False
                self._send_message(token, chat_id, "Створення повідомлення скасовано.")
                return
            selected_groups = self._chat_state.setdefault(chat_id, {}).setdefault("announce_groups_selected", [])
            if text_lower == "👀 обрано":
                self._send_message(
                    token,
                    chat_id,
                    "Поточний вибір: " + (", ".join(selected_groups) if selected_groups else "нічого не обрано"),
                    reply_markup=self._multi_group_keyboard(),
                )
                return
            if text_lower in ("✅ завершити вибір", "/done_groups", "done", "готово"):
                if not selected_groups:
                    self._send_message(token, chat_id, "Спочатку оберіть хоча б одну групу.")
                    return
                title = (self._chat_state.get(chat_id, {}).get("announce_title") or "").strip()
                body = (self._chat_state.get(chat_id, {}).get("announce_text") or "").strip()
                author_name = " ".join(
                    [
                        (state.get("last_name") or "").strip(),
                        (state.get("first_name") or "").strip(),
                        (state.get("middle_name") or "").strip(),
                    ]
                ).strip() or "Невідомий користувач"
                self._chat_state[chat_id]["awaiting_announce_group_multi"] = False
                self._chat_state[chat_id]["announce_title"] = ""
                self._chat_state[chat_id]["announce_text"] = ""
                self._chat_state[chat_id]["announce_groups_selected"] = []
                self._apply_updates(
                    {
                        "announcement_payload": {
                            "title": title,
                            "text": body,
                            "target_groups": list(selected_groups),
                            "author_name": author_name,
                            "author_role": role,
                        }
                    }
                )
                self._send_message(token, chat_id, "Оголошення опубліковано для груп: " + ", ".join(selected_groups))
                return
            if text.startswith("🎓 "):
                g = text[2:].strip()
                groups = self._get_groups() or []
                if groups and g not in groups:
                    self._send_message(token, chat_id, "Такої групи немає в списку.")
                    return
                if g in selected_groups:
                    selected_groups.remove(g)
                    self._send_message(token, chat_id, f"Групу знято: {g}", reply_markup=self._multi_group_keyboard())
                else:
                    selected_groups.append(g)
                    self._send_message(token, chat_id, f"Групу додано: {g}", reply_markup=self._multi_group_keyboard())
                return
            self._send_message(
                token,
                chat_id,
                "Обирайте групи кнопками або натисніть «✅ Завершити вибір».",
                reply_markup=self._multi_group_keyboard(),
            )
            return
        if cmd in ("/start", "/help"):
            self._send_message(
                token,
                chat_id,
                "Команди:\n"
                "/login <код> - підтвердити вхід у додаток\n"
                "/status - поточні налаштування\n"
                "/groups - список груп\n"
                "/group <назва> - вибрати групу\n"
                "/notify on|off - увімкнути/вимкнути сповіщення\n"
                "/time <хв> - за скільки хвилин нагадувати\n"
                "/time_custom - ввести свій час у хвилинах\n"
                "/parse_groups - оновити всі групи з усіх папок розкладу\n"
                "/announce <текст> - надіслати оголошення (тільки викладач/адмін)\n"
                "/setrole <student|teacher|admin> - змінити роль (тільки адмін)\n"
                "/requests - список заявок на роль\n"
                "/approve <id> - погодити заявку\n"
                "/reject <id> - відхилити заявку\n"
                "/grant <email> <student|teacher|admin> - видати роль вручну\n\n"
                "Також можна користуватись кнопками внизу чату.",
            )
            return
        if cmd == "/login":
            entered = text[len("/login") :].strip()
            expected = (state.get("tg_login_code") or "").strip()
            expires_at = (state.get("tg_login_code_expires_at") or "").strip()
            if not expected:
                self._send_message(token, chat_id, "Код не згенеровано. Зайдіть у додаток і натисніть «Згенерувати код».")
                return
            if not entered:
                self._send_message(token, chat_id, "Використовуйте: /login 123456")
                return
            try:
                is_expired = bool(expires_at) and datetime.now() > datetime.fromisoformat(expires_at)
            except Exception:
                is_expired = False
            if is_expired:
                self._send_message(token, chat_id, "Код вже прострочено. Згенеруйте новий у додатку.")
                return
            if entered != expected:
                self._send_message(token, chat_id, "Невірний код. Перевірте код у додатку.")
                return
            self._apply_updates(
                {
                    "tg_login_verified": True,
                    "telegram_chat_id": chat_id,
                    "tg_login_code": "",
                    "tg_login_code_expires_at": "",
                }
            )
            self._send_message(token, chat_id, "Вхід підтверджено. Тепер додаток розблоковано ✅")
            return
        if cmd == "/status":
            self._send_message(
                token,
                chat_id,
                "Поточні налаштування:\n"
                f"Роль: {role}\n"
                f"Група: {state.get('notify_group') or 'не вибрано'}\n"
                f"Сповіщення: {'увімкнено' if state.get('notifications_enabled') else 'вимкнено'}\n"
                f"Час: {state.get('notify_minutes', 10)} хв",
            )
            return
        if cmd == "/groups":
            groups = self._get_groups()
            preview = "\n".join(groups[:40]) if groups else "Список груп порожній."
            self._send_message(token, chat_id, f"Доступні групи:\n{preview}")
            return
        if cmd == "/parse_groups":
            self._apply_updates({"parse_groups": True})
            self._send_message(token, chat_id, "Запустив парсинг усіх папок розкладу. Оновлений список груп з'явиться через кілька секунд.")
            return
        if cmd == "/group_pick":
            self._send_group_picker(token, chat_id)
            return
        if cmd == "/group":
            group_name = text[len("/group") :].strip()
            groups = self._get_groups()
            if not group_name:
                self._send_message(token, chat_id, "Вкажіть групу: /group КН-21")
                return
            if groups and group_name not in groups:
                self._send_message(token, chat_id, "Такої групи немає у поточному списку.")
                return
            self._apply_updates({"notify_group": group_name})
            self._send_message(token, chat_id, f"Групу оновлено: {group_name}")
            return
        if cmd == "/time_pick":
            self._send_time_picker(token, chat_id)
            return
        if cmd == "/announce_pick":
            if not (is_teacher or is_admin):
                denied("Викладач або Адміністратор")
                return
            self._chat_state.setdefault(chat_id, {})["awaiting_announce_title"] = True
            self._send_message(
                token,
                chat_id,
                "Введіть заголовок повідомлення:",
                reply_markup={
                    "keyboard": [[{"text": "↩️ Скасувати"}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            )
            return
        if cmd == "/notify":
            arg = text[len("/notify") :].strip().lower()
            if arg not in ("on", "off"):
                self._send_message(token, chat_id, "Використовуйте: /notify on або /notify off")
                return
            self._apply_updates({"notifications_enabled": arg == "on"})
            self._send_message(token, chat_id, f"Сповіщення {'увімкнено' if arg == 'on' else 'вимкнено'}.")
            return
        if cmd == "/time":
            arg = text[len("/time") :].strip()
            try:
                minutes = max(1, min(180, int(arg)))
            except (TypeError, ValueError):
                self._send_message(token, chat_id, "Використовуйте: /time 10")
                return
            self._apply_updates({"notify_minutes": minutes})
            self._send_message(token, chat_id, f"Час нагадування змінено: {minutes} хв.")
            return
        if cmd == "/announce":
            if not (is_teacher or is_admin):
                denied("Викладач або Адміністратор")
                return
            body = text[len("/announce") :].strip()
            if not body:
                self._send_message(token, chat_id, "Використовуйте: /announce Текст оголошення")
                return
            self._apply_updates({"announcement_text": body})
            self._send_message(token, chat_id, "Оголошення опубліковано.")
            return
        if cmd == "/setrole":
            if not is_admin:
                denied("Адміністратор")
                return
            arg = text[len("/setrole") :].strip()
            new_role = normalize_role(arg)
            if not new_role:
                self._send_message(token, chat_id, "Використовуйте: /setrole student|teacher|admin")
                return
            self._apply_updates({"user_role": new_role})
            self._send_message(token, chat_id, f"Роль оновлено: {new_role}")
            return
        if cmd == "/requests":
            if not is_admin:
                denied("Адміністратор")
                return
            reqs = get_pending_role_requests(limit=20)
            if not reqs:
                self._send_message(token, chat_id, "Немає заявок у статусі pending.")
                return
            lines = ["Заявки на зміну ролі:"]
            for r in reqs:
                fio = " ".join([r.get("last_name", ""), r.get("first_name", ""), r.get("middle_name", "")]).strip()
                lines.append(f"#{r['id']} | {fio or '-'} | {r['email']} | {r['current_role']} -> {r['requested_role']}")
            self._send_message(token, chat_id, "\n".join(lines))
            return
        if cmd == "/approve":
            if not is_admin:
                denied("Адміністратор")
                return
            arg = text[len("/approve") :].strip()
            try:
                rid = int(arg)
            except (TypeError, ValueError):
                self._send_message(token, chat_id, "Використовуйте: /approve <id>")
                return
            reviewed = review_role_request(rid, approved=True, reviewer_email=user_email)
            if not reviewed:
                self._send_message(token, chat_id, "Заявку не знайдено.")
                return
            self._apply_updates({"set_role_for_email": {"email": reviewed["email"], "role": reviewed["requested_role"]}})
            self._send_message(token, chat_id, f"Заявку #{rid} погоджено. Роль: {reviewed['requested_role']}.")
            return
        if cmd == "/reject":
            if not is_admin:
                denied("Адміністратор")
                return
            arg = text[len("/reject") :].strip()
            try:
                rid = int(arg)
            except (TypeError, ValueError):
                self._send_message(token, chat_id, "Використовуйте: /reject <id>")
                return
            reviewed = review_role_request(rid, approved=False, reviewer_email=user_email)
            if not reviewed:
                self._send_message(token, chat_id, "Заявку не знайдено.")
                return
            self._send_message(token, chat_id, f"Заявку #{rid} відхилено.")
            return
        if cmd == "/grant":
            if not is_admin:
                denied("Адміністратор")
                return
            args = text[len("/grant") :].strip().split()
            if len(args) < 2:
                self._send_message(token, chat_id, "Використовуйте: /grant user@mail.com teacher")
                return
            email = args[0].strip().lower()
            role_new = normalize_role(" ".join(args[1:]).strip())
            if not role_new:
                self._send_message(token, chat_id, "Роль невідома. Доступно: student|teacher|admin")
                return
            self._apply_updates({"set_role_for_email": {"email": email, "role": role_new}})
            self._send_message(token, chat_id, f"Роль для {email} оновлено на {role_new}.")
            return
