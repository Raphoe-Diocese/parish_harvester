from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.guard_ok_count import guard, ok_count


class GuardOkCountTests(unittest.TestCase):
    def _write(self, path: Path, ok: int, extra: int = 0) -> None:
        parishes = {
            f"ok{i}": {"outcome": "ok"} for i in range(ok)
        }
        parishes.update(
            {f"stale{i}": {"outcome": "stale"} for i in range(extra)}
        )
        path.write_text(
            json.dumps({"summary": {"ok": ok}, "parishes": parishes}),
            encoding="utf-8",
        )

    def test_ok_count_uses_summary(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            self._write(path, 12, extra=3)
            self.assertEqual(ok_count(path), 12)

    def test_allows_small_drop(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.json"
            after = root / "after.json"
            self._write(before, 100)
            self._write(after, 95)
            allowed, msg = guard(before, after)
            self.assertTrue(allowed)
            self.assertIn("95", msg)

    def test_blocks_drop_over_ten_percent(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.json"
            after = root / "after.json"
            self._write(before, 400)
            self._write(after, 300)
            allowed, msg = guard(before, after)
            self.assertFalse(allowed)
            self.assertIn("dropped too far", msg)
            self.assertIn("floor=360", msg)

    def test_missing_previous_allows(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            after = root / "after.json"
            self._write(after, 10)
            allowed, _msg = guard(root / "missing.json", after)
            self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
