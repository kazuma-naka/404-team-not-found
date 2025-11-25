from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import EW, NSEW, SUCCESS, W

from db.manager import DatabaseManager
from service.auth import authenticate


class WelcomeScreen(ttk.Frame):
    """
    Centered 'Welcome' card with name/email inputs and a Login/Register button.

    Args:
        master: parent window
        db_path (str): sqlite file path
        schema_path (str): path to schema.sql
        on_login (callable|None): callback receiving the logged-in sqlite3.Row
    """

    def __init__(self, master, db_path: str, schema_path: str, on_login=None):
        super().__init__(master)
        self.on_login = on_login

        # ---- DB init --------------------------------------------------------
        self.db = DatabaseManager(db_path)
        self.db.run_schema_file(schema_path)

        # ---- Centered card --------------------------------------------------
        wrapper = ttk.Frame(self)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        card = ttk.Frame(wrapper, padding=30, bootstyle="secondary")
        card.grid(row=0, column=0, sticky=NSEW)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Welcome!", font=("-size", 14, "-weight", "bold"), bootstyle="inverse-secondary").grid(
            row=0, column=0, pady=(0, 16)
        )

        # Name
        self.name_var = ttk.StringVar()
        ttk.Label(card, text="Name:", bootstyle="inverse-secondary").grid(row=1, column=0, sticky=W)
        self.name_entry = ttk.Entry(card, textvariable=self.name_var, width=44)
        self.name_entry.grid(row=2, column=0, sticky=EW, pady=(4, 12))

        # Email
        self.email_var = ttk.StringVar()
        ttk.Label(card, text="Email:", bootstyle="inverse-secondary").grid(row=3, column=0, sticky=W)
        self.email_entry = ttk.Entry(
            card, textvariable=self.email_var, width=44)
        self.email_entry.grid(row=4, column=0, sticky=EW, pady=(4, 16))

        # Action
        self.submit_btn = ttk.Button(
            card, text="Login / Register", bootstyle=SUCCESS, command=self.on_submit
        )
        self.submit_btn.grid(row=5, column=0, sticky=EW)

        self.name_entry.focus_set()

    # ---- DB helpers ---------------------------------------------------------
    def _get_user_by_email(self, email: str):
        rows = self.db.fetchall(
            "SELECT id, name, email FROM USER WHERE email=? LIMIT 1", (email,)
        )
        return rows[0] if rows else None

    def _create_user(self, name: str, email: str):
        return self.db.execute(
            "INSERT INTO USER (name, email) VALUES (?, ?)", (name, email)
        )

    # ---- UI events ----------------------------------------------------------
    def on_submit(self):
        name = (self.name_var.get() or "").strip()
        email = (self.email_var.get() or "").strip()

        def ask_confirm(entered: str, saved: str) -> bool:
            return messagebox.askyesno(
                "Name doesn't match",
                f"This email is registered as '{saved}'.\n"
                f"You entered '{entered}'.\n\n"
                "Log in as the saved user?",
            )

        status, user = authenticate(
            self.db, name, email, confirm_on_mismatch=ask_confirm)

        if status == "invalid_input":
            messagebox.showerror(
                "Input Error", "Name and Email are required, and email must contain '@'.")
            return
        if status == "db_error":
            messagebox.showerror(
                "Database Error", "Something went wrong. Please try again.")
            return
        if status == "mismatch_declined":
            messagebox.showinfo(
                "Cancelled", "Login was cancelled. Please correct your name or use another email.")
            return
        if status == "created":
            messagebox.showinfo(
                "Welcome!", f"Account created. You're now logged in as {user['name']} ({user['email']}).")
        if status == "logged_in":
            title = "Welcome back"
            messagebox.showinfo(
                title, f"Logged in as {user['name']} ({user['email']}).")

        if user and self.on_login:
            self.on_login(user)
