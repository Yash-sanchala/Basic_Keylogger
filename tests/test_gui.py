"""Real Tk widget tests using synthetic events; requires a desktop/display.

These tests briefly open windows and change focus. They do not inject OS keys.
Physical keyboard, window switching, native dialogs, and OS repeat behavior
still need the manual checks in README.md.
"""

import csv
from pathlib import Path
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from models import CSV_HEADINGS
from ui import KeyboardMonitorApp


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.app = KeyboardMonitorApp(self.root)
        self.root.update()
        self.app.typing_area.focus_force()
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.assertEqual(self.errors, [], "Tk callback raised an exception")

    def emit(self, keysym, state=0, pressed=True, widget=None):
        target = widget or self.root.focus_get()
        target.event_generate("<KeyPress>" if pressed else "<KeyRelease>", keysym=keysym, state=state)

    def pair(self, keysym, state=0):
        self.emit(keysym, state)
        self.emit(keysym, state, False)

    def drain_table(self):
        deadline = time.monotonic() + 8
        while self.app._render_job is not None and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.005)
        self.assertIsNone(self.app._render_job)

    def test_initial_stop_repeated_start_stop_and_typing(self):
        self.assertEqual(self.app.monitor.status, "Stopped")
        self.pair("a")
        self.assertEqual(self.app.history.total, 0)
        self.assertEqual(self.app.typing_area.get("1.0", "end-1c"), "a")
        for _ in range(3):
            self.app.start()
            self.app.start()
            self.pair("b")
            self.assertEqual(self.app.monitor.status, "Monitoring")
            self.app.stop()
            self.app.stop()
            self.pair("c")
            self.assertFalse(self.app.monitor.held)
        self.assertEqual((self.app.history.total, self.app.history.presses, self.app.history.releases), (6, 3, 3))

    def test_binding_order_navigation_and_single_registration(self):
        self.app.start()
        self.app.monitor.attach_widgets(self.root)
        self.app.monitor.attach_widgets(self.root)
        self.pair("a")
        self.pair("Tab")
        self.assertEqual(self.app.typing_area.get("1.0", "end-1c"), "a\t")
        # Widget bindings returning break cannot suppress the earlier observer.
        binding = self.app.typing_area.bind("<KeyPress-F2>", lambda event: "break")
        self.pair("F2")
        self.app.typing_area.unbind("<KeyPress-F2>", binding)
        self.assertEqual(self.app.history.total, 6)
        self.app.stop_button.focus_force()
        self.root.update()
        self.emit("Tab")
        self.root.update()
        self.assertEqual(self.root.focus_get(), self.app.clear_button)
        self.emit("Tab", pressed=False)
        self.assertEqual(self.app.history.total, 8)
        self.assertEqual(self.app.monitor.status, "Monitoring")
        self.assertFalse(self.app.monitor.held)

    def test_editing_and_special_keys(self):
        self.app.start()
        for key in ("a", "1", "space", "Return", "b", "BackSpace", "Left", "Right", "Up", "Down", "Delete", "Escape", "F12"):
            self.pair(key)
        self.assertEqual(self.app.history.total, 26)
        self.assertEqual(self.app.typing_area.get("1.0", "end-1c"), "a1 \n")
        self.assertFalse(self.app.monitor.held)

    def test_modifier_combinations_and_repeat(self):
        self.app.start()
        self.emit("Control_L")
        self.emit("Shift_L", 0x4)
        self.pair("F6", 0x5)
        self.assertEqual(self.app.history.rows[-1].display, "Ctrl + Shift + F6")
        self.emit("Shift_L", 0x5, False)
        self.assertEqual(self.app.history.rows[-1].modifiers, ("Ctrl",))
        self.emit("Control_L", 0x4, False)
        self.assertFalse(self.app.monitor.held)
        for _ in range(20):
            self.emit("a")
        self.assertEqual(len(self.app.monitor.held), 1)
        self.emit("a", pressed=False)
        self.assertFalse(self.app.monitor.held)
        # Exercise each platform's Alt decoding independently of the host OS.
        monitor = self.app.monitor
        original = monitor.windowing_system
        for system, mask in (("win32", 0x20000), ("x11", 0x8), ("aqua", 0x10)):
            monitor.windowing_system = system
            self.assertEqual(monitor._modifiers(SimpleNamespace(keysym="F6", state=mask), True), ("Alt",))
        monitor.windowing_system = original

    def test_windows_numlock_does_not_become_alt_in_history_or_csv(self):
        monitor = self.app.monitor
        monitor.windowing_system = "win32"
        self.app.start()
        for state, expected in ((0x8, ()), (0xA, ()), (0x20008, ("Alt",)),
                                (0xD, ("Ctrl", "Shift"))):
            for pressed in (True, False):
                monitor._capture(SimpleNamespace(keysym="a", keycode=65, state=state), pressed)
                row = self.app.history.rows[-1]
                self.assertEqual(row.modifiers, expected)
                self.assertEqual(row.csv_row()[7], "Alt" in expected)
                self.assertEqual(row.display.startswith("Alt + "), expected == ("Alt",))
        self.drain_table()
        self.assertEqual(self.app.table.item("1", "values")[-1], "a")

    def test_focus_transitions_no_synthetic_releases_and_stop_persists(self):
        self.app.start()
        self.emit("a")
        self.app.table.focus_force()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Monitoring")
        self.assertTrue(self.app.monitor.held)
        self.emit("a", pressed=False)
        self.emit("b")
        count = self.app.history.total
        # Withdrawal produces real Tk focus loss, but is not an Alt+Tab test.
        self.root.withdraw()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Paused — app unfocused")
        self.assertFalse(self.app.monitor.held)
        self.assertEqual(self.app.history.total, count)
        self.root.deiconify()
        self.app.typing_area.focus_force()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Monitoring")
        self.assertFalse(self.app.monitor.held)
        self.app.stop()
        self.root.withdraw()
        self.root.update()
        self.root.deiconify()
        self.app.typing_area.focus_force()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Stopped")

    def test_clear_and_bounded_rendering_under_burst(self):
        self.app.start()
        for _ in range(2601):
            self.pair("F6")
        self.drain_table()
        self.assertEqual(self.app.history.total, 5202)
        self.assertEqual(len(self.app.history.rows), 5000)
        items = self.app.table.get_children()
        self.assertEqual((len(items), items[0], items[-1]), (5000, "203", "5202"))
        self.assertAlmostEqual(self.app.table.yview()[1], 1.0)
        self.pair("b")  # Clear while rendering is queued.
        self.app.clear()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Monitoring")
        self.assertEqual(self.app.history.total, 0)
        self.assertEqual(self.app.table.get_children(), ())
        self.assertFalse(self.app.monitor.held)
        self.assertEqual(self.app.typing_area.get("1.0", "end-1c"), "")
        self.app.stop()
        self.app.clear()
        self.assertEqual(self.app.monitor.status, "Stopped")

    def test_export_empty_cancel_failure_and_success(self):
        with patch("ui.messagebox.showinfo") as info, patch("ui.filedialog.asksaveasfilename") as dialog:
            self.app.export()
            info.assert_called_once()
            dialog.assert_not_called()
        self.app.start()
        self.pair("a")
        def cancel(**kwargs):
            self.assertFalse(self.app.monitor.active)
            self.pair("b")
            return ""
        with patch("ui.filedialog.asksaveasfilename", side_effect=cancel), patch("ui.messagebox.showerror") as error:
            self.app.export()
            error.assert_not_called()
        self.assertEqual(self.app.history.total, 2)
        self.assertTrue(self.app.monitor.active)
        with patch("ui.filedialog.asksaveasfilename", return_value="unused.csv"), \
                patch("ui.export_events", side_effect=PermissionError("Access denied")), \
                patch("ui.messagebox.showerror") as error:
            self.app.export()
            error.assert_called_once()
            self.assertIn("Access denied", error.call_args.args[1])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "events.csv"
            with patch("ui.filedialog.asksaveasfilename", return_value=str(target)), patch("ui.messagebox.showinfo"):
                self.app.export()
            with target.open(encoding="utf-8", newline="") as source:
                rows = list(csv.reader(source))
            self.assertEqual(tuple(rows[0]), CSV_HEADINGS)
            self.assertEqual(len(rows), 3)

    def test_close_removes_bindings_and_callbacks(self):
        self.app.start()
        self.emit("a")
        monitor = self.app.monitor
        commands = tuple(monitor._commands.values())
        jobs = tuple(job for job in (monitor._poll_job, monitor._focus_job,
                                     self.app._refresh_job, self.app._render_job) if job)
        monitor.close()
        for widget in (self.root, self.app.typing_area, self.app.table):
            self.assertNotIn(monitor._tag, widget.bindtags())
        for command in commands:
            self.assertFalse(self.root.tk.call("info", "commands", command))
        self.app.close()
        pending = self.root.tk.call("after", "info")
        self.assertFalse(set(jobs).intersection(pending))
        self.app.close()

    def test_new_widgets_and_clear_while_paused(self):
        self.app.start()
        entry = tk.Entry(self.app.root)
        entry.place(x=25, y=25)
        self.root.update()
        entry.focus_force()
        self.root.update()
        self.pair("a")
        self.assertEqual(entry.get(), "a")
        self.assertEqual(self.app.history.total, 2)
        self.root.withdraw()
        self.root.update()
        self.app.clear()
        self.assertEqual(self.app.monitor.status, "Paused — app unfocused")
        self.assertEqual((self.app.history.total, self.app.history.presses, self.app.history.releases), (0, 0, 0))
        self.root.deiconify()
        self.app.typing_area.focus_force()
        self.root.update()
        self.assertEqual(self.app.monitor.status, "Monitoring")





if __name__ == "__main__":
    unittest.main()
