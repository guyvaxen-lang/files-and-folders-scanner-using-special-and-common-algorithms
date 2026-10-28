# diskscan

מנתח שימוש בדיסק, מאתר קבצים כפולים ויוצר דוח treemap אינטראקטיבי. ללא תלויות חיצוניות, Python 3.9+.

A dependency-free disk usage analyzer, duplicate finder and interactive treemap generator.

## Install

```
pip install -e .
```

(or run without installing: `PYTHONPATH=src python -m diskscan ...`)

## Usage

```
diskscan analyze ~/Downloads -d 3 -n 15          # tree, largest files, file types
diskscan analyze . -x node_modules -x .git --min-size 100MB
diskscan dupes ~/Pictures --min-size 1MB --json dupes.json
diskscan html ~/ -o report.html                  # open report.html in a browser
diskscan ~/Downloads                             # shorthand for `analyze`
```

| Command   | What it does                                                                 |
|-----------|------------------------------------------------------------------------------|
| `analyze` | Directory tree with bars, N largest files, breakdown by extension, JSON export |
| `dupes`   | Finds identical files. Read-only: it never deletes anything                  |
| `html`    | Single-file interactive treemap; click a folder to drill down                |

Common options: `-x/--exclude PATTERN`, `--one-file-system`, `--no-color`, `-v/--verbose`.

## How it works

- **Scanner**: iterative `os.scandir` traversal; each directory's size is aggregated bottom-up in one pass
  (O(files)). Reports real allocated disk space by default (`--apparent` for logical size).
  Symlinks are skipped and hard links are counted once.
- **Duplicates**: group by size -> hash the first 64 KB -> full BLAKE2b hash only for the survivors,
  with parallel hashing. Most files are eliminated before being read in full.
- **Treemap**: squarified layout rendered in the browser from embedded JSON; works offline.

## Tests

```
PYTHONPATH=src python -m unittest discover -s tests -v
```
