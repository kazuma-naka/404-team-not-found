# ui/llm_chat.py
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X

# 関数ごとではなくモジュール単位で import（循環参照回避）
from llm import smollm_client


class SingleLlmTab(ttk.Frame):
    """
    A single LLM tab that contains:
      - log area,
      - input area,
      - Send / Reset / Copy buttons,
      - status bar.

    The behavior is controlled by the provided generate_func.
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

        # Status bar text (used as a lightweight toast)
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

        # Copy-last-reply button below the log
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

        # ---- Status Bar (lightweight toast) --------------------------------
        status_label = ttk.Label(
            self,
            textvariable=self._status_var,
            bootstyle="secondary",
            anchor="w",
            padding=(4, 2),
        )
        status_label.pack(fill=X, pady=(4, 0))

        # Shortcut: Ctrl+Enter to send
        self.txt_input.bind("<Control-Return>", self._on_ctrl_enter)

        # Initial system message
        self._append_system(self._system_message)

    # ---- Helpers -----------------------------------------------------------
    def _append_text(self, prefix: str, text: str):
        """Append a message to the log."""
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
        """
        Show a short status message in the bottom bar (like a toast).
        Automatically clears after duration_ms milliseconds.
        """
        self._status_var.set(message)
        self.after(duration_ms, lambda: self._status_var.set(""))

    def show_status(self, message: str, duration_ms: int = 1500):
        """Public wrapper so the parent frame can show status messages."""
        self._show_status(message, duration_ms)

    # ---- Events ------------------------------------------------------------
    def _on_ctrl_enter(self, event):
        self.on_send()
        return "break"

    def on_send(self):
        """Called when the Send button (or Ctrl+Enter) is pressed."""
        msg = self.txt_input.get("1.0", tk.END).strip()
        if not msg:
            return

        self._append_user(msg)
        self.txt_input.delete("1.0", tk.END)

        self.btn_send.configure(state="disabled", text="Thinking...")

        # Run LLM in a background thread
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

        # UI updates must be done on the main thread
        self.after(0, lambda: self._on_llm_done(reply))

    def _on_llm_done(self, reply: str):
        """Called when LLM generation finishes."""
        self._last_reply = reply
        self._append_bot(reply)
        self.btn_send.configure(state="normal", text="Send")

    # ---- Copy last reply ---------------------------------------------------
    def on_copy_last_reply(self):
        """Copy the last Assistant reply to the clipboard."""
        if not self._last_reply:
            self._show_status("No reply to copy yet.")
            return

        self.clipboard_clear()
        self.clipboard_append(self._last_reply)
        self._show_status("Copied last reply to clipboard.")

    # ---- Reset -------------------------------------------------------------
    def on_reset(self):
        """
        Reset the conversation in this tab:
          - clear log,
          - clear input box,
          - forget last reply,
          - re-show the system message.
        """
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state="disabled")

        self.txt_input.delete("1.0", tk.END)
        self._last_reply = None

        self._append_system(self._system_message)
        self._show_status("Conversation reset.")


class LlmChatFrame(ttk.Frame):
    """
    Main frame that provides:

      - Model selection (current model, change, reset)
      - Llama library selection (DLL / .so)
      - Notebook with three tabs:
         * Rewrite: rewrite English text politely
         * Typos: fix English typos with minimal changes
         * Q&A: general question & answer
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # ==== Model selection UI ============================================
        model_frame = ttk.LabelFrame(self, text="Model", padding=8)
        model_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(model_frame, text="Current model:").pack(side=tk.LEFT)

        try:
            current_model_path = smollm_client.get_current_model_path()
        except Exception:
            current_model_path = "<no model configured>"

        self.model_path_var = tk.StringVar(value=current_model_path)
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

        # ==== Llama library (DLL / .so) selection UI ========================
        lib_frame = ttk.LabelFrame(
            self, text="Llama library (DLL / .so)", padding=8)
        lib_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(lib_frame, text="Current LIBLLAMA:").pack(side=tk.LEFT)

        try:
            current_lib_path = smollm_client.get_current_libllama_path()
        except Exception:
            current_lib_path = "<not set>"

        self.lib_path_var = tk.StringVar(value=current_lib_path)
        self.lbl_lib_path = ttk.Label(
            lib_frame,
            textvariable=self.lib_path_var,
            anchor="w",
            bootstyle="secondary",
        )
        self.lbl_lib_path.pack(side=tk.LEFT, fill=X, expand=True, padx=(4, 8))

        self.btn_lib_browse = ttk.Button(
            lib_frame,
            text="Change library…",
            bootstyle="info",
            command=self.on_change_lib,
        )
        self.btn_lib_browse.pack(side=tk.RIGHT, padx=(0, 4))

        # ==== Notebook (Rewrite / Typos / Q&A) ==============================
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True)

        # ---- Rewrite tab ---------------------------------------------------
        self.rewrite_tab = SingleLlmTab(
            notebook,
            title_label="Rewrite (English)",
            system_message=(
                "This tab rewrites English text in natural, professional and polite English.\n"
                "Paste your sentence and press Send."
            ),
            generate_func=smollm_client.generate_rewrite,
        )

        # ---- Typos tab -----------------------------------------------------
        self.typo_tab = SingleLlmTab(
            notebook,
            title_label="Fix Typos (English)",
            system_message=(
                "This tab fixes English typos and spelling mistakes.\n"
                "It keeps your wording and style, and only corrects errors."
            ),
            generate_func=smollm_client.generate_spellcheck,
        )

        # ---- Q&A tab -------------------------------------------------------
        self.qa_tab = SingleLlmTab(
            notebook,
            title_label="LLM Q&A",
            system_message=(
                "This tab uses the local LLM to answer your questions.\n"
                "Ask about tasks or study, then press Send."
            ),
            generate_func=smollm_client.generate_qa_answer,
        )

        notebook.add(self.rewrite_tab, text="Rewrite")
        notebook.add(self.typo_tab, text="Typos")
        notebook.add(self.qa_tab, text="Q&A")

    # ==== Helper for model buttons =========================================
    def _set_model_buttons_state(self, state: str):
        self.btn_model_browse.configure(state=state)
        self.btn_model_reset.configure(state=state)

    # ==== Model change handlers ============================================
    def on_change_model(self):
        """Let the user choose a GGUF file and switch the model."""
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
            smollm_client.set_model_path(path)
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self._on_model_loaded(False, error_msg))
        else:
            self.after(0, lambda: self._on_model_loaded(True, ""))

    def on_reset_model(self):
        """Reset the model to the default one."""
        self.model_path_var.set("Resetting to default model...")
        self._set_model_buttons_state("disabled")

        threading.Thread(
            target=self._reset_model_thread,
            daemon=True,
        ).start()

    def _reset_model_thread(self):
        try:
            smollm_client.reset_to_default_model()
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self._on_model_loaded(False, error_msg))
        else:
            self.after(0, lambda: self._on_model_loaded(True, ""))

    def _on_model_loaded(self, success: bool, error_msg: str):
        """Update UI after model load/reset finishes."""
        self._set_model_buttons_state("normal")

        try:
            self.model_path_var.set(smollm_client.get_current_model_path())
        except Exception:
            self.model_path_var.set("<no model configured>")

        if success:
            # Show a short message on each tab
            self.rewrite_tab.show_status("Model changed.")
            self.typo_tab.show_status("Model changed.")
            self.qa_tab.show_status("Model changed.")
            messagebox.showinfo("Model", "Model loaded successfully.")
        else:
            self.rewrite_tab.show_status("Failed to change model.")
            self.typo_tab.show_status("Failed to change model.")
            self.qa_tab.show_status("Failed to change model.")
            messagebox.showerror(
                "Model load error",
                f"Failed to load model:\n{error_msg}",
            )

    # ==== Llama library change handler =====================================
    def on_change_lib(self):
        """
        Let the user choose llama.dll / libllama.so and set LIBLLAMA.

        NOTE:
          - This should be called BEFORE the first LLM call for it to affect
            which shared library is loaded.
        """
        # 簡易的なフィルタだけ（OS 毎に完璧ではないが十分）
        if self.controller.tk.call("tk", "windowingsystem") == "win32":
            filetypes = [("llama.dll", "llama.dll"), ("All files", "*.*")]
        else:
            filetypes = [
                ("Llama library", "libllama*.so"),
                ("All files", "*.*"),
            ]

        path = filedialog.askopenfilename(
            title="Select llama library (DLL / .so)",
            filetypes=filetypes,
        )
        if not path:
            return

        try:
            smollm_client.set_libllama_path(path)
        except Exception as e:
            messagebox.showerror(
                "LIBLLAMA error",
                f"Failed to set LIBLLAMA:\n{e}",
            )
            return

        # 更新後の値を表示
        try:
            self.lib_path_var.set(smollm_client.get_current_libllama_path())
        except Exception:
            self.lib_path_var.set(path)

        # 各タブにトースト表示
        self.rewrite_tab.show_status("LIBLLAMA updated.")
        self.typo_tab.show_status("LIBLLAMA updated.")
        self.qa_tab.show_status("LIBLLAMA updated.")
