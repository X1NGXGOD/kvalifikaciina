import webbrowser

import flet as ft

from mntu_app.database import get_unread_announcements, load_settings, mark_announcements_seen

def show_snack(page: ft.Page, message: str):
    snackbar = ft.SnackBar(content=ft.Text(message))
    page.overlay.append(snackbar)
    snackbar.open = True
    page.update()

def show_class_notification(page: ft.Page, notif_data: dict, colors: dict = None):
    if colors is None:
        colors = {"TEXT_MUTED": "#666", "ACCENT": "#0078d4"}

    msg = notif_data.get("message", "")
    link = notif_data.get("link")
    subject = notif_data.get("subject", "")
    teacher = notif_data.get("teacher", "")

    show_system_notification("МНТУ Помічник", msg, timeout=10)

    def open_link(e):
        if link:
            webbrowser.open(link)
        if dialog_ref["current"]:
            dialog_ref["current"].open = False
            page.update()

    dialog_ref = {"current": None}
    content_items = [
        ft.Text(msg, size=14),
        ft.Text(f"Предмет: {subject}", size=12, color=colors.get("TEXT_MUTED", "#666")),
    ]
    if teacher:
        content_items.append(ft.Text(f"Викладач: {teacher}", size=12, color=colors.get("TEXT_MUTED", "#666")))

    actions = [
        ft.TextButton("Закрити", on_click=lambda e: setattr(dialog_ref["current"], "open", False) or page.update()),
    ]
    if link:
        actions.append(ft.ElevatedButton("Підключитися", on_click=open_link, bgcolor=colors.get("ACCENT", "#0078d4")))

    dialog = ft.AlertDialog(
        title=ft.Text("Нагадування про пару"),
        content=ft.Column(content_items, tight=True, spacing=8),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )
    dialog_ref["current"] = dialog
    page.dialog = dialog
    dialog.open = True
    page.update()

    show_snack(page, msg)

def show_system_notification(title: str, message: str, timeout: int = 10):
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message[:500] if len(message) > 500 else message,
            timeout=timeout,
            app_name="МНТУ Помічник",
        )
    except (ImportError, ModuleNotFoundError, AttributeError, Exception) as e:

        pass

def show_pending_announcements(page: ft.Page, notifications_enabled: bool = None, target_group: str = ""):

    if notifications_enabled is None:
        settings = load_settings()
        notifications_enabled = settings.get("notifications_enabled", True)
    if not notifications_enabled:
        return

    unread = get_unread_announcements(target_group=target_group, include_meta=True)
    if not unread:
        return
    max_id = 0
    messages_to_show = []
    for aid, msg, created_at, _meta in unread:
        max_id = max(max_id, aid)
        msg_clean = (msg or "").strip()
        if msg_clean:
            messages_to_show.append(msg_clean)
    if not messages_to_show:
        mark_announcements_seen(max_id)
        return
    title = "МНТУ Помічник — нове повідомлення" if len(unread) == 1 else f"МНТУ Помічник — {len(unread)} нових повідомлень"
    body = messages_to_show[0] if len(messages_to_show) == 1 else "\n".join(f"• {m}" for m in messages_to_show[:5])
    if len(messages_to_show) > 5:
        body += f"\n… та ще {len(messages_to_show) - 5}"
    show_system_notification(title, body, timeout=12)
    snack_text = body if len(messages_to_show) == 1 else f"Нові повідомлення від викладача:\n\n{body}"
    show_snack(page, snack_text)
    mark_announcements_seen(max_id)
