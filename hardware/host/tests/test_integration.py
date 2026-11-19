"""End to end test: firmware logic <-> bridge <-> obs-websocket server.

Nothing here is a stand-in for the firmware: ``firmware/test/host_sim`` runs
the same app.c/keys.c/protocol.c/ui.c that the RP2040 image is built from, the
bridge is the production Bridge, and the OBS side is the real simpleobsws
client talking obs-websocket v5 to the mock server.

What this proves: handshake, a key press travelling to OBS, the LED following
the real OBS recording state, scene and mute commands, duplicate suppression,
and what happens when OBS disappears and comes back.
What it cannot prove: USB CDC behaviour, I2C display timing, key switch
electrics - those need the assembled board (see HARDWARE_VERIFICATION.md).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

HOST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import SIM_BINARY, SimDeviceLink
from mock_obs import MockOBS
from takedeck.bridge import AckCache, Bridge
from takedeck.obs import SimpleObsBackend

pytestmark = pytest.mark.skipif(
    not SIM_BINARY.exists(),
    reason=f"build the firmware simulator first: firmware/test/run_host_tests.sh ({SIM_BINARY})",
)


async def wait_until(predicate, timeout: float = 8.0, interval: float = 0.02) -> bool:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def wait_diag(link: SimDeviceLink, needle: str, timeout: float = 8.0) -> bool:
    return await wait_until(lambda: any(needle in line for line in link.diag_log), timeout)


def test_key_press_reaches_obs_and_led_follows_obs(tmp_path):
    async def scenario():
        obs = await MockOBS().start()
        link = SimDeviceLink()
        link.start()
        backend = SimpleObsBackend(port=obs.port, mute_input="Mic/Aux")
        bridge = Bridge(backend, link, ack_cache=AckCache(str(tmp_path / "acks.json")))
        task = asyncio.create_task(bridge.run())
        try:
            # 1. handshake: the device announced itself and got a state back
            assert await wait_until(lambda: bridge.sid is not None)
            assert await wait_until(lambda: any(l.startswith("H STATE") for l in link.lines))
            assert await wait_diag(link, "#LED 0")

            # 2. REC key -> OBS really starts recording -> device LED on
            link.command("PRESS REC")
            assert await wait_until(lambda: obs.recording), "OBS never started recording"
            assert await wait_diag(link, "#LED 1"), "LED did not follow OBS"

            # 3. elapsed time reaches the device from OBS (not from the device)
            await asyncio.sleep(1.2)
            assert any("rec=1" in line and " t=1" in line for line in link.lines), link.lines[-5:]

            # A human key press needs the debounce window to pass before the
            # next edge is recognised (15 ms stable + release), so keep a
            # realistic gap between presses.
            await asyncio.sleep(0.2)

            # 4. REC again -> OBS stops -> LED off
            link.command("PRESS REC")
            assert await wait_until(lambda: not obs.recording)
            assert await wait_diag(link, "#LED 0")

            # 5. scene next / prev use OBS's scene order
            before = obs.current
            link.command("PRESS NEXT")
            assert await wait_until(lambda: obs.current == (before + 1) % len(obs.scenes))
            assert await wait_until(lambda: any(f'idx={obs.current}' in l for l in link.lines))
            link.command("PRESS PREV")
            assert await wait_until(lambda: obs.current == before)

            # 6. mute key toggles the configured OBS input
            link.command("PRESS MUTE")
            assert await wait_until(lambda: obs.muted is True)
            assert await wait_until(lambda: any("mute=1" in l for l in link.lines))
            await asyncio.sleep(0.2)
            link.command("PRESS MUTE")
            assert await wait_until(lambda: obs.muted is False)
        finally:
            bridge.stop()
            link.stop()
            await asyncio.wait_for(task, timeout=5)
            await obs.stop()

    asyncio.run(scenario())


def test_obs_loss_is_announced_then_recovered(tmp_path):
    async def scenario():
        obs = await MockOBS().start()
        port = obs.port
        link = SimDeviceLink()
        link.start()
        backend = SimpleObsBackend(port=port)
        bridge = Bridge(backend, link, ack_cache=AckCache(None))
        task = asyncio.create_task(bridge.run())
        try:
            assert await wait_until(lambda: any(l.startswith("H STATE") for l in link.lines))

            # OBS goes away
            await obs.stop()
            assert await wait_until(
                lambda: any(l.startswith("H ERR code=OBS_DOWN") for l in link.lines), timeout=5
            )
            # the device shows it, the recording state stops being claimed
            link.command("FB")
            assert await wait_until(
                lambda: any("#FB" in l and "ERR" in l for l in link.diag_log)
            )

            # OBS comes back on the same port: state resumes without a re-plug
            mark = len(link.lines)
            obs2 = await MockOBS(port=port).start()
            try:
                assert await wait_until(
                    lambda: any(l.startswith("H STATE") for l in link.lines[mark:]), timeout=20
                )
                # the bridge needs its next poll to notice the recovery before
                # it can execute a command
                assert await wait_until(lambda: bridge.status()["obs_ready"], timeout=5)
                link.command("PRESS REC")
                assert await wait_until(lambda: obs2.recording, timeout=8)
                assert await wait_diag(link, "#LED 1", timeout=8)
            finally:
                await obs2.stop()
        finally:
            bridge.stop()
            link.stop()
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_duplicate_press_retry_does_not_double_toggle(tmp_path):
    """A retried CMD (ACK lost on the way back) must not stop a recording twice."""

    async def scenario():
        obs = await MockOBS().start()
        link = SimDeviceLink()
        link.start()
        backend = SimpleObsBackend(port=obs.port)
        bridge = Bridge(backend, link, ack_cache=AckCache(None))
        task = asyncio.create_task(bridge.run())
        try:
            assert await wait_until(lambda: bridge.sid is not None)
            # Deliver the same command twice by hand, exactly what a lost ACK
            # makes the firmware do (same seq, same id).
            await bridge.on_device_line(f"D CMD seq=77 id=REC_TOGGLE")
            assert obs.recording is True
            await bridge.on_device_line(f"D CMD seq=77 id=REC_TOGGLE")
            await asyncio.sleep(0.3)
            assert obs.recording is True, "duplicate command toggled recording off"
            assert bridge.status()["duplicates"] == 1
        finally:
            bridge.stop()
            link.stop()
            await asyncio.wait_for(task, timeout=5)
            await obs.stop()

    asyncio.run(scenario())


def test_device_disappearing_ends_the_run_cleanly(tmp_path):
    async def scenario():
        obs = await MockOBS().start()
        link = SimDeviceLink()
        link.start()
        backend = SimpleObsBackend(port=obs.port)
        bridge = Bridge(backend, link, ack_cache=AckCache(None))
        task = asyncio.create_task(bridge.run())
        try:
            assert await wait_until(lambda: bridge.sid is not None)
        finally:
            link.stop()  # unplug
            await asyncio.wait_for(task, timeout=6)
            assert task.done() and task.exception() is None
            await obs.stop()

    asyncio.run(scenario())
