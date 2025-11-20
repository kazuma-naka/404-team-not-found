# ui/weekly_schedule.py
import logging
import tkinter as tk
from dataclasses import dataclass
from typing import List

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import textwrap

import ttkbootstrap as ttk
from ttkbootstrap.constants import X
from ttkbootstrap.dialogs import Messagebox

from PIL import Image, ImageTk
from tkinter import filedialog

log = logging.getLogger("TaskManager.WeeklySchedule")

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class EventBlock:
    day: int          # 0=Mon, 1=Tue, ... 6=Sun
    start: float      # start time in hours (e.g., 9.0, 13.5)
    end: float        # end time
    title: str
    location: str = ""
    color: str = "#4285F4"


def _format_hour_label(h: int) -> str:
    return f"{h:02d}:00"


def _render_weekly_schedule_google(
    events: List[EventBlock],
    filename: str,
    day_start: int = 0,
    day_end: int = 4,
    hour_start: int = 9,
    hour_end: int = 20,
) -> None:
    """Render Google Calendar–style weekly schedule to an image file."""
    visible_days = DAYS[day_start:day_end + 1]
    num_days = len(visible_days)

    fig, ax = plt.subplots(figsize=(7.5, 10))
    fig.patch.set_facecolor("#FFFFFF")

    ax.set_xlim(-1.0, num_days)
    ax.set_ylim(hour_end, hour_start)
    ax.axis("off")

    # Column background (alternating)
    for i in range(num_days):
        bg_color = "#FFFFFF" if i % 2 == 0 else "#FBFBFB"
        rect = patches.Rectangle(
            (i, hour_start),
            1,
            hour_end - hour_start,
            facecolor=bg_color,
            edgecolor="none",
            zorder=-10,
        )
        ax.add_patch(rect)

    # Vertical separators
    for i in range(num_days + 1):
        ax.axvline(i, color="#E0E0E0", linewidth=0.8, zorder=-5)

    # Horizontal grid + time labels
    for h in range(hour_start, hour_end + 1):
        ax.axhline(h, color="#E0E0E0", linewidth=0.6, zorder=-5)
        ax.text(
            -0.35,
            h,
            _format_hour_label(h),
            ha="right",
            va="center",
            fontsize=8,
            color="#5F6368",
        )

    # Day headers
    for i, day in enumerate(visible_days):
        ax.text(
            i + 0.5,
            hour_start - 0.5,
            day,
            ha="center",
            va="top",
            fontsize=11,
            fontweight="bold",
            color="#202124",
        )

    # Event cards
    slot_margin = 0.05  # vertical margin between stacked slots

    for ev in events:
        if not (day_start <= ev.day <= day_end):
            continue

        day_idx = ev.day - day_start
        x = day_idx + 0.08
        width = 0.84

        # small vertical margin so back-to-back slots do not visually merge
        raw_height = ev.end - ev.start
        y = ev.start + slot_margin
        height = max(raw_height - 2 * slot_margin, 0.25)

        # Shadow
        shadow = patches.FancyBboxPatch(
            (x + 0.02, y - 0.03),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            linewidth=0,
            facecolor="#000000",
            alpha=0.10,
            zorder=1,
        )
        ax.add_patch(shadow)

        # Card (white border makes stacking clearer)
        card = patches.FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.16",
            linewidth=1,
            edgecolor="white",
            facecolor=ev.color,
            alpha=0.95,
            zorder=2,
        )
        ax.add_patch(card)

        # Text
        lines = [ev.title]
        if ev.location:
            lines.append(ev.location)

        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, width=16))

        fontsize = 8 if height < 1.0 else 9

        ax.text(
            x + width / 2,
            y + height / 2,
            "\n".join(wrapped),
            ha="center",
            va="center",
            fontsize=fontsize,
            color="white",
            zorder=3,
        )

    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close(fig)


