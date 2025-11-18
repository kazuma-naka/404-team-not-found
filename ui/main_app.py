# ui/main_app.py
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, YES, X

from ui.llm_chat import LlmChatFrame
from ui.task_manager import TaskManagerFrame


class MainAppFrame(ttk.Frame):
    """
    TaskManager と LLM チャットをボトムナビゲーションで切り替えるコンテナ。
    Android の BottomNavigation に近いイメージ。
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
        self.task_frame = TaskManagerFrame(self.content, controller)
        self.chat_frame = LlmChatFrame(self.content, controller)

        # TaskManager のユーザー設定
        self.task_frame.set_user(self.current_user_id)

        # 最初は TaskManager を表示
        self.task_frame.pack(fill=BOTH, expand=YES)
        self.chat_frame.pack_forget()

        # ---- Bottom Navigation --------------------------------------------
        nav = ttk.Frame(self, padding=(12, 8))
        nav.pack(fill=X, side=tk.BOTTOM)

        self.btn_tasks = ttk.Button(
            nav,
            text="Tasks",
            bootstyle="primary",
            command=self.show_tasks,
        )
        self.btn_tasks.pack(side=tk.LEFT, expand=True, fill=X, padx=(0, 6))

        self.btn_chat = ttk.Button(
            nav,
            text="LLM Chat",
            bootstyle="secondary",
            command=self.show_chat,
        )
        self.btn_chat.pack(side=tk.LEFT, expand=True, fill=X, padx=(6, 0))

    # ---- Navigation actions -----------------------------------------------
    def show_tasks(self):
        self.chat_frame.pack_forget()
        self.task_frame.pack(fill=BOTH, expand=YES)
        self.controller.title("Task Manager")
        self.btn_tasks.configure(bootstyle="primary")
        self.btn_chat.configure(bootstyle="secondary")

    def show_chat(self):
        self.task_frame.pack_forget()
        self.chat_frame.pack(fill=BOTH, expand=YES)
        self.controller.title("Task Manager - LLM Chat")
        self.btn_tasks.configure(bootstyle="secondary")
        self.btn_chat.configure(bootstyle="primary")
