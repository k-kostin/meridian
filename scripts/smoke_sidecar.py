from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    timeout: float = 2.0,
) -> tuple[int, bytes]:
    headers = {}
    if token:
        headers["X-Warehouse-Shutdown-Token"] = token
    req = urllib.request.Request(url, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def wait_for_healthz(base_url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, body = request(f"{base_url}/healthz/")
            if status == 200 and b'"ok"' in body:
                return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"sidecar did not become healthy: {last_error}")


def terminate(process: subprocess.Popen[bytes], base_url: str, token: str) -> None:
    if process.poll() is not None:
        return
    try:
        request(f"{base_url}/shutdown/", method="POST", token=token, timeout=1.5)
    except Exception:
        pass
    try:
        process.wait(timeout=4)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        process.send_signal(signal.SIGKILL)
    process.wait(timeout=4)


def tail_file(path: Path, limit: int = 4000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            content = handle.read()
    except OSError:
        return ""
    return content.decode("utf-8", errors="replace").strip()


def print_log_tails(stdout_log: Path, stderr_log: Path) -> None:
    for label, path in (("stdout", stdout_log), ("stderr", stderr_log)):
        content = tail_file(path)
        if content:
            print(f"\nSidecar {label} log tail ({path}):\n{content}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Meridian Python sidecar.")
    parser.add_argument("--command", nargs="+", required=True, help="Command to start the sidecar.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--keep-data-dir", action="store_true")
    args = parser.parse_args()

    port = free_port()
    token = "smoke-token"
    temp_dir = Path(tempfile.mkdtemp(prefix="meridian-sidecar-smoke-"))
    stdout_log = temp_dir / "sidecar.stdout.log"
    stderr_log = temp_dir / "sidecar.stderr.log"
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "WAREHOUSE_APP_HOST": "127.0.0.1",
        "WAREHOUSE_APP_PORT": str(port),
        "WAREHOUSE_DATA_DIR": str(temp_dir),
        "DJANGO_DB_PATH": str(temp_dir / "db.sqlite3"),
        "DJANGO_DEBUG": "0",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "WAREHOUSE_AUTO_MIGRATE": "1",
        "WAREHOUSE_ENABLE_SHUTDOWN": "1",
        "WAREHOUSE_SHUTDOWN_TOKEN": token,
    }
    stdout_handle = stdout_log.open("wb")
    stderr_handle = stderr_log.open("wb")
    process: subprocess.Popen[bytes] | None = None
    success = False
    try:
        process = subprocess.Popen(args.command, stdout=stdout_handle, stderr=stderr_handle, env=env)
        wait_for_healthz(base_url, args.timeout)
        checks = [
            ("/", b"<html"),
            ("/export/items.xlsx", b"PK"),
        ]
        for path, expected in checks:
            status, body = request(f"{base_url}{path}", timeout=10)
            if status != 200:
                raise RuntimeError(f"{path} returned HTTP {status}")
            if expected not in body[:200]:
                raise RuntimeError(f"{path} response did not look valid")
        print(f"Sidecar smoke OK: {base_url}")
        success = True
        return 0
    finally:
        try:
            if process is not None:
                try:
                    terminate(process, base_url, token)
                except Exception as exc:
                    print(f"Warning: failed to terminate sidecar process: {exc}", file=sys.stderr)
        finally:
            stdout_handle.close()
            stderr_handle.close()
            if not success:
                print_log_tails(stdout_log, stderr_log)
            if not args.keep_data_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            else:
                print(f"Data dir kept: {temp_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
