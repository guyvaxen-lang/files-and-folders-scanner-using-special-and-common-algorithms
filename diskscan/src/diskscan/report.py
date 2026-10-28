"""Terminal and JSON reports."""
from __future__ import annotations

import json
import os
import sys

from . import __version__
from .duplicates import DupGroup
from .scanner import DirNode, ScanResult
from .utils import Style, bar, human_size


def _color_for(pct: float, st: Style):
    return st.red if pct >= 50 else st.yellow if pct >= 20 else st.green


def print_tree(node: DirNode, st: Style, *, max_depth: int, top: int, min_size: int,
               prefix: str = "", depth: int = 1) -> None:
    if depth > max_depth:
        return
    kids = [c for c in sorted(node.children, key=lambda c: -c.size) if c.size >= min_size]
    shown, hidden = kids[:top], kids[top:]

    for i, child in enumerate(shown):
        last = i == len(shown) - 1 and not hidden
        pct = child.size / node.size * 100 if node.size else 0
        paint = _color_for(pct, st)
        branch = "└── " if last else "├── "
        print(
            f"{prefix}{branch}{paint(bar(pct / 100, 12))} "
            f"{human_size(child.size):>10} {pct:5.1f}%  "
            f"{st.bold(child.name)} {st.dim(f'({child.file_count:,} files)')}"
        )
        print_tree(child, st, max_depth=max_depth, top=top, min_size=min_size,
                   prefix=prefix + ("    " if last else "│   "), depth=depth + 1)

    if hidden:
        rest = sum(c.size for c in hidden)
        print(f"{prefix}└── {st.dim(f'... {len(hidden)} more ({human_size(rest)})')}")


def print_analysis(result: ScanResult, st: Style, *, depth: int, top: int,
                   min_size: int, apparent: bool, verbose: bool) -> None:
    root = result.root
    mode = "apparent size" if apparent else "disk usage"
    print()
    print(st.bold(root.path) + st.dim(f"  [{mode}]"))
    print(f"Total: {st.cyan(human_size(root.size))} in {result.total_files:,} files "
          f"({result.elapsed:.2f}s)\n")

    print(st.bold("Directory tree"))
    print_tree(root, st, max_depth=depth, top=top, min_size=min_size)

    print("\n" + st.bold(f"Largest files (top {top})"))
    if result.top_files:
        for size, path in result.top_files:
            print(f"  {human_size(size):>10}  {os.path.relpath(path, root.path)}")
    else:
        print("  (none)")

    print("\n" + st.bold("By file type"))
    ranked = sorted(result.by_extension.items(), key=lambda kv: -kv[1][0])[:top]
    for ext, (size, count) in ranked:
        pct = size / root.size * 100 if root.size else 0
        print(f"  {ext:<10} {human_size(size):>10} {pct:5.1f}%  {st.dim(f'{count:,} files')}")

    _print_notes(result, st, verbose)


def _print_notes(result: ScanResult, st: Style, verbose: bool) -> None:
    notes = []
    if result.hardlinks_skipped:
        notes.append(f"{result.hardlinks_skipped:,} hard links counted once")
    if result.errors:
        notes.append(f"{len(result.errors):,} paths skipped (use --verbose to list)")
    if notes:
        print("\n" + st.dim("Notes: " + "; ".join(notes)))
    if verbose:
        for path, reason in result.errors:
            print(st.red(f"  ! {path}: {reason}"), file=sys.stderr)


def print_duplicates(groups: list, result: ScanResult, st: Style, *, top: int, verbose: bool) -> None:
    wasted = sum(g.wasted for g in groups)
    files = sum(len(g.paths) for g in groups)
    print()
    print(st.bold(result.root.path))
    print(f"Scanned {result.total_files:,} files in {result.elapsed:.2f}s")
    if not groups:
        print(st.green("No duplicates found."))
        _print_notes(result, st, verbose)
        return

    print(f"Found {st.bold(str(len(groups)))} duplicate groups ({files:,} files). "
          f"Reclaimable: {st.cyan(human_size(wasted))}\n")
    for i, g in enumerate(groups[:top], 1):
        print(f"{st.bold(f'#{i}')}  {len(g.paths)} copies x {human_size(g.size)}  "
              f"-> wastes {st.yellow(human_size(g.wasted))}")
        for p in g.paths:
            print(f"     {os.path.relpath(p, result.root.path)}")
    if len(groups) > top:
        print(st.dim(f"\n... {len(groups) - top} more groups (raise --top or use --json)"))
    print(st.dim("\nNothing was deleted. Review the list and remove copies yourself."))
    _print_notes(result, st, verbose)


def export_analysis_json(result: ScanResult, path: str, depth: int) -> None:
    payload = {
        "version": __version__,
        "root": result.root.to_dict(depth),
        "total_bytes": result.root.size,
        "total_files": result.total_files,
        "largest_files": [{"size": s, "path": p} for s, p in result.top_files],
        "by_extension": {e: {"bytes": v[0], "files": v[1]} for e, v in result.by_extension.items()},
        "errors": [{"path": p, "reason": r} for p, r in result.errors],
        "elapsed_seconds": round(result.elapsed, 3),
    }
    _dump(payload, path)


def export_duplicates_json(groups: list, path: str) -> None:
    _dump({
        "version": __version__,
        "reclaimable_bytes": sum(g.wasted for g in groups),
        "groups": [{"size": g.size, "wasted": g.wasted, "paths": g.paths} for g in groups],
    }, path)


def _dump(payload: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
