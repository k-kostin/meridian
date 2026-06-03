from __future__ import annotations

import os
import sys
from pathlib import Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = bundle_root()


def default_data_dir() -> Path:
    explicit = os.getenv("WAREHOUSE_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser()

    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))

    return base / "Warehouse Control Desk"


def env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value in {"1", "true", "True", "yes", "on"}


def build_wsgi_application():
    import django

    django.setup()

    if env_flag("WAREHOUSE_AUTO_MIGRATE", default=True):
        from django.core.management import call_command

        call_command("migrate", interactive=False, verbosity=0)

    from config.wsgi import application
    from django.contrib.staticfiles.handlers import StaticFilesHandler

    return StaticFilesHandler(application)


def main() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    os.chdir(PROJECT_ROOT)
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("DJANGO_DEBUG", "0")
    os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("DJANGO_SECRET_KEY", "desktop-local-key-change-me")
    os.environ.setdefault("WAREHOUSE_DATA_DIR", str(data_dir))
    os.environ.setdefault("DJANGO_DB_PATH", str(data_dir / "db.sqlite3"))

    host = os.getenv("WAREHOUSE_APP_HOST", "127.0.0.1")
    port = int(os.getenv("WAREHOUSE_APP_PORT", "8765"))
    threads = int(os.getenv("WAREHOUSE_APP_THREADS", "8"))

    from waitress import serve

    serve(build_wsgi_application(), host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
