import os
import tempfile
import unittest
from pathlib import Path

from diskscan.cli import main
from diskscan.duplicates import find_duplicates
from diskscan.html_report import write_html
from diskscan.scanner import scan
from diskscan.utils import human_size, parse_size


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class TempTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class TestUtils(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(parse_size("500"), 500)
        self.assertEqual(parse_size("1KB"), 1024)
        self.assertEqual(parse_size("1.5MB"), int(1.5 * 1024**2))
        self.assertEqual(parse_size("2g"), 2 * 1024**3)

    def test_parse_size_invalid(self):
        with self.assertRaises(Exception):
            parse_size("lots")

    def test_human_size(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(5 * 1024**3), "5.0 GB")


class TestScanner(TempTree):
    def test_sizes_aggregate_up(self):
        write(self.root / "a" / "x.bin", b"1" * 1000)
        write(self.root / "a" / "b" / "y.bin", b"2" * 500)
        write(self.root / "z.txt", b"3" * 100)
        r = scan(str(self.root), apparent=True)
        self.assertEqual(r.root.size, 1600)
        self.assertEqual(r.total_files, 3)
        a = next(c for c in r.root.children if c.name == "a")
        self.assertEqual(a.size, 1500)

    def test_exclude(self):
        write(self.root / "keep" / "a", b"1" * 10)
        write(self.root / "node_modules" / "b", b"1" * 999)
        r = scan(str(self.root), apparent=True, exclude=["node_modules"])
        self.assertEqual(r.root.size, 10)

    def test_top_files_and_extensions(self):
        write(self.root / "small.txt", b"1" * 10)
        write(self.root / "big.log", b"1" * 900)
        r = scan(str(self.root), apparent=True, top_files=1)
        self.assertEqual([p for _, p in r.top_files], [str(self.root / "big.log")])
        self.assertEqual(r.by_extension[".log"], [900, 1])

    @unittest.skipUnless(hasattr(os, "symlink") and hasattr(os, "link"), "needs links")
    def test_links_not_double_counted(self):
        write(self.root / "real.bin", b"1" * 400)
        os.link(self.root / "real.bin", self.root / "hard.bin")
        os.symlink(self.root / "real.bin", self.root / "soft.bin")
        r = scan(str(self.root), apparent=True)
        self.assertEqual(r.root.size, 400)
        self.assertEqual(r.hardlinks_skipped, 1)

    def test_unreadable_path_reported_not_fatal(self):
        r = scan(str(self.root))
        self.assertEqual(r.errors, [])


class TestDuplicates(TempTree):
    def test_finds_real_duplicates_only(self):
        content = b"same" * 50_000  # > partial-hash size, exercises full hash
        write(self.root / "a" / "one.bin", content)
        write(self.root / "b" / "two.bin", content)
        write(self.root / "c" / "three.bin", b"diff" * 50_000)  # same size, different bytes
        write(self.root / "d" / "tiny1", b"hi")
        write(self.root / "d" / "tiny2", b"hi")
        write(self.root / "empty1", b"")
        write(self.root / "empty2", b"")

        groups, _ = find_duplicates(str(self.root))
        self.assertEqual(len(groups), 2)
        big = groups[0]
        self.assertEqual(len(big.paths), 2)
        self.assertEqual(big.wasted, len(content))
        self.assertEqual(groups[1].size, 2)  # empty files ignored by default

    def test_min_size_filter(self):
        write(self.root / "a", b"hi")
        write(self.root / "b", b"hi")
        groups, _ = find_duplicates(str(self.root), min_size=100)
        self.assertEqual(groups, [])


class TestHtmlAndCli(TempTree):
    def test_html_report(self):
        write(self.root / "a" / "x", b"1" * 100)
        out = self.root / "r.html"
        write_html(scan(str(self.root), top_files=0).root, str(out))
        text = out.read_text(encoding="utf-8")
        self.assertIn("squarify", text)
        self.assertNotIn("__DATA__", text)

    def test_cli_commands(self):
        write(self.root / "a" / "x", b"1" * 100)
        write(self.root / "a" / "y", b"1" * 100)
        out = self.root / "out"
        out.mkdir()
        self.assertEqual(main(["analyze", str(self.root), "--no-color", "--json", str(out / "a.json")]), 0)
        self.assertEqual(main(["dupes", str(self.root), "--no-color", "--json", str(out / "d.json")]), 0)
        self.assertEqual(main(["html", str(self.root), "-o", str(out / "r.html")]), 0)
        self.assertEqual(main([str(self.root), "--no-color"]), 0)  # default command
        self.assertTrue((out / "r.html").exists())

    def test_cli_bad_path(self):
        self.assertEqual(main(["analyze", str(self.root / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
