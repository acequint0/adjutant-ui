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
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

BIND_DEFAULT = os.environ.get("ADJUTANT_SUDO_BIND", os.environ.get("ADJUTANT_BIND", "0.0.0.0"))
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
        host = "127.0.0.1" if state.get("bind") in ("0.0.0.0", "::", "::0", "") else state["bind"]
        url = f"http://{host}:{state['port']}/health"
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


WINDOW_WIDTH = 410
WINDOW_HEIGHT = 340
WINDOW_TITLE = "ADJUTANT // NOPASSWD"

NOLOCK_WHO = "adjutant-sudo"
NOLOCK_WHY = "session no-lock"
DEFAULT_XSET = {"timeout": 600, "cycle": 600, "dpms": False, "blank": True}
_nolock_mu = threading.Lock()


def _force_window_size() -> None:
    import subprocess

    if not shutil.which("wmctrl"):
        return
    for _ in range(50):
        time.sleep(0.12)
        listing = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        for line in listing.stdout.splitlines():
            if "NOPASSWD" not in line:
                continue
            wid = line.split(None, 1)[0]
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-e", f"0,-1,-1,{WINDOW_WIDTH},{WINDOW_HEIGHT}"],
                capture_output=True,
            )
            return


def open_browser(url: str) -> None:
    chrome = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    import subprocess

    if chrome:
        profile = _state_dir() / "chrome-profile"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [
                chrome,
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                f"--app={url}",
                "--new-window",
                f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
                "--window-position=160,80",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        threading.Thread(target=_force_window_size, daemon=True).start()
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
        threading.Thread(target=_force_window_size, daemon=True).start()


def nolock_path() -> Path:
    return _state_dir() / "nolock.json"


def _load_nolock() -> dict[str, Any]:
    p = nolock_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_nolock(data: dict[str, Any]) -> None:
    nolock_path().write_text(json.dumps(data))


def parse_xset(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"timeout": None, "cycle": None, "dpms": None, "blank": None}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("prefer blanking:"):
            token = line.split("prefer blanking:", 1)[1].strip().split()[0].lower()
            out["blank"] = token.startswith("yes")
        if "timeout:" in line and "cycle:" in line:
            nums: list[int] = []
            bits = line.replace("timeout:", " ").replace("cycle:", " ").split()
            for bit in bits:
                if bit.isdigit():
                    nums.append(int(bit))
            if len(nums) >= 2:
                out["timeout"], out["cycle"] = nums[0], nums[1]
        if line.startswith("DPMS is "):
            out["dpms"] = line.lower().rstrip(".").endswith("enabled")
    return out


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
    except OSError:
        return False
    return "--nolock-hold" in cmd


def _read_xset() -> dict[str, Any]:
    xset = shutil.which("xset")
    if not xset:
        return dict(DEFAULT_XSET)
    proc = subprocess.run([xset, "q"], capture_output=True, text=True)
    got = parse_xset(proc.stdout or "")
    if got.get("timeout") is None:
        return dict(DEFAULT_XSET)
    return {
        "timeout": int(got["timeout"]),
        "cycle": int(got["cycle"] if got.get("cycle") is not None else DEFAULT_XSET["cycle"]),
        "dpms": bool(got["dpms"]) if got.get("dpms") is not None else False,
        "blank": bool(got["blank"]) if got.get("blank") is not None else True,
    }


def _snapshot_xset(prev: dict[str, Any] | None = None) -> dict[str, Any]:
    if prev and int(prev.get("timeout") or 0) > 0:
        return {
            "timeout": int(prev["timeout"]),
            "cycle": int(prev.get("cycle") or DEFAULT_XSET["cycle"]),
            "dpms": bool(prev.get("dpms")),
            "blank": bool(prev.get("blank", True)),
        }
    got = _read_xset()
    if int(got.get("timeout") or 0) <= 0:
        return dict(DEFAULT_XSET)
    return got


def _xset_off() -> None:
    xset = shutil.which("xset")
    if not xset:
        return
    for args in (["s", "off"], ["s", "noblank"], ["-dpms"], ["s", "reset"]):
        subprocess.run([xset, *args], capture_output=True)


def _xset_restore(saved: dict[str, Any]) -> None:
    xset = shutil.which("xset")
    if not xset:
        return
    timeout = int(saved.get("timeout") or DEFAULT_XSET["timeout"])
    cycle = int(saved.get("cycle") or DEFAULT_XSET["cycle"])
    subprocess.run([xset, "s", str(timeout), str(cycle)], capture_output=True)
    subprocess.run([xset, "s", "blank" if saved.get("blank", True) else "noblank"], capture_output=True)
    subprocess.run([xset, "+dpms" if saved.get("dpms") else "-dpms"], capture_output=True)


def _inhibit_argv() -> list[str]:
    ll = shutil.which("light-locker-command")
    if ll:
        return [ll, "--inhibit", "--application-name", NOLOCK_WHO, "--reason", NOLOCK_WHY]
    xf = shutil.which("xfce4-screensaver-command")
    if xf:
        return [xf, "--inhibit"]
    gs = shutil.which("gnome-screensaver-command")
    if gs:
        return [gs, "--inhibit"]
    mate = shutil.which("mate-screensaver-command")
    if mate:
        return [mate, "--inhibit"]
    cin = shutil.which("cinnamon-screensaver-command")
    if cin:
        return [cin, "--inhibit"]
    inh = shutil.which("systemd-inhibit")
    if inh:
        return [
            inh,
            "--what=idle:sleep",
            f"--who={NOLOCK_WHO}",
            f"--why={NOLOCK_WHY}",
            "--mode=block",
            "sleep",
            "infinity",
        ]
    return []


def _nolock_hold() -> None:
    child: subprocess.Popen[bytes] | None = None

    def stop(*_args: object) -> None:
        nonlocal child
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except OSError:
                try:
                    child.terminate()
                except OSError:
                    pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    argv = _inhibit_argv()
    while True:
        _xset_off()
        if argv and (child is None or child.poll() is not None):
            child = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        poke = shutil.which("light-locker-command")
        if poke:
            subprocess.run([poke, "--poke"], capture_output=True)
        time.sleep(40)


def _start_holder() -> int:
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--nolock-hold"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=os.environ.copy(),
    )
    return int(proc.pid)


