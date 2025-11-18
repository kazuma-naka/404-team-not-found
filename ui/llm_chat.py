# ui/llm_chat.py
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X

from llm.smollm_client import (
    generate_rewrite,
    generate_qa_answer,
    get_current_model_path,
    set_model_path,
    reset_to_default_model,
)


class SingleLlmTab(ttk.Frame):
    """
    1 つの LLM タブ（ログ、入力欄、Send / Reset / Copy ボタン）をまとめたクラス。
    generate_func で、書き換え or Q&A を切り替える。
    """

    def __init__(
        self,
        parent,
        title_label: str,
        system_message: str,
        generate_func,
    ):
        super().__init__(parent)

        self._generate_func = generate_func
        self._last_reply: str | None = None
        self._system_message = system_message

        # ステータス表示用（Copied! など）
        self._status_var = tk.StringVar(value="")

        # ---- Chat Log ------------------------------------------------------
        log_frame = ttk.LabelFrame(self, text=title_label, padding=10)
        log_frame.pack(fill=BOTH, expand=True)

        self.txt_log = tk.Text(
            log_frame,
            height=16,
            state="disabled",
            wrap="word",
        )
        self.txt_log.pack(fill=BOTH, expand=True)

        # 🔹コピー用ボタンを置く小さなフレーム
        copy_btn_frame = ttk.Frame(log_frame)
        copy_btn_frame.pack(fill=X, pady=(4, 0))

        self.btn_copy_last = ttk.Button(
            copy_btn_frame,
            text="📋 Copy last reply",
            bootstyle="secondary-outline",
            command=self.on_copy_last_reply,
        )
        self.btn_copy_last.pack(side=tk.RIGHT)

        # ---- Input Area ----------------------------------------------------
        input_frame = ttk.Frame(self, padding=(0, 8, 0, 0))
        input_frame.pack(fill=X)

        self.txt_input = tk.Text(input_frame, height=3, wrap="word")
        self.txt_input.pack(fill=BOTH, expand=True, side=tk.LEFT)

        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        self.btn_send = ttk.Button(
            btn_frame,
            text="Send",
            bootstyle="success",
            command=self.on_send,
        )
        self.btn_send.pack(fill=X)

        self.btn_reset = ttk.Button(
            btn_frame,
            text="Reset",
            bootstyle="secondary",
            command=self.on_reset,
        )
        self.btn_reset.pack(fill=X, pady=(8, 0))

        # ---- Status Bar (簡易トースト用) -----------------------------------
        status_label = ttk.Label(
            self,
            textvariable=self._status_var,
            bootstyle="secondary",
            anchor="w",
            padding=(4, 2),
        )
        status_label.pack(fill=X, pady=(4, 0))

        # ショートカット: Ctrl+Enter で送信
        self.txt_input.bind("<Control-Return>", self._on_ctrl_enter)

        # 初期メッセージ
        self._append_system(self._system_message)

    # ---- Helpers -----------------------------------------------------------
    def _append_text(self, prefix: str, text: str):
        """ログにメッセージを追加。"""
        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, f"{prefix}: {text}\n\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")

    def _append_user(self, text: str):
        self._append_text("You", text)

    def _append_bot(self, text: str):
        self._append_text("Assistant", text)

    def _append_system(self, text: str):
        self._append_text("System", text)

    def _show_status(self, message: str, duration_ms: int = 1500):
        """下部にステータステキストを一時的に表示（簡易トースト）。"""
        self._status_var.set(message)
        # duration_ms 後にクリア
        self.after(duration_ms, lambda: self._status_var.set(""))

    def show_status(self, message: str, duration_ms: int = 1500):
        """外からも呼べるステータス表示のラッパー。"""
        self._show_status(message, duration_ms)

    # ---- Events ------------------------------------------------------------
    def _on_ctrl_enter(self, event):
        self.on_send()
        return "break"

    def on_send(self):
        msg = self.txt_input.get("1.0", tk.END).strip()
        if not msg:
            return

        self._append_user(msg)
        self.txt_input.delete("1.0", tk.END)

        self.btn_send.configure(state="disabled", text="Thinking...")

        # 別スレッドで LLM を叩く
        threading.Thread(
            target=self._run_llm_thread,
            args=(msg,),
            daemon=True,
        ).start()

    def _run_llm_thread(self, msg: str):
        try:
            reply = self._generate_func(msg)
        except Exception as e:
            reply = f"[Error while generating reply: {e}]"

        # UI 更新はメインスレッドで
        self.after(0, lambda: self._on_llm_done(reply))

    def _on_llm_done(self, reply: str):
        # 🔹最後の回答を保存
        self._last_reply = reply

        self._append_bot(reply)
        self.btn_send.configure(state="normal", text="Send")

    # ---- Copy last reply ---------------------------------------------------
    def on_copy_last_reply(self):
        """最後の Assistant 応答をクリップボードにコピーする。"""
        if not self._last_reply:
            self._show_status("No reply to copy yet.")
            return

        self.clipboard_clear()
        self.clipboard_append(self._last_reply)
        self._show_status("Copied last reply to clipboard.")

    # ---- Reset -------------------------------------------------------------
    def on_reset(self):
        """タブ内のチャット履歴と入力欄をリセットする。"""
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state="disabled")

        self.txt_input.delete("1.0", tk.END)
        self._last_reply = None

        # 初期メッセージを再表示
        self._append_system(self._system_message)
        self._show_status("Conversation reset.")


