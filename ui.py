"""
CustomTkinter UI: main window (user list) + Add/Edit dialog.

Threading model
  Tkinter is NOT thread-safe: only the main thread may touch widgets.
  Each Login runs portal.login_user() in a worker thread (it blocks until
  Chrome is closed). The worker never touches widgets; it puts
  (user_id, text, finished) messages on a queue.Queue, and the main thread
  drains that queue every 100 ms with .after().
"""
from __future__ import annotations

import logging
import queue
import threading
from datetime import date
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

import config as C
import portal
import storage

log = logging.getLogger(__name__)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = [f"{d:02d}" for d in range(1, 32)]
YEARS = [str(y) for y in range(C.DOB_YEAR_MAX, C.DOB_YEAR_MIN - 1, -1)]  # newest first
VTYPE_LABELS = list(C.VERIFICATION_TYPES.values())
VTYPE_BY_LABEL = {v: k for k, v in C.VERIFICATION_TYPES.items()}

STATUS_COLORS = {
    portal.Outcome.LOGGED_IN: "#2e9e4f",
    portal.Outcome.ALREADY_LOGGED_IN: "#2e9e4f",
    portal.Outcome.MANUAL_NEEDED: "#d08a00",
    portal.Outcome.FAILED: "#d03a3a",
    portal.Outcome.CANCELLED: "gray60",
}


