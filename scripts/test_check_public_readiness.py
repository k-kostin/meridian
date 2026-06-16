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

    def test_desktop_build_scripts_are_allowed_public_exceptions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            build = root / "desktop" / "build"
            build.mkdir(parents=True)
            (build / "example.bat").write_text("@echo off\n", encoding="utf-8")
            (build / "example.ps1").write_text("Write-Output 'ok'\n", encoding="utf-8")

            self.assertEqual(check_forbidden_paths(root), [])

    def test_agent_plan_markdown_is_allowed_public_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plans = root / "docs" / ("super" + "powers") / "plans"
            plans.mkdir(parents=True)
            (plans / "example.md").write_text("# Example\n", encoding="utf-8")

            self.assertEqual(check_forbidden_paths(root), [])

    def test_non_matching_files_under_allowed_exception_dirs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            desktop_build = root / "desktop" / "build"
            desktop_build.mkdir(parents=True)
            (desktop_build / "example.txt").write_text("not allowed\n", encoding="utf-8")
            (desktop_build / "nested").mkdir()
            (desktop_build / "nested" / "example.bat").write_text("@echo off\n", encoding="utf-8")
            plan_nested = root / "docs" / ("super" + "powers") / "plans" / "nested"
            plan_nested.mkdir(parents=True)
            (plan_nested / "example.md").write_text("# Nested\n", encoding="utf-8")

            self.assertEqual(
                check_forbidden_paths(root),
                [
                    "forbidden path: desktop/build/example.txt",
                    "forbidden path: desktop/build/nested/example.bat",
                    "forbidden path: docs/super" + "powers/plans/nested/example.md",
                ],
            )

    def test_allowed_exception_files_are_scanned_for_forbidden_public_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            build = root / "desktop" / "build"
            plans = root / "docs" / ("super" + "powers") / "plans"
            build.mkdir(parents=True)
            plans.mkdir(parents=True)
            private_path = "/Users/kirillkostin/Projects/" + "warehouse"
            forbidden_tool = "Co" + "dex"
            (build / "example.ps1").write_text(f"Write-Output '{forbidden_tool}'\n", encoding="utf-8")
            (plans / "example.md").write_text(f"{private_path}\n", encoding="utf-8")

            self.assertEqual(
                check_forbidden_public_text(root),
                [
                    f"forbidden public text in desktop/build/example.ps1: {forbidden_tool}",
                    "forbidden public text in docs/super" + f"powers/plans/example.md: {private_path}",
                ],
            )

    def test_allowed_exception_files_are_scanned_for_secret_patterns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            build = root / "desktop" / "build"
            plans = root / "docs" / ("super" + "powers") / "plans"
            build.mkdir(parents=True)
            plans.mkdir(parents=True)
            (build / "example.bat").write_text("set TOKEN=ghp_" + "1" * 24 + "\n", encoding="utf-8")
            (plans / "example.md").write_text("AKIA" + "1" * 16 + "\n", encoding="utf-8")

            self.assertEqual(
                check_secret_patterns(root),
                [
                    "secret-like pattern in desktop/build/example.bat: ghp_[A-Za-z0-9_]{20,}",
                    "secret-like pattern in docs/super" + "powers/plans/example.md: AKIA[0-9A-Z]{16}",
                ],
            )


if __name__ == "__main__":
    unittest.main()
