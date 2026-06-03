import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_changed import command_plan


class CommandPlanTests(unittest.TestCase):
    def test_no_paths_runs_django_check(self):
        commands = command_plan([], python_cmd="python")
        self.assertEqual(commands, [["python", "manage.py", "check"]])

    def test_docs_only_has_no_commands(self):
        commands = command_plan(["README.md", "docs/STATUS.md"], python_cmd="python")
        self.assertEqual(commands, [])

    def test_python_domain_file_runs_compile_check_and_tests(self):
        commands = command_plan(["warehouse_app/services.py"], python_cmd="python")
        self.assertEqual(
            commands,
            [
                ["python", "-m", "py_compile", "warehouse_app/services.py"],
                ["python", "manage.py", "check"],
                ["python", "manage.py", "test"],
            ],
        )

    def test_manage_py_runs_compile_check_and_tests(self):
        commands = command_plan(["manage.py"], python_cmd="python")
        self.assertEqual(
            commands,
            [
                ["python", "-m", "py_compile", "manage.py"],
                ["python", "manage.py", "check"],
                ["python", "manage.py", "test"],
            ],
        )

    def test_template_change_runs_check_and_tests(self):
        commands = command_plan(["templates/base.html"], python_cmd="python")
        self.assertEqual(
            commands,
            [
                ["python", "manage.py", "check"],
                ["python", "manage.py", "test"],
            ],
        )

    def test_full_runs_check_and_tests(self):
        commands = command_plan(["README.md"], python_cmd="python", full=True)
        self.assertEqual(
            commands,
            [
                ["python", "manage.py", "check"],
                ["python", "manage.py", "test"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
