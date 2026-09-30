"""Launch Keyboard Monitor Lab with the Python standard library."""

import tkinter as tk

from ui import KeyboardMonitorApp


def main() -> None:
    root = tk.Tk()
    KeyboardMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
