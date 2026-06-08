#!/usr/bin/env python3
"""Prebuild step for the BOLD/DToL Species Lookup.

Reads the dated source TSV (e.g. ``2026_06_06_bold_dtol.txt``) and writes:

  * ``data.json``      — a compact, columnar, dictionary-encoded payload that the
                         worker streams, parses and indexes off the main thread.
  * ``data.meta.json`` — a tiny manifest (version, byte size, row count) used for
                         the download progress bar and service-worker cache
                         invalidation.

Only the columns the page displays are kept (the source's organism_key,
taxon_version_key, kingdom, phylum_division and class are dropped). Low-cardinality
columns are dictionary-encoded to integer indices, which shrinks the raw size and
roughly halves browser parse/build time.

Usage:
    python3 build.py [path/to/source.txt]

With no argument it auto-selects the newest ``*_bold_dtol.txt`` in this folder.
"""

import csv
import glob
import hashlib
import json
import os
import sys
from datetime import date

# Columns the page renders, in display order. Anything else in the TSV is dropped.
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

# Columns with fewer than this fraction of distinct values are dictionary-encoded.
DICT_CARDINALITY_RATIO = 0.3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_OUT = os.path.join(HERE, "data.json")
META_OUT = os.path.join(HERE, "data.meta.json")


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
    return max(candidates, key=os.path.getmtime)


def read_rows(source):
    """Return a list of per-row value lists (one entry per FIELDS column)."""
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
    return rows


def encode_columns(rows):
    """Transpose to columns, dictionary-encoding low-cardinality fields.

    Returns ``(dict_map, columns)`` where ``columns[i]`` is either a list of
    strings (raw) or a list of ints (indices into ``dict_map[field]``).
    """
    n = len(rows)
    dict_map = {}
    columns = []
    for i, field in enumerate(FIELDS):
        col = [row[i] for row in rows]
        distinct = set(col)
        if n and len(distinct) < n * DICT_CARDINALITY_RATIO:
            values = sorted(distinct)
            lookup = {v: k for k, v in enumerate(values)}
            dict_map[field] = values
            columns.append([lookup[v] for v in col])
        else:
            columns.append(col)
    return dict_map, columns


def main():
    source = pick_source(sys.argv)
    if not os.path.isfile(source):
        sys.exit(f"Source file not found: {source}")

    raw_bytes = open(source, "rb").read()
    version = hashlib.sha1(raw_bytes).hexdigest()[:12]

    rows = read_rows(source)
    dict_map, columns = encode_columns(rows)

    meta = {
        "source": os.path.basename(source),
        "rows": len(rows),
        "built": date.today().isoformat(),
        "version": version,
    }
    payload = {"meta": meta, "fields": FIELDS, "dict": dict_map, "columns": columns}

    with open(DATA_OUT, "w", encoding="utf-8") as out:
        json.dump(payload, out, ensure_ascii=False, separators=(",", ":"))

    out_bytes = os.path.getsize(DATA_OUT)
    # rawBytes lets the loader show an accurate progress bar (the streamed body is
    # decompressed, so the gzip Content-Length can't give a percentage).
    meta_file = dict(meta, rawBytes=out_bytes)
    with open(META_OUT, "w", encoding="utf-8") as out:
        json.dump(meta_file, out, ensure_ascii=False, separators=(",", ":"))

    encoded = ", ".join(dict_map.keys())
    print(
        f"Built data.json from {os.path.basename(source)}: "
        f"{len(rows):,} rows, {len(FIELDS)} fields, {out_bytes / 1_000_000:.1f} MB "
        f"(version {version})\n"
        f"  dictionary-encoded: {encoded}"
    )


if __name__ == "__main__":
    main()
