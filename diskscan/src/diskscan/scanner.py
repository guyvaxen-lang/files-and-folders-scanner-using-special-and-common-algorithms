"""Core filesystem scanner (iterative, bottom-up aggregation)."""
from __future__ import annotations

import fnmatch
import heapq
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(eq=False)
class DirNode:
    path: str
    name: str
    parent: Optional["DirNode"] = None
    size: int = 0
    file_count: int = 0
    children: list = field(default_factory=list)

    def to_dict(self, depth: int) -> dict:
        d = {"path": self.path, "size": self.size, "files": self.file_count}
        if depth > 0:
            kids = sorted(self.children, key=lambda c: -c.size)
            d["children"] = [c.to_dict(depth - 1) for c in kids]
        return d


@dataclass
class ScanResult:
    root: DirNode
    top_files: list  # [(size, path)] largest first
    by_extension: dict  # ext -> [bytes, count]
    errors: list  # [(path, reason)]
    hardlinks_skipped: int
    total_files: int
    elapsed: float


def disk_size(st: os.stat_result, apparent: bool) -> int:
    """Space actually used on disk where the OS reports allocated blocks."""
    blocks = getattr(st, "st_blocks", None)
    if apparent or blocks is None:
        return st.st_size
    return blocks * 512


def is_excluded(name: str, path: str, patterns: list) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(path, p) for p in patterns)


def scan(
    root: str,
    *,
    exclude: Optional[list] = None,
    apparent: bool = False,
    one_file_system: bool = False,
    top_files: int = 10,
    min_file_size: int = 0,
    show_progress: bool = False,
    on_file: Optional[Callable[[str, int], None]] = None,
) -> ScanResult:
    """Scan ``root``.

    ``on_file(path, logical_size)`` is called once per regular file (hard links
    after the first are skipped), letting other tools such as the duplicate
    finder reuse the same traversal.
    """
    exclude = exclude or []
    start = time.monotonic()
    root_path = os.path.abspath(root)
    root_dev = os.stat(root_path).st_dev

    root_node = DirNode(root_path, root_path)
    discovered = [root_node]  # parents always appear before their children
    stack = [root_node]

    seen_inodes: set = set()
    hardlinks_skipped = 0
    heap: list = []  # min-heap keeps the N largest files
    ext_stats: dict = defaultdict(lambda: [0, 0])
    errors: list = []
    total_files = 0
    tiebreak = 0
    last_tick = 0.0

    while stack:
        node = stack.pop()
        try:
            iterator = os.scandir(node.path)
        except OSError as e:
            errors.append((node.path, e.strerror or str(e)))
            continue

        with iterator:
            for entry in iterator:
                if exclude and is_excluded(entry.name, entry.path, exclude):
                    continue
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if one_file_system and entry.stat(follow_symlinks=False).st_dev != root_dev:
                            continue
                        child = DirNode(entry.path, entry.name, node)
                        node.children.append(child)
                        discovered.append(child)
                        stack.append(child)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        if st.st_nlink > 1:  # count hard-linked data only once
                            key = (st.st_dev, st.st_ino)
                            if key in seen_inodes:
                                hardlinks_skipped += 1
                                continue
                            seen_inodes.add(key)

                        size = disk_size(st, apparent)
                        node.size += size
                        node.file_count += 1
                        total_files += 1

                        ext = os.path.splitext(entry.name)[1].lower() or "(none)"
                        stats = ext_stats[ext]
                        stats[0] += size
                        stats[1] += 1

                        if on_file:
                            on_file(entry.path, st.st_size)

                        if top_files > 0 and size >= min_file_size:
                            tiebreak += 1
                            item = (size, tiebreak, entry.path)
                            if len(heap) < top_files:
                                heapq.heappush(heap, item)
                            else:
                                heapq.heappushpop(heap, item)
                except OSError as e:
                    errors.append((entry.path, e.strerror or str(e)))

        if show_progress:
            now = time.monotonic()
            if now - last_tick > 0.15:
                last_tick = now
                sys.stderr.write(f"\rScanning... {total_files:,} files")
                sys.stderr.flush()

    if show_progress:
        sys.stderr.write("\r" + " " * 40 + "\r")

    # Bottom-up aggregation: children are always processed before parents.
    for node in reversed(discovered):
        if node.parent:
            node.parent.size += node.size
            node.parent.file_count += node.file_count

    largest = sorted(((s, p) for s, _, p in heap), reverse=True)
    return ScanResult(
        root=root_node,
        top_files=largest,
        by_extension=dict(ext_stats),
        errors=errors,
        hardlinks_skipped=hardlinks_skipped,
        total_files=total_files,
        elapsed=time.monotonic() - start,
    )
