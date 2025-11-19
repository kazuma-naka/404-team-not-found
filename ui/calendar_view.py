# ui/calendar_view.py
import calendar
from datetime import date

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X


class CalendarTaskFrame(ttk.Frame):
    """
    Calendar + task list frame.

    Left: monthly calendar
        - each day is a "tile" with rounded-card feeling
        - if the day has tasks, show small dots under the day number
        - clicking a day highlights the tile and shows tasks on the right
    Right: task list for the selected day
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

        self.tasks_list = tk.Listbox(
            right_card,
            height=18,
            borderwidth=0,
            highlightthickness=0,
        )
        self.tasks_list.pack(fill=BOTH, expand=True, pady=(8, 0))

        # Initial build (user will be set later by set_user)
        self._rebuild_calendar()

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
    def refresh_month(self):
        """
        Load tasks for the current year/month from DB and rebuild calendar.
        """
        if not self.current_user_id:
            return

        # Month label (e.g. "2025 / 11")
        self.lbl_month.configure(
            text=f"{self.current_year} / {self.current_month:02d}"
        )

        self._load_tasks_for_month()
        self._rebuild_calendar()
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
            SELECT T.id, T.name, T.description, T.due_date
            FROM TASK T
            JOIN COURSE C ON T.course_id = C.id
            WHERE C.user_id = ?
              AND T.due_date IS NOT NULL
              AND T.due_date <> ''
              AND T.due_date BETWEEN ? AND ?
            ORDER BY T.due_date
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
                    # Use a heavy circle character and add spaces between them
                    dot_char = "●"  # thicker than "•"
                    dots_text = " ".join(dot_char for _ in range(dots_count))

                    lbl_dots = ttk.Label(
                        tile,
                        text=dots_text,
                        font=("-size", 12, "-weight", "bold"),  # bigger & bold
                        foreground="#7C3AED",  # purple-ish
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
        tasks = self.tasks_by_date.get(day_str, [])

        self.lbl_selected_day.configure(text=f"Tasks on {day_str}")
        self.tasks_list.delete(0, tk.END)

        if not tasks:
            self.tasks_list.insert(tk.END, "No tasks.")
        else:
            for row in tasks:
                name = row["name"]
                desc = (row["description"] or "").strip()
                if desc:
                    display = f"{name} - {desc[:40]}"
                else:
                    display = name
                self.tasks_list.insert(tk.END, display)

        self._update_day_tile_selection()

    def _update_day_tile_selection(self):
        """
        Visually highlight the selected day tile.
        """
        for day, tile in self._day_tiles.items():
            if self.selected_day == day:
                # Selected: purple outline-like feeling
                tile.configure(bootstyle="info")  # or "info-outline"
            else:
                tile.configure(bootstyle="light")

    def _clear_selected_day(self):
        """
        Reset selection and clear the task list on the right pane.
        """
        self.selected_day = None
        self.lbl_selected_day.configure(text="No date selected")
        self.tasks_list.delete(0, tk.END)
        self._update_day_tile_selection()
