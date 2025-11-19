# ui/main_app.py
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X

from ui.calendar_view import CalendarTaskFrame

# from ui.task_manager import TaskManagerFrame  # Restore if needed later


class MainAppFrame(ttk.Frame):
    """
    Main container for the application.
    Top: user name + user menu (icon)
    Bottom: calendar-based task UI.
    """

    def __init__(self, parent, controller, user_row):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id = user_row["id"]

        # sqlite3.Row does not have .get, so use try/except for safety
        try:
            name = user_row["name"]
        except Exception:
            name = "User"

        # ---- Top Bar: Welcome / User Menu ---------------------------------
        top = ttk.Frame(self, padding=(12, 12, 12, 0))
        top.pack(fill=X, side=tk.TOP)

        self.user_label = ttk.Label(
            top,
            text=f"Welcome, {name}!",
            font=("-size", 12),
        )
        self.user_label.pack(side=tk.LEFT)

        # User menu (theme toggle + logout)
        self._build_user_menu(top)

        # ---- Content Area --------------------------------------------------
        self.content = ttk.Frame(self, padding=(0, 8, 0, 0))
        self.content.pack(fill=BOTH, expand=YES)

        # Show the calendar as the main screen
        self.calendar_frame = CalendarTaskFrame(self.content, controller)
        self.calendar_frame.pack(fill=BOTH, expand=YES)
        self.calendar_frame.set_user(self.current_user_id)

        # Window title
        self.controller.title("Task Manager - Calendar")

    # ------------------------------------------------------------------ #
    # User icon + popup menu
    # ------------------------------------------------------------------ #
    def _build_user_menu(self, parent: ttk.Frame) -> None:
        """
        Build the popup menu for the user icon.
        Items:
          - Toggle theme (light/dark)
          - Logout
        """
        self.user_menu = tk.Menu(self, tearoff=0)

        # Toggle theme (if controller exposes toggle_theme)
        toggle_theme = getattr(self.controller, "toggle_theme", None)
        if callable(toggle_theme):
            self.user_menu.add_command(
                label="Toggle theme (light / dark)",
                command=toggle_theme,
            )
            self.user_menu.add_separator()

        # Logout
        self.user_menu.add_command(
            label="Logout",
            command=self.controller.logout,
        )

        # User icon button
        self.user_icon_button = ttk.Button(
            parent,
            text="Account ▼",
            width=6,
        )
        self.user_icon_button.pack(side=tk.RIGHT)

        # Show popup menu on left click
        self.user_icon_button.bind("<Button-1>", self._show_user_menu)

    def _show_user_menu(self, event: tk.Event) -> None:
        """
        Show the user popup menu at the mouse position.
        """
        try:
            self.user_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.user_menu.grab_release()
