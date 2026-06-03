from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


HOST = os.getenv("WAREHOUSE_APP_HOST", "127.0.0.1")
PORT = int(os.getenv("WAREHOUSE_APP_PORT", "8765"))
STARTUP_TIMEOUT = float(os.getenv("WAREHOUSE_STARTUP_TIMEOUT", "20"))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sidecar_command() -> list[str]:
    override = os.getenv("WAREHOUSE_SIDECAR_PATH")
    if override:
        return [override]

    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / "warehouse-sidecar.exe"
        if candidate.exists():
            return [str(candidate)]
        raise FileNotFoundError(
            "Cannot find packaged sidecar. Set WAREHOUSE_SIDECAR_PATH or place "
            "warehouse-sidecar.exe next to the shell executable."
        )

    return [sys.executable, str(project_root() / "desktop" / "python_sidecar" / "serve.py")]


def start_sidecar() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    env.setdefault("DJANGO_DEBUG", "0")
    env.setdefault("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
    env.setdefault("WAREHOUSE_APP_HOST", HOST)
    env.setdefault("WAREHOUSE_APP_PORT", str(PORT))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        sidecar_command(),
        cwd=str(project_root()),
        env=env,
        creationflags=creationflags,
    )


def wait_for_server(process: subprocess.Popen[bytes]) -> str:
    url = f"http://{HOST}:{PORT}/"
    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Sidecar exited early with code {process.returncode}.")

        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return url
        except URLError:
            time.sleep(0.25)

    raise TimeoutError(f"Desktop shell could not reach {url} within {STARTUP_TIMEOUT} seconds.")


def stop_sidecar(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> None:
    import webview

    process = start_sidecar()
    try:
        url = wait_for_server(process)
        webview.create_window("Warehouse Control Desk", url, width=1400, height=950)
        webview.start(debug=False)
    finally:
        stop_sidecar(process)


if __name__ == "__main__":
    main()
