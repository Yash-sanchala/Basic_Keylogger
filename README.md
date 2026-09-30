# Keyboard Monitor Lab — Basic Demo

A visible educational demonstration of keyboard events using Python and Tkinter.
It observes presses and releases only while its own window is focused. Start is
always an explicit action. No global listener, background capture, clipboard access,
web server, network transmission, automatic startup, or automatic saving is included.

## Run

Use Python 3.10+ with Tkinter. No pip packages are required.

```sh
python -m tkinter
python main.py
```

Close the Tkinter demonstration window before launching the app. On Windows you
can also use `py`; on macOS/Linux use `python3` if needed. Windows python.org
installers offer Tcl/Tk support; enable it if missing. The python.org macOS
installer includes Tk. On Debian/Ubuntu install `python3-tk` using your system
package manager (`sudo apt install python3-tk`). A graphical desktop is required.

## Manual test checklist

Use harmless test input such as `hello 123`.

1. Launch: confirm **Stopped** and zero counters. Type in the test area; no event
   rows should appear until Start.
2. Click **Start Monitoring**, click the typing area, and type `hello 123`.
   Confirm text edits normally and the table shows KeyPress and KeyRelease rows
   with timestamps, names, codes and modifiers.
3. Try Space, Enter, Backspace, Delete, arrows, Escape and F2. Try Shift+A and
   Ctrl+A. Tab inserts a tab in the text area; Ctrl+Tab moves to another widget.
4. Move between buttons and the text area: monitoring continues. Switch to
   Notepad: this app pauses and records no Notepad keys. Return: it resumes.
5. Hold a key, switch applications, release it, then return. Held indicators
   should reset without fabricated release rows.
6. Click **Stop Monitoring**. Type again: counters and history should not grow.
   Repeat Start/Stop several times to check for duplicate registration.
7. Click **Clear**: history, counters and typing area reset; the monitoring mode
   stays as it was. Check both while stopped and while monitoring.
8. Capture a few events, click **Export CSV**, cancel once, then export to a file.
   Open it and check column headings and matching retained rows. Exporting with
   empty history should show an understandable message. Nothing saves by itself.
9. Resize the window, then close it. Confirm the window exits cleanly.

## Behavior and limitations

The latest 5,000 events are retained in memory. Counters include older events
since Clear. CSV exports only retained rows. Export totals provides aggregate
activity statistics and stops monitoring. CSV exports may contain sensitive key
metadata: this repository's .gitignore excludes CSV files by default.

Key repeat and keycodes differ across operating systems; event counts do not
equal physical key presses. OS shortcuts, Fn/media keys, IME composition and
some keyboard layouts may behave differently. This demonstrates key events,
not reconstruction of documents, pasted text or full typed sentences.

## Files and testing

- `main.py`: entry point.
- `ui.py`: interface, batched rendering and explicit export dialogs.
- `monitor.py`: Tk event bindings, focus state, modifiers and cleanup.
- `models.py`: bounded history, records and activity statistics.
- `exporter.py`: CSV writers.
- `tests/`: model and Tk integration checks using synthetic events.

Run from this folder:

```sh
python -m unittest discover -s tests -v
```

GUI tests briefly open windows and move focus. Physical keyboard behavior and
native Save As dialogs require the manual checklist above.

Verified on Windows on 2026-09-30: all 15 tests passed (5 model/export tests and
10 Tk integration tests), including a regression check that Num Lock is not
misreported as Alt in the table or CSV fields. Manual physical-input checks
remain for the user. Restart the app after updating the source; old exported
files are not rewritten by this fix.

## Repository contents

This repository contains the standalone focused-window demo. No system-wide
listener or web version is required. Virtual environments, generated caches and
exported CSV files are excluded by `.gitignore`.
