#!/usr/bin/env python3
"""Adjutant command console: localhost web terminal around Grok Build."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import pty
import secrets
import shutil
import signal
import struct
import fcntl
import termios
import threading
import time
import urllib.parse
from http import HTTPStatus
from pathlib import Path
from typing import Any

BIND_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 4747
UI_NAME = "adjutant-ui"
LLAMAFILE_DEFAULT = "http://127.0.0.1:8080"
LLAMAFILE_WAIT_DEFAULT = 90
_llamafile_start_lock = threading.Lock()

HERE = Path(__file__).resolve().parent
WWW = HERE / "www"


def _state_dir() -> Path:
    env = os.environ.get("ADJUTANT_STATE_DIR")
    if env:
        p = Path(env)
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        if xdg:
            p = Path(xdg) / UI_NAME
        else:
            p = Path.home() / ".local" / "state" / UI_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_path() -> Path:
    return _state_dir() / "server.json"


def log_path() -> Path:
    return _state_dir() / "server.log"


def clip_path() -> Path:
    env = os.environ.get("ADJUTANT_ONLINE_CLIP")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "adjutant" / "adjutant-online.wav"


def agent_path() -> str | None:
    env = os.environ.get("ADJUTANT_AGENT")
    if env:
        return env
    bundled = Path.home() / ".grok" / "bin" / "agent"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    grok = Path.home() / ".grok" / "bin" / "grok"
    if grok.is_file() and os.access(grok, os.X_OK):
        return str(grok)
    return shutil.which("agent") or shutil.which("grok")


def has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def load_state() -> dict[str, Any] | None:
    p = state_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    pid = data.get("pid")
    if not isinstance(pid, int):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return data


def save_state(data: dict[str, Any]) -> None:
    p = state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(p)


def clear_state() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass


def play_clip() -> None:
    wav = clip_path()
    if not wav.is_file():
        return
    for cmd in (
        ["paplay", str(wav)],
        ["aplay", "-q", str(wav)],
    ):
        if shutil.which(cmd[0]):
            try:
                os.spawnvp(os.P_NOWAIT, cmd[0], cmd)
            except OSError:
                pass
            return


def run_tui(argv: list[str]) -> None:
    play_clip()
    agent = agent_path()
    if not agent:
        raise SystemExit("adjutant: grok build is not installed (agent/grok not found)")
    os.execv(agent, [agent, *argv])


def open_browser(url: str) -> None:
    chrome = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome:
        subprocess_detach(
            [
                chrome,
                f"--app={url}",
                "--new-window",
                "--autoplay-policy=no-user-gesture-required",
                "--window-size=1440,900",
            ]
        )
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess_detach([opener, url])
        return
    print("adjutant: open this URL in a browser:", url)


def subprocess_detach(cmd: list[str]) -> None:
    import subprocess

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


# --- WebSocket -------------------------------------------------------------

WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 8, 9, 10


def ws_accept_key(key: str) -> str:
    digest = hashlib.sha1(key.encode("ascii") + WS_MAGIC).digest()
    return base64.b64encode(digest).decode("ascii")


def ws_pack(payload: bytes, opcode: int = OP_BIN) -> bytes:
    n = len(payload)
    header = bytearray()
    header.append(0x80 | opcode)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    return bytes(header) + payload


async def ws_read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    hdr = await reader.readexactly(2)
    opcode = hdr[0] & 0x0F
    masked = bool(hdr[1] & 0x80)
    length = hdr[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length) if length else b""
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


# --- PTY -------------------------------------------------------------------

def set_winsize(fd: int, rows: int, cols: int) -> None:
    rows = max(2, min(rows, 500))
    cols = max(2, min(cols, 1000))
    packed = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)


def spawn_pty(argv: list[str], cwd: str, cols: int, rows: int) -> tuple[int, int]:
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(cwd)
        except OSError:
            pass
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["COLUMNS"] = str(cols)
        env["LINES"] = str(rows)
        try:
            os.execvpe(argv[0], argv, env)
        except OSError as exc:
            try:
                os.write(2, f"adjutant: failed to exec {argv[0]}: {exc}\n".encode())
            except OSError:
                pass
            os._exit(127)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    set_winsize(fd, rows, cols)
    return pid, fd


# --- HTTP / server ---------------------------------------------------------

class Session:
    def __init__(self, sid: str, cwd: str, argv: list[str], mode: str) -> None:
        self.id = sid
        self.cwd = cwd
        self.argv = argv
        self.mode = mode
        self.created = time.time()
        self.pid: int | None = None
        self.fd: int | None = None
        self.started = False
        self.ready = asyncio.Event()


class ConsoleServer:
    def __init__(self, bind: str, port: int, token: str) -> None:
        self.bind = bind
        self.port = port
        self.token = token
        self.sessions: dict[str, Session] = {}
        self._server: asyncio.base_events.Server | None = None

    def create_session(self, cwd: str, argv: list[str], mode: str) -> Session:
        sid = secrets.token_urlsafe(12)
        sess = Session(sid, cwd, argv, mode)
        self.sessions[sid] = sess
        return sess

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, host=self.bind, port=self.port
        )
        sockets = self._server.sockets or []
        if sockets:
            self.port = sockets[0].getsockname()[1]
        save_state(
            {
                "pid": os.getpid(),
                "port": self.port,
                "bind": self.bind,
                "token": self.token,
            }
        )

    async def serve_forever(self) -> None:
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=15)
            if not line:
                writer.close()
                return
            parts = line.decode("iso-8859-1").strip().split()
            if len(parts) < 2:
                await self._send_status(writer, HTTPStatus.BAD_REQUEST)
                return
            method, raw_path = parts[0], parts[1]
            headers: dict[str, str] = {}
            while True:
                raw = await reader.readline()
                if raw in (b"\r\n", b"\n", b""):
                    break
                if b":" not in raw:
                    continue
                k, v = raw.decode("iso-8859-1").split(":", 1)
                headers[k.strip().lower()] = v.strip()
            parsed = urllib.parse.urlparse(raw_path)
            path = urllib.parse.unquote(parsed.path)
            query = urllib.parse.parse_qs(parsed.query)
            if (
                headers.get("upgrade", "").lower() == "websocket"
                and path.startswith("/ws/")
            ):
                await self._websocket(reader, writer, headers, path)
                return
            body = b""
            n = int(headers.get("content-length") or 0)
            if n:
                body = await reader.readexactly(n)
            await self._http(writer, method, path, query, headers, body)
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _http(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        path: str,
        query: dict[str, list[str]],
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        if method == "GET" and path == "/health":
            await self._send_json(writer, {"ok": True, "pid": os.getpid()})
            return
        if method == "GET" and path == "/api/meta":
            await self._send_json(
                writer,
                {
                    "ok": True,
                    "cwd": os.getcwd(),
                    "has_sound": clip_path().is_file(),
                },
            )
            return
        if method == "GET" and path == "/api/llamafile":
            await self._send_json(writer, await asyncio.to_thread(probe_llamafile))
            return
        if method == "POST" and path == "/api/llamafile":
            await self._send_json(writer, await asyncio.to_thread(start_llamafile))
            return
        if method == "POST" and path == "/api/session":
            if not self._authorized(headers, query):
                await self._send_status(writer, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                await self._send_status(writer, HTTPStatus.BAD_REQUEST)
                return
            cwd = payload.get("cwd") or os.getcwd()
            argv = payload.get("argv")
            mode = payload.get("mode") or "AGENT"
            if not isinstance(argv, list) or not argv:
                await self._send_status(writer, HTTPStatus.BAD_REQUEST)
                return
            argv = [str(x) for x in argv]
            sess = self.create_session(str(cwd), argv, str(mode))
            url = f"http://{self.bind}:{self.port}/?s={sess.id}"
            await self._send_json(writer, {"id": sess.id, "url": url})
            return
        if method == "GET" and path == "/sound/online.wav":
            wav = clip_path()
            if wav.is_file():
                await self._send_file(writer, wav)
            else:
                await self._send_status(writer, HTTPStatus.NOT_FOUND)
            return
        if method != "GET":
            await self._send_status(writer, HTTPStatus.METHOD_NOT_ALLOWED)
            return
        await self._static(writer, path)

    def _authorized(self, headers: dict[str, str], query: dict[str, list[str]]) -> bool:
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and auth.split(" ", 1)[1] == self.token:
            return True
        got = (query.get("k") or [None])[0]
        return got == self.token

    async def _static(self, writer: asyncio.StreamWriter, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = (WWW / rel).resolve()
        try:
            target.relative_to(WWW.resolve())
        except ValueError:
            await self._send_status(writer, HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            await self._send_status(writer, HTTPStatus.NOT_FOUND)
            return
        await self._send_file(writer, target)

    async def _send_file(self, writer: asyncio.StreamWriter, path: Path) -> None:
        data = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        extra = {
            ".js": "application/javascript",
            ".mjs": "application/javascript",
            ".css": "text/css",
            ".html": "text/html; charset=utf-8",
            ".svg": "image/svg+xml",
            ".wav": "audio/wav",
            ".ttf": "font/ttf",
            ".woff2": "font/woff2",
        }
        content_type = extra.get(path.suffix, mime or "application/octet-stream")
        await self._send(
            writer, HTTPStatus.OK, data, {"Content-Type": content_type}
        )

    async def _send_json(self, writer: asyncio.StreamWriter, obj: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(obj).encode()
        await self._send(
            writer,
            status,
            data,
            {"Content-Type": "application/json"},
        )

    async def _send_status(self, writer: asyncio.StreamWriter, status: HTTPStatus) -> None:
        body = f"{status.value} {status.phrase}\n".encode()
        await self._send(writer, status, body, {"Content-Type": "text/plain"})

    async def _send(
        self,
        writer: asyncio.StreamWriter,
        status: HTTPStatus,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        out = [
            f"HTTP/1.1 {status.value} {status.phrase}",
            f"Content-Length: {len(body)}",
            "Connection: close",
        ]
        for k, v in headers.items():
            out.append(f"{k}: {v}")
        writer.write(("\r\n".join(out) + "\r\n\r\n").encode("ascii") + body)
        await writer.drain()

    async def _websocket(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        headers: dict[str, str],
        path: str,
    ) -> None:
        sid = path.rsplit("/", 1)[-1]
        sess = self.sessions.get(sid)
        key = headers.get("sec-websocket-key")
        if not sess or not key:
            await self._send_status(writer, HTTPStatus.NOT_FOUND)
            return
        accept = ws_accept_key(key)
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            ).encode("ascii")
        )
        await writer.drain()

        write_lock = asyncio.Lock()

        async def send(payload: bytes, opcode: int = OP_BIN) -> None:
            async with write_lock:
                try:
                    writer.write(ws_pack(payload, opcode))
                    await writer.drain()
                except (ConnectionError, RuntimeError):
                    pass

        cols, rows = 120, 36

        async def pump_pty() -> None:
            assert sess.fd is not None
            loop = asyncio.get_running_loop()
            q: asyncio.Queue[bytes | None] = asyncio.Queue()

            def _on_read() -> None:
                try:
                    chunk = os.read(sess.fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    loop.remove_reader(sess.fd)
                    q.put_nowait(None)
                    return
                q.put_nowait(chunk)

            loop.add_reader(sess.fd, _on_read)
            try:
                while True:
                    chunk = await q.get()
                    if chunk is None:
                        break
                    await send(chunk, OP_BIN)
            finally:
                try:
                    loop.remove_reader(sess.fd)
                except Exception:
                    pass

        async def pump_ws() -> None:
            nonlocal cols, rows
            while True:
                opcode, payload = await ws_read_frame(reader)
                if opcode in (OP_CLOSE,):
                    await send(b"", OP_CLOSE)
                    break
                if opcode == OP_PING:
                    await send(payload, OP_PONG)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode in (OP_TEXT, OP_BIN) and payload.startswith(b"{") and sess.fd is not None:
                    try:
                        msg = json.loads(payload.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        msg = None
                    if isinstance(msg, dict) and msg.get("type") == "resize":
                        cols = int(msg.get("cols") or cols)
                        rows = int(msg.get("rows") or rows)
                        try:
                            set_winsize(sess.fd, rows, cols)
                            if sess.pid:
                                os.kill(sess.pid, signal.SIGWINCH)
                        except OSError:
                            pass
                        continue
                if not sess.started:
                    if opcode in (OP_TEXT, OP_BIN) and payload.startswith(b"{"):
                        try:
                            msg = json.loads(payload.decode())
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            msg = None
                        if isinstance(msg, dict) and msg.get("type") == "resize":
                            cols = int(msg.get("cols") or cols)
                            rows = int(msg.get("rows") or rows)
                            self._spawn(sess, cols, rows)
                            await send(
                                json.dumps(
                                    {
                                        "type": "meta",
                                        "cwd": sess.cwd,
                                        "mode": sess.mode,
                                    }
                                ).encode(),
                                OP_TEXT,
                            )
                            continue
                    self._spawn(sess, cols, rows)
                if sess.fd is not None and payload:
                    try:
                        os.write(sess.fd, payload)
                    except OSError:
                        break

        tasks = [
            asyncio.create_task(pump_ws()),
            asyncio.create_task(self._pty_after_start(sess, pump_pty)),
        ]
        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            for task in done:
                exc = task.exception() if not task.cancelled() else None
                if exc and not isinstance(
                    exc, (asyncio.IncompleteReadError, ConnectionError)
                ):
                    pass
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            try:
                await send(
                    json.dumps({"type": "exit", "code": self._wait_code(sess)}).encode(),
                    OP_TEXT,
                )
            except Exception:
                pass
            self._reap(sess)

    async def _pty_after_start(self, sess: Session, pump_pty) -> None:
        try:
            await asyncio.wait_for(sess.ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            return
        await pump_pty()

    def _spawn(self, sess: Session, cols: int, rows: int) -> None:
        if sess.started:
            return
        pid, fd = spawn_pty(sess.argv, sess.cwd, cols, rows)
        sess.pid = pid
        sess.fd = fd
        sess.started = True
        sess.ready.set()

    def _wait_code(self, sess: Session) -> int | None:
        if sess.pid is None:
            return None
        try:
            _, status = os.waitpid(sess.pid, os.WNOHANG)
            if status == 0:
                return None
            return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            return None

    def _reap(self, sess: Session) -> None:
        if sess.fd is not None:
            try:
                os.close(sess.fd)
            except OSError:
                pass
            sess.fd = None
        if sess.pid is not None:
            try:
                os.kill(sess.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                os.waitpid(sess.pid, os.WNOHANG)
            except ChildProcessError:
                pass
            sess.pid = None
        self.sessions.pop(sess.id, None)


def llamafile_base() -> str:
    return (os.environ.get("ADJUTANT_LLAMAFILE") or LLAMAFILE_DEFAULT).rstrip("/")


def llamafile_root() -> Path:
    env = os.environ.get("ADJUTANT_LLAMAFILE_ROOT")
    if env:
        return Path(env)
    return Path.home() / "llamafile-pentest"


def llamafile_wait_secs() -> float:
    raw = os.environ.get("ADJUTANT_LLAMAFILE_WAIT")
    if not raw:
        return float(LLAMAFILE_WAIT_DEFAULT)
    try:
        return max(3.0, float(raw))
    except ValueError:
        return float(LLAMAFILE_WAIT_DEFAULT)


def probe_llamafile() -> dict[str, Any]:
    import urllib.request

    base = llamafile_base()
    url = base + "/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
        ok = status == 200
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict) and payload.get("status") and payload["status"] != "ok":
            ok = False
        return {"ok": ok, "url": base + "/", "status": payload.get("status") if isinstance(payload, dict) else None}
    except Exception:
        return {"ok": False, "url": base + "/", "status": "offline"}


def start_llamafile() -> dict[str, Any]:
    import subprocess

    probe = probe_llamafile()
    if probe.get("ok"):
        probe["started"] = False
        return probe

    with _llamafile_start_lock:
        probe = probe_llamafile()
        if probe.get("ok"):
            probe["started"] = False
            return probe

        root = llamafile_root()
        script = root / "run.sh"
        if not script.is_file():
            return {
                "ok": False,
                "url": llamafile_base() + "/",
                "status": "missing",
                "error": f"llamafile launcher not found: {script}",
                "started": False,
            }
        if not os.access(script, os.X_OK):
            return {
                "ok": False,
                "url": llamafile_base() + "/",
                "status": "missing",
                "error": f"llamafile launcher is not executable: {script}",
                "started": False,
            }

        parsed = urllib.parse.urlparse(llamafile_base())
        env = os.environ.copy()
        env["HOST"] = parsed.hostname or "127.0.0.1"
        env["PORT"] = str(parsed.port or 8080)

        log_path_lf = root / "logs" / "llamafile.log"
        log_path_lf.parent.mkdir(parents=True, exist_ok=True)
        log_f = log_path_lf.open("a")
        try:
            proc = subprocess.Popen(
                [str(script)],
                cwd=str(root),
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            log_f.close()
            return {
                "ok": False,
                "url": llamafile_base() + "/",
                "status": "error",
                "error": str(exc),
                "started": False,
            }
        finally:
            try:
                log_f.close()
            except OSError:
                pass

        deadline = time.time() + llamafile_wait_secs()
        while time.time() < deadline:
            if proc.poll() is not None:
                tail = ""
                try:
                    tail = log_path_lf.read_text(errors="replace")[-400:]
                except OSError:
                    pass
                return {
                    "ok": False,
                    "url": llamafile_base() + "/",
                    "status": "exited",
                    "error": (tail.strip() or f"llamafile exited {proc.returncode}"),
                    "started": False,
                    "pid": proc.pid,
                }
            probe = probe_llamafile()
            if probe.get("ok"):
                probe["started"] = True
                probe["pid"] = proc.pid
                return probe
            time.sleep(0.4)

        return {
            "ok": False,
            "url": llamafile_base() + "/",
            "status": "timeout",
            "error": "llamafile did not become ready in time",
            "started": False,
            "pid": proc.pid,
        }


def post_session(state: dict[str, Any], cwd: str, argv: list[str], mode: str) -> dict[str, Any]:
    import urllib.request

    url = f"http://{state['bind']}:{state['port']}/api/session"
    req = urllib.request.Request(
        url,
        data=json.dumps({"cwd": cwd, "argv": argv, "mode": mode}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {state['token']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode())


def health_ok(state: dict[str, Any]) -> bool:
    import urllib.request

    url = f"http://{state['bind']}:{state['port']}/health"
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def stop_server() -> None:
    state = load_state()
    if not state:
        print("adjutant: console is not running")
        return
    pid = state["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        clear_state()
        print("adjutant: stale process cleared")
        return
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.05)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    clear_state()
    print("adjutant: console stopped")


def start_daemon(bind: str, port: int) -> dict[str, Any]:
    import subprocess

    log = log_path().open("a")
    proc = subprocess.Popen(
        [sys_executable(), str(Path(__file__).resolve()), "--serve", "--bind", bind, "--port", str(port)],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    for _ in range(50):
        time.sleep(0.05)
        state = load_state()
        if state and state.get("pid") == proc.pid and health_ok(state):
            return state
        if proc.poll() is not None:
            break
    raise SystemExit(
        f"adjutant: failed to start console (see {log_path()})"
    )


def sys_executable() -> str:
    import sys

    return sys.executable


def ensure_server(bind: str, port: int) -> dict[str, Any]:
    state = load_state()
    if state and health_ok(state):
        return state
    if state:
        clear_state()
    return start_daemon(bind, port)


def serve_main(bind: str, port: int) -> None:
    token = secrets.token_urlsafe(18)
    server = ConsoleServer(bind, port, token)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(*_args: object) -> None:
        for sess in list(server.sessions.values()):
            server._reap(sess)
        loop.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    loop.run_until_complete(server.start())
    print(f"adjutant: listening on http://{server.bind}:{server.port}", flush=True)
    try:
        loop.run_until_complete(server.serve_forever())
    except KeyboardInterrupt:
        pass
    finally:
        for sess in list(server.sessions.values()):
            server._reap(sess)
        clear_state()


def build_argv(shell: bool, agent_args: list[str]) -> tuple[list[str], str]:
    if shell:
        sh = os.environ.get("SHELL") or "/bin/bash"
        return [sh], "SHELL"
    agent = agent_path()
    if not agent:
        raise SystemExit(
            "adjutant: Grok Build is not installed.\n"
            "Install grok first, then re-run adjutant.\n"
            "Expected ~/.grok/bin/agent or 'agent' on PATH."
        )
    return [agent, *agent_args], "AGENT"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="adjutant",
        description="Launch Grok Build inside the Adjutant web console.",
    )
    p.add_argument("--tui", action="store_true", help="classic terminal, no web UI")
    p.add_argument("--web", action="store_true", help="force the web console")
    p.add_argument("--shell", action="store_true", help="open a shell instead of grok")
    p.add_argument("--stop", action="store_true", help="stop the background console")
    p.add_argument("--status", action="store_true", help="print console status")
    p.add_argument("--version", action="store_true", help="print version and exit")
    p.add_argument("--no-browser", action="store_true", help="do not open a window")
    p.add_argument(
        "--imagine",
        action="store_true",
        help="open grok.com/imagine (official 4-up picker) instead of the console",
    )
    p.add_argument(
        "--grok-web",
        action="store_true",
        help="open grok.com chat instead of the console",
    )
    p.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--bind", default=BIND_DEFAULT)
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    p.add_argument(
        "agent_args",
        nargs=argparse.REMAINDER,
        help="arguments forwarded to grok/agent",
    )
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    rest = list(args.agent_args or [])
    if rest[:1] == ["--"]:
        rest = rest[1:]

    if args.serve:
        serve_main(args.bind, args.port)
        return
    if args.version:
        ver_path = HERE / "VERSION"
        ver = ver_path.read_text().strip() if ver_path.is_file() else "0.2.2"
        print(f"adjutant-ui {ver}")
        return
    if args.stop:
        stop_server()
        return
    if args.status:
        state = load_state()
        if state and health_ok(state):
            print(f"online  pid={state['pid']}  http://{state['bind']}:{state['port']}")
        else:
            print("offline")
        return
    if args.imagine:
        url = "https://grok.com/imagine"
        open_browser(url)
        print("IMAGINE  " + url)
        return
    if args.grok_web:
        url = "https://grok.com"
        open_browser(url)
        print("GROK  " + url)
        return

    use_tui = args.tui or (not has_display() and not args.web)
    if use_tui:
        if args.shell:
            play_clip()
            sh = os.environ.get("SHELL") or "/bin/bash"
            os.execvp(sh, [sh])
        run_tui(rest)
        return

    argv, mode = build_argv(args.shell, rest)
    state = ensure_server(args.bind, args.port)
    sess = post_session(state, os.getcwd(), argv, mode)
    url = sess["url"]
    if not args.no_browser:
        open_browser(url)
    print(f"ADJUTANT ONLINE")
    print(url)
    print("adjutant --stop   to shut down the console")


if __name__ == "__main__":
    main()
