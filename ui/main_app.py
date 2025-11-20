# ui/main_app.py
import logging
import tkinter as tk
from datetime import datetime
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X
from ttkbootstrap.dialogs import Messagebox

from ui.calendar_view import CalendarTaskFrame
from ui.weekly_schedule import WeeklyScheduleFrame

log = logging.getLogger("TaskManager.MainApp")


class MainAppFrame(ttk.Frame):
    """
    Main container for the application.

    Layout:
      - Top bar: user name + user menu (account button)
      - Center: switched content (Calendar / Weekly Schedule)
      - No bottom navigation; switching is done via user menu.
    """

    def __init__(self, parent, controller, user_row):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id = user_row["id"]

        try:
            name = user_row["name"]
        except Exception:
            name = "User"

        # ---- Top Bar -------------------------------------------------------
        top = ttk.Frame(self, padding=(12, 12, 12, 0))
        top.pack(fill=X, side=tk.TOP)

        self.user_label = ttk.Label(
            top,
            text=f"Welcome, {name}!",
            font=("-size", 12),
        )
        self.user_label.pack(side=tk.LEFT)

        # User menu (account button)
        self._build_user_menu(top)

        # ---- Content Area (stacked frames) --------------------------------
        self.content = ttk.Frame(self, padding=(0, 8, 0, 0))
        self.content.pack(fill=BOTH, expand=YES)

        # Calendar view (existing)
        self.calendar_frame = CalendarTaskFrame(self.content, controller)
        self.calendar_frame.set_user(self.current_user_id)

        # Weekly schedule view (new)
        self.weekly_frame = WeeklyScheduleFrame(
            self.content,
            controller,
            self.current_user_id,
        )

        # Pack both into the same place, but show only one at a time
        for frame in (self.calendar_frame, self.weekly_frame):
            frame.pack_forget()

        # Show Calendar as default
        self._active_frame = None
        self._show_calendar()

        # Window title
        self.controller.title("Task Manager - Calendar")

    # ------------------------------------------------------------------ #
    # Screen switching helpers
    # ------------------------------------------------------------------ #
    def _switch_content(self, frame: ttk.Frame) -> None:
        """Hide current screen and show the requested frame."""
        if self._active_frame is frame:
            return
        if self._active_frame is not None:
            self._active_frame.pack_forget()
        self._active_frame = frame
        self._active_frame.pack(fill=BOTH, expand=YES)

    def _show_calendar(self) -> None:
        """Show calendar tab."""
        self._switch_content(self.calendar_frame)

    def _show_weekly(self) -> None:
        """Show weekly schedule tab."""
        # Ensure it uses the current user id
        self.weekly_frame.set_user(self.current_user_id)
        self._switch_content(self.weekly_frame)

    def _toggle_weekly_from_menu(self) -> None:
        """
        Menu action:
          - If Weekly is visible -> go back to Calendar
          - If Calendar is visible -> show Weekly
        """
        if self._active_frame is self.weekly_frame:
            self._show_calendar()
        else:
            self._show_weekly()

    # ------------------------------------------------------------------ #
    # User icon + popup menu
    # ------------------------------------------------------------------ #
    def _build_user_menu(self, parent: ttk.Frame) -> None:
        """
        Build the popup menu for the user icon.

        Order:
          1) Toggle theme (light/dark)    [if available]
          2) Weekly Schedule              (toggle Calendar / Weekly)
          3) Import iCalendar (.ics)...
          4) Logout
        """
        self.user_menu = tk.Menu(self, tearoff=0)

        # Theme toggle (if available on controller)
        toggle_theme = getattr(self.controller, "toggle_theme", None)
        if callable(toggle_theme):
            self.user_menu.add_command(
                label="Toggle theme (light / dark)",
                command=toggle_theme,
            )

        # Weekly schedule toggle
        self.user_menu.add_command(
            label="Weekly Schedule",
            command=self._toggle_weekly_from_menu,
        )

        # iCalendar import
        self.user_menu.add_command(
            label="Import iCalendar (.ics)...",
            command=self._import_ics,
        )

        # Separator + Logout
        self.user_menu.add_separator()
        self.user_menu.add_command(
            label="Logout",
            command=self.controller.logout,
        )

        # User icon button
        self.user_icon_button = ttk.Button(
            parent,
            text="Account ▼",
            width=10,
        )
        self.user_icon_button.pack(side=tk.RIGHT)

        # Show popup menu on left click
        self.user_icon_button.bind("<Button-1>", self._show_user_menu)

    def _show_user_menu(self, event: tk.Event) -> None:
        """Show the user popup menu at the mouse position."""
        try:
            self.user_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.user_menu.grab_release()

        # Install temporary global binding to dismiss menu when clicking outside
        # Use ButtonRelease so we don't catch the same click that opened it.
        self.after(10, self._install_menu_dismiss_binding)

    def _install_menu_dismiss_binding(self) -> None:
        # bind_all so clicks anywhere in the app will close the menu
        self.controller.bind_all(
            "<ButtonRelease-1>",
            self._dismiss_user_menu,
            add="+",
        )

    def _dismiss_user_menu(self, event: tk.Event) -> None:
        """Unpost the user menu and remove the temporary binding."""
        try:
            self.user_menu.unpost()
        except Exception:
            pass
        # remove this temporary binding
        self.controller.unbind_all("<ButtonRelease-1>")

    # ------------------------------------------------------------------ #
    # iCalendar (.ics) Import
    # ------------------------------------------------------------------ #
    def _import_ics(self) -> None:
        """
        Import an .ics file and insert events into the database.

        Mapping:
          - CATEGORIES  -> COURSE.name  (per user, get-or-create)
          - SUMMARY     -> TASK.name (with trailing ' is due' removed)
          - DTEND       -> TASK.due_date (YYYY-MM-DD; falls back to DTSTART)
          - DESCRIPTION -> TASK.description

        If a task with the same (course_id, name, due_date) already exists,
        it is skipped.
        """
        path = filedialog.askopenfilename(
            title="Select iCalendar (.ics) file",
            filetypes=[("iCalendar files", "*.ics"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            log.exception("Failed to read ics file: %s", path)
            Messagebox.show_error(
                title="Import iCalendar",
                message="Failed to read the selected .ics file.",
            )
            return

        events = self._parse_ics_events(raw)
        if not events:
            Messagebox.show_warning(
                title="Import iCalendar",
                message="No VEVENT entries were found in the .ics file.",
            )
            return

        imported = 0
        for ev in events:
            summary = ev.get("SUMMARY")
            categories = ev.get("CATEGORIES")
            dtend_raw = ev.get("DTEND") or ev.get("DTSTART")

            # Skip if required fields are missing
            if not (summary and categories and dtend_raw):
                continue

            # Remove " is due" suffix from the task name
            task_name = summary.replace(" is due", "").strip()

            # Convert DTEND / DTSTART to YYYY-MM-DD (no timezone conversion)
            due_date = self._parse_ics_datetime(dtend_raw)
            if not due_date:
                continue

            # Map CATEGORIES -> COURSE (per user; get or create)
            course_id = self._get_or_create_course(
                self.current_user_id, categories
            )

            # Skip if the same task already exists
            existing = self.db.fetchall(
                "SELECT id FROM TASK WHERE course_id=? AND name=? AND due_date=?",
                (course_id, task_name, due_date),
            )
            if existing:
                continue

            description = ev.get("DESCRIPTION", "")

            # Insert TASK
            self.db.execute(
                """
                INSERT INTO TASK (course_id, name, description, due_date)
                VALUES (?, ?, ?, ?)
                """,
                (course_id, task_name, description, due_date),
            )
            imported += 1

        if imported:
            Messagebox.show_info(
                title="Import iCalendar",
                message=f"Imported {imported} tasks from the calendar.",
            )
            if hasattr(self.calendar_frame, "set_user"):
                self.calendar_frame.set_user(self.current_user_id)
        else:
            Messagebox.show_info(
                title="Import iCalendar",
                message="No new tasks were imported (they may already exist).",
            )

    # ------------------------------------------------------------------ #
    # Helpers for iCalendar parsing
    # ------------------------------------------------------------------ #
    def _parse_ics_events(self, raw: str) -> list[dict[str, str]]:
        """Parse VEVENT blocks from an iCalendar (.ics) string."""
        raw_lines = raw.splitlines()
        lines: list[str] = []
        for line in raw_lines:
            if line.startswith((" ", "\t")) and lines:
                lines[-1] += line[1:]
            else:
                lines.append(line)

        events: list[dict[str, str]] = []
        current: dict[str, str] | None = None

        for line in lines:
            if line == "BEGIN:VEVENT":
                current = {}
                continue
            if line == "END:VEVENT":
                if current:
                    events.append(current)
                current = None
                continue
            if current is None:
                continue
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.split(";", 1)[0]
            current[key] = value

        return events

    def _parse_ics_datetime(self, dt_text: str) -> str | None:
        """Convert iCalendar datetime value into 'YYYY-MM-DD' string."""
        text = dt_text.strip()
        try:
            if text.endswith("Z"):
                dt = datetime.strptime(text, "%Y%m%dT%H%M%SZ")
                return dt.date().isoformat()
            if "T" in text:
                dt = datetime.strptime(text, "%Y%m%dT%H%M%S")
                return dt.date().isoformat()
            dt = datetime.strptime(text, "%Y%m%d")
            return dt.date().isoformat()
        except Exception:
            log.warning("Failed to parse iCalendar datetime: %s", dt_text)
            return None

    def _get_or_create_course(self, user_id: int, name: str) -> int:
        """Return COURSE.id for (user_id, name); create if missing."""
        rows = self.db.fetchall(
            "SELECT id FROM COURSE WHERE user_id=? AND name=?",
            (user_id, name),
        )
        if rows:
            return rows[0]["id"]

        course_id = self.db.execute(
            """
            INSERT INTO COURSE (user_id, name, description)
            VALUES (?, ?, ?)
            """,
            (user_id, name, ""),
        )
        return int(course_id)
