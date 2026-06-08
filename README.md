# quick-check — BOLD & DToL Species Lookup

A static, single-page tool for looking up UK species against the UKBOL / BOLD / DToL
dataset. Paste species names (one per line) and get coverage, BAGS grade, status, and
DToL priority. Synonyms and close (fuzzy) spellings are matched automatically.

## How it works

The page (`index.html`) loads a compact **`data.json`** and runs entirely in the browser
— no server required. `data.json` is generated from the dated source TSV by `build.py`.

## Updating the data

1. Drop the new dated source file (e.g. `2026_06_06_bold_dtol.txt`) into the repo root.
2. Regenerate the compact data file:
   ```sh
   python3 build.py
   ```
   It auto-selects the newest `*_bold_dtol.txt` (or pass a path:
   `python3 build.py path/to/file.txt`) and writes `data.json`.
3. Commit both the source TSV and the new `data.json`.

`index.html` always loads `data.json`, so no code edit is needed on each update.

`build.py` keeps only the columns the page displays (dropping `organism_key`,
`taxon_version_key`, `kingdom`, `phylum_division`, `class`) and stores rows as arrays,
which makes the file smaller and much faster for the browser to parse than the raw TSV.

## Branding / logo

The header expects the UKBOL logo at `assets/images/ukbol-text-logo-clear.png`. If the
file is absent it falls back to a "UKBOL" text wordmark automatically. Drop the real PNG
in that path to display it.

## Search behaviour

- **Exact** (case-insensitive) match on taxon name or any synonym.
- **Fuzzy fallback** when there's no exact match — a "Did you mean?" list of approximate
  matches by edit distance (a few different letters) and by species epithet (same epithet,
  different genus). Click a suggestion to view its full record.
