"""The real obs-websocket v5 client against the mock server.

This is the test that keeps the OBS side honest: ``SimpleObsBackend`` uses the
``simpleobsws`` library (a separate implementation) and talks over a real
websocket to a server that speaks the obs-websocket v5 handshake, including
password authentication. No OBS Studio is required.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST_DIR))

from mock_obs import MockOBS
from takedeck.obs import ObsError, SimpleObsBackend


def run(coro):
    return asyncio.run(coro)


async def _wait_for(predicate, timeout=3.0, interval=0.02):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


def test_state_roundtrip_over_websocket():
    async def scenario():
        async with MockOBS() as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                state = await backend.get_state()
                assert state.rec is False
                assert state.count == 3
                assert state.scene == "Standby"
                assert state.idx == 0

                await backend.start_record()
                state = await backend.get_state()
                assert state.rec is True

                await backend.stop_record()
                state = await backend.get_state()
                assert state.rec is False
            finally:
                await backend.close()

    run(scenario())


def test_scene_cycling_uses_reported_order():
    async def scenario():
        async with MockOBS(scenes=["A", "B", "C"]) as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                await backend.set_scene_index(1)
                state = await backend.get_state()
                assert state.scene == "B" and state.idx == 1
                await backend.set_scene_index(0)
                state = await backend.get_state()
                assert state.scene == "A" and state.idx == 0
            finally:
                await backend.close()

    run(scenario())


def test_scene_names_from_obs_order_are_normalised():
    """obs-websocket lists scenes newest-first; the bridge must use UI order."""

    async def scenario():
        async with MockOBS(scenes=["First", "Second", "Third"]) as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                assert backend._scenes == ["First", "Second", "Third"]
            finally:
                await backend.close()

    run(scenario())


def test_mute_requires_and_uses_configured_input():
    async def scenario():
        async with MockOBS() as obs:
            backend = SimpleObsBackend(port=obs.port, mute_input="Mic/Aux")
            await backend.connect()
            try:
                state = await backend.get_state()
                assert state.mute is False
                await backend.toggle_mute()
                state = await backend.get_state()
                assert state.mute is True
            finally:
                await backend.close()

    run(scenario())


def test_mute_without_input_name_raises_a_stable_code():
    async def scenario():
        async with MockOBS() as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                try:
                    await backend.toggle_mute()
                except ObsError as exc:
                    assert exc.code == "NO_MUTE_SRC"
                else:
                    raise AssertionError("expected ObsError")
            finally:
                await backend.close()

    run(scenario())


def test_password_authentication():
    async def scenario():
        async with MockOBS(password="correct horse") as obs:
            backend = SimpleObsBackend(port=obs.port, password="correct horse")
            await backend.connect()
            try:
                state = await backend.get_state()
                assert state.count == 3
            finally:
                await backend.close()

    run(scenario())


def test_wrong_password_is_reported_as_connect_error():
    async def scenario():
        async with MockOBS(password="correct horse") as obs:
            backend = SimpleObsBackend(port=obs.port, password="wrong")
            try:
                await backend.connect()
            except ObsError as exc:
                assert exc.code == "OBS_CONNECT"
            else:
                raise AssertionError("expected ObsError")

    run(scenario())


def test_unknown_scene_request_is_rejected_by_server():
    async def scenario():
        async with MockOBS() as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                data = await backend._request("SetCurrentProgramScene", {"sceneName": "Nope"})
                raise AssertionError(f"expected rejection, got {data}")
            except ObsError as exc:
                assert exc.code == "OBS_REJECTED"
            finally:
                await backend.close()

    run(scenario())


def test_connection_refused_is_a_connect_error():
    async def scenario():
        backend = SimpleObsBackend(port=1, request_timeout=0.4)
        try:
            await backend.connect()
        except ObsError as exc:
            assert exc.code == "OBS_CONNECT"
        else:
            raise AssertionError("expected ObsError")

    run(scenario())


def test_recording_started_in_obs_is_seen_by_the_backend():
    """The controller must follow OBS, not the other way round."""

    async def scenario():
        async with MockOBS() as obs:
            backend = SimpleObsBackend(port=obs.port)
            await backend.connect()
            try:
                await obs.set_recording(True)  # as if the user pressed OBS's own button
                ok = await _wait_for(lambda: True)
                assert ok
                state = await backend.get_state()
                assert state.rec is True
                assert state.elapsed_s >= 0
            finally:
                await backend.close()

    run(scenario())
