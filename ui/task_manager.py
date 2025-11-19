# ui/task_manager.py
import tkinter as tk
from datetime import datetime, date

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import DateEntry  # ★ 追加


class TaskManagerFrame(ttk.Frame):
    """
    Simple card-style Task Manager.
    Focused on:
      - Course name
      - Task name
      - Due date (YYYY-MM-DD)
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id = None

        # ---- Notion風の枠なしスタイルを定義 ---------------------------------
        style = ttk.Style()

        # Entry 用（Task のタイトルなど）
        style.configure(
            "Notion.TEntry",
            borderwidth=0,
            relief="flat",
            padding=0,
        )

        # Combobox 用（Course 選択）
        style.configure(
            "Notion.TCombobox",
            borderwidth=0,
            relief="flat",
            padding=0,
        )

        # ---- Top Bar --------------------------------------------------------
        top = ttk.Frame(self, padding=(12, 12, 12, 0))
        top.pack(fill=X)
        self.user_label = ttk.Label(top, text="Welcome!", font=("-size", 12))
        self.user_label.pack(side=tk.LEFT)
        ttk.Button(
            top,
            text="Logout",
            bootstyle="danger",
            command=self.controller.logout,
        ).pack(side=tk.RIGHT)

        # ---- Main Area (center card) ---------------------------------------
        main = ttk.Frame(self, padding=24)
        main.pack(fill=BOTH, expand=True)

        # 中央寄せ用コンテナ
        center = ttk.Frame(main)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # カード本体
        self.card = ttk.Frame(
            center,
            padding=6,
        )
        self.card.grid(row=0, column=0, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(0, weight=1)

        # "Course" pill
        self.lbl_course_pill = ttk.Label(
            self.card,
            text="Course",
            padding=(12, 4),
            bootstyle="light",
        )
        self.lbl_course_pill.grid(row=0, column=0, sticky="w")

        # Course input（既存コースを選ぶ + 新規も入力できる ComboBox）
        ttk.Label(self.card, text="Course", bootstyle="secondary").grid(
            row=1, column=0, sticky="w", pady=(16, 4)
        )
        self.course_var = tk.StringVar()
        self.cmb_course = ttk.Combobox(
            self.card,
            textvariable=self.course_var,
            width=30,
            style="Notion.TCombobox",  # ★ 枠なしスタイルを適用
        )
        self.cmb_course.grid(row=2, column=0, sticky="ew")
        self.card.columnconfigure(0, weight=1)

        # Task title（大きめのフォント）
        ttk.Label(self.card, text="Task", bootstyle="secondary").grid(
            row=3, column=0, sticky="w", pady=(24, 4)
        )
        self.task_var = tk.StringVar()
        self.ent_task = ttk.Entry(
            self.card,
            textvariable=self.task_var,
            font=("-size", 20),
            style="Notion.TEntry",  # ★ 枠なしスタイルを適用
        )
        self.ent_task.grid(row=4, column=0, sticky="ew")

        # Due date（DateEntry でカレンダーから選択）
        ttk.Label(self.card, text="Due Date (YYYY-MM-DD)").grid(
            row=5, column=0, sticky="w", pady=(24, 4)
        )

        # ★ StringVar はやめて、DateEntry 内の Entry から値を取るように統一
        self.ent_due = DateEntry(
            self.card,
            dateformat="%Y-%m-%d",  # 表示フォーマット
            width=12,
        )
        self.ent_due.grid(row=6, column=0, sticky="ew")

        # ★ DateEntry 内部の Entry も枠なしに
        try:
            self.ent_due.entry.configure(borderwidth=0, relief="flat")
        except Exception:
            # もしプラットフォーム依存で失敗してもアプリが落ちないようにする
            pass

        # Time left 表示
        self.lbl_timeleft = ttk.Label(
            self.card,
            text="Time Left: -",
            bootstyle="secondary",
        )
        self.lbl_timeleft.grid(row=7, column=0, sticky="w", pady=(8, 0))

        # Save ボタン
        self.btn_save = ttk.Button(
            self.card,
            text="Save Task",
            bootstyle="success",
            command=self.save_task,
        )
        self.btn_save.grid(row=8, column=0, sticky="ew", pady=(16, 0))

        # 最近追加したタスク一覧（簡易）
        self.recent_frame = ttk.LabelFrame(
            main,
            text="Recently added tasks",
            padding=12,
        )
        self.recent_frame.pack(side=tk.BOTTOM, fill=X, padx=24, pady=(16, 0))
        self.lst_recent = tk.Listbox(self.recent_frame, height=4)
        self.lst_recent.pack(fill=X)

        # Enter キーで保存
        self.ent_task.bind("<Return>", lambda e: self.save_task())
        self.ent_due.bind("<Return>", lambda e: self.save_task())

        # ★ DateEntry で日付を選択したときに TimeLeft を更新
        self.ent_due.bind(
            "<<DateEntrySelected>>",
            lambda e: self._update_timeleft_label(self.ent_due.entry.get()),
        )

    # ---- Public API ---------------------------------------------------------
    def set_user(self, user_id: int):
        """Called by App after login."""
        self.current_user_id = user_id
        rows = self.db.fetchall("SELECT name FROM USER WHERE id=?", (user_id,))
        name = rows[0]["name"] if rows else "User"
        self.user_label.configure(text=f"Welcome, {name}!")
        self.controller.title(f"Task Manager - {name}")

        self._load_courses_into_combobox()
        self._load_recent_tasks()

    # ---- Helpers ------------------------------------------------------------
    def _load_courses_into_combobox(self):
        if not self.current_user_id:
            return
        rows = self.db.fetchall(
            "SELECT name FROM COURSE WHERE user_id=? ORDER BY id DESC",
            (self.current_user_id,),
        )
        names = [r["name"] for r in rows]
        self.cmb_course["values"] = names

    def _load_recent_tasks(self, limit: int = 5):
        self.lst_recent.delete(0, tk.END)
        if not self.current_user_id:
            return
        rows = self.db.fetchall(
            """
            SELECT T.name AS task_name, T.due_date, C.name AS course_name
            FROM TASK T
            JOIN COURSE C ON T.course_id = C.id
            WHERE C.user_id = ?
            ORDER BY T.id DESC
            LIMIT ?
            """,
            (self.current_user_id, limit),
        )
        for r in rows:
            line = f"[{r['course_name']}] {r['task_name']}  ({r['due_date'] or '-'})"
            self.lst_recent.insert(tk.END, line)

    def _get_or_create_course_id(self, course_name: str) -> int:
        """コース名から ID を取得。なければ新規作成して ID を返す。"""
        rows = self.db.fetchall(
            "SELECT id FROM COURSE WHERE user_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (self.current_user_id, course_name),
        )
        if rows:
            return rows[0]["id"]

        # 新規作成
        self.db.execute(
            "INSERT INTO COURSE (user_id, name, description) VALUES (?, ?, '')",
            (self.current_user_id, course_name),
        )
        rows = self.db.fetchall(
            "SELECT id FROM COURSE WHERE user_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (self.current_user_id, course_name),
        )
        return rows[0]["id"]

    def _update_timeleft_label(self, due_str: str):
        due_str = (due_str or "").strip()
        if not due_str:
            self.lbl_timeleft.configure(text="Time Left: -")
            return

        try:
            d = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            self.lbl_timeleft.configure(text="Time Left: -")
            return

        today = date.today()
        delta = d - today
        if delta.days < 0:
            txt = f"Time Left: overdue by {-delta.days} day(s)"
        elif delta.days == 0:
            txt = "Time Left: today"
        else:
            txt = f"Time Left: {delta.days} day(s)"
        self.lbl_timeleft.configure(text=txt)

    # ---- Actions ------------------------------------------------------------
    def save_task(self):
        course_name = self.course_var.get().strip()
        task_name = self.task_var.get().strip()
        # ★ DateEntry 内部の Entry から文字列を取得
        due_str = self.ent_due.entry.get().strip()

        if not course_name:
            Messagebox.show_error("Course is required.", "Error")
            return
        if not task_name:
            Messagebox.show_error("Task is required.", "Error")
            return

        # 期日文字列は任意。あればフォーマットだけチェック
        if due_str:
            try:
                datetime.strptime(due_str, "%Y-%m-%d")
            except ValueError:
                Messagebox.show_error(
                    "Due date must be in YYYY-MM-DD format.", "Error"
                )
                return

        cid = self._get_or_create_course_id(course_name)

        # TASK 登録（description は空で入れる）
        self.db.execute(
            "INSERT INTO TASK (course_id, name, description, due_date) "
            "VALUES (?, ?, ?, ?)",
            (cid, task_name, "", due_str or None),
        )

        # UI 更新
        self._load_courses_into_combobox()
        self._load_recent_tasks()
        self._update_timeleft_label(due_str)

        # 簡単に入力欄をリセット（コースは残すと連続入力しやすい）
        self.task_var.set("")
        # Due 日付もクリア（Notion っぽく毎回空から）
        try:
            self.ent_due.entry.delete(0, tk.END)
        except Exception:
            pass

        self.ent_task.focus_set()
