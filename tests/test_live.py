#!/usr/bin/env python3
"""Spin up the console against a throwaway PTY command and read output."""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ws_client_handshake(sock: socket.socket, host: str, path: str) -> None:
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("handshake closed")
        data += chunk
    if b"101" not in data.split(b"\r\n", 1)[0]:
        raise RuntimeError(f"handshake failed: {data[:200]!r}")


def ws_send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode()
    mask = b"\x37\xfa\x21\x3d"
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    n = len(payload)
    header = bytearray([0x81])
    if n < 126:
        header.append(0x80 | n)
    else:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    sock.sendall(bytes(header) + mask + masked)


def ws_recv(sock: socket.socket, timeout: float = 3.0) -> tuple[int, bytes]:
    sock.settimeout(timeout)
    hdr = sock.recv(2)
    if len(hdr) < 2:
        raise RuntimeError("short frame")
    opcode = hdr[0] & 0x0F
    length = hdr[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk
    return opcode, payload


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env["ADJUTANT_STATE_DIR"] = td
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"), "--serve", "--bind", "127.0.0.1", "--port", "0"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            line = proc.stdout.readline()
            if "listening" not in line:
                rest = proc.stdout.read() if proc.poll() is not None else ""
                raise SystemExit(f"server failed: {line}{rest}")
            port = int(line.strip().rsplit(":", 1)[-1])
            state = json.loads((Path(td) / "server.json").read_text())
            token = state["token"]
            payload = json.dumps(
                {
                    "cwd": str(ROOT),
                    "argv": ["/bin/bash", "-lc", "printf 'PTY_OK\\n'; exec cat"],
                    "mode": "TEST",
                }
            ).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/session",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                sess = json.loads(resp.read().decode())
            sid = sess["id"]

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as resp:
                html = resp.read().decode()
            assert "ADJUTANT" in html
            assert "/app.js" in html
            assert "btn-llamafile" in html
            assert "llama-frame" in html
            assert "127.0.0.1:8080" in html

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/llamafile", timeout=3) as resp:
                llama = json.loads(resp.read().decode())
            assert "ok" in llama
            assert llama.get("url", "").startswith("http://")

            sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            ws_client_handshake(sock, f"127.0.0.1:{port}", f"/ws/{sid}")
            ws_send_text(sock, json.dumps({"type": "resize", "cols": 80, "rows": 24}))
            got = b""
            deadline = time.time() + 4
            while time.time() < deadline and b"PTY_OK" not in got:
                try:
                    op, payload = ws_recv(sock, timeout=1)
                except socket.timeout:
                    continue
                if op in (1, 2):
                    got += payload
            sock.close()
            if b"PTY_OK" not in got:
                raise SystemExit(f"did not receive PTY output, got {got!r}")
            print("ok live session")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