def _stop_holder(pid: int) -> None:
    if not _pid_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(20):
        time.sleep(0.05)
        if not _pid_alive(pid):
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def probe_nolock() -> dict[str, Any]:
    st = _load_nolock()
    pid = int(st.get("pid") or 0)
    alive = _pid_alive(pid)
    enabled = bool(st.get("enabled") and alive)
    out: dict[str, Any] = {"ok": True, "enabled": enabled}
    if pid and not alive and st.get("enabled"):
        out["stale"] = True
    if alive:
        out["pid"] = pid
    return out


def set_nolock(enabled: bool) -> dict[str, Any]:
    with _nolock_mu:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return {"ok": False, "enabled": False, "error": "no graphical session (DISPLAY unset)"}
        st = _load_nolock()
        pid = int(st.get("pid") or 0)
        if enabled:
            saved = _snapshot_xset(st.get("saved") if isinstance(st.get("saved"), dict) else None)
            if _pid_alive(pid):
                _xset_off()
                _save_nolock({"enabled": True, "pid": pid, "saved": saved})
                return {"ok": True, "enabled": True, "pid": pid}
            new_pid = _start_holder()
            _xset_off()
            _save_nolock({"enabled": True, "pid": new_pid, "saved": saved})
            return {"ok": True, "enabled": True, "pid": new_pid}
        if pid:
            _stop_holder(pid)
        saved = st.get("saved") if isinstance(st.get("saved"), dict) else dict(DEFAULT_XSET)
        _xset_restore(saved)
        _save_nolock({"enabled": False, "saved": saved})
        return {"ok": True, "enabled": False}


class Handler(BaseHTTPRequestHandler):
    server_version = "adjutant-sudo/0.2.7"

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
        if path == "/api/nolock":
            self._json(probe_nolock())
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
        if path == "/api/nolock":
            try:
                payload = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self._json(set_nolock(bool(payload.get("enabled"))))
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
    p.add_argument("--nolock-hold", action="store_true")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--bind", default=BIND_DEFAULT)
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    args = p.parse_args()
    if args.nolock_hold:
        _nolock_hold()
        return
    if args.serve:
        serve(args.bind, args.port)
        return
    if args.stop:
        stop_server()
        return
    if args.status:
        state = load_state()
        if state and health_ok(state):
            host = "127.0.0.1" if state.get("bind") in ("0.0.0.0", "::", "::0", "") else state["bind"]
            print(f"online  http://{host}:{state['port']}")
        else:
            print("offline")
        return
    state = load_state()
    if not (state and health_ok(state)):
        state = start_daemon(args.bind, args.port)
    host = "127.0.0.1" if state.get("bind") in ("0.0.0.0", "::", "::0", "") else state["bind"]
    url = f"http://{host}:{state['port']}/"
    if not args.no_browser:
        open_browser(url)
    print("ADJUTANT NOPASSWD")
    print(url)


if __name__ == "__main__":
    main()
