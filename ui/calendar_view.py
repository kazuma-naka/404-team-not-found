# ui/calendar_view.py
import calendar
from datetime import date

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.dialogs.dialogs import Querybox


class CalendarTaskFrame(ttk.Frame):
    """
    Calendar + task list frame.

    Left: monthly calendar
        - each day is a "tile" with rounded-card feeling
        - if the day has tasks, show small dots under the day number
        - clicking a day highlights the tile and shows tasks on the right
    Right: task list for the selected day
        - tasks are grouped by course
        - user can edit / delete the selected task
        - selected task details are shown in a card at the bottom
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id: int | None = None

        today = date.today()
        self.current_year = today.year
        self.current_month = today.month
        self.selected_day: int | None = None

        # "YYYY-MM-DD" -> list[Row]
        self.tasks_by_date: dict[str, list] = {}

        # day int -> tile frame widget (for selection highlight)
        self._day_tiles: dict[int, ttk.Frame] = {}

        # Currently selected date string (e.g. "2025-11-19")
        self._current_date_str: str | None = None

        # Mapping from listbox index -> sqlite3.Row (None for course header rows)
        self._list_index_to_task: dict[int, object | None] = {}

        # Currently selected task row (sqlite3.Row) or None
        self._selected_task_row: object | None = None

        # ---- Top Bar (month navigation) -----------------------------------
        top = ttk.Frame(self, padding=(16, 16, 16, 0))
        top.pack(fill=X)

        self.btn_prev = ttk.Button(
            top,
            text="◀",
            width=3,
            bootstyle="secondary-outline",
            command=self.goto_prev_month,
        )
        self.btn_prev.pack(side=tk.LEFT)

        self.lbl_month = ttk.Label(
            top,
            text="",
            font=("-size", 16, "-weight", "bold"),
            anchor="center",
        )
        self.lbl_month.pack(side=tk.LEFT, expand=True)

        self.btn_next = ttk.Button(
            top,
            text="▶",
            width=3,
            bootstyle="secondary-outline",
            command=self.goto_next_month,
        )
        self.btn_next.pack(side=tk.RIGHT)

        # ---- Main area: calendar + task list ------------------------------
        main = ttk.Frame(self, padding=16)
        main.pack(fill=BOTH, expand=True)

        # Left: calendar card
        self.calendar_card = ttk.Frame(
            main,
            padding=16,
            bootstyle="light",  # white card feeling
            borderwidth=1,
            relief="solid",
        )
        self.calendar_card.pack(side=tk.LEFT, fill=BOTH, expand=True)

        self.calendar_frame = ttk.Frame(self.calendar_card)
        self.calendar_frame.pack(fill=BOTH, expand=True)

        # Right: selected day task list card
        right_card = ttk.Frame(
            main,
            padding=16,
            bootstyle="dark",
        )
        right_card.pack(side=tk.LEFT, fill=BOTH, expand=True, padx=(16, 0))

        self.lbl_selected_day = ttk.Label(
            right_card,
            text="No date selected",
            font=("-size", 12, "-weight", "bold"),
        )
        self.lbl_selected_day.pack(anchor="w")

        # Task list (grouped by course, with headers)
        self.tasks_list = tk.Listbox(
            right_card,
            height=18,
            borderwidth=0,
            highlightthickness=0,
        )
        self.tasks_list.pack(fill=BOTH, expand=True, pady=(8, 0))

        # Bind selection event to show details and enable buttons
        self.tasks_list.bind("<<ListboxSelect>>", self.on_task_selected)

        # Action buttons (Edit / Delete)
        btn_bar = ttk.Frame(right_card)
        btn_bar.pack(fill=X, pady=(4, 0))

        self.btn_edit = ttk.Button(
            btn_bar,
            text="Edit",
            bootstyle="outline",
            command=self.on_edit_task,
            state="disabled",
            width=8,
        )
        self.btn_edit.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_delete = ttk.Button(
            btn_bar,
            text="Delete",
            bootstyle="danger-outline",
            command=self.on_delete_task,
            state="disabled",
            width=8,
        )
        self.btn_delete.pack(side=tk.LEFT)

        # Details card for selected task
        self.detail_card = ttk.Frame(
            right_card,
            padding=12,
            bootstyle="secondary",
        )
        self.detail_card.pack(fill=X, pady=(12, 0))

        self.lbl_detail_title = ttk.Label(
            self.detail_card,
            text="Task details",
            font=("-size", 11, "-weight", "bold"),
        )
        self.lbl_detail_title.grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(
            self.detail_card,
            text="Course:",
            bootstyle="secondary",
        ).grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.lbl_detail_course = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_course.grid(row=1, column=1, sticky="w", pady=(8, 2))

        ttk.Label(
            self.detail_card,
            text="Task:",
            bootstyle="secondary",
        ).grid(row=2, column=0, sticky="w", pady=(2, 2))
        self.lbl_detail_task = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_task.grid(row=2, column=1, sticky="w", pady=(2, 2))

        ttk.Label(
            self.detail_card,
            text="Due:",
            bootstyle="secondary",
        ).grid(row=3, column=0, sticky="w", pady=(2, 2))
        self.lbl_detail_due = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_due.grid(row=3, column=1, sticky="w", pady=(2, 2))

        ttk.Label(
            self.detail_card,
            text="Description:",
            bootstyle="secondary",
        ).grid(row=4, column=0, sticky="nw", pady=(2, 0))
        self.lbl_detail_desc = ttk.Label(
            self.detail_card,
            text="-",
            wraplength=260,
            justify="left",
        )
        self.lbl_detail_desc.grid(row=4, column=1, sticky="w", pady=(2, 0))

        self.detail_card.columnconfigure(1, weight=1)

        # Initial build (user will be set later by set_user)
        self._rebuild_calendar()

    # ------------------------------------------------------------------ helpers
    def _row_value(self, row, key: str, default=None):
        """
        Safe accessor for sqlite3.Row.

        sqlite3.Row supports row[key] but does not provide .get().
        """
        try:
            value = row[key]
        except Exception:
            return default
        return value if value is not None else default

    # ---- Public API -------------------------------------------------------
    def set_user(self, user_id: int):
        """Called from App after login."""
        self.current_user_id = user_id
        self.refresh_month()

    # ---- Month navigation -------------------------------------------------
    def goto_prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.refresh_month()

    def goto_next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.refresh_month()

    # ---- Data loading + UI refresh ---------------------------------------
    def refresh_month(self, keep_selection: bool = False):
        """
        Load tasks for the current year/month from DB and rebuild calendar.

        If keep_selection is True, the previously selected day is re-selected
        (if still in the current month).
        """
        if not self.current_user_id:
            return

        # Month label (e.g. "2025 / 11")
        self.lbl_month.configure(
            text=f"{self.current_year} / {self.current_month:02d}"
        )

        prev_selected_day = self.selected_day if keep_selection else None

        self._load_tasks_for_month()
        self._rebuild_calendar()

        if keep_selection and prev_selected_day in self._day_tiles:
            self.on_day_clicked(prev_selected_day)
        else:
            self._clear_selected_day()

    def _load_tasks_for_month(self):
        """
        Load tasks for this user and current month from TASK & COURSE tables.
        """
        self.tasks_by_date.clear()
        if not self.current_user_id:
            return

        _, last_day = calendar.monthrange(
            self.current_year, self.current_month
        )
        month_start = f"{self.current_year}-{self.current_month:02d}-01"
        month_end = f"{self.current_year}-{self.current_month:02d}-{last_day:02d}"

        rows = self.db.fetchall(
            """
            SELECT
                T.id,
                T.name,
                T.description,
                T.due_date,
                C.id   AS course_id,
                C.name AS course_name
            FROM TASK T
            JOIN COURSE C ON T.course_id = C.id
            WHERE C.user_id = ?
              AND T.due_date IS NOT NULL
              AND T.due_date <> ''
              AND T.due_date BETWEEN ? AND ?
            ORDER BY C.name, T.id
            """,
            (self.current_user_id, month_start, month_end),
        )

        for row in rows:
            due = row["due_date"]
            if not isinstance(due, str):
                continue
            self.tasks_by_date.setdefault(due, []).append(row)

    def _rebuild_calendar(self):
        """
        Rebuild calendar tiles for the current month.
        """
        # Clear old widgets
        for child in self.calendar_frame.winfo_children():
            child.destroy()
        self._day_tiles.clear()

        # Weekday header (M T W T F S S)
        weekdays = ["M", "T", "W", "T", "F", "S", "S"]
        for col, name in enumerate(weekdays):
            lbl = ttk.Label(
                self.calendar_frame,
                text=name,
                anchor="center",
                font=("-size", 10, "-weight", "bold"),
            )
            lbl.grid(row=0, column=col, padx=4, pady=4, sticky="nsew")

        cal = calendar.Calendar(firstweekday=0)  # Monday
        weeks = cal.monthdayscalendar(self.current_year, self.current_month)

        # Day tiles
        for row_idx, week in enumerate(weeks, start=1):
            for col_idx, day in enumerate(week):
                if day == 0:
                    # Empty cell (outside this month)
                    spacer = ttk.Frame(self.calendar_frame)
                    spacer.grid(
                        row=row_idx,
                        column=col_idx,
                        padx=4,
                        pady=4,
                        sticky="nsew",
                    )
                    continue

                day_str = (
                    f"{self.current_year}-{self.current_month:02d}-{day:02d}"
                )
                tasks = self.tasks_by_date.get(day_str, [])

                # Tile frame (card-like button)
                tile = ttk.Frame(
                    self.calendar_frame,
                    padding=(4, 6),
                    bootstyle="light",  # base style / background
                    borderwidth=1,
                    relief="solid",
                )
                tile.grid(
                    row=row_idx,
                    column=col_idx,
                    padx=4,
                    pady=4,
                    sticky="nsew",
                )

                # Large day number
                lbl_day = ttk.Label(
                    tile,
                    text=str(day),
                    font=("-size", 11, "-weight", "bold"),
                    anchor="center",
                )
                lbl_day.pack(anchor="center")

                # Dots for tasks count (max 4 dots)
                if tasks:
                    dots_count = min(len(tasks), 4)
                    dot_char = "●"
                    dots_text = " ".join(dot_char for _ in range(dots_count))

                    lbl_dots = ttk.Label(
                        tile,
                        text=dots_text,
                        font=("-size", 12, "-weight", "bold"),
                        foreground="#7C3AED",
                    )
                    lbl_dots.pack(anchor="center", pady=(4, 0))
                else:
                    lbl_dots = None

                # Click binding (whole tile behaves like a button)
                def _bind_click(widget):
                    widget.bind(
                        "<Button-1>",
                        lambda _event, d=day: self.on_day_clicked(d),
                    )

                _bind_click(tile)
                _bind_click(lbl_day)
                if lbl_dots is not None:
                    _bind_click(lbl_dots)

                self._day_tiles[day] = tile

        # Configure grid weights for responsive layout
        rows_count = len(weeks) + 1  # header + weeks
        for r in range(rows_count):
            self.calendar_frame.rowconfigure(r, weight=1)
        for c in range(7):
            self.calendar_frame.columnconfigure(c, weight=1)

    # ---- Day selection ----------------------------------------------------
    def on_day_clicked(self, day: int):
        """
        Update selected day highlight and task list on the right pane.
        """
        self.selected_day = day
        day_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"
        self._current_date_str = day_str

        tasks = self.tasks_by_date.get(day_str, [])

        self.lbl_selected_day.configure(text=f"Tasks on {day_str}")
        self.tasks_list.delete(0, tk.END)
        self._list_index_to_task.clear()
        self._selected_task_row = None
        self._clear_task_detail()
        self._update_action_buttons_enabled(False)

        if not tasks:
            self.tasks_list.insert(tk.END, "No tasks.")
        else:
            index = 0
            last_course = None
            # Tasks are already ordered by course_name, T.id
            for row in tasks:
                course_name = self._row_value(row, "course_name", "-")
                if course_name != last_course:
                    header_text = f"[{course_name}]"
                    self.tasks_list.insert(tk.END, header_text)
                    self._list_index_to_task[index] = None  # header row
                    index += 1
                    last_course = course_name

                display = self._row_value(row, "name", "-")
                self.tasks_list.insert(tk.END, f"  • {display}")
                self._list_index_to_task[index] = row
                index += 1

        self._update_day_tile_selection()

    def _update_day_tile_selection(self):
        """
        Visually highlight the selected day tile.
        """
        for day, tile in self._day_tiles.items():
            if self.selected_day == day:
                tile.configure(bootstyle="info")
            else:
                tile.configure(bootstyle="light")

    def _clear_selected_day(self):
        """
        Reset selection and clear the task list on the right pane.
        """
        self.selected_day = None
        self._current_date_str = None
        self._selected_task_row = None
        self._list_index_to_task.clear()

        self.lbl_selected_day.configure(text="No date selected")
        self.tasks_list.delete(0, tk.END)
        self._clear_task_detail()
        self._update_action_buttons_enabled(False)
        self._update_day_tile_selection()

    # ---- Task selection and details --------------------------------------
    def on_task_selected(self, _event):
        """
        Called when the user selects an item in the task list.
        Headers are ignored; only real task rows can be selected.
        """
        selection = self.tasks_list.curselection()
        if not selection:
            self._selected_task_row = None
            self._clear_task_detail()
            self._update_action_buttons_enabled(False)
            return

        index = selection[0]
        row = self._list_index_to_task.get(index)

        if row is None:
            # Course header row was selected; ignore it as a task
            self._selected_task_row = None
            self._clear_task_detail()
            self._update_action_buttons_enabled(False)
            return

        self._selected_task_row = row
        self._update_task_detail(row)
        self._update_action_buttons_enabled(True)

    def _update_task_detail(self, row):
        """
        Show selected task details in the detail card.
        """
        course_name = self._row_value(row, "course_name", "-")
        task_name = self._row_value(row, "name", "-")
        due_date = self._row_value(row, "due_date", "-") or "-"
        desc_raw = self._row_value(row, "description", None)
        desc = (desc_raw or "").strip() or "-"

        self.lbl_detail_course.configure(text=course_name)
        self.lbl_detail_task.configure(text=task_name)
        self.lbl_detail_due.configure(text=due_date)
        self.lbl_detail_desc.configure(text=desc)

    def _clear_task_detail(self):
        """
        Clear the detail card labels.
        """
        self.lbl_detail_course.configure(text="-")
        self.lbl_detail_task.configure(text="-")
        self.lbl_detail_due.configure(text="-")
        self.lbl_detail_desc.configure(text="-")

    def _update_action_buttons_enabled(self, enabled: bool):
        """
        Enable or disable Edit/Delete buttons.
        """
        state = "normal" if enabled else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)

    # ---- Edit / Delete actions -------------------------------------------
    def on_edit_task(self):
        """
        Edit the selected task (name and description).
        """
        if not self._selected_task_row:
            return

        row = self._selected_task_row
        task_id = row["id"]
        current_name = self._row_value(row, "name", "")
        current_desc = self._row_value(row, "description", "") or ""

        # Ask user for new task name
        new_name = Querybox.get_string(
            "Edit task name",
            "Task name:",
            initialvalue=current_name,
        )
        if new_name is None:
            # User canceled
            return
        new_name = new_name.strip()
        if not new_name:
            Messagebox.show_error("Task name cannot be empty.", "Error")
            return

        # Ask user for new description
        new_desc = Querybox.get_string(
            "Edit description",
            "Description (optional):",
            initialvalue=current_desc,
        )
        if new_desc is None:
            # If user cancels here, keep original description
            new_desc = current_desc

        # Update DB
        self.db.execute(
            "UPDATE TASK SET name = ?, description = ? WHERE id = ?",
            (new_name, new_desc, task_id),
        )

        # Refresh month and keep current day selection
        self.refresh_month(keep_selection=True)

    def on_delete_task(self):
        """
        Delete the selected task from DB.
        """
        if not self._selected_task_row:
            return

        row = self._selected_task_row
        task_id = row["id"]
        task_name = self._row_value(row, "name", "")

        result = Messagebox.okcancel(
            f"Delete this task?\n\n{task_name}",
            "Confirm delete",
        )
        if result != "OK":
            return

        # Delete from DB
        self.db.execute(
            "DELETE FROM TASK WHERE id = ?",
            (task_id,),
        )

        # Refresh month and keep current day selection
        self.refresh_month(keep_selection=True)
