"""Duplicate file detection: size -> partial hash -> full hash."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from .scanner import ScanResult, scan

PARTIAL_BYTES = 64 * 1024
CHUNK = 1024 * 1024


@dataclass
class DupGroup:
    size: int
    paths: list

    @property
    def wasted(self) -> int:
        """Bytes that would be freed by keeping a single copy."""
        return self.size * (len(self.paths) - 1)


def _hash(path: str, limit: Optional[int] = None) -> Optional[str]:
    h = hashlib.blake2b()
    try:
        with open(path, "rb") as f:
            if limit is not None:
                h.update(f.read(limit))
            else:
                while chunk := f.read(CHUNK):
                    h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _group_by_hash(paths: list, workers: int, limit: Optional[int] = None) -> list:
    groups: dict = defaultdict(list)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for path, digest in zip(paths, pool.map(lambda p: _hash(p, limit), paths)):
            if digest:
                groups[digest].append(path)
    return [g for g in groups.values() if len(g) > 1]


def find_duplicates(
    root: str,
    *,
    min_size: int = 1,
    exclude: Optional[list] = None,
    one_file_system: bool = False,
    workers: int = 4,
    show_progress: bool = False,
) -> tuple:
    """Return ``(groups, scan_result)``; groups sorted by wasted space."""
    by_size: dict = defaultdict(list)

    def on_file(path: str, size: int) -> None:
        if size >= min_size:
            by_size[size].append(path)

    result: ScanResult = scan(
        root,
        exclude=exclude,
        apparent=True,
        one_file_system=one_file_system,
        top_files=0,
        show_progress=show_progress,
        on_file=on_file,
    )

    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for same_start in _group_by_hash(paths, workers, PARTIAL_BYTES):
            # Small files are already fully compared by the partial hash.
            full = [same_start] if size <= PARTIAL_BYTES else _group_by_hash(same_start, workers)
            groups.extend(DupGroup(size, sorted(g)) for g in full)

    groups.sort(key=lambda g: -g.wasted)
    return groups, result
