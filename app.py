# app.py
import logging
import sys
from pathlib import Path

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES

from session.session import SessionManager  # session/session.py
from ui.main_app import MainAppFrame
from ui.welcome import WelcomeScreen

logger = logging.getLogger(__name__)


def resource_path(rel: str) -> Path:
    """
    Resolve a resource path that works both in development and when bundled with PyInstaller.

    - In a PyInstaller onefile build, resources are extracted under sys._MEIPASS.
    - Otherwise, resolve the path relative to this file's directory.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return base / rel


def main() -> None:
    # Basic logging setup (you can adjust the level if you want more/less logs)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Main window (root Tk controller)
    app = ttk.Window(themename="darkly")
    app.title("Task Manager")
    app.geometry("900x900")

    # Track the current theme name
    app.current_theme = "darkly"

    # ---- Theme helper functions -------------------------------------------
    def set_theme(theme_name: str) -> None:
        """
        Change the ttkbootstrap theme at runtime.

        Expected values:
          - "lumen"  (light)
          - "darkly" (dark)
        """
        try:
            app.style.theme_use(theme_name)
            app.current_theme = theme_name
            logger.info("Theme changed to %s", theme_name)
        except Exception:
            logger.warning("Failed to change theme to %s",
                           theme_name, exc_info=True)

    def toggle_theme() -> None:
        """
        Toggle between light and dark themes:
          - darkly -> lumen
          - lumen  -> darkly
        """
        try:
            current = getattr(app, "current_theme", app.style.theme_use())
        except Exception:
            current = "darkly"

        if current == "darkly":
            set_theme("lumen")
        else:
            set_theme("darkly")

    # Expose theme helpers on the root so child frames can call them
    app.set_theme = set_theme        # type: ignore[attr-defined]
    app.toggle_theme = toggle_theme  # type: ignore[attr-defined]

    # Paths for the SQLite DB and schema (works in dev and in PyInstaller)
    db_path = resource_path("task_manager.db")
    schema_path = resource_path("db/schema.sql")

    # Session file lives next to the executable / script
    session_file = resource_path("session.txt")
    session = SessionManager(session_file)

    def logout() -> None:
        """
        Log out the current user.

        - Clear the stored session.
        - Return to the Welcome screen (no auto-login this time).
        """
        session.clear()
        app.title("Task Manager")
        show_welcome(auto_login=False)

    def on_login(user_row) -> None:
        """
        Called by WelcomeScreen after a successful login or registration.

        Parameters
        ----------
        user_row : sqlite3.Row or dict
            A row/dict with at least the key: "id".
        """
        # Try to persist the user_id to disk, but don't crash if it fails.
        try:
            user_id = int(user_row["id"])
            session.save(user_id)
        except Exception:
            logger.warning("Failed to save session.", exc_info=True)

        # Clear any existing content in the root window
        for w in app.winfo_children():
            w.destroy()

        # Expose controller API to children
        app.logout = logout          # type: ignore[attr-defined]
        app.set_theme = set_theme
        app.toggle_theme = toggle_theme

        # Show the main application frame (Calendar + Task Manager)
        main_frame = MainAppFrame(app, app, user_row)
        main_frame.pack(fill=BOTH, expand=YES)

    def show_main_for_user_id(user_id: int) -> bool:
        """
        Try to load the user row for the given user_id from the database
        and show the MainAppFrame directly.

        Uses the USER table defined in schema.sql.

        Returns
        -------
        bool
            True if the user was found and the main screen was shown,
            False otherwise.
        """
        try:
            # We expect controller.db to be a DatabaseManager with:
            #   db.fetchall(sql: str, params: tuple) -> list[sqlite3.Row]
            db = app.db  # type: ignore[attr-defined]

            rows = db.fetchall(
                "SELECT id, name, email FROM USER WHERE id = ?",
                (user_id,),
            )

            if not rows:
                # No such user_id in the database
                return False

            row = rows[0]

            # Clear current content (e.g. Welcome screen)
            for w in app.winfo_children():
                w.destroy()

            app.logout = logout          # type: ignore[attr-defined]
            app.set_theme = set_theme
            app.toggle_theme = toggle_theme

            main_frame = MainAppFrame(app, app, row)
            main_frame.pack(fill=BOTH, expand=YES)
            return True
        except Exception:
            logger.warning(
                "Failed to auto-login user_id=%s; falling back to WelcomeScreen.",
                user_id,
                exc_info=True,
            )
            return False

    def show_welcome(auto_login: bool = False) -> None:
        """
        Show the Welcome screen and initialize the DatabaseManager.

        Parameters
        ----------
        auto_login : bool
            If True, this function will try to auto-login using the stored
            session (last user_id). If auto-login fails, it just shows the
            normal Welcome screen.
        """
        # Clear existing content (if any)
        for w in app.winfo_children():
            w.destroy()

        # Create the Welcome screen; it is responsible for initializing the DB
        screen = WelcomeScreen(
            app,
            db_path=str(db_path),
            schema_path=str(schema_path),
            on_login=on_login,
        )

        # Expose the DB handle and controller API to other frames
        app.db = screen.db  # type: ignore[attr-defined]
        app.logout = logout
        app.set_theme = set_theme
        app.toggle_theme = toggle_theme

        # If auto_login is requested, try to read the last user_id and skip
        # the Welcome screen if possible.
        if auto_login:
            user_id = session.load()
            if user_id is not None:
                logger.info("Found stored session for user_id=%s", user_id)
                if show_main_for_user_id(user_id):
                    # Successfully auto-logged in, so we do NOT pack the Welcome screen.
                    return
                else:
                    logger.info(
                        "Auto-login failed; showing Welcome screen instead."
                    )

        # Either auto_login is False, or auto-login failed.
        # Show the Welcome screen normally.
        screen.pack(fill=BOTH, expand=YES)

    # Initial screen on app startup: try auto-login once
    show_welcome(auto_login=True)
    app.mainloop()


if __name__ == "__main__":
    main()
