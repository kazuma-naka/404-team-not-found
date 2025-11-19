# ui/main_app.py
import logging
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog
from zoneinfo import ZoneInfo

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X
from ttkbootstrap.dialogs import Messagebox

from ui.calendar_view import CalendarTaskFrame

log = logging.getLogger("TaskManager.MainApp")

# Local timezone (York University / Toronto)
LOCAL_TZ = ZoneInfo("America/Toronto")


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

        # User menu (theme toggle + logout + ics import)
        self._build_user_menu(top)

        # ---- Content Area --------------------------------------------------
        self.content = ttk.Frame(self, padding=(0, 8, 0, 0))
        self.content.pack(fill=BOTH, expand=YES)

        # Calendar as the main screen
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
          - Import iCalendar (.ics)...
          - Toggle theme (light/dark)  *if controller provides toggle_theme*
          - Logout
        """
        self.user_menu = tk.Menu(self, tearoff=0)

        # --- iCalendar import ---------------------------------------------
        self.user_menu.add_command(
            label="Import iCalendar (.ics)...",
            command=self._import_ics,
        )
        self.user_menu.add_separator()

        # Theme toggle (if available on controller)
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

    # ------------------------------------------------------------------ #
    # iCalendar (.ics) Import
    # ------------------------------------------------------------------ #
    def _import_ics(self) -> None:
        """
        Import an .ics file and insert events into the database.

        Mapping:
          - CATEGORIES  -> COURSE.name  (per user, get-or-create)
          - SUMMARY     -> TASK.name (with trailing ' is due' removed)
          - DTEND       -> TASK.due_date (YYYY-MM-DD in local time; falls back to DTSTART)
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

            # Convert DTEND / DTSTART to YYYY-MM-DD in local time
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
            # Refresh calendar after import
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
        """
        Parse VEVENT blocks from an iCalendar (.ics) string.

        Returns a list of dicts like:
          { "SUMMARY": "...", "CATEGORIES": "...", "DTEND": "...", ... }

        Behavior:
          - Handles line folding (lines starting with space or tab are
            treated as continuation of the previous line).
          - Only parses lines inside BEGIN:VEVENT ... END:VEVENT blocks.
          - Property parameters are ignored (e.g., "DTEND;TZID=..." ->
            key "DTEND").
        """
        # Unfold lines according to RFC 5545 (line folding)
        raw_lines = raw.splitlines()
        lines: list[str] = []
        for line in raw_lines:
            if line.startswith((" ", "\t")) and lines:
                # continuation line: append without the first space/tab
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

            # Example: "DTEND:20251102T040000Z"
            # or      "DTEND;TZID=America/Toronto:20251102T000000"
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0]  # drop parameters such as ;TZID=...
            current[key] = value

        return events

    def _parse_ics_datetime(self, dt_text: str) -> str | None:
        """
        Convert an iCalendar datetime value into a date string "YYYY-MM-DD".

        Supported formats:
          - UTC datetime:       20251102T040000Z
          - Local datetime:     20251102T000000
          - Date only:          20251102

        For UTC values, this converts to local time (America/Toronto)
        before taking the date.
        """
        text = dt_text.strip()
        try:
            if text.endswith("Z"):
                # UTC datetime
                dt = datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
                dt_local = dt.astimezone(LOCAL_TZ)
                return dt_local.date().isoformat()
            if "T" in text:
                # Floating local datetime (no timezone info)
                dt = datetime.strptime(text, "%Y%m%dT%H%M%S")
                return dt.date().isoformat()
            # Date-only value
            dt = datetime.strptime(text, "%Y%m%d")
            return dt.date().isoformat()
        except Exception:
            log.warning("Failed to parse iCalendar datetime: %s", dt_text)
            return None

    def _get_or_create_course(self, user_id: int, name: str) -> int:
        """
        Return the id of COURSE for (user_id, name).
        If it does not exist, create it and return the new id.
        """
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
