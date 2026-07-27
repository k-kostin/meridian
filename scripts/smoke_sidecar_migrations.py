from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_python(arguments: list[str], *, env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            f"Python subprocess failed ({result.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="meridian-migration-smoke-"))
    env = {
        **os.environ,
        "WAREHOUSE_DATA_DIR": str(temp_dir),
        "DJANGO_DB_PATH": str(temp_dir / "db.sqlite3"),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_SECRET_KEY": "migration-smoke-secret",
        "DJANGO_DEBUG": "0",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "WAREHOUSE_AUTO_MIGRATE": "1",
    }
    try:
        run_python(["manage.py", "migrate", "warehouse_app", "0001", "--noinput", "--verbosity", "0"], env=env)
        if list((temp_dir / "backups").glob("*-pre_migration.sqlite3")):
            raise RuntimeError("Pre-migration backup appeared before the sidecar upgrade")

        startup_code = "from desktop.python_sidecar.serve import build_wsgi_application; build_wsgi_application()"
        run_python(["-c", startup_code], env=env)
        backups_after_upgrade = list((temp_dir / "backups").glob("*-pre_migration.sqlite3"))
        if len(backups_after_upgrade) != 1:
            raise RuntimeError(f"Expected one pre-migration backup, found {len(backups_after_upgrade)}")

        run_python(["-c", startup_code], env=env)
        backups_after_restart = list((temp_dir / "backups").glob("*-pre_migration.sqlite3"))
        if backups_after_restart != backups_after_upgrade:
            raise RuntimeError("Current-schema restart created another pre-migration backup")

        print("Sidecar migration smoke OK")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
