"""Command line interface: analyze | dupes | html."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .duplicates import find_duplicates
from .html_report import write_html
from .report import (export_analysis_json, export_duplicates_json,
                     print_analysis, print_duplicates)
from .scanner import scan
from .utils import Style, parse_size

COMMANDS = ("analyze", "dupes", "html")


def _common() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("path", nargs="?", default=".", help="directory to scan (default: .)")
    p.add_argument("-x", "--exclude", action="append", default=[], metavar="PATTERN",
                   help="glob pattern to skip (repeatable), e.g. node_modules")
    p.add_argument("--one-file-system", action="store_true", help="do not cross filesystem boundaries")
    p.add_argument("--no-color", action="store_true", help="disable colored output")
    p.add_argument("-v", "--verbose", action="store_true", help="list paths that could not be read")
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diskscan",
        description="Disk usage analyzer, duplicate finder and HTML treemap reports.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    common = _common()

    a = sub.add_parser("analyze", parents=[common], help="directory tree, largest files, file types")
    a.add_argument("-d", "--depth", type=int, default=2, help="tree depth to display (default: 2)")
    a.add_argument("-n", "--top", type=int, default=10, help="entries per section (default: 10)")
    a.add_argument("--min-size", type=parse_size, default=0, metavar="SIZE", help="hide entries smaller than SIZE")
    a.add_argument("--apparent", action="store_true", help="file sizes instead of allocated disk blocks")
    a.add_argument("--json", metavar="FILE", help="also write a JSON report")

    d = sub.add_parser("dupes", parents=[common], help="find duplicate files (read-only)")
    d.add_argument("-n", "--top", type=int, default=10, help="groups to display (default: 10)")
    d.add_argument("--min-size", type=parse_size, default=1, metavar="SIZE",
                   help="ignore files smaller than SIZE (default: 1B)")
    d.add_argument("--workers", type=int, default=4, help="parallel hashing threads (default: 4)")
    d.add_argument("--json", metavar="FILE", help="also write a JSON report")

    h = sub.add_parser("html", parents=[common], help="write an interactive treemap report")
    h.add_argument("-o", "--output", default="diskscan-report.html", help="output file")
    h.add_argument("--apparent", action="store_true", help="file sizes instead of allocated disk blocks")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `diskscan ~/Downloads` is shorthand for `diskscan analyze ~/Downloads`
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version"):
        argv.insert(0, "analyze")

    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.path):
        print(f"error: not a directory: {args.path}", file=sys.stderr)
        return 2
    if getattr(args, "depth", 1) < 1 or getattr(args, "top", 1) < 1:
        print("error: --depth and --top must be >= 1", file=sys.stderr)
        return 2

    st = Style(sys.stdout.isatty() and not args.no_color and os.environ.get("NO_COLOR") is None)
    progress = sys.stderr.isatty()
    try:
        if args.command == "analyze":
            result = scan(args.path, exclude=args.exclude, apparent=args.apparent,
                          one_file_system=args.one_file_system, top_files=args.top,
                          min_file_size=args.min_size, show_progress=progress)
            print_analysis(result, st, depth=args.depth, top=args.top, min_size=args.min_size,
                           apparent=args.apparent, verbose=args.verbose)
            if args.json:
                export_analysis_json(result, args.json, args.depth)
                print(f"\nJSON report written to {args.json}")

        elif args.command == "dupes":
            groups, result = find_duplicates(args.path, min_size=args.min_size, exclude=args.exclude,
                                             one_file_system=args.one_file_system,
                                             workers=args.workers, show_progress=progress)
            print_duplicates(groups, result, st, top=args.top, verbose=args.verbose)
            if args.json:
                export_duplicates_json(groups, args.json)
                print(f"JSON report written to {args.json}")

        else:  # html
            result = scan(args.path, exclude=args.exclude, apparent=args.apparent,
                          one_file_system=args.one_file_system, top_files=0, show_progress=progress)
            write_html(result.root, args.output)
            print(f"Report for {result.root.path} ({result.total_files:,} files) written to {args.output}")
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # e.g. `diskscan . | head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
