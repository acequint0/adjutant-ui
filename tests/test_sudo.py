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
    assert 'id="tab-alpha"' in html
    assert 'id="tab-beta"' in html
    assert 'id="tab-omega"' in html
    assert 'id="term-alpha"' in html
    assert 'id="term-beta"' in html
    assert 'id="term-omega"' in html
    assert 'id="sudo-prompt"' in html
    assert 'id="sudo-app-uninstall"' in html
    assert 'class="switch"' in html
    assert "NOPASSWD" in html
    assert ".switch-track" in css
    assert ".switch-knob" in css
    assert ".foot-link" in css
    assert 'role="switch"' in html
    assert "/api/sudo" in js
    assert "/api/sudo-app" in js
    assert "/api/session/clone" in js
    assert 'TAB_NAMES = ["alpha", "beta", "omega"]' in js
    assert ".chan-tabs" in css
    assert ".chan-tab" in css
    assert 'magenta: "#e22b2b"' in js
    assert "aria-checked" in js
    app_html = (ROOT / "sudo_app" / "www" / "index.html").read_text()
    assert "UNINSTALL NOPASSWD UTILITY" in app_html
    assert 'id="btn-nolock"' in app_html
    assert 'id="nolock-state"' in app_html
    assert "NOLOCK" in app_html
    assert (ROOT / "packaging" / "install-sudo-app.sh").is_file()
    assert (ROOT / "packaging" / "uninstall-sudo-app.sh").is_file()
    assert (ROOT / "packaging" / "sudo-askpass.sh").is_file()
    sudo_js = (ROOT / "sudo_app" / "www" / "app.js").read_text()
    assert "IDENTIFY WITH YOUR PASSWORD" in sudo_js
    assert "/api/nolock" in sudo_js
    assert "SCREEN WILL NOT LOCK FOR THIS SESSION" in sudo_js
    sudo_css = (ROOT / "sudo_app" / "www" / "app.css").read_text()
    assert ".stage-docks" in sudo_css
    sudo_srv = (ROOT / "sudo_app" / "server.py").read_text()
    assert "WINDOW_WIDTH = 410" in sudo_srv
    assert "WINDOW_HEIGHT = 340" in sudo_srv
    assert "--window-size=820,560" not in sudo_srv
    assert 'path == "/api/nolock"' in sudo_srv
    assert "--nolock-hold" in sudo_srv
    helper = (ROOT / "packaging" / "sudo-switch.sh").read_text()
    assert "PASSWD:" in helper
    assert "sudo-switch off" in helper or "off" in helper
    assert "NOPASSWD: ${path} status, ${path} off" in helper
    ctl_src = (ROOT / "server.py").read_text()
    assert '["sudo", "-A", "bash"' in ctl_src
    assert '["sudo", "-k"]' in ctl_src


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


def test_visudo_switch_rule() -> None:
    path = "/usr/local/lib/adjutant-ui/sudo-switch"
    body = (
        "# Managed by Adjutant UI. Do not edit.\n"
        f"ace ALL=(root) NOPASSWD: {path} status, {path} off\n"
        f"ace ALL=(root) PASSWD: {path} on\n"
    )
    with tempfile.NamedTemporaryFile("w", delete=False) as fh:
        fh.write(body)
        frag = fh.name
    try:
        os.chmod(frag, 0o440)
        proc = subprocess.run(["visudo", "-c", "-f", frag], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr or proc.stdout
    finally:
        os.unlink(frag)


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


def test_sudo_app_status_shape() -> None:
    got = mod.sudo_app_status()
    assert got["ok"] is True
    assert "installed" in got
    assert "declined" in got


def test_loopback_host() -> None:
    assert mod.loopback_host("0.0.0.0") == "127.0.0.1"
    assert mod.loopback_host("127.0.0.1") == "127.0.0.1"
    assert mod.loopback_host("192.168.1.5") == "192.168.1.5"


def _load_sudo_app():
    spec = importlib.util.spec_from_file_location("adjutant_sudo_server", ROOT / "sudo_app" / "server.py")
    sudo_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sudo_mod)
    return sudo_mod


def test_parse_xset() -> None:
    sudo_mod = _load_sudo_app()
    sample = (
        "Screen Saver:\n"
        "  prefer blanking:  yes    allow exposures:  yes\n"
        "  timeout:  600    cycle:  600\n"
        "DPMS (Display Power Management Signaling):\n"
        "  Standby: 600    Suspend: 600    Off: 600\n"
        "  DPMS is Disabled\n"
    )
    got = sudo_mod.parse_xset(sample)
    assert got["timeout"] == 600
    assert got["cycle"] == 600
    assert got["dpms"] is False
    assert got["blank"] is True
    off = sudo_mod.parse_xset(
        "  prefer blanking:  no    allow exposures:  yes\n"
        "  timeout:  0    cycle:  600\n"
        "  DPMS is Enabled\n"
    )
    assert off["timeout"] == 0
    assert off["blank"] is False
    assert off["dpms"] is True


def test_nolock_probe_shape() -> None:
    sudo_mod = _load_sudo_app()
    got = sudo_mod.probe_nolock()
    assert got["ok"] is True
    assert "enabled" in got
    assert isinstance(got["enabled"], bool)


def test_pty_env_grok_palette() -> None:
    grok = mod.pty_env(80, 24, grok_palette=True)
    assert grok["TERM"] == "xterm"
    assert "COLORTERM" not in grok
    assert grok["GROK_THEME"] == "groknight"
    shell = mod.pty_env(80, 24, grok_palette=False)
    assert shell["TERM"] == "xterm-256color"
    assert shell["COLORTERM"] == "truecolor"


if __name__ == "__main__":
    tests = [
        test_ui_assets,
        test_nopasswd_line_re,
        test_visudo_fragment,
        test_visudo_switch_rule,
        test_helper_refuses_non_root,
        test_probe_sudo_shape,
        test_sudo_app_status_shape,
        test_pty_env_grok_palette,
        test_loopback_host,
        test_parse_xset,
        test_nolock_probe_shape,
    ]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
