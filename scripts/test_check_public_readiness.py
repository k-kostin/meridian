import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_public_readiness import check_forbidden_paths, check_forbidden_public_text, check_secret_patterns


class PublicReadinessTests(unittest.TestCase):
    def test_forbidden_directory_is_reported_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / ".venv" / "lib" / "package"
            nested.mkdir(parents=True)
            (nested / "one.py").write_text("print('one')", encoding="utf-8")
            (nested / "two.py").write_text("print('two')", encoding="utf-8")

            self.assertEqual(check_forbidden_paths(root), ["forbidden path: .venv"])

    def test_secret_and_text_scans_skip_forbidden_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            forbidden = root / "node_modules" / "package"
            forbidden.mkdir(parents=True)
            (forbidden / "secret.txt").write_text("ghp_" + "1" * 24, encoding="utf-8")
            (forbidden / "internal.md").write_text("Co" + "dex", encoding="utf-8")

            self.assertEqual(check_secret_patterns(root), [])
            self.assertEqual(check_forbidden_public_text(root), [])


if __name__ == "__main__":
    unittest.main()
