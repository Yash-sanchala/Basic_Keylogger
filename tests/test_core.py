import csv
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from exporter import export_events, export_totals
from models import Activity, CSV_HEADINGS, EventHistory, HISTORY_LIMIT, combination, readable_key


class HistoryTests(unittest.TestCase):
    def test_retention_and_lifetime_counters(self):
        history = EventHistory()
        for index in range(12_007):
            history.append("KeyPress" if index % 2 == 0 else "KeyRelease", "a", 65, ())
        self.assertEqual(len(history.rows), HISTORY_LIMIT)
        self.assertEqual(history.rows[0].number, 7008)
        self.assertEqual(history.rows[-1].number, 12007)
        self.assertEqual((history.total, history.presses, history.releases), (12007, 6004, 6003))
        history.clear()
        self.assertEqual((len(history.rows), history.total, history.presses, history.releases), (0, 0, 0, 0))
        self.assertEqual(history.append("KeyPress", "b", 66, ()).number, 1)

    def test_timestamp_and_readable_names(self):
        history = EventHistory()
        row = history.append("KeyPress", "Return", 13, ("Ctrl", "Shift"),
                             datetime(2026, 9, 25, 15, 30, 1, 123456, timezone.utc))
        self.assertEqual(row.timestamp, "2026-09-25T15:30:01.123+00:00")
        self.assertEqual(row.display, "Ctrl + Shift + Enter")
        self.assertEqual(row.keysym, "Return")
        self.assertEqual(combination("Control_L", ("Ctrl",)), "Left Ctrl")
        for key in ("space", "BackSpace", "Delete", "Escape", "Tab", "Left", "F12", "1"):
            self.assertTrue(readable_key(key))

    def test_export_retained_rows_and_utf8(self):
        history = EventHistory()
        for index in range(5012):
            history.append("KeyPress", "eacute" if index % 2 else "é", 69, ("Ctrl",))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "events.csv"
            export_events(target, history.rows)
            with target.open(encoding="utf-8", newline="") as source:
                rows = list(csv.reader(source))
            self.assertEqual(tuple(rows[0]), CSV_HEADINGS)
            self.assertEqual(len(rows), 5001)
            self.assertEqual(rows[1][0], "13")
            self.assertEqual(rows[-1][0], "5012")
            self.assertEqual(rows[1][3], "é")
            self.assertEqual(rows[1][5:8], ["True", "False", "False"])
            self.assertNotIn(b"\r\r\n", target.read_bytes())

    def test_export_failure_propagates_to_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                export_events(Path(directory) / "missing" / "events.csv", [])

    def test_existing_activity_statistics_and_export(self):
        activity = Activity()
        activity.record()
        self.assertEqual(activity.keypresses, 0)
        activity.start(10)
        activity.start(11)
        activity.record()
        activity.pause(12)
        activity.pause(13)
        activity.start(20)
        activity.record()
        activity.pause(22)
        self.assertEqual(activity.snapshot(30),
                         {"keypresses": 2, "elapsed_seconds": 4, "keypresses_per_minute": 30.0})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "totals.csv"
            export_totals(target, {"exported_at": "test", **activity.snapshot(30)})
            with target.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(rows[0]["keypresses"], "2")


if __name__ == "__main__":
    unittest.main()
