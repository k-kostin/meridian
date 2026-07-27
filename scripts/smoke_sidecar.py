from __future__ import annotations

import argparse
import http.cookiejar
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
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


def browser_request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, bytes, str]:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    with opener.open(req, timeout=timeout) as response:
        return response.status, response.read(), response.geturl()


def csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    if not match:
        raise RuntimeError("CSRF token was not found in the form")
    return match.group(1).decode()


def option_value(html: bytes, label: str) -> str:
    pattern = rb'<option value="(\d+)"[^>]*>\s*' + re.escape(label.encode()) + rb"\s*</option>"
    match = re.search(pattern, html)
    if not match:
        raise RuntimeError(f"Option was not found: {label}")
    return match.group(1).decode()


def post_form(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    fields: dict[str, str],
    *,
    form_path: str | None = None,
) -> tuple[bytes, str]:
    status, form_html, _ = browser_request(opener, f"{base_url}{form_path or path}")
    if status != 200:
        raise RuntimeError(f"{path} form returned HTTP {status}")
    payload = {"csrfmiddlewaretoken": csrf_token(form_html), **fields}
    status, response_html, final_url = browser_request(
        opener,
        f"{base_url}{path}",
        method="POST",
        form=payload,
    )
    if status != 200:
        raise RuntimeError(f"{path} POST returned HTTP {status}")
    return response_html, final_url


def run_fresh_profile_workflow(base_url: str) -> None:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    post_form(
        opener,
        base_url,
        "/units/",
        {"code": "pcs", "name": "Smoke Unit", "display_precision": "0"},
    )
    unit_id = option_value(
        browser_request(opener, f"{base_url}/items/")[1],
        "Smoke Unit (pcs)",
    )

    post_form(
        opener,
        base_url,
        "/warehouses/",
        {"code": "smoke", "name": "Smoke Warehouse", "is_active": "on"},
    )
    document_form_html = browser_request(opener, f"{base_url}/documents/new/?type=receipt")[1]
    warehouse_id = option_value(document_form_html, "Smoke Warehouse")

    post_form(
        opener,
        base_url,
        "/items/",
        {
            "sku": "SMOKE-001",
            "name": "Smoke Item",
            "unit": unit_id,
            "category": "",
            "is_active": "on",
            "notes": "Fresh profile smoke test",
        },
    )
    document_form_html = browser_request(opener, f"{base_url}/documents/new/?type=receipt")[1]
    item_id = option_value(document_form_html, "Smoke Item [SMOKE-001]")

    _, document_url = post_form(
        opener,
        base_url,
        "/documents/new/?type=receipt",
        {
            "document_type": "receipt",
            "warehouse": warehouse_id,
            "destination_warehouse": "",
            "operation_date": date.today().isoformat(),
            "comment": "Fresh profile smoke test",
            "lines-TOTAL_FORMS": "6",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-item": item_id,
            "lines-0-quantity": "7",
            "lines-0-comment": "Initial receipt",
        },
    )
    document_path = urllib.parse.urlparse(document_url).path
    if not re.fullmatch(r"/documents/\d+/", document_path):
        raise RuntimeError(f"Document creation did not redirect to a detail page: {document_url}")

    post_form(opener, base_url, f"{document_path}post/", {}, form_path=document_path)
    balances_html = browser_request(opener, f"{base_url}/balances/")[1]
    if b"SMOKE-001" not in balances_html or not re.search(rb">\s*7\s*</td>", balances_html):
        raise RuntimeError("Posted receipt is not visible in current balances")

    export_status, export_body, _ = browser_request(opener, f"{base_url}/export/items.xlsx")
    if export_status != 200 or b"PK" not in export_body[:4]:
        raise RuntimeError("Item Excel export did not return a valid XLSX response")

    backup_html, _ = post_form(opener, base_url, "/backups/create/", {}, form_path="/backups/")
    if "Резервная копия создана".encode() not in backup_html:
        raise RuntimeError("Manual backup was not confirmed in the UI")


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
        "DJANGO_SECRET_KEY": "sidecar-smoke-secret",
        "DJANGO_DEBUG": "0",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "WAREHOUSE_LOCAL_TRUSTED_MODE": "1",
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
        run_fresh_profile_workflow(base_url)

        terminate(process, base_url, token)
        process = None
        pre_migration_backups = list((temp_dir / "backups").glob("*-pre_migration.sqlite3"))
        if pre_migration_backups:
            raise RuntimeError("Fresh database startup unexpectedly created a pre-migration backup")

        process = subprocess.Popen(args.command, stdout=stdout_handle, stderr=stderr_handle, env=env)
        wait_for_healthz(base_url, args.timeout)
        terminate(process, base_url, token)
        process = None
        pre_migration_backups = list((temp_dir / "backups").glob("*-pre_migration.sqlite3"))
        if pre_migration_backups:
            raise RuntimeError("Current-schema restart unexpectedly created a pre-migration backup")

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
