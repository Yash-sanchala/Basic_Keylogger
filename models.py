"""In-memory event records and the original activity statistics."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime


HISTORY_LIMIT = 5_000
CSV_HEADINGS = ("Event number", "Local timestamp", "Event type", "Key name",
                "Key code", "Ctrl", "Shift", "Alt", "Combination")
KEY_NAMES = {
    "space": "Space", "Return": "Enter", "KP_Enter": "Numpad Enter",
    "BackSpace": "Backspace", "Delete": "Delete", "Escape": "Escape",
    "Tab": "Tab", "ISO_Left_Tab": "Tab", "Prior": "Page Up", "Next": "Page Down",
    "Control_L": "Left Ctrl", "Control_R": "Right Ctrl",
    "Shift_L": "Left Shift", "Shift_R": "Right Shift",
    "Alt_L": "Left Alt", "Alt_R": "Right Alt", "ISO_Level3_Shift": "AltGr",
    "Caps_Lock": "Caps Lock", "Super_L": "Left Super", "Super_R": "Right Super",
}
MODIFIER_KEYS = {
    "Control_L": "Ctrl", "Control_R": "Ctrl", "Shift_L": "Shift", "Shift_R": "Shift",
    "Alt_L": "Alt", "Alt_R": "Alt",
}


def readable_key(keysym: str) -> str:
    return KEY_NAMES.get(keysym, keysym)


def combination(keysym: str, modifiers: tuple[str, ...]) -> str:
    prefix = [name for name in modifiers if name != MODIFIER_KEYS.get(keysym)]
    return " + ".join([*prefix, readable_key(keysym)])


@dataclass(frozen=True)
class KeyEventRecord:
    number: int
    timestamp: str
    event_type: str
    keysym: str
    keycode: int
    modifiers: tuple[str, ...]
    display: str

    def csv_row(self) -> tuple:
        return (self.number, self.timestamp, self.event_type, self.keysym,
                self.keycode, *(name in self.modifiers for name in ("Ctrl", "Shift", "Alt")),
                self.display)

    def table_row(self) -> tuple:
        return (self.number, self.timestamp, self.event_type, readable_key(self.keysym),
                self.keycode, " + ".join(self.modifiers) or "—", self.display)


class EventHistory:
    def __init__(self) -> None:
        self.rows: deque[KeyEventRecord] = deque(maxlen=HISTORY_LIMIT)
        self.total = self.presses = self.releases = 0

    def append(self, event_type: str, keysym: str, keycode: int,
               modifiers: tuple[str, ...], now: datetime | None = None) -> KeyEventRecord:
        if event_type not in ("KeyPress", "KeyRelease"):
            raise ValueError("Unsupported keyboard event type")
        self.total += 1
        self.presses += event_type == "KeyPress"
        self.releases += event_type == "KeyRelease"
        record = KeyEventRecord(
            self.total, (now or datetime.now().astimezone()).isoformat(timespec="milliseconds"),
            event_type, keysym, keycode, modifiers, combination(keysym, modifiers),
        )
        self.rows.append(record)
        return record

    def clear(self) -> None:
        self.rows.clear()
        self.total = self.presses = self.releases = 0


@dataclass
class Activity:
    keypresses: int = 0
    accumulated_seconds: float = 0.0
    started_at: float | None = None

    @property
    def running(self) -> bool:
        return self.started_at is not None

    def start(self, now: float) -> None:
        if not self.running:
            self.started_at = now

    def pause(self, now: float) -> None:
        if self.started_at is not None:
            self.accumulated_seconds += now - self.started_at
            self.started_at = None

    def elapsed(self, now: float) -> float:
        return self.accumulated_seconds + (0.0 if self.started_at is None else now - self.started_at)

    def record(self) -> None:
        if self.running:
            self.keypresses += 1

    def snapshot(self, now: float) -> dict:
        seconds = self.elapsed(now)
        return {"keypresses": self.keypresses, "elapsed_seconds": round(seconds, 2),
                "keypresses_per_minute": round(self.keypresses * 60 / seconds, 1) if seconds > 0 else 0.0}
