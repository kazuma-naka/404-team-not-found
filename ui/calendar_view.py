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
        - selected day has an inline "Add Task" form
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

        # Add-task form variables (right pane)
        self.course_var = tk.StringVar()
        self.task_var = tk.StringVar()

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

        # ---- header: "Tasks on ..." + +Add Task ボタン --------------------
        header = ttk.Frame(right_card, padding=(0, 0, 0, 4))
        header.pack(fill=X)

        self.lbl_selected_day = ttk.Label(
            header,
            text="No date selected",
            font=("-size", 12, "-weight", "bold"),
        )
        self.lbl_selected_day.pack(side=tk.LEFT)

        self.btn_toggle_add = ttk.Button(
            header,
            text="+ Add task for this day",
            bootstyle="success",           # filled green button (more visible)
            command=self.on_add_task_button_click,
            padding=(16, 6),               # bigger clickable area
            width=20,                      # wide enough to stand out
        )
        # 最初は pack しない

        # ---- Add-task form (最初は非表示) ---------------------------------
        self.add_task_frame = ttk.LabelFrame(
            right_card,
            text="Add task",
            padding=8,
        )

        self.btn_close_add = ttk.Button(
            self.add_task_frame,
            text="×",
            width=3,
            bootstyle="danger",
            command=self._hide_add_task_form,
        )

        self.btn_close_add.grid(row=0, column=1, sticky="e")

        ttk.Label(self.add_task_frame, text="Course", bootstyle="secondary").grid(
            row=0, column=0, sticky="w"
        )
        self.cmb_course = ttk.Combobox(
            self.add_task_frame,
            textvariable=self.course_var,
            width=26,
        )
        self.cmb_course.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 4),
        )

        ttk.Label(self.add_task_frame, text="Task", bootstyle="secondary").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        self.ent_task = ttk.Entry(
            self.add_task_frame,
            textvariable=self.task_var,
        )
        self.ent_task.grid(row=3, column=0, columnspan=2, sticky="ew")

        self.btn_add_task = ttk.Button(
            self.add_task_frame,
            text="Add",
            bootstyle="success",
            width=10,
            command=self.on_add_task,
        )
        self.btn_add_task.grid(row=4, column=1, sticky="e", pady=(8, 0))

        self.add_task_frame.columnconfigure(0, weight=1)
        self.add_task_frame.columnconfigure(1, weight=1)

        # ---- Task list (grouped by course, with headers) -------------------
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
        ).grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.lbl_detail_course = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_course.grid(row=1, column=1, sticky="w", pady=(8, 2))

        ttk.Label(
            self.detail_card,
            text="Task:",
        ).grid(row=2, column=0, sticky="w", pady=(2, 2))
        self.lbl_detail_task = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_task.grid(row=2, column=1, sticky="w", pady=(2, 2))

        ttk.Label(
            self.detail_card,
            text="Due:",
        ).grid(row=3, column=0, sticky="w", pady=(2, 2))
        self.lbl_detail_due = ttk.Label(self.detail_card, text="-")
        self.lbl_detail_due.grid(row=3, column=1, sticky="w", pady=(2, 2))

        ttk.Label(
            self.detail_card,
            text="Description:",
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
        """Safe accessor for sqlite3.Row."""
        try:
            value = row[key]
        except Exception:
            return default
        return value if value is not None else default

    # ---- Public API -------------------------------------------------------
    def set_user(self, user_id: int):
        """Called from App after login."""
        self.current_user_id = user_id
        self._load_courses_into_combobox()
        self.refresh_month()

    # ---- Month navigation -------------------------------------------------
    def goto_prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.refresh_month(keep_selection=True)

    def goto_next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.refresh_month(keep_selection=True)

    # ---- Data loading + UI refresh ---------------------------------------
    def refresh_month(self, keep_selection: bool = False):
        """
        Load tasks for the current year/month from DB and rebuild calendar.
        """
        if not self.current_user_id:
            return

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
        """Load tasks for this user and current month from TASK & COURSE."""
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
        """Rebuild calendar tiles for the current month."""
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

                tile = ttk.Frame(
                    self.calendar_frame,
                    padding=(4, 6),
                    bootstyle="light",
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

                lbl_day = ttk.Label(
                    tile,
                    text=str(day),
                    font=("-size", 11, "-weight", "bold"),
                    anchor="center",

                )
                lbl_day.pack(anchor="center")

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

        rows_count = len(weeks) + 1
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

        # 日付が選択されたので +Add Task ボタンを表示
        if self.btn_toggle_add.winfo_manager() == "":
            self.btn_toggle_add.pack(side=tk.RIGHT)

        # すでにフォームが開いている場合はタイトルだけ更新
        if self.add_task_frame.winfo_manager():
            self.add_task_frame.configure(text=f"Add task on {day_str}")

        if not tasks:
            self.tasks_list.insert(tk.END, "No tasks.")
        else:
            index = 0
            last_course = None
            for row in tasks:
                course_name = self._row_value(row, "course_name", "-")
                if course_name != last_course:
                    header_text = f"[{course_name}]"
                    self.tasks_list.insert(tk.END, header_text)
                    self._list_index_to_task[index] = None
                    index += 1
                    last_course = course_name

                display = self._row_value(row, "name", "-")
                self.tasks_list.insert(tk.END, f"  • {display}")
                self._list_index_to_task[index] = row
                index += 1

        self._update_day_tile_selection()

    def _update_day_tile_selection(self):
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

        # ボタンとフォームを隠す
        if self.btn_toggle_add.winfo_manager():
            self.btn_toggle_add.pack_forget()
        self._hide_add_task_form()

    # ---- Add-task form toggle --------------------------------------------
    def on_add_task_button_click(self):
        """
        上部の「+ Add Task」ボタンが押されたとき。
        最初のクリックでフォームを表示、2回目で閉じるトグルにしてある。
        """
        if not self._current_date_str:
            Messagebox.show_info(
                "Please select a date on the calendar first.",
                "No date selected",
            )
            return

        if self.add_task_frame.winfo_manager():
            self._hide_add_task_form()
        else:
            self._show_add_task_form()

    def _show_add_task_form(self):
        if self._current_date_str:
            self.add_task_frame.configure(
                text=f"Add task on {self._current_date_str}"
            )

        if self.add_task_frame.winfo_manager() == "":
            self.add_task_frame.pack(
                fill=X,
                pady=(8, 4),
                before=self.tasks_list,
            )

        self.ent_task.focus_set()

    def _hide_add_task_form(self):
        if self.add_task_frame.winfo_manager():
            self.add_task_frame.pack_forget()
        self.task_var.set("")
        # course_var は維持（連続入力しやすくするため）

    # ---- Task selection and details --------------------------------------
    def on_task_selected(self, _event):
        selection = self.tasks_list.curselection()
        if not selection:
            self._selected_task_row = None
            self._clear_task_detail()
            self._update_action_buttons_enabled(False)
            return

        index = selection[0]
        row = self._list_index_to_task.get(index)

        if row is None:
            self._selected_task_row = None
            self._clear_task_detail()
            self._update_action_buttons_enabled(False)
            return

        self._selected_task_row = row
        self._update_task_detail(row)
        self._update_action_buttons_enabled(True)

    def _update_task_detail(self, row):
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
        self.lbl_detail_course.configure(text="-")
        self.lbl_detail_task.configure(text="-")
        self.lbl_detail_due.configure(text="-")
        self.lbl_detail_desc.configure(text="-")

    def _update_action_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)

    # ---- Edit / Delete actions -------------------------------------------
    def on_edit_task(self):
        if not self._selected_task_row:
            return

        row = self._selected_task_row
        task_id = row["id"]
        current_name = self._row_value(row, "name", "")
        current_desc = self._row_value(row, "description", "") or ""

        new_name = Querybox.get_string(
            "Edit task name",
            "Task name:",
            initialvalue=current_name,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            Messagebox.show_error("Task name cannot be empty.", "Error")
            return

        new_desc = Querybox.get_string(
            "Edit description",
            "Description (optional):",
            initialvalue=current_desc,
        )
        if new_desc is None:
            new_desc = current_desc

        self.db.execute(
            "UPDATE TASK SET name = ?, description = ? WHERE id = ?",
            (new_name, new_desc, task_id),
        )

        self.refresh_month(keep_selection=True)

    def on_delete_task(self):
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

        self.db.execute(
            "DELETE FROM TASK WHERE id = ?",
            (task_id,),
        )

        self.refresh_month(keep_selection=True)

    # ---- Add task from calendar ------------------------------------------
    def _load_courses_into_combobox(self):
        if not self.current_user_id:
            return
        rows = self.db.fetchall(
            "SELECT name FROM COURSE WHERE user_id=? ORDER BY id DESC",
            (self.current_user_id,),
        )
        names = [r["name"] for r in rows]
        self.cmb_course["values"] = names

    def _get_or_create_course_id(self, course_name: str) -> int:
        rows = self.db.fetchall(
            "SELECT id FROM COURSE WHERE user_id=? AND name=? "
            "ORDER BY id DESC LIMIT 1",
            (self.current_user_id, course_name),
        )
        if rows:
            return rows[0]["id"]

        self.db.execute(
            "INSERT INTO COURSE (user_id, name, description) VALUES (?, ?, '')",
            (self.current_user_id, course_name),
        )
        rows = self.db.fetchall(
            "SELECT id FROM COURSE WHERE user_id=? AND name=? "
            "ORDER BY id DESC LIMIT 1",
            (self.current_user_id, course_name),
        )
        return rows[0]["id"]

    def on_add_task(self):
        """
        Form 内の「Add」ボタン。
        現在選択中の日付にタスクを追加する。
        """
        if not self._current_date_str:
            Messagebox.show_info(
                "Please select a date on the calendar first.",
                "No date selected",
            )
            return

        course_name = self.course_var.get().strip()
        task_name = self.task_var.get().strip()

        if not course_name:
            Messagebox.show_error("Course is required.", "Error")
            return
        if not task_name:
            Messagebox.show_error("Task name is required.", "Error")
            return

        cid = self._get_or_create_course_id(course_name)

        self.db.execute(
            "INSERT INTO TASK (course_id, name, description, due_date) "
            "VALUES (?, ?, ?, ?)",
            (cid, task_name, "", self._current_date_str),
        )

        self._load_courses_into_combobox()

        self.task_var.set("")
        self.ent_task.focus_set()

        self.refresh_month(keep_selection=True)
