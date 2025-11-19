# ui/calendar_view.py
import calendar
from datetime import date

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X


class CalendarTaskFrame(ttk.Frame):
    """
    カレンダーをメインにして、TASK テーブルの due_date を日付ごとに表示するフレーム。
    - 左側: 月間カレンダー
        - その日にタスクがあれば「日付 + (件数)」を表示
        - クリックすると右側にタスク一覧を表示
    - 右側: 選択した日のタスク一覧
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

        # ---- Top Bar (month navigation) -----------------------------------
        top = ttk.Frame(self, padding=(12, 12, 12, 0))
        top.pack(fill=X)

        self.btn_prev = ttk.Button(
            top, text="◀ Prev", command=self.goto_prev_month
        )
        self.btn_prev.pack(side=tk.LEFT)

        self.lbl_month = ttk.Label(
            top,
            text="",
            font=("-size", 14, "-weight", "bold"),
        )
        self.lbl_month.pack(side=tk.LEFT, expand=True)

        self.btn_next = ttk.Button(
            top, text="Next ▶", command=self.goto_next_month
        )
        self.btn_next.pack(side=tk.RIGHT)

        # ---- Main area: calendar + task list ------------------------------
        main = ttk.Frame(self, padding=12)
        main.pack(fill=BOTH, expand=True)

        # 左: カレンダー
        self.calendar_frame = ttk.Frame(main)
        self.calendar_frame.pack(side=tk.LEFT, fill=BOTH, expand=True)

        # 右: 選択した日のタスク一覧
        right = ttk.Frame(main, padding=(12, 0, 0, 0))
        right.pack(side=tk.LEFT, fill=BOTH, expand=True)

        self.lbl_selected_day = ttk.Label(
            right,
            text="No date selected",
            font=("-size", 12, "-weight", "bold"),
        )
        self.lbl_selected_day.pack(anchor="w")

        self.tasks_list = tk.Listbox(right, height=16)
        self.tasks_list.pack(fill=BOTH, expand=True, pady=(8, 0))

        # 追加で詳細を出したければここに Text や LabelFrame を足せる

        # 初期表示（ユーザーは set_user で設定される）
        self._rebuild_calendar()

    # ---- Public API -------------------------------------------------------
    def set_user(self, user_id: int):
        """ログイン後に App から呼ばれる想定。"""
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
        """現在の year/month について DB からタスクを読み込み、カレンダーを更新。"""
        if not self.current_user_id:
            return

        # タイトル
        self.lbl_month.configure(
            text=f"{self.current_year} - {self.current_month:02d}"
        )

        # その月のタスクをロード
        self._load_tasks_for_month()
        # カレンダーを作り直し
        self._rebuild_calendar()
        # 選択中の日付表示をリセット
        self._clear_selected_day()

    def _load_tasks_for_month(self):
        """TASK & COURSE から、そのユーザーの該当月のタスクを読み込んで dict 化。"""
        self.tasks_by_date.clear()
        if not self.current_user_id:
            return

        _, last_day = calendar.monthrange(
            self.current_year, self.current_month)
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
        """カレンダー部分の Widget を全部作り直す。"""
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        # 曜日ヘッダ
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
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

        # 日付セル
        for row_idx, week in enumerate(weeks, start=1):
            for col_idx, day in enumerate(week):
                if day == 0:
                    # 月に属さない空セル
                    frame = ttk.Frame(self.calendar_frame)
                    frame.grid(row=row_idx, column=col_idx,
                               padx=2, pady=2, sticky="nsew")
                    continue

                day_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"
                tasks = self.tasks_by_date.get(day_str, [])
                text = str(day)
                if tasks:
                    # タスク件数を () 内に表示
                    text += f"\n({len(tasks)})"

                btn = ttk.Button(
                    self.calendar_frame,
                    text=text,
                    command=lambda d=day: self.on_day_clicked(d),
                    width=6,
                )
                btn.grid(row=row_idx, column=col_idx,
                         padx=2, pady=2, sticky="nsew")

        # グリッドのリサイズ設定
        rows_count = len(weeks) + 1  # header + weeks
        for r in range(rows_count):
            self.calendar_frame.rowconfigure(r, weight=1)
        for c in range(7):
            self.calendar_frame.columnconfigure(c, weight=1)

    # ---- Day selection ----------------------------------------------------
    def on_day_clicked(self, day: int):
        self.selected_day = day
        day_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"
        tasks = self.tasks_by_date.get(day_str, [])

        self.lbl_selected_day.configure(text=f"Tasks on {day_str}")
        self.tasks_list.delete(0, tk.END)

        if not tasks:
            self.tasks_list.insert(tk.END, "No tasks.")
            return

        for row in tasks:
            name = row["name"]
            desc = (row["description"] or "").strip()
            if desc:
                display = f"{name} - {desc[:40]}"
            else:
                display = name
            self.tasks_list.insert(tk.END, display)

    def _clear_selected_day(self):
        self.selected_day = None
        self.lbl_selected_day.configure(text="No date selected")
        self.tasks_list.delete(0, tk.END)
