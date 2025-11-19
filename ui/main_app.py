# ui/main_app.py
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X

from ui.calendar_view import CalendarTaskFrame
# from ui.task_manager import TaskManagerFrame  # 必要ならあとで復活


class MainAppFrame(ttk.Frame):
    """
    アプリ全体のメインコンテナ。
    上部にユーザー名と Logout、下にカレンダー UI。
    """

    def __init__(self, parent, controller, user_row):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id = user_row["id"]

        # sqlite3.Row は .get を持たないので try/except で安全に取り出す
        try:
            name = user_row["name"]
        except Exception:
            name = "User"

        # ---- Top Bar: Welcome / Logout ------------------------------------
        top = ttk.Frame(self, padding=(12, 12, 12, 0))
        top.pack(fill=X, side=tk.TOP)

        self.user_label = ttk.Label(
            top,
            text=f"Welcome, {name}!",
            font=("-size", 12),
        )
        self.user_label.pack(side=tk.LEFT)

        ttk.Button(
            top,
            text="Logout",
            bootstyle="danger",
            command=self.controller.logout,
        ).pack(side=tk.RIGHT)

        # ---- Content Area --------------------------------------------------
        self.content = ttk.Frame(self, padding=(0, 8, 0, 0))
        self.content.pack(fill=BOTH, expand=YES)

        # カレンダーをメイン画面として表示
        self.calendar_frame = CalendarTaskFrame(self.content, controller)
        self.calendar_frame.pack(fill=BOTH, expand=YES)
        self.calendar_frame.set_user(self.current_user_id)

        # ウィンドウタイトル
        self.controller.title("Task Manager - Calendar")
