from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
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


def process_output(process: subprocess.Popen[bytes]) -> str:
    try:
        stdout, stderr = process.communicate(timeout=0.5)
    except subprocess.TimeoutExpired:
        return ""
    output = b"\n".join(part for part in (stdout, stderr) if part)
    return output.decode("utf-8", errors="replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Meridian Python sidecar.")
    parser.add_argument("--command", nargs="+", required=True, help="Command to start the sidecar.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--keep-data-dir", action="store_true")
    args = parser.parse_args()

    port = free_port()
    token = "smoke-token"
    temp_dir = Path(tempfile.mkdtemp(prefix="meridian-sidecar-smoke-"))
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
    process = subprocess.Popen(args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
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
        return 0
    except Exception as exc:
        output = process_output(process)
        if output:
            raise RuntimeError(f"{exc}\n\nSidecar output:\n{output}") from exc
        raise
    finally:
        terminate(process, base_url, token)
        if not args.keep_data_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"Data dir kept: {temp_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
