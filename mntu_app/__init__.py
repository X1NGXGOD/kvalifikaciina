
from mntu_app.app_main import main

__all__ = ["main", "run"]


def run() -> None:
    import flet as ft

    import mntu_app.flet_compat

    ft.app(main)
