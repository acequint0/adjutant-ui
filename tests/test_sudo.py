#!/usr/bin/env python3
"""Passwordless sudo toggle: sudoers fragments, helper, UI wiring."""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adjutant_server", ROOT / "server.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["adjutant_server"] = mod
spec.loader.exec_module(mod)


def test_ui_assets() -> None:
    html = (ROOT / "www" / "index.html").read_text()
    css = (ROOT / "www" / "app.css").read_text()
    js = (ROOT / "www" / "app.js").read_text()
    assert 'id="btn-sudo"' in html
    assert 'class="switch"' in html
    assert "NOPASSWD" in html
    assert ".switch-track" in css
    assert ".switch-knob" in css
    assert 'role="switch"' in html
    assert "/api/sudo" in js
    assert "aria-checked" in js


def test_nopasswd_line_re() -> None:
    pat = re.compile(mod.NOPASSWD_ALL_RE)
    assert pat.match("ace ALL=(ALL:ALL) NOPASSWD: ALL")
    assert pat.match("ace ALL=(ALL) NOPASSWD: ALL")
    assert not pat.match("ace ALL=(ALL:ALL) ALL")
    assert not pat.match("ALL ALL = NOPASSWD:/usr/bin/mint-refresh-cache")


def test_visudo_fragment() -> None:
    body = "# Managed by Adjutant UI. Do not edit.\nace ALL=(ALL:ALL) NOPASSWD: ALL\n"
    with tempfile.NamedTemporaryFile("w", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        os.chmod(path, 0o440)
        proc = subprocess.run(["visudo", "-c", "-f", path], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr or proc.stdout
    finally:
        os.unlink(path)


def test_helper_refuses_non_root() -> None:
    script = ROOT / "packaging" / "sudo-switch.sh"
    proc = subprocess.run(["bash", str(script), "status"], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "root required" in (proc.stderr + proc.stdout)


def test_probe_sudo_shape() -> None:
    got = mod.probe_sudo()
    assert got["ok"] is True
    assert "enabled" in got
    assert isinstance(got["enabled"], bool)


if __name__ == "__main__":
    tests = [
        test_ui_assets,
        test_nopasswd_line_re,
        test_visudo_fragment,
        test_helper_refuses_non_root,
        test_probe_sudo_shape,
    ]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
