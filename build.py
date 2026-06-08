#!/usr/bin/env python3
"""Prebuild step for the BOLD/DToL Species Lookup.

Reads the dated source TSV (e.g. ``2026_06_06_bold_dtol.txt``) and writes a
compact ``data.json`` that the static ``index.html`` loads directly. The JSON
keeps only the columns the page actually displays and stores rows as arrays
(no repeated per-row keys), so it is both smaller and far faster for the
browser's native ``JSON.parse`` than parsing the full TSV on the main thread.

Usage:
    python3 build.py [path/to/source.txt]

With no argument it auto-selects the newest ``*_bold_dtol.txt`` in this folder.
"""

import csv
import glob
import json
import os
import sys
from datetime import date

# Columns the page renders, in display order. Anything else in the TSV
# (organism_key, taxon_version_key, kingdom, phylum_division, class) is dropped.
FIELDS = [
    "order",
    "family",
    "taxon_name",
    "synonyms",
    "BOLD_number_records",
    "BOLD_gb_records",
    "bags_grade",
    "species_status",
    "BOLD_other_names",
    "dtol_status",
]

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "data.json")


def pick_source(argv):
    """Return the source TSV path: an explicit arg, or the newest dated file."""
    if len(argv) > 1:
        return argv[1]
    candidates = glob.glob(os.path.join(HERE, "*_bold_dtol.txt"))
    if not candidates:
        sys.exit(
            "No source file found. Pass a path or place a *_bold_dtol.txt "
            "file next to build.py."
        )
    # Newest by modification time (filenames are date-prefixed, but mtime is safe).
    return max(candidates, key=os.path.getmtime)


def main():
    source = pick_source(sys.argv)
    if not os.path.isfile(source):
        sys.exit(f"Source file not found: {source}")

    # Source files have been seen as UTF-8 and as Windows-1252/Latin-1
    # (accented author names). Try UTF-8 first, fall back to cp1252.
    encoding = "utf-8"
    try:
        with open(source, "r", encoding="utf-8") as probe:
            probe.read()
    except UnicodeDecodeError:
        encoding = "cp1252"

    rows = []
    with open(source, "r", encoding=encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        missing = [f for f in FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            sys.exit(
                f"Source is missing expected column(s): {', '.join(missing)}\n"
                f"Found columns: {', '.join(reader.fieldnames or [])}"
            )
        for r in reader:
            rows.append([(r.get(f) or "").strip() for f in FIELDS])

    payload = {
        "meta": {
            "source": os.path.basename(source),
            "rows": len(rows),
            "built": date.today().isoformat(),
        },
        "fields": FIELDS,
        "rows": rows,
    }

    with open(OUTPUT, "w", encoding="utf-8") as out:
        # Compact separators keep the file small; ensure_ascii=False keeps
        # accented taxon names readable and a touch smaller.
        json.dump(payload, out, ensure_ascii=False, separators=(",", ":"))

    out_bytes = os.path.getsize(OUTPUT)
    print(
        f"Built data.json from {os.path.basename(source)}: "
        f"{len(rows):,} rows, {len(FIELDS)} fields, {out_bytes / 1_000_000:.1f} MB"
    )


if __name__ == "__main__":
    main()
