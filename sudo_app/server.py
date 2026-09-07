#!/usr/bin/env python3
"""Standalone Adjutant NOPASSWD desktop utility."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import signal
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

BIND_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 4748
NAME = "adjutant-sudo"

HERE = Path(__file__).resolve().parent
WWW = HERE / "www"


def _state_dir() -> Path:
    env = os.environ.get("ADJUTANT_SUDO_STATE_DIR")
    if env:
        p = Path(env)
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        p = Path(xdg) / NAME if xdg else Path.home() / ".local" / "state" / NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_path() -> Path:
    return _state_dir() / "server.json"


def load_ctl():
    root = Path(os.environ.get("ADJUTANT_UI_ROOT") or "")
    candidates = [
        root / "server.py",
        HERE.parent / "server.py",
        Path.home() / ".local" / "share" / "adjutant-ui" / "server.py",
        Path("/usr/local/share/adjutant-ui/server.py"),
        Path("/usr/share/adjutant-ui/server.py"),
    ]
    for p in candidates:
        if p.is_file():
            spec = importlib.util.spec_from_file_location("adjutant_server", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit("adjutant-sudo: adjutant-ui server.py not found")


CTL = None


def ctl():
    global CTL
    if CTL is None:
        CTL = load_ctl()
    return CTL


def load_state() -> dict[str, Any] | None:
    p = state_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def save_state(data: dict[str, Any]) -> None:
    state_path().write_text(json.dumps(data))


def clear_state() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass


def health_ok(state: dict[str, Any]) -> bool:
    import urllib.request

    try:
        url = f"http://{state['bind']}:{state['port']}/health"
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def open_browser(url: str) -> None:
    chrome = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    import subprocess

    if chrome:
        subprocess.Popen(
            [chrome, f"--app={url}", "--new-window", "--window-size=820,560"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen(
            [opener, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )


class Handler(BaseHTTPRequestHandler):
    server_version = "adjutant-sudo/0.2.4"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = "application/octet-stream"
        if path.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif path.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif path.suffix == ".svg":
            ctype = "image/svg+xml"
        elif path.suffix == ".ttf":
            ctype = "font/ttf"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/health":
            self._json({"ok": True, "pid": os.getpid()})
            return
        if path == "/api/sudo":
            self._json(ctl().probe_sudo())
            return
        if path in ("/", "/index.html"):
            self._file(WWW / "index.html")
            return
        rel = path.lstrip("/")
        extra = Path(os.environ.get("ADJUTANT_UI_ROOT") or "") / "www"
        for root in (WWW, extra):
            if not root.is_dir():
                continue
            cand = (root / rel).resolve()
            try:
                cand.relative_to(root.resolve())
            except ValueError:
                continue
            if cand.is_file():
                self._file(cand)
                return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b"{}"
        if path == "/api/sudo":
            try:
                payload = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self._json(ctl().set_sudo(bool(payload.get("enabled"))))
            return
        if path == "/api/uninstall":
            self._json(uninstall_self())
            threading.Thread(target=_stop_later, daemon=True).start()
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def _stop_later() -> None:
    time.sleep(0.4)
    os.kill(os.getpid(), signal.SIGTERM)


def uninstall_self() -> dict[str, Any]:
    import subprocess

    script = Path(os.environ.get("ADJUTANT_SUDO_UNINSTALL") or "")
    candidates = [
        script,
        HERE / "uninstall-sudo-app.sh",
        Path.home() / ".local" / "share" / "adjutant-ui" / "uninstall-sudo-app.sh",
        Path("/usr/local/share/adjutant-ui/uninstall-sudo-app.sh"),
    ]
    for p in candidates:
        if p and p.is_file():
            subprocess.Popen(
                ["bash", str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {"ok": True}
    return {"ok": False, "error": "uninstall-sudo-app.sh not found"}


def serve(bind: str, port: int) -> None:
    httpd = ThreadingHTTPServer((bind, port), Handler)
    save_state({"pid": os.getpid(), "bind": bind, "port": httpd.server_address[1], "token": secrets.token_urlsafe(12)})
    print(f"adjutant-sudo: listening on http://{bind}:{httpd.server_address[1]}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        clear_state()


def start_daemon(bind: str, port: int) -> dict[str, Any]:
    import subprocess

    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--serve", "--bind", bind, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=os.environ.copy(),
    )
    for _ in range(40):
        time.sleep(0.05)
        state = load_state()
        if state and health_ok(state):
            return state
    raise SystemExit(f"adjutant-sudo: failed to start (pid {proc.pid})")


def stop_server() -> None:
    state = load_state()
    if not state:
        print("adjutant-sudo: offline")
        return
    pid = int(state.get("pid") or 0)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    clear_state()
    print("adjutant-sudo: stopped")


def main() -> None:
    p = argparse.ArgumentParser(prog="adjutant-sudo")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--bind", default=BIND_DEFAULT)
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    args = p.parse_args()
    if args.serve:
        serve(args.bind, args.port)
        return
    if args.stop:
        stop_server()
        return
    if args.status:
        state = load_state()
        if state and health_ok(state):
            print(f"online  http://{state['bind']}:{state['port']}")
        else:
            print("offline")
        return
    state = load_state()
    if not (state and health_ok(state)):
        state = start_daemon(args.bind, args.port)
    url = f"http://{state['bind']}:{state['port']}/"
    if not args.no_browser:
        open_browser(url)
    print("ADJUTANT NOPASSWD")
    print(url)


if __name__ == "__main__":
    main()
