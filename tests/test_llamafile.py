#!/usr/bin/env python3
"""Llamafile wrap: health probe, autostart, UI wiring."""
from __future__ import annotations

import http.server
import importlib.util
import os
import signal
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adjutant_server", ROOT / "server.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["adjutant_server"] = mod
spec.loader.exec_module(mod)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def test_probe_online() -> None:
    port = _free_port()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Health)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        os.environ["ADJUTANT_LLAMAFILE"] = f"http://127.0.0.1:{port}"
        got = mod.probe_llamafile()
        assert got["ok"] is True, got
        assert got["url"] == f"http://127.0.0.1:{port}/"
        assert got["status"] == "ok"
    finally:
        httpd.shutdown()
        os.environ.pop("ADJUTANT_LLAMAFILE", None)


def test_probe_offline() -> None:
    os.environ["ADJUTANT_LLAMAFILE"] = "http://127.0.0.1:1"
    try:
        got = mod.probe_llamafile()
        assert got["ok"] is False, got
        assert got["status"] == "offline"
        assert got["url"] == "http://127.0.0.1:1/"
    finally:
        os.environ.pop("ADJUTANT_LLAMAFILE", None)


def test_ui_assets() -> None:
    html = (ROOT / "www" / "index.html").read_text()
    css = (ROOT / "www" / "app.css").read_text()
    js = (ROOT / "www" / "app.js").read_text()
    assert 'id="btn-llamafile"' in html
    assert 'id="llama-frame"' in html
    assert "run.sh" not in html
    assert "html.llama" in css
    assert "--red: #2ee56a" in css
    assert 'method: "POST"' in js
    assert "/api/llamafile" in js
    assert "127.0.0.1:8080" in js


def test_start_already_up() -> None:
    port = _free_port()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Health)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        os.environ["ADJUTANT_LLAMAFILE"] = f"http://127.0.0.1:{port}"
        got = mod.start_llamafile()
        assert got["ok"] is True, got
        assert got["started"] is False
    finally:
        httpd.shutdown()
        os.environ.pop("ADJUTANT_LLAMAFILE", None)


def test_start_missing_script() -> None:
    os.environ["ADJUTANT_LLAMAFILE"] = "http://127.0.0.1:1"
    os.environ["ADJUTANT_LLAMAFILE_ROOT"] = "/tmp/adjutant-no-llamafile-root"
    try:
        got = mod.start_llamafile()
        assert got["ok"] is False, got
        assert got["status"] == "missing"
        assert got["started"] is False
    finally:
        os.environ.pop("ADJUTANT_LLAMAFILE", None)
        os.environ.pop("ADJUTANT_LLAMAFILE_ROOT", None)


def test_start_launches() -> None:
    port = _free_port()
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    script = root / "run.sh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import http.server\n"
        f"PORT = {port}\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        if self.path.rstrip('/') == '/health':\n"
        "            body = b'{\\\"status\\\":\\\"ok\\\"}'\n"
        "            self.send_response(200)\n"
        "            self.send_header('Content-Type', 'application/json')\n"
        "            self.send_header('Content-Length', str(len(body)))\n"
        "            self.end_headers()\n"
        "            self.wfile.write(body)\n"
        "            return\n"
        "        self.send_error(404)\n"
        "    def log_message(self, *args):\n"
        "        return\n"
        "http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    os.environ["ADJUTANT_LLAMAFILE"] = f"http://127.0.0.1:{port}"
    os.environ["ADJUTANT_LLAMAFILE_ROOT"] = str(root)
    os.environ["ADJUTANT_LLAMAFILE_WAIT"] = "8"
    proc_pid = None
    try:
        got = mod.start_llamafile()
        assert got["ok"] is True, got
        assert got["started"] is True, got
        proc_pid = got.get("pid")
        again = mod.start_llamafile()
        assert again["ok"] is True, again
        assert again["started"] is False
    finally:
        if proc_pid:
            try:
                os.kill(proc_pid, signal.SIGTERM)
            except OSError:
                pass
            for _ in range(20):
                try:
                    os.kill(proc_pid, 0)
                except OSError:
                    break
                time.sleep(0.05)
        os.environ.pop("ADJUTANT_LLAMAFILE", None)
        os.environ.pop("ADJUTANT_LLAMAFILE_ROOT", None)
        os.environ.pop("ADJUTANT_LLAMAFILE_WAIT", None)
        td.cleanup()


if __name__ == "__main__":
    for fn in (
        test_probe_online,
        test_probe_offline,
        test_ui_assets,
        test_start_already_up,
        test_start_missing_script,
        test_start_launches,
    ):
        fn()
        print("ok", fn.__name__)
    print("all passed")
