"""Bridge behaviour: handshake, command execution, duplicate suppression,
state push, link supervision and OBS outages. No sockets, no hardware."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fakes import FakeLink, FakeObs, MutableClock
from takedeck import protocol
from takedeck.bridge import AckCache, Bridge

SID = "0A1B2C3D"


def make(obs=None, clock=None, cache=None) -> tuple[Bridge, FakeLink, FakeObs, MutableClock]:
    obs = obs or FakeObs()
    clock = clock or MutableClock()
    link = FakeLink()
    bridge = Bridge(obs, link, ack_cache=cache, clock=clock)
    link.start()
    return bridge, link, obs, clock


def run(coro):
    return asyncio.run(coro)


def test_hello_is_answered_with_state():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 fw=1.0.0 sid={SID}")

    run(scenario())
    assert link.last("H HELLO") == "H HELLO v=1"
    state = link.last("H STATE")
    assert state is not None and "rec=0" in state
    assert bridge.sid == SID
    assert bridge.status()["sessions"] == 1


def test_ping_is_answered_with_pong():
    bridge, link, _, clock = make()
    clock.value = 42.5
    run(bridge.on_device_line("D PING t=100"))
    assert link.last("H PONG") == "H PONG t=42500"


def test_rec_toggle_starts_and_updates_state():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=1 id=REC_TOGGLE")

    run(scenario())
    assert obs.calls.count("start_record") == 1
    assert link.last("H ACK") == "H ACK seq=1 ok=1"
    assert "rec=1" in (link.last("H STATE") or "")


def test_rec_toggle_stops_when_already_recording():
    bridge, link, obs, _ = make()
    obs.rec = True

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=1 id=REC_TOGGLE")

    run(scenario())
    assert obs.calls.count("stop_record") == 1
    assert obs.calls.count("start_record") == 0


def test_duplicate_command_is_not_executed_twice():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=5 id=REC_TOGGLE")
        await bridge.on_device_line("D CMD seq=5 id=REC_TOGGLE")  # retry, ACK lost

    run(scenario())
    assert obs.calls.count("start_record") == 1
    acks = [line for line in link.sent if line.startswith("H ACK")]
    assert len(acks) == 2
    assert acks[0] == "H ACK seq=5 ok=1"
    assert acks[1] == "H ACK seq=5 ok=1"
    assert bridge.status()["duplicates"] == 1


def test_duplicate_suppression_survives_a_bridge_restart(tmp_path):
    cache_path = tmp_path / "acks.json"
    cache = AckCache(str(cache_path))

    bridge, link, obs, _ = make(cache=cache)

    async def first_run():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=3 id=SCENE_NEXT")

    run(first_run())
    assert obs.calls.count("set_scene:1") == 1

    # a new bridge process with the same cache file must not repeat the command
    bridge2, link2, obs2, _ = make(cache=AckCache(str(cache_path)))

    async def second_run():
        await bridge2.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge2.on_device_line("D CMD seq=3 id=SCENE_NEXT")

    run(second_run())
    assert obs2.calls.count("set_scene:1") == 0
    assert link2.last("H ACK") == "H ACK seq=3 ok=1"


def test_sequence_numbers_are_scoped_per_device_session():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=1 id=SCENE_NEXT")
        # device rebooted: same seq number, different session
        await bridge.on_device_line("D HELLO v=1 sid=DEADBEEF")
        await bridge.on_device_line("D CMD seq=1 id=SCENE_NEXT")

    run(scenario())
    assert obs.calls.count("set_scene:1") == 1
    assert obs.calls.count("set_scene:2") == 1
    assert bridge.status()["duplicates"] == 0


def test_scene_next_and_prev_wrap_around():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=1 id=SCENE_PREV")  # 0 -> 2
        await bridge.on_device_line("D CMD seq=2 id=SCENE_NEXT")  # 2 -> 0
        await bridge.on_device_line("D CMD seq=3 id=SCENE_NEXT")  # 0 -> 1

    run(scenario())
    scenes = [call for call in obs.calls if call.startswith("set_scene")]
    assert scenes == ["set_scene:2", "set_scene:0", "set_scene:1"]


def test_mute_without_configured_input_reports_error_and_is_not_cached():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=2 id=MUTE_TOGGLE")
        await bridge.on_device_line("D CMD seq=2 id=MUTE_TOGGLE")  # retry may retry

    run(scenario())
    acks = [line for line in link.sent if line.startswith("H ACK")]
    assert acks[0] == "H ACK seq=2 ok=0 err=NO_MUTE_SRC"
    # a failed command is not cached, so the retry is executed again
    assert len(acks) == 2
    assert bridge.status()["failures"] == 2


def test_unknown_command_is_rejected():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=9 id=SELF_DESTRUCT")

    run(scenario())
    assert link.last("H ACK") == "H ACK seq=9 ok=0 err=UNKNOWN_CMD"


def test_obs_outage_is_announced_and_recovered():
    bridge, link, obs, clock = make()
    obs.connect_failures = 99

    async def outage():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")

    run(outage())
    errs = link.sent_matching("H ERR")
    assert errs and errs[0].startswith("H ERR code=OBS_DOWN")
    assert len(link.sent_matching("H STATE")) == 0

    # OBS comes back: the next state push succeeds
    obs.connect_failures = 0
    clock.advance(30)
    run(bridge.push_state())
    assert len(link.sent_matching("H STATE")) == 1


def test_command_while_obs_down_is_acknowledged_as_failure():
    bridge, link, obs, _ = make()
    obs.connect_failures = 99

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        await bridge.on_device_line("D CMD seq=4 id=REC_TOGGLE")

    run(scenario())
    assert link.last("H ACK") == "H ACK seq=4 ok=0 err=OBS_DOWN"
    assert obs.calls.count("start_record") == 0


def test_state_is_pushed_on_the_configured_period_only():
    bridge, link, obs, clock = make()

    async def scenario():
        await bridge.on_device_line(f"D HELLO v=1 sid={SID}")
        link.sent.clear()
        await bridge.step(timeout=0.0)
        assert len(link.sent_matching("H STATE")) == 0
        clock.advance(0.3)
        await bridge.step(timeout=0.0)
        assert len(link.sent_matching("H STATE")) == 1
        await bridge.step(timeout=0.0)
        assert len(link.sent_matching("H STATE")) == 1

    run(scenario())


def test_garbage_lines_are_ignored():
    bridge, link, obs, _ = make()

    async def scenario():
        await bridge.on_device_line("!! not a protocol line")
        await bridge.on_device_line("H STATE rec=1")  # wrong direction
        await bridge.on_device_line("D CMD seq=x id=")

    run(scenario())
    assert link.sent == []
    assert obs.calls == []


def test_device_note_is_logged_not_answered():
    bridge, link, obs, _ = make()
    run(bridge.on_device_line("D NOTE code=NO_ACK"))
    assert link.sent == []
