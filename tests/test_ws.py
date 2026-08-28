#!/usr/bin/env python3
import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adjutant_server", ROOT / "server.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["adjutant_server"] = mod
spec.loader.exec_module(mod)


def test_ws_accept():
    # RFC 6455 example key
    got = mod.ws_accept_key("dGhlIHNhbXBsZSBub25jZQ==")
    assert got == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_ws_pack_small():
    frame = mod.ws_pack(b"hi", opcode=1)
    assert frame[0] == 0x81
    assert frame[1] == 2
    assert frame[2:] == b"hi"


def test_ws_pack_medium():
    payload = b"x" * 200
    frame = mod.ws_pack(payload, opcode=2)
    assert frame[0] == 0x82
    assert frame[1] == 126
    assert struct.unpack("!H", frame[2:4])[0] == 200
    assert frame[4:] == payload


def test_agent_path_exists():
    path = mod.agent_path()
    assert path is not None
    assert Path(path).exists()


if __name__ == "__main__":
    tests = [test_ws_accept, test_ws_pack_small, test_ws_pack_medium, test_agent_path_exists]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
