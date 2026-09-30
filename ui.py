"""Tk widgets, bounded table rendering, and explicit export dialogs."""

from collections import deque
from datetime import datetime
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from exporter import export_events, export_totals
from models import EventHistory, HISTORY_LIMIT, KeyEventRecord, readable_key
from monitor import KeyboardMonitor


class KeyboardMonitorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.history = EventHistory()
        self._closed = False
        self._refresh_job = None
        self._render_job = None
        self._pending: deque[KeyEventRecord] = deque(maxlen=HISTORY_LIMIT)
        self._displayed: deque[int] = deque()
        root.title("Keyboard Monitor Lab")
        root.geometry("1080x800")
        root.minsize(780, 650)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._build_widgets()
        self.monitor = KeyboardMonitor(root, self.history, self._queue_record)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._refresh()

    def _build_widgets(self) -> None:
        frame = ttk.Frame(self.root, padding=20)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        frame.rowconfigure(6, weight=3)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Keyboard Monitor Lab", font=("Segoe UI", 22, "bold")).grid(sticky="w")
        self.status = tk.StringVar(value="Stopped")
        self.status_label = ttk.Label(header, textvariable=self.status, font=("Segoe UI", 11, "bold"))
        self.status_label.grid(row=0, column=1, padx=(12, 0))
        notice_frame = ttk.Frame(frame)
        notice_frame.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.notice = tk.StringVar(value="Monitoring works only while this application is focused.")
        ttk.Label(notice_frame, textvariable=self.notice, wraplength=710).pack(anchor="w")

        latest = ttk.LabelFrame(frame, text="Latest key event", padding=(14, 8))
        self.latest_frame = latest
        latest.grid(row=2, column=0, sticky="ew")
        latest.columnconfigure(0, weight=1)
        self.latest = tk.StringVar(value="Press Start Monitoring to begin")
        self.latest_detail = tk.StringVar(value="No events captured")
        self.held = tk.StringVar(value="Held keys: none")
        ttk.Label(latest, textvariable=self.latest, font=("Segoe UI", 23, "bold"), wraplength=700).grid(sticky="w")
        ttk.Label(latest, textvariable=self.latest_detail).grid(sticky="w", pady=(3, 3))
        held_label = ttk.Label(latest, textvariable=self.held, wraplength=700)
        held_label.grid(sticky="w")
        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, sticky="ew", pady=12)
        self.start_button = ttk.Button(controls, text="Start Monitoring", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop Monitoring", command=self.stop)
        self.stop_button.pack(side="left", padx=(8, 8))
        self.clear_button = ttk.Button(controls, text="Clear", command=self.clear)
        self.clear_button.pack(side="left")
        self.export_button = ttk.Button(controls, text="Export CSV…", command=self.export)
        self.export_button.pack(side="left", padx=8)
        self.totals_button = ttk.Button(controls, text="Export totals…", command=self.export_activity)
        self.totals_button.pack(side="left")

        stats = ttk.Frame(frame)
        stats.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self.total = tk.StringVar(value="0")
        self.presses = tk.StringVar(value="0")
        self.releases = tk.StringVar(value="0")
        self.elapsed = tk.StringVar(value="00:00")
        self.rate = tk.StringVar(value="0.0")
        for column, (label, variable) in enumerate(zip(
            ("Total events", "Key presses", "Key releases", "Active time", "Press events / min"),
            (self.total, self.presses, self.releases, self.elapsed, self.rate),
        )):
            stats.columnconfigure(column, weight=1)
            card = ttk.LabelFrame(stats, text=label, padding=8)
            card.grid(row=0, column=column, sticky="ew", padx=(0, 6))
            ttk.Label(card, textvariable=variable, font=("Segoe UI", 18, "bold")).pack()

        typing = ttk.LabelFrame(frame, text="Type here to test keyboard events.", padding=8)
        typing.grid(row=5, column=0, sticky="nsew", pady=(0, 12))
        typing.rowconfigure(0, weight=1)
        typing.columnconfigure(0, weight=1)
        # Standard Text behavior (including literal Tab insertion) is preserved.
        self.typing_area = tk.Text(typing, height=4, wrap="word", undo=False,
                                   font=("Consolas", 12), padx=8, pady=8)
        self.typing_area.grid(row=0, column=0, sticky="nsew")
        text_scroll = ttk.Scrollbar(typing, orient="vertical", command=self.typing_area.yview)
        text_scroll.grid(row=0, column=1, sticky="ns")
        self.typing_area.configure(yscrollcommand=text_scroll.set)

        events = ttk.LabelFrame(frame, text="Event history · latest 5,000 events", padding=8)
        self.events_frame = events
        events.grid(row=6, column=0, sticky="nsew")
        events.rowconfigure(0, weight=1)
        events.columnconfigure(0, weight=1)
        columns = ("number", "timestamp", "type", "key", "code", "modifiers", "combination")
        self.table = ttk.Treeview(events, columns=columns, show="headings", height=8)
        for column, title, width in zip(columns,
                ("#", "Local timestamp", "Event type", "Key", "Code", "Modifiers", "Combination"),
                (60, 250, 95, 110, 65, 115, 165)):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=50, stretch=column in ("key", "combination"))
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(events, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(events, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        footer = ttk.Label(frame, text="Held keys may repeat; counts are delivered events, not physical presses. "
                           "Ctrl+Tab leaves the typing area.", wraplength=980)
        footer.grid(row=7, column=0, sticky="w", pady=(10, 0))
        def resize_labels(event):
            footer.configure(wraplength=max(200, event.width - 40))
            held_label.configure(wraplength=max(200, event.width - 70))
        self._layout_frame = frame
        self._layout_binding = frame.bind("<Configure>", resize_labels, add="+")

    def start(self) -> None:
        self.monitor.start()
        self._update_labels()

    def stop(self) -> None:
        self.monitor.stop()
        self._update_labels()

    def clear(self) -> None:
        self.monitor.clear()
        if self._render_job is not None:
            self.root.after_cancel(self._render_job)
            self._render_job = None
        self._pending.clear()
        if self._displayed:
            self.table.delete(*(str(number) for number in self._displayed))
        self._displayed.clear()
        self.typing_area.configure(state="normal")
        self.typing_area.delete("1.0", "end")
        self._update_labels()


    def _queue_record(self, row: KeyEventRecord) -> None:
        self._pending.append(row)
        if self._render_job is None:
            self._render_job = self.root.after(16, self._render_pending)

    def _render_pending(self) -> None:
        self._render_job = None
        oldest = self.history.rows[0].number if self.history.rows else self.history.total + 1
        expired = []
        while self._displayed and self._displayed[0] < oldest:
            expired.append(str(self._displayed.popleft()))
        if expired:
            self.table.delete(*expired)
        # Small batches leave room for input and focus events between updates.
        for _ in range(min(250, len(self._pending))):
            row = self._pending.popleft()
            if row.number >= oldest:
                self.table.insert("", "end", iid=str(row.number), values=row.table_row())
                self._displayed.append(row.number)
        if self._displayed:
            self.table.see(str(self._displayed[-1]))
        if self._pending:
            self._render_job = self.root.after(16, self._render_pending)
        self._update_labels()

    def _update_labels(self) -> None:
        self.status.set(self.monitor.status)
        self.status_label.configure(foreground="#167044" if self.monitor.active else "#765019")
        self.start_button.state(["disabled"] if self.monitor.enabled else ["!disabled"])
        self.stop_button.state(["!disabled"] if self.monitor.enabled else ["disabled"])
        self.total.set(f"{self.history.total:,}")
        self.presses.set(f"{self.history.presses:,}")
        self.releases.set(f"{self.history.releases:,}")
        snapshot = self.monitor.activity.snapshot(time.monotonic())
        seconds = int(snapshot["elapsed_seconds"])
        self.elapsed.set(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self.rate.set(str(snapshot["keypresses_per_minute"]))
        if self.history.rows:
            row = self.history.rows[-1]
            self.latest.set(row.display)
            self.latest_detail.set(f"{row.event_type} · {row.timestamp} · keycode {row.keycode}")
        else:
            self.latest.set("Waiting for a key" if self.monitor.enabled else "Press Start Monitoring to begin")
            self.latest_detail.set("No events captured")
        held = ", ".join(readable_key(key) for key in self.monitor.held.values())
        if len(held) > 150:
            held = held[:147] + "…"
        self.held.set("Held keys: " + (held or "none"))

    def _refresh(self) -> None:
        self._refresh_job = None
        if not self._closed:
            self._update_labels()
            self._refresh_job = self.root.after(50, self._refresh)

    def export(self) -> None:
        with self.monitor.suspend_for_dialog():
            self._update_labels()
            if not self.history.rows:
                messagebox.showinfo("Nothing to export", "Capture some keyboard events before exporting.", parent=self.root)
                return
            rows = tuple(self.history.rows)
            destination = filedialog.asksaveasfilename(parent=self.root, title="Export keyboard events",
                defaultextension=".csv", initialfile="keyboard_events.csv", filetypes=[("CSV files", "*.csv")])
            if not destination:
                return
            try:
                export_events(destination, rows)
            except (OSError, UnicodeError) as error:
                messagebox.showerror("Export failed", f"Could not write the CSV file.\n\n{error}", parent=self.root)
            else:
                messagebox.showinfo("Export complete", f"Exported {len(rows):,} retained events.", parent=self.root)
        self._update_labels()

    def export_activity(self) -> None:
        # Preserve the old app's aggregate-only export and pause-after-export.
        self.stop()
        with self.monitor.suspend_for_dialog():
            snapshot = {"exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        **self.monitor.activity.snapshot(time.monotonic())}
            destination = filedialog.asksaveasfilename(parent=self.root, title="Export activity totals",
                defaultextension=".csv", initialfile="keyboard_activity_totals.csv",
                filetypes=[("CSV files", "*.csv")])
            if not destination:
                return
            try:
                export_totals(destination, snapshot)
            except (OSError, UnicodeError) as error:
                messagebox.showerror("Export failed", f"Could not write the totals file.\n\n{error}", parent=self.root)
            else:
                messagebox.showinfo("Totals exported", "Activity totals saved. Monitoring is stopped.", parent=self.root)

    def close(self) -> None:
        if self._closed:
            return
        self.stop()
        self._closed = True
        self.monitor.close()
        self._layout_frame.unbind("<Configure>", self._layout_binding)
        for job in (self._refresh_job, self._render_job):
            if job is not None:
                self.root.after_cancel(job)
        self._refresh_job = self._render_job = None
        self._pending.clear()
        self.root.destroy()