class LlmChatFrame(ttk.Frame):
    """llama.cpp (SmolLM2) を使った、Rewrite / Q&A タブ付きチャット画面。"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # ==== Model selection UI ============================================
        model_frame = ttk.LabelFrame(self, text="Model", padding=8)
        model_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(model_frame, text="Current model:").pack(side=tk.LEFT)

        self.model_path_var = tk.StringVar(value=get_current_model_path())
        self.lbl_model_path = ttk.Label(
            model_frame,
            textvariable=self.model_path_var,
            anchor="w",
            bootstyle="secondary",
        )
        self.lbl_model_path.pack(side=tk.LEFT, fill=X,
                                 expand=True, padx=(4, 8))

        self.btn_model_reset = ttk.Button(
            model_frame,
            text="Reset to default",
            bootstyle="secondary-outline",
            command=self.on_reset_model,
        )
        self.btn_model_reset.pack(side=tk.RIGHT)

        self.btn_model_browse = ttk.Button(
            model_frame,
            text="Change model…",
            bootstyle="info",
            command=self.on_change_model,
        )
        self.btn_model_browse.pack(side=tk.RIGHT, padx=(0, 4))

        # ==== Notebook (Rewrite / Q&A) ======================================
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True)

        # ---- Rewrite タブ --------------------------------------------------
        self.rewrite_tab = SingleLlmTab(
            notebook,
            title_label="Rewrite (English)",
            system_message=(
                "This tab rewrites English text in natural, professional and polite English.\n"
                "Paste your sentence and press Send."
            ),
            generate_func=generate_rewrite,
        )

        # ---- Q&A タブ ------------------------------------------------------
        self.qa_tab = SingleLlmTab(
            notebook,
            title_label="LLM Q&A",
            system_message=(
                "This tab uses the local LLM to answer your questions.\n"
                "Ask about tasks or study, then press Send."
            ),
            generate_func=generate_qa_answer,
        )

        notebook.add(self.rewrite_tab, text="Rewrite")
        notebook.add(self.qa_tab, text="Q&A")

    # ==== Model change handlers =============================================
    def _set_model_buttons_state(self, state: str):
        self.btn_model_browse.configure(state=state)
        self.btn_model_reset.configure(state=state)

    def on_change_model(self):
        """ユーザーに .gguf を選ばせてモデルを切り替える。"""
        path = filedialog.askopenfilename(
            title="Select GGUF model file",
            filetypes=[("GGUF model", "*.gguf"), ("All files", "*.*")],
        )
        if not path:
            return

        self.model_path_var.set(f"Loading model: {path}")
        self._set_model_buttons_state("disabled")

        threading.Thread(
            target=self._load_model_thread,
            args=(path,),
            daemon=True,
        ).start()

    def _load_model_thread(self, path: str):
        try:
            set_model_path(path)
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self._on_model_loaded(False, error_msg))
        else:
            self.after(0, lambda: self._on_model_loaded(True, ""))

    def on_reset_model(self):
        """デフォルトモデルに戻す。"""
        self.model_path_var.set("Resetting to default model...")
        self._set_model_buttons_state("disabled")

        threading.Thread(
            target=self._reset_model_thread,
            daemon=True,
        ).start()

    def _reset_model_thread(self):
        try:
            reset_to_default_model()
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self._on_model_loaded(False, error_msg))
        else:
            self.after(0, lambda: self._on_model_loaded(True, ""))

    def _on_model_loaded(self, success: bool, error_msg: str):
        self._set_model_buttons_state("normal")
        # 現在のモデルパスを反映（成功していない場合は古いまま）
        self.model_path_var.set(get_current_model_path())

        if success:
            # 各タブのステータスバーにも表示
            self.rewrite_tab.show_status("Model changed.")
            self.qa_tab.show_status("Model changed.")
            messagebox.showinfo("Model", "Model loaded successfully.")
        else:
            self.rewrite_tab.show_status("Failed to change model.")
            self.qa_tab.show_status("Failed to change model.")
            messagebox.showerror("Model load error",
                                 f"Failed to load model:\n{error_msg}")
