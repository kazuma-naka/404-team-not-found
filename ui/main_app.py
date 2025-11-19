# ui/main_app.py
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X

from ui.task_manager import TaskManagerFrame
from ui.calendar_view import CalendarTaskFrame


class MainAppFrame(ttk.Frame):
    """
    カレンダーと TaskManager をボトムナビで切り替えるコンテナ。
    カレンダーがメイン UI。
    """

    def __init__(self, parent, controller, user_row):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id = user_row["id"]

        # ---- Content Area --------------------------------------------------
        self.content = ttk.Frame(self, padding=0)
        self.content.pack(fill=BOTH, expand=YES)

        # 2つの画面を同じ場所に重ねておき、pack_forget / pack で切り替える
        self.calendar_frame = CalendarTaskFrame(self.content, controller)
        self.task_frame = TaskManagerFrame(self.content, controller)

        # ユーザー設定
        self.calendar_frame.set_user(self.current_user_id)
        self.task_frame.set_user(self.current_user_id)

        # 最初は Calendar を表示
        self.calendar_frame.pack(fill=BOTH, expand=YES)
        self.task_frame.pack_forget()
        self.controller.title("Task Manager - Calendar")

        # ---- Bottom Navigation --------------------------------------------
        nav = ttk.Frame(self, padding=(12, 8))
        nav.pack(fill=X, side=tk.BOTTOM)

        self.btn_calendar = ttk.Button(
            nav,
            text="Calendar",
            bootstyle="primary",
            command=self.show_calendar,
        )
        self.btn_calendar.pack(side=tk.LEFT, expand=True, fill=X, padx=(0, 6))

        self.btn_tasks = ttk.Button(
            nav,
            text="Tasks",
            bootstyle="secondary",
            command=self.show_tasks,
        )
        self.btn_tasks.pack(side=tk.LEFT, expand=True, fill=X, padx=(6, 0))

    # ---- Navigation actions -----------------------------------------------
    def show_calendar(self):
        self.calendar_frame.refresh_month()
        self.task_frame.pack_forget()
        self.calendar_frame.pack(fill=BOTH, expand=YES)
        self.controller.title("Task Manager - Calendar")
        self.btn_calendar.configure(bootstyle="primary")
        self.btn_tasks.configure(bootstyle="secondary")

    def show_tasks(self):
        self.calendar_frame.pack_forget()
        self.task_frame.pack(fill=BOTH, expand=YES)
        # TaskManagerFrame 側でもタイトルを更新しているが、ここではシンプルに上書き
        self.controller.title("Task Manager - Tasks")
        self.btn_calendar.configure(bootstyle="secondary")
        self.btn_tasks.configure(bootstyle="primary")
