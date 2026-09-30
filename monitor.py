"""Main-thread, main-window-only Tk event monitoring. No global hooks."""

from contextlib import contextmanager
import time
import tkinter as tk
from typing import Callable

from models import Activity, EventHistory, KeyEventRecord, MODIFIER_KEYS


class KeyboardMonitor:
    def __init__(self, root: tk.Tk, history: EventHistory,
                 on_record: Callable[[KeyEventRecord], None]) -> None:
        self.root = root
        self.history = history
        self.on_record = on_record
        self.activity = Activity()
        self.enabled = False
        self.focused = False
        self.held: dict[int, str] = {}
        self._closed = False
        self._suspended = 0
        self._focus_job = None
        self._poll_job = None
        self._tag = f"KeyboardMonitorLab_{id(self)}"
        self._widgets: set[tk.Misc] = set()
        self._commands = {}
        self.windowing_system = str(root.tk.call("tk", "windowingsystem"))
        for sequence, callback in (
            ("<KeyPress>", self._on_press), ("<KeyRelease>", self._on_release),
            ("<FocusIn>", self._schedule_focus_check),
            ("<FocusOut>", self._schedule_focus_check),
        ):
            self._commands[sequence] = root.bind_class(self._tag, sequence, callback)
        self.attach_widgets(root)
        self._map_binding = root.bind("<Map>", self._on_map, add="+")
        self._poll_focus()

    @property
    def active(self) -> bool:
        return self.enabled and self.focused and not self._suspended and not self._closed

    @property
    def status(self) -> str:
        if not self.enabled:
            return "Stopped"
        return "Monitoring" if self.active else "Paused — app unfocused"

    def attach_widgets(self, widget: tk.Misc) -> None:
        """Prepend exactly one observer tag before widget/class event consumers."""
        if widget.winfo_toplevel() != self.root:
            return
        tags = widget.bindtags()
        if self._tag not in tags:
            widget.bindtags((self._tag, *tags))
        self._widgets.add(widget)
        for child in widget.winfo_children():
            self.attach_widgets(child)

    def _on_map(self, event: tk.Event) -> None:
        if not self._closed:
            self.attach_widgets(event.widget)

    def _has_focus(self) -> bool:
        try:
            widget = self.root.focus_get()
            return widget is not None and widget.winfo_toplevel() == self.root
        except (tk.TclError, KeyError):
            return False

    def _sync_activity(self) -> None:
        if self.active:
            self.activity.start(time.monotonic())
        else:
            self.activity.pause(time.monotonic())

    def _check_focus(self) -> None:
        self._focus_job = None
        if self._closed:
            return
        self.focused = self._has_focus()
        if not self.focused:
            # Never fabricate release events: clear indicators only.
            self.held.clear()
        self._sync_activity()

    def _schedule_focus_check(self, _event=None) -> None:
        # Let FocusOut/FocusIn settle when moving between this window's widgets.
        if not self._closed and self._focus_job is None:
            self._focus_job = self.root.after_idle(self._check_focus)

    def _poll_focus(self) -> None:
        self._poll_job = None
        if not self._closed:
            self._schedule_focus_check()
            self._poll_job = self.root.after(100, self._poll_focus)

    def start(self) -> None:
        if not self._closed:
            self.enabled = True
            self.focused = self._has_focus()
            self._sync_activity()

    def stop(self) -> None:
        self.enabled = False
        self.held.clear()
        self._sync_activity()

    def clear(self) -> None:
        self.history.clear()
        self.held.clear()
        self.activity = Activity()
        self._sync_activity()

    @contextmanager
    def suspend_for_dialog(self):
        """Exclude native Save As/message dialogs, including filename typing."""
        self._suspended += 1
        self.held.clear()
        self._sync_activity()
        try:
            yield
        finally:
            self._suspended -= 1
            self.focused = self._has_focus()
            self._sync_activity()
            self._schedule_focus_check()

    def _modifiers(self, event: tk.Event, pressed: bool) -> tuple[str, ...]:
        # Tk state is BEFORE this event. Normalize a modifier's own transition
        # so its release describes the modifiers still down afterward.
        # Windows Mod1 (0x8) means Num Lock, not Alt. X11 uses Mod1 for Alt.
        alt_mask = {"win32": 0x20000, "aqua": 0x10}.get(self.windowing_system, 0x8)
        masks = {"Ctrl": 0x4, "Shift": 0x1, "Alt": alt_mask}
        active = {name for name, mask in masks.items() if event.state & mask}
        own = MODIFIER_KEYS.get(event.keysym)
        if own:
            if pressed or own in (MODIFIER_KEYS.get(key) for key in self.held.values()):
                active.add(own)
            else:
                active.discard(own)
        # A later event's state can repair a missed modifier release.
        for code, key in list(self.held.items()):
            family = MODIFIER_KEYS.get(key)
            if family and family not in active:
                del self.held[code]
        return tuple(name for name in masks if name in active)

    def _capture(self, event: tk.Event, pressed: bool) -> None:
        if self._closed:
            return
        # Also check live focus in case deactivation is waiting in after_idle.
        self.focused = self._has_focus()
        if not self.focused:
            self.held.clear()
        self._sync_activity()
        if not self.active:
            return
        if pressed:
            self.held[event.keycode] = event.keysym
        else:
            self.held.pop(event.keycode, None)
        modifiers = self._modifiers(event, pressed)
        row = self.history.append("KeyPress" if pressed else "KeyRelease",
                                  event.keysym, event.keycode, modifiers)
        if pressed:
            self.activity.record()
        self.on_record(row)

    def _on_press(self, event: tk.Event) -> None:
        self._capture(event, True)

    def _on_release(self, event: tk.Event) -> None:
        self._capture(event, False)

    def close(self) -> None:
        if self._closed:
            return
        self.stop()
        self._closed = True
        for job in (self._focus_job, self._poll_job):
            if job is not None:
                self.root.after_cancel(job)
        self._focus_job = self._poll_job = None
        self.root.unbind("<Map>", self._map_binding)
        for widget in self._widgets:
            if widget.winfo_exists():
                widget.bindtags(tuple(tag for tag in widget.bindtags() if tag != self._tag))
        self._widgets.clear()
        for sequence, command in self._commands.items():
            self.root.unbind_class(self._tag, sequence)
            self.root.deletecommand(command)
        self._commands.clear()