# ── Add / Edit dialog ─────────────────────────────────────────────────────
class UserDialog(ctk.CTkToplevel):
    """Modal form. user=None -> Add, otherwise Edit (prefilled)."""

    def __init__(self, master, on_saved: Callable[[], None], user: Optional[storage.User] = None):
        super().__init__(master)
        self.user = user
        self.on_saved = on_saved
        self.title("Edit user" if user else "Add user")
        self.resizable(False, False)
        self.transient(master)          # stay on top of the main window

        pad = {"padx": 16, "pady": (8, 0), "sticky": "w"}
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Display name").grid(row=0, column=0, **pad)
        self.name = ctk.CTkEntry(self, width=320, placeholder_text="e.g. Bharath")
        self.name.grid(row=1, column=0, padx=16, sticky="ew")

        ctk.CTkLabel(self, text="USN").grid(row=2, column=0, **pad)
        self.usn = ctk.CTkEntry(self, width=320, placeholder_text="1BG22CS001")
        self.usn.grid(row=3, column=0, padx=16, sticky="ew")
        self.usn.bind("<KeyRelease>", self._uppercase_usn)

        # DOB as three dropdowns, mirroring the portal: no date typing errors.
        ctk.CTkLabel(self, text="Date of birth").grid(row=4, column=0, **pad)
        dob_row = ctk.CTkFrame(self, fg_color="transparent")
        dob_row.grid(row=5, column=0, padx=16, sticky="w")
        self.day = ctk.CTkOptionMenu(dob_row, values=DAYS, width=80)
        self.month = ctk.CTkOptionMenu(dob_row, values=MONTHS, width=90)
        self.year = ctk.CTkOptionMenu(dob_row, values=YEARS, width=100)
        for w in (self.day, self.month, self.year):
            w.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self, text="Verification type").grid(row=6, column=0, **pad)
        self.vtype = ctk.CTkOptionMenu(self, values=VTYPE_LABELS, width=320)
        self.vtype.grid(row=7, column=0, padx=16, sticky="ew")

        ctk.CTkLabel(self, text="Last 4 digits").grid(row=8, column=0, **pad)
        # validatecommand runs on every keystroke with the would-be new text
        # (%P); returning False rejects the keystroke. So only 0-4 digits fit.
        only_4_digits = (self.register(lambda new: new == "" or (new.isdigit() and len(new) <= 4)), "%P")
        self.last4 = ctk.CTkEntry(self, width=120, show="•",
                                  validate="key", validatecommand=only_4_digits)
        self.last4.grid(row=9, column=0, padx=16, sticky="w")

        self.error = ctk.CTkLabel(self, text="", text_color="#d03a3a", wraplength=320, justify="left")
        self.error.grid(row=10, column=0, padx=16, pady=(8, 0), sticky="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=11, column=0, padx=16, pady=16, sticky="e")
        ctk.CTkButton(btns, text="Cancel", width=90, fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Save", width=90, command=self._save).pack(side="left")

        self._prefill()
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())

        # Make it modal. On Windows a CTkToplevel can open behind its parent,
        # so wait until it is visible, then grab input and focus it.
        self.after(50, self._make_modal)

    def _make_modal(self) -> None:
        self.lift()
        self.grab_set()
        self.name.focus_set()

    def _uppercase_usn(self, _event=None) -> None:
        text = self.usn.get()
        if text != text.upper():
            pos = self.usn.index("insert")
            self.usn.delete(0, "end")
            self.usn.insert(0, text.upper())
            self.usn.icursor(pos)

    def _prefill(self) -> None:
        self.day.set("Day")
        self.month.set("Month")
        self.year.set("Year")
        self.vtype.set(VTYPE_LABELS[0])
        if not self.user:
            return
        self.name.insert(0, self.user.display_name)
        self.usn.insert(0, self.user.usn)
        self.vtype.set(C.VERIFICATION_TYPES.get(self.user.verification_type, VTYPE_LABELS[0]))
        secrets = storage.get_secrets(self.user.id)
        if secrets:
            self.day.set(f"{secrets.dob.day:02d}")
            self.month.set(MONTHS[secrets.dob.month - 1])
            self.year.set(str(secrets.dob.year))
            self.last4.insert(0, secrets.last4)

    def _read_dob(self) -> date:
        d, m, y = self.day.get(), self.month.get(), self.year.get()
        if d == "Day" or m == "Month" or y == "Year":
            raise ValueError("Pick day, month and year of birth.")
        try:
            return date(int(y), MONTHS.index(m) + 1, int(d))
        except ValueError:
            raise ValueError(f"{d} {m} {y} is not a real date.") from None

    def _save(self) -> None:
        try:
            args = (
                self.name.get(),
                self.usn.get(),
                self._read_dob(),
                VTYPE_BY_LABEL[self.vtype.get()],
                self.last4.get(),
            )
            if self.user:
                storage.update_user(self.user.id, *args)
                log.info("updated user %s", self.user.id)
            else:
                u = storage.add_user(*args)
                log.info("added user %s", u.id)
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.on_saved()
        self.destroy()


# ── Main window ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Contineo Auto-Login")
        self.geometry("720x460")
        self.minsize(560, 320)

        self.messages: queue.Queue[tuple[str, str, Optional[portal.Outcome]]] = queue.Queue()
        self.running: set[str] = set()                          # user ids with an open browser
        self.status: dict[str, tuple[str, Optional[str]]] = {}  # user id -> (text, color)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text="Users", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="+ Add User", width=110, command=self.open_add).pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()
        self.after(100, self._drain_messages)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self) -> None:
        """Browsers are owned by this process: quitting the app closes them."""
        if self.running:
            n = len(self.running)
            if not messagebox.askyesno(
                "Quit",
                f"{n} browser window{'s are' if n > 1 else ' is'} still open from this app "
                "and will be closed too.\n\nQuit anyway?",
                parent=self,
            ):
                return
        log.info("app closed (%d browser(s) open)", len(self.running))
        self.destroy()

    def report_callback_exception(self, exc, val, tb) -> None:
        """Tk calls this when a button handler raises. Log it instead of
        silently printing to a console the .exe won't have."""
        log.error("UI error", exc_info=(exc, val, tb))
        messagebox.showerror("Error", f"Something went wrong:\n{val}\n\nDetails are in app.log.", parent=self)

    # ── list rendering ──
    def refresh(self) -> None:
        """Rebuild all rows from storage. Simple and fast enough for a few users."""
        for child in self.list_frame.winfo_children():
            child.destroy()

        users = storage.list_users()
        if not users:
            ctk.CTkLabel(self.list_frame, text="No users yet. Click “+ Add User” to start.",
                         text_color="gray60").grid(row=0, column=0, pady=40)
            return

        for i, u in enumerate(users):
            self._build_row(i, u)

    def _build_row(self, i: int, u: storage.User) -> None:
        row = ctk.CTkFrame(self.list_frame)
        row.grid(row=i, column=0, sticky="ew", pady=4)
        row.grid_columnconfigure(0, weight=1)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkLabel(info, text=u.display_name,
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
        vlabel = C.VERIFICATION_TYPES.get(u.verification_type, "?").replace(" Last 4 Digits", "")
        ctk.CTkLabel(info, text=f"{u.usn}  ·  {vlabel}", text_color="gray60").pack(anchor="w")
        text, color = self.status.get(u.id, ("", None))
        ctk.CTkLabel(info, text=text, text_color=color or "gray70").pack(anchor="w")

        busy = u.id in self.running
        state = "disabled" if busy else "normal"
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.grid(row=0, column=1, padx=12)
        ctk.CTkButton(btns, text="Login", width=80, state=state,
                      command=lambda uid=u.id: self.start_login(uid)).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="Edit", width=70, fg_color="gray40", state=state,
                      command=lambda user=u: self.open_edit(user)).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="Delete", width=70, fg_color="#8a2b2b", hover_color="#a33",
                      state=state, command=lambda user=u: self.confirm_delete(user)).pack(side="left", padx=3)

    # ── actions ──
    def open_add(self) -> None:
        UserDialog(self, on_saved=self.refresh)

    def open_edit(self, user: storage.User) -> None:
        UserDialog(self, on_saved=self.refresh, user=user)

    def confirm_delete(self, user: storage.User) -> None:
        ok = messagebox.askyesno(
            "Delete user",
            f"Delete {user.display_name} ({user.usn})?\n\n"
            "This removes their saved details and their browser session.",
            parent=self,
        )
        if ok:
            storage.delete_user(user.id)
            self.status.pop(user.id, None)
            log.info("deleted user %s", user.id)
            self.refresh()

    def start_login(self, user_id: str) -> None:
        if user_id in self.running:
            return  # Chrome can't open the same profile twice
        log.info("login started for %s", user_id)
        self.running.add(user_id)
        self.status[user_id] = ("Logging in…", None)
        self.refresh()
        threading.Thread(target=self._login_worker, args=(user_id,), daemon=True).start()

    # ── worker thread (no widget access here!) ──
    def _login_worker(self, user_id: str) -> None:
        def status(text: str) -> None:
            self.messages.put((user_id, text, None))

        try:
            result = portal.login_user(user_id, status=status)
            # Browser has been closed by now; leave the final result visible.
            outcome, text = result.outcome, result.message
        except Exception:
            log.exception("login crashed for %s", user_id)
            outcome, text = portal.Outcome.FAILED, "Login failed – unexpected error (see app.log)"
        self.messages.put((user_id, text, outcome))
        self.messages.put((user_id, "", "DONE"))  # sentinel: browser closed

    # ── main thread: apply worker messages ──
    def _drain_messages(self) -> None:
        changed = False
        try:
            while True:
                user_id, text, outcome = self.messages.get_nowait()
                if outcome == "DONE":
                    self.running.discard(user_id)
                else:
                    color = STATUS_COLORS.get(outcome) if outcome else None
                    # Results from login() arrive via status() first, uncolored;
                    # color them by matching the outcome text.
                    if color is None:
                        for oc, col in STATUS_COLORS.items():
                            if text.startswith(oc.value):
                                color = col
                    self.status[user_id] = (text, color)
                changed = True
        except queue.Empty:
            pass
        if changed:
            self.refresh()
        self.after(100, self._drain_messages)
