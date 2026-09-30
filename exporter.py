"""Explicit CSV writing; importing this module never creates files."""

import csv
from pathlib import Path
from typing import Iterable

from models import CSV_HEADINGS, KeyEventRecord


def export_events(destination: str | Path, rows: Iterable[KeyEventRecord]) -> None:
    with Path(destination).open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(CSV_HEADINGS)
        writer.writerows(row.csv_row() for row in rows)


def export_totals(destination: str | Path, snapshot: dict) -> None:
    with Path(destination).open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(snapshot))
        writer.writeheader()
        writer.writerow(snapshot)
