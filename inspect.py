#!/usr/bin/env python3
"""
csv-duplicate-inspector — inspect a CSV for duplicate risks.

Finds:
  - exact-duplicate rows (streamed: only row hashes are kept in memory)
  - duplicate values in a key column (--key)
  - near-duplicate values in a column via normalized comparison
    (case / whitespace / punctuation insensitive)

Prints a summary report (counts, % duplicated, sample groups).

Exit codes: 0 = no duplicates found, 1 = duplicates found (or unusable
input), 2 = no duplicates, but data-quality warnings only.

Usage:
  python3 inspect.py contacts.csv
  python3 inspect.py contacts.csv --key email
  python3 inspect.py contacts.csv --key company --near-dup
  python3 inspect.py contacts.csv --json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

NEAR_DUP_NORMALIZE = re.compile(r"[^\w\s]", re.UNICODE)
WS_COLLAPSE = re.compile(r"\s+")


def normalize(value: str) -> str:
    """Normalize for near-duplicate comparison."""
    v = value.lower()
    v = NEAR_DUP_NORMALIZE.sub("", v)
    v = WS_COLLAPSE.sub(" ", v)
    return v.strip()


class Inspection:
    def __init__(self, path: str, key: str | None, near_dup: bool,
                 sample: int):
        self.path = path
        self.key = key
        self.near_dup = near_dup
        self.sample = sample
        self.total_rows = 0
        self.blank_lines = 0
        self.ragged_lines: list[int] = []
        self.header: list[str] | None = None
        # exact duplicates: row-tuple -> [count, first_line]
        # (only the tuple key is kept; row contents are never stored twice)
        self.exact: dict[tuple, list] = {}
        # key column: value -> [count, [line numbers...]]
        self.key_counts: dict[str, list] = {}
        # near duplicates: normalized -> {raw_value: count}
        self.near: dict[str, dict[str, int]] = {}
        self.key_index: int | None = None
        self.key_missing = False

    def run(self) -> None:
        with open(self.path, "r", newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            try:
                self.header = next(reader)
            except StopIteration:
                return
            ncols = len(self.header)
            if self.key is not None:
                if self.key in self.header:
                    self.key_index = self.header.index(self.key)
                else:
                    self.key_missing = True
            for lineno, row in enumerate(reader, start=2):  # header is line 1
                if not row or all(c == "" for c in row):
                    self.blank_lines += 1
                    continue
                self.total_rows += 1
                if len(row) != ncols:
                    self.ragged_lines.append(lineno)
                key = tuple(row)
                entry = self.exact.get(key)
                if entry is None:
                    self.exact[key] = [1, lineno]
                else:
                    entry[0] += 1
                if self.key_index is not None and self.key_index < len(row):
                    val = row[self.key_index]
                    kc = self.key_counts.get(val)
                    if kc is None:
                        self.key_counts[val] = [1, [lineno]]
                    else:
                        kc[0] += 1
                        if len(kc[1]) < 10:
                            kc[1].append(lineno)
                    if self.near_dup:
                        norm = normalize(val)
                        group = self.near.setdefault(norm, {})
                        group[val] = group.get(val, 0) + 1

    @property
    def exact_dupe_groups(self):
        return {k: v for k, v in self.exact.items() if v[0] > 1}

    @property
    def exact_dupe_rows(self) -> int:
        return sum(v[0] for v in self.exact_dupe_groups.values())

    @property
    def key_dupe_values(self):
        return {k: v for k, v in self.key_counts.items() if v[0] > 1}

    @property
    def near_dupe_clusters(self):
        return {k: v for k, v in self.near.items() if len(v) > 1}

    def has_duplicates(self) -> bool:
        return bool(self.exact_dupe_groups or self.key_dupe_values
                    or self.near_dupe_clusters)

    def warnings(self) -> list[str]:
        w = []
        if self.blank_lines:
            w.append(f"{self.blank_lines} blank line(s) skipped")
        if self.ragged_lines:
            shown = ", ".join(map(str, self.ragged_lines[:10]))
            extra = f" (+{len(self.ragged_lines) - 10} more)" \
                if len(self.ragged_lines) > 10 else ""
            w.append(f"{len(self.ragged_lines)} ragged row(s) with a "
                     f"different field count than the header "
                     f"(lines {shown}{extra})")
        return w

    def report_text(self) -> str:
        lines = [f"CSV duplicate inspection: {self.path}",
                 f"Rows: {self.total_rows} (header excluded)"]
        groups = self.exact_dupe_groups
        if groups:
            pct = 100.0 * self.exact_dupe_rows / max(self.total_rows, 1)
            lines.append(f"Exact-duplicate rows: {self.exact_dupe_rows} rows "
                         f"in {len(groups)} groups ({pct:.2f}% of rows)")
            for row, (count, first_line) in \
                    list(groups.items())[:self.sample]:
                preview = ", ".join(row[:4])
                if len(row) > 4:
                    preview += ", ..."
                lines.append(f"  - x{count} (first at line {first_line}): "
                             f"{preview}")
        else:
            lines.append("Exact-duplicate rows: none")
        if self.key is not None:
            if self.key_missing:
                lines.append(f'Key column "{self.key}": NOT FOUND in header')
            else:
                dupes = self.key_dupe_values
                affected = sum(v[0] for v in dupes.values())
                lines.append(f'Key column "{self.key}": {len(dupes)} duplicate '
                             f"value(s) affecting {affected} rows")
                for val, (count, linenos) in list(dupes.items())[:self.sample]:
                    lines.append(f"  - {val!r} x{count} "
                                 f"(lines {', '.join(map(str, linenos))})")
        if self.near_dup and self.key is not None and not self.key_missing:
            clusters = self.near_dupe_clusters
            lines.append(f"Near-duplicate clusters in \"{self.key}\" "
                         f"(normalized): {len(clusters)}")
            for norm, variants in list(clusters.items())[:self.sample]:
                raw = ", ".join(f"{r!r} x{c}" for r, c in variants.items())
                lines.append(f"  - {norm!r} <- {raw}")
        for w in self.warnings():
            lines.append(f"Warning: {w}")
        return "\n".join(lines)

    def report_json(self) -> dict:
        return {
            "file": self.path,
            "rows": self.total_rows,
            "exact_duplicate_rows": self.exact_dupe_rows,
            "exact_duplicate_groups": len(self.exact_dupe_groups),
            "key": self.key,
            "key_duplicates": {k: {"count": v[0], "lines": v[1]}
                               for k, v in self.key_dupe_values.items()},
            "near_duplicate_clusters": {k: v for k, v in
                                        self.near_dupe_clusters.items()},
            "warnings": self.warnings(),
            "has_duplicates": self.has_duplicates(),
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Inspect a CSV for duplicate rows and duplicate key values.")
    ap.add_argument("csv_file", help="path to the CSV file")
    ap.add_argument("--key",
                    help="column name to check for duplicate values")
    ap.add_argument("--near-dup", action="store_true",
                    help="also find near-duplicate values in --key via "
                         "normalized comparison (requires --key)")
    ap.add_argument("--sample", type=int, default=5,
                    help="max example groups shown per section (default 5)")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of text")
    args = ap.parse_args(argv)

    if args.near_dup and not args.key:
        print("ERROR: --near-dup requires --key", file=sys.stderr)
        return 1
    if not Path(args.csv_file).is_file():
        print(f"ERROR: file not found: {args.csv_file}", file=sys.stderr)
        return 1

    insp = Inspection(args.csv_file, args.key, args.near_dup, args.sample)
    try:
        insp.run()
    except (OSError, csv.Error) as exc:
        print(f"ERROR: cannot read {args.csv_file}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(insp.report_json(), indent=2))
    else:
        print(insp.report_text())

    if insp.key_missing:
        return 1
    if insp.has_duplicates():
        return 1
    if insp.warnings():
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
