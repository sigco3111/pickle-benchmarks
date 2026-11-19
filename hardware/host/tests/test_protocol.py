"""Protocol codec tests (no sockets, no hardware)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from takedeck import protocol


def test_parse_hello():
    msg = protocol.parse_line("D HELLO v=1 fw=1.0.0 sid=0A1B2C3D")
    assert msg is not None
    assert msg.direction == "D"
    assert msg.kind == "HELLO"
    assert msg.get("sid") == "0A1B2C3D"
    assert msg.get_int("v") == 1


def test_parse_cmd():
    msg = protocol.parse_line("D CMD seq=12 id=REC_TOGGLE")
    assert msg is not None and msg.kind == "CMD"
    assert msg.get_int("seq") == 12
    assert msg.get("id") == "REC_TOGGLE"


def test_parse_quoted_scene_with_spaces():
    msg = protocol.parse_line('H STATE rec=1 t=42 scene="Main Camera A" idx=2 cnt=5 mute=0')
    assert msg is not None
    assert msg.get("scene") == "Main Camera A"
    assert msg.get_int("rec") == 1
    assert msg.get_int("t") == 42


def test_parse_escaped_quote_in_scene():
    msg = protocol.parse_line('H STATE scene="He said \\"hi\\"" idx=0')
    assert msg is not None
    assert msg.get("scene") == 'He said "hi"'


def test_parse_rejects_garbage():
    assert protocol.parse_line("") is None
    assert protocol.parse_line("   ") is None
    assert protocol.parse_line("HELLO") is None
    assert protocol.parse_line("Z HELLO v=1") is None


def test_state_roundtrip_of_awkward_scene_name():
    snapshot = protocol.ObsStateSnapshot(
        rec=True, elapsed_s=61, scene='Cam "A" \\ left', idx=1, count=3, mute=True
    )
    line = protocol.state(snapshot)
    assert "\n" not in line
    parsed = protocol.parse_line(line)
    assert parsed is not None
    assert parsed.get("scene") == 'Cam "A" \\ left'
    assert parsed.get_int("rec") == 1
    assert parsed.get_int("t") == 61
    assert parsed.get_int("mute") == 1


def test_format_helpers():
    assert protocol.hello() == "H HELLO v=1"
    assert protocol.pong(1234) == "H PONG t=1234"
    assert protocol.ack(7, True) == "H ACK seq=7 ok=1"
    assert protocol.ack(7, False, "OBS_DOWN") == "H ACK seq=7 ok=0 err=OBS_DOWN"
    assert protocol.err("OBS_DOWN", "no answer") == 'H ERR code=OBS_DOWN text="no answer"'


def test_quote_keeps_simple_tokens_bare():
    assert protocol.quote("Standby") == "Standby"
    assert protocol.quote("Wide Shot") == '"Wide Shot"'
    assert protocol.quote("") == '""'
