
import asyncio
import inspect
import flet as ft


def patch_flet_page_run_task_cancelled_safe() -> None:
    try:
        from flet_core.page import Page, _session_page
    except ImportError:
        return

    if getattr(Page.run_task, "_mntu_cancel_safe", False):
        return

    def run_task(self, handler, *args, **kwargs):
        _session_page.set(self)
        assert asyncio.iscoroutinefunction(handler)


        loop = getattr(self, "_Page__loop", None)
        if loop is None:
            loop = getattr(self, "__loop", None)
        if loop is None:
            raise AttributeError("Page has no event loop (_Page__loop)")
        future = asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), loop)

        def _on_completion(f):
            if f.cancelled():
                return
            exception = f.exception()
            if exception:
                raise exception

        future.add_done_callback(_on_completion)
        return future

    run_task._mntu_cancel_safe = True
    Page.run_task = run_task

if hasattr(ft, "Icons"):
    ft.icons = ft.Icons
if hasattr(ft, "Colors"):
    ft.colors = ft.Colors
if not hasattr(ft, "Button"):
    ft.Button = ft.ElevatedButton


def border_all(width, color):
    fn = getattr(ft.Border, "all", None)
    if callable(fn):
        return fn(width, color)
    return ft.border.all(width, color)


def dropdown_event_kw(handler):
    if "on_select" in inspect.signature(ft.Dropdown.__init__).parameters:
        return {"on_select": handler}
    return {"on_change": handler}


def dropdown_menu_height_kw(height: int | None = None) -> dict:
    if height is None:
        return {}
    if "menu_height" in inspect.signature(ft.Dropdown.__init__).parameters:
        return {"menu_height": height}
    return {}


def bind_dropdown_change(dd: ft.Dropdown, handler):
    if hasattr(dd, "on_select"):
        dd.on_select = handler
    else:
        dd.on_change = handler


def padding_all(value: float):
    fn = getattr(ft.Padding, "all", None)
    if callable(fn):
        return fn(value)
    return ft.padding.all(value)


def padding_symmetric(*, horizontal: float = 0, vertical: float = 0):
    fn = getattr(ft.Padding, "symmetric", None)
    if callable(fn):
        return fn(horizontal=horizontal, vertical=vertical)
    return ft.padding.symmetric(horizontal=horizontal, vertical=vertical)


def padding_only(**kwargs):
    if hasattr(ft.Padding, "only"):
        return ft.Padding.only(**kwargs)
    return ft.padding.only(**kwargs)


def dropdown_value_from_event(e):
    c = getattr(e, "control", None)
    if c is not None:
        v = getattr(c, "value", None)
        if v is not None and str(v).strip() != "":
            return str(v)
    for attr in ("value", "data", "selected_value"):
        if hasattr(e, attr):
            v = getattr(e, attr)
            if v is not None and str(v).strip() != "":
                return str(v)
    return None


patch_flet_page_run_task_cancelled_safe()
