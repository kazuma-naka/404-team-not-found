# app.py
import sys
from pathlib import Path

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES

from ui.main_app import MainAppFrame
from ui.welcome import WelcomeScreen


def resource_path(rel: str) -> Path:
    """
    Resolve a resource path that works both in development and when bundled with PyInstaller.
    - In a PyInstaller onefile build, resources are extracted under sys._MEIPASS.
    - Otherwise, resolve relative to this file's directory.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return base / rel


def main() -> None:
    # Main window (controller for all main screens)
    app = ttk.Window(themename="superhero")
    app.title("Task Manager")
    app.geometry("900x600")

    # DB / schema paths (dev + PyInstaller 両対応)
    db_path = resource_path("task_manager.db")
    schema_path = resource_path("db/schema.sql")

    def logout() -> None:
        """Return to the Welcome screen."""
        app.title("Task Manager")
        show_welcome()

    def on_login(user_row) -> None:
        """
        Called by WelcomeScreen after a successful Login/Register.
        user_row is a sqlite3.Row with keys: id, name, email.
        """
        # Clear current content
        for w in app.winfo_children():
            w.destroy()

        # Controller API exposed to children
        app.logout = logout  # type: ignore[attr-defined]

        # MainAppFrame 内で TaskManager + LLM Chat を切り替える
        main_frame = MainAppFrame(app, app, user_row)
        main_frame.pack(fill=BOTH, expand=YES)

    def show_welcome() -> None:
        """Show the Welcome screen and initialize the DatabaseManager."""
        for w in app.winfo_children():
            w.destroy()

        screen = WelcomeScreen(
            app,
            db_path=str(db_path),
            schema_path=str(schema_path),
            on_login=on_login,
        )

        # Expose DB handle on the controller (TaskManagerFrame / MainAppFrame expects controller.db)
        app.db = screen.db  # type: ignore[attr-defined]
        app.logout = logout  # type: ignore[attr-defined]

        screen.pack(fill=BOTH, expand=YES)

    # Initial screen
    show_welcome()
    app.mainloop()


if __name__ == "__main__":
    main()