class WeeklyScheduleFrame(ttk.Frame):
    """
    Weekly schedule editor + preview.

    Left side  : form to edit course meta and time slot.
    Right side : slot list + preview image.
    """

    def __init__(self, parent, controller, user_id: int):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.current_user_id: int | None = user_id

        # track which schedule row is being edited (None = new)
        self._edit_schedule_id: int | None = None

        # mapping: tree item id -> row dict
        self._slot_index: dict[str, dict] = {}

        # Grid configuration: left (form) fixed, right (preview) expands
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_form_panel()
        self._build_preview_panel()

        # initial load
        self._refresh_slot_list()
        self._generate_and_show(save_path=None, silent_if_no_data=True)

    # ------------------------------------------------------------------
    def set_user(self, user_id: int) -> None:
        """Update current user id (called from MainAppFrame)."""
        self.current_user_id = user_id
        self._edit_schedule_id = None
        self._refresh_slot_list()
        self._generate_and_show(save_path=None, silent_if_no_data=True)

    # ------------------------------------------------------------------
    # Left: course / time form
    # ------------------------------------------------------------------
    def _build_form_panel(self) -> None:
        form = ttk.Frame(self, padding=12)
        form.grid(row=0, column=0, sticky="ns")

        ttk.Label(form, text="Course Name").pack(anchor="w")
        self.course_name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.course_name_var, width=28).pack(
            fill=X, pady=(0, 8)
        )

        ttk.Label(form, text="Course Detail").pack(anchor="w")
        self.course_detail = tk.Text(form, height=4, width=28)
        self.course_detail.pack(fill=X, pady=(0, 12))

        # Day selector
        ttk.Label(form, text="Day of Week").pack(anchor="w")
        self.day_var = tk.StringVar(value=DAYS[0])
        self.day_combo = ttk.Combobox(
            form,
            textvariable=self.day_var,
            values=DAYS,
            state="readonly",
            width=10,
        )
        self.day_combo.pack(fill=X, pady=(0, 8))

        # Time slots (08:00–21:00 in 30min steps)
        times = []
        for h in range(8, 22):
            for m in (0, 30):
                times.append(f"{h:02d}:{m:02d}")

        ttk.Label(form, text="Start Time").pack(anchor="w")
        self.start_var = tk.StringVar(value="09:00")
        ttk.Combobox(
            form,
            textvariable=self.start_var,
            values=times,
            width=10,
            state="readonly",
        ).pack(fill=X, pady=(0, 8))

        ttk.Label(form, text="End Time").pack(anchor="w")
        self.end_var = tk.StringVar(value="10:30")
        ttk.Combobox(
            form,
            textvariable=self.end_var,
            values=times,
            width=10,
            state="readonly",
        ).pack(fill=X, pady=(0, 12))

        # Buttons
        ttk.Button(
            form,
            text="Save Course & Slot",
            bootstyle="primary",
            command=self._on_save_course,
        ).pack(fill=X, pady=(0, 8))

        ttk.Button(
            form,
            text="Generate Weekly Image",
            bootstyle="secondary",
            command=self._on_generate_image,
        ).pack(fill=X)

    # ------------------------------------------------------------------
    # Right: slot list + preview area
    # ------------------------------------------------------------------
    def _build_preview_panel(self) -> None:
        right = ttk.Frame(self, padding=(0, 12, 12, 12))
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(
            right,
            text="Weekly Schedule",
            font=("TkDefaultFont", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        # --- slot list (Treeview) --------------------------------------
        slot_frame = ttk.Frame(right)
        slot_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        slot_frame.columnconfigure(0, weight=1)
        slot_frame.rowconfigure(0, weight=1)

        self.slot_tree = ttk.Treeview(
            slot_frame,
            columns=("day", "time", "course"),
            show="headings",
            height=5,
        )
        self.slot_tree.heading("day", text="Day")
        self.slot_tree.heading("time", text="Time")
        self.slot_tree.heading("course", text="Course")
        self.slot_tree.column("day", width=60, anchor="center")
        self.slot_tree.column("time", width=120, anchor="center")
        self.slot_tree.column("course", width=180, anchor="w")
        self.slot_tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll = ttk.Scrollbar(
            slot_frame, orient="vertical", command=self.slot_tree.yview
        )
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.slot_tree.configure(yscrollcommand=tree_scroll.set)

        btns = ttk.Frame(slot_frame)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Button(
            btns,
            text="Load Selected",
            command=self._on_load_selected,
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            btns,
            text="Delete Selected",
            bootstyle="danger",
            command=self._on_delete_selected,
        ).pack(side=tk.LEFT)

        # --- preview canvas (image) ------------------------------------
        self.canvas = tk.Canvas(right, highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            right, orient="vertical", command=self.canvas.yview
        )
        y_scroll.grid(row=2, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=y_scroll.set)

        self.image_container = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.image_container,
            anchor="nw",
        )

        self.image_container.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )

        self.preview_label = ttk.Label(self.image_container)
        self.preview_label.pack()

        # keep reference to PhotoImage to prevent garbage collection
        self._preview_image_ref = None

    # ------------------------------------------------------------------
    # Slot list helpers
    # ------------------------------------------------------------------
    def _fetch_slots(self) -> List[dict]:
        """Fetch all schedule slots for the current user."""
        if self.current_user_id is None:
            return []
        rows = self.db.fetchall(
            """
            SELECT
                cs.id AS schedule_id,
                cs.day,
                cs.start_time,
                cs.end_time,
                c.name,
                c.description
            FROM COURSE_SCHEDULE cs
            JOIN COURSE c ON cs.course_id = c.id
            WHERE cs.user_id = ?
            ORDER BY cs.day, cs.start_time
            """,
            (self.current_user_id,),
        )
        return [dict(r) for r in rows]

    def _refresh_slot_list(self) -> None:
        """Reload Treeview from DB."""
        for item in self.slot_tree.get_children():
            self.slot_tree.delete(item)
        self._slot_index.clear()

        rows = self._fetch_slots()
        for row in rows:
            day_str = DAYS[int(row["day"])]
            time_str = f'{row["start_time"]}–{row["end_time"]}'
            course_str = row["name"]

            iid = self.slot_tree.insert(
                "", "end",
                values=(day_str, time_str, course_str),
            )
            self._slot_index[iid] = row

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_save_course(self) -> None:
        """Save course meta and schedule slot into the database."""
        if self.current_user_id is None:
            Messagebox.show_error("Error", "No user is selected.")
            return

        name = self.course_name_var.get().strip()
        if not name:
            Messagebox.show_warning("Validation", "Course name is required.")
            return

        detail = self.course_detail.get("1.0", "end").strip()

        day_name = self.day_var.get()
        start_str = self.start_var.get()
        end_str = self.end_var.get()

        if start_str >= end_str:
            Messagebox.show_warning(
                "Validation", "End time must be later than start time."
            )
            return

        day_index = DAYS.index(day_name)

        #
        # Find or create COURSE by (user_id, name, description)
        # We DO NOT update existing descriptions.
        #
        rows = self.db.fetchall(
            """
            SELECT id
            FROM COURSE
            WHERE user_id = ? AND name = ? AND description = ?
            """,
            (self.current_user_id, name, detail),
        )
        if rows:
            course_id = rows[0]["id"]
        else:
            course_id = self.db.execute(
                """
                INSERT INTO COURSE (user_id, name, description)
                VALUES (?, ?, ?)
                """,
                (self.current_user_id, name, detail),
            )

        # Insert or update schedule row
        if self._edit_schedule_id is not None:
            self.db.execute(
                """
                UPDATE COURSE_SCHEDULE
                SET course_id=?, day=?, start_time=?, end_time=?
                WHERE id=?
                """,
                (
                    course_id,
                    day_index,
                    start_str,
                    end_str,
                    self._edit_schedule_id,
                ),
            )
            Messagebox.show_info(
                "Updated",
                "Course slot has been updated.",
            )
        else:
            self.db.execute(
                """
                INSERT INTO COURSE_SCHEDULE
                (user_id, course_id, day, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.current_user_id, course_id, day_index, start_str, end_str),
            )
            Messagebox.show_info(
                "Saved",
                "Course and time slot have been saved.",
            )

        # reset edit mode
        self._edit_schedule_id = None

        # refresh list and preview
        self._refresh_slot_list()
        self._generate_and_show(save_path=None, silent_if_no_data=True)

    def _on_generate_image(self) -> None:
        """Ask where to save PNG and generate weekly schedule image."""
        path = filedialog.asksaveasfilename(
            title="Save weekly schedule as PNG",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
            initialfile="weekly_schedule.png",
        )
        if not path:
            return

        self._generate_and_show(save_path=path, silent_if_no_data=False)

    def _on_load_selected(self) -> None:
        """Load selected slot into the left-hand form for editing."""
        selection = self.slot_tree.selection()
        if not selection:
            Messagebox.show_warning("Select", "Please select a slot.")
            return

        iid = selection[0]
        row = self._slot_index.get(iid)
        if not row:
            return

        self._edit_schedule_id = int(row["schedule_id"])

        # fill form fields
        self.course_name_var.set(row["name"])
        self.course_detail.delete("1.0", "end")
        self.course_detail.insert("1.0", row.get("description", ""))

        day_idx = int(row["day"])
        self.day_var.set(DAYS[day_idx])
        self.start_var.set(row["start_time"])
        self.end_var.set(row["end_time"])

    def _on_delete_selected(self) -> None:
        """Delete selected slot from DB and refresh."""
        selection = self.slot_tree.selection()
        if not selection:
            Messagebox.show_warning(
                "Select", "Please select a slot to delete.")
            return

        iid = selection[0]
        row = self._slot_index.get(iid)
        if not row:
            return

        schedule_id = int(row["schedule_id"])

        if not Messagebox.okcancel(
            "Delete",
            "Are you sure you want to delete this slot?",
        ):
            return

        self.db.execute(
            "DELETE FROM COURSE_SCHEDULE WHERE id=?",
            (schedule_id,),
        )
        self._edit_schedule_id = None

        self._refresh_slot_list()
        self._generate_and_show(save_path=None, silent_if_no_data=True)

    # ------------------------------------------------------------------
    # Core generator used by both save & auto-preview
    # ------------------------------------------------------------------
    def _generate_and_show(
        self,
        save_path: str | None,
        silent_if_no_data: bool,
    ) -> None:
        """Generate schedule image from DB, show preview, optionally save to path."""
        if self.current_user_id is None:
            if not silent_if_no_data:
                Messagebox.show_error("Error", "No user is selected.")
            return

        rows = self._fetch_slots()
        if not rows:
            if not silent_if_no_data:
                Messagebox.show_warning(
                    "No data",
                    "No course schedules found. Please add at least one slot.",
                )
            return

        events: List[EventBlock] = []
        # Google-like color palette, rotate per slot
        colors = ["#4285F4", "#FBBC04", "#34A853", "#EA4335", "#AB47BC"]

        for idx, row in enumerate(rows):
            day = int(row["day"])
            start_f = _time_to_float(row["start_time"])
            end_f = _time_to_float(row["end_time"])
            title = row["name"]
            desc = row.get("description", "")

            color = colors[idx % len(colors)]

            events.append(
                EventBlock(
                    day=day,
                    start=start_f,
                    end=end_f,
                    title=title,
                    location=desc,
                    color=color,
                )
            )

        img_path = save_path or "weekly_schedule_preview.png"
        _render_weekly_schedule_google(events, img_path)

        try:
            pil_img = Image.open(img_path)
        except Exception:
            log.exception("Failed to open generated image: %s", img_path)
            if not silent_if_no_data:
                Messagebox.show_error(
                    "Error", "Failed to open generated schedule image."
                )
            return

        self._preview_image_ref = ImageTk.PhotoImage(pil_img)
        self.preview_label.configure(image=self._preview_image_ref)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        if save_path:
            Messagebox.show_info(
                "Saved",
                f"Weekly schedule image saved to:\n{save_path}",
            )


# ----------------------------------------------------------------------
# Helper: "HH:MM" -> float hours
# ----------------------------------------------------------------------
def _time_to_float(t: str) -> float:
    h, m = t.split(":")
    return int(h) + int(m) / 60.0
