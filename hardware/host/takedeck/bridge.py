"""Bridge core: OBS Studio on one side, the USB controller on the other.

Responsibilities, in the order the requirements list them:

* connection and reconnection of both sides (device and OBS),
* duplicate command suppression (per device session + sequence number, with an
  optional on-disk cache so a bridge restart does not repeat a toggle),
* pushing the real OBS state (recording flag, elapsed time, scene, mute) to the
  controller so its LED shows what OBS is actually doing,
* telling the controller explicitly when OBS cannot be reached, instead of
  letting a stale state stay on the display.

The class is transport agnostic: any object implementing ``DeviceLink`` works,
and any object implementing ``ObsBackend`` works, which is what makes the unit
and integration tests possible.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass

from . import protocol
from .link import DeviceLink, LinkClosed
from .obs import ObsBackend, ObsError, ObsState

log = logging.getLogger(__name__)

ACK_CACHE_SIZE = 128
ACK_CACHE_FILE = "takedeck-acks.json"
DEVICE_SILENCE_S = 3.0
OBS_RETRY_MIN_S = 1.0
OBS_RETRY_MAX_S = 15.0
ERR_REPEAT_S = 1.0


class AckCache:
    """Remembers successful command results so a retry is never executed twice.

    The key is (device session id, sequence number). The device keeps its
    session id until it reboots, and sequence numbers only grow, so this covers
    retries after a lost ACK and even a bridge restart when ``path`` is given.
    """

    def __init__(self, path: str | None = None, size: int = ACK_CACHE_SIZE) -> None:
        self.path = path
        self.size = size
        self._items: "OrderedDict[str, dict]" = OrderedDict()
        self._load()

    @staticmethod
    def key(sid: str, seq: int) -> str:
        return f"{sid}:{seq}"

    def get(self, sid: str, seq: int) -> dict | None:
        return self._items.get(self.key(sid, seq))

    def put(self, sid: str, seq: int, value: dict) -> None:
        self._items[self.key(sid, seq)] = value
        self._items.move_to_end(self.key(sid, seq))
        while len(self._items) > self.size:
            self._items.popitem(last=False)
        self._save()

    def __len__(self) -> int:
        return len(self._items)

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key, value in data.items():
                self._items[key] = value
        except (OSError, ValueError) as exc:  # pragma: no cover - corrupt file
            log.warning("could not read ack cache %s: %s", self.path, exc)

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._items, fh)
            os.replace(tmp, self.path)
        except OSError as exc:  # pragma: no cover - read only fs
            log.warning("could not write ack cache %s: %s", self.path, exc)


@dataclass
class BridgeStats:
    commands: int = 0
    duplicates: int = 0
    failures: int = 0
    state_pushes: int = 0
    obs_errors: int = 0
    sessions: int = 0


class Bridge:
    def __init__(
        self,
        obs: ObsBackend,
        link: DeviceLink,
        *,
        state_period: float = 0.25,
        ack_cache: AckCache | None = None,
        clock=time.monotonic,
    ) -> None:
        self.obs = obs
        self.link = link
        self.state_period = state_period
        # `or` would replace an empty cache: AckCache defines __len__ (falsy when empty)
        self.acks = ack_cache if ack_cache is not None else AckCache()
        self.clock = clock
        self.stats = BridgeStats()

        self.sid: str | None = None
        self._last_state_push = 0.0
        self._last_device_rx = 0.0
        self._last_err = 0.0
        self._obs_ready = False
        self._obs_retry_at = 0.0
        self._obs_backoff = OBS_RETRY_MIN_S
        self._cmd_lock = asyncio.Lock()
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------ helpers
    def _send(self, line: str) -> None:
        try:
            self.link.send(line)
            log.debug("-> %s", line)
        except (LinkClosed, OSError) as exc:
            log.warning("device link lost while sending: %s", exc)

    def now_ms(self) -> int:
        return int(self.clock() * 1000)

    # ------------------------------------------------------------------- OBS side
    async def ensure_obs(self) -> bool:
        """Connect (or reconnect) to OBS; returns True when it is usable."""
        now = self.clock()
        if self._obs_ready:
            return True
        if now < self._obs_retry_at:
            return False
        try:
            await self.obs.connect()
            self._obs_ready = True
            self._obs_backoff = OBS_RETRY_MIN_S
            log.info("OBS connected")
        except ObsError as exc:
            self.stats.obs_errors += 1
            self._obs_ready = False
            self._obs_retry_at = now + self._obs_backoff
            log.warning("OBS connect failed (%s); retry in %.1fs", exc, self._obs_backoff)
            self._obs_backoff = min(self._obs_backoff * 2, OBS_RETRY_MAX_S)
        return self._obs_ready

    async def push_state(self) -> None:
        """Send the current OBS state to the device (or an explicit error)."""
        if not await self.ensure_obs():
            if self.clock() - self._last_err >= ERR_REPEAT_S:
                self._last_err = self.clock()
                self._send(protocol.err("OBS_DOWN", "OBS is not reachable"))
            return
        try:
            state = await self.obs.get_state()
        except ObsError as exc:
            self.stats.obs_errors += 1
            self._obs_ready = False
            self._obs_retry_at = self.clock() + OBS_RETRY_MIN_S
            log.warning("state poll failed: %s", exc)
            self._send(protocol.err("OBS_DOWN", str(exc)))
            self._last_err = self.clock()
            return

        snapshot = protocol.ObsStateSnapshot(
            rec=state.rec,
            elapsed_s=state.elapsed_s,
            scene=state.scene,
            idx=state.idx,
            count=state.count,
            mute=state.mute,
        )
        self._send(protocol.state(snapshot))
        self.stats.state_pushes += 1
        self._last_state_push = self.clock()

    # ---------------------------------------------------------------- device side
    async def on_device_line(self, line: str) -> None:
        msg = protocol.parse_line(line)
        if msg is None:
            log.debug("ignoring unparsable device line: %r", line)
            return
        if msg.direction != "D":
            return
        self._last_device_rx = self.clock()

        if msg.kind == "HELLO":
            await self._on_hello(msg)
        elif msg.kind == "PING":
            self._send(protocol.pong(self.now_ms()))
        elif msg.kind == "CMD":
            await self._on_cmd(msg)
        elif msg.kind == "NOTE":
            log.info("device note: %s", msg.get("code"))

    async def _on_hello(self, msg: protocol.DeviceMessage) -> None:
        sid = msg.get("sid", "") or "nosid"
        new_session = sid != self.sid
        if new_session:
            self.sid = sid
            self.stats.sessions += 1
            log.info(
                "device session %s attached (fw %s, protocol %s)",
                sid,
                msg.get("fw", "?"),
                msg.get("v", "?"),
            )
        # Answer every HELLO: the device repeats it until it hears us.
        self._send(protocol.hello())
        await self.push_state()

    async def _on_cmd(self, msg: protocol.DeviceMessage) -> None:
        seq = msg.get_int("seq")
        cmd_id = msg.get("id", "")
        sid = self.sid or "nosid"
        if seq is None or not cmd_id:
            log.warning("malformed CMD from device: %r", msg)
            return

        cached = self.acks.get(sid, seq)
        if cached is not None:
            self.stats.duplicates += 1
            log.info("duplicate command %s seq=%s: replaying ACK", cmd_id, seq)
            self._send(protocol.ack(seq, bool(cached.get("ok", 1)), cached.get("err")))
            return

        async with self._cmd_lock:
            # Re-check inside the lock: two identical CMDS can be queued at once.
            cached = self.acks.get(sid, seq)
            if cached is not None:
                self.stats.duplicates += 1
                self._send(protocol.ack(seq, bool(cached.get("ok", 1)), cached.get("err")))
                return

            self.stats.commands += 1
            ok, err = await self._execute(cmd_id)
            if ok:
                self.acks.put(sid, seq, {"ok": 1, "id": cmd_id, "at": int(self.clock())})
            else:
                self.stats.failures += 1
            self._send(protocol.ack(seq, ok, err))
            await self.push_state()

    async def _execute(self, cmd_id: str) -> tuple[bool, str | None]:
        if not await self.ensure_obs():
            return False, "OBS_DOWN"
        try:
            if cmd_id == "REC_TOGGLE":
                # Resolve the toggle against the state OBS reports right now, so
                # a state that is one poll old cannot flip the wrong way.
                state = await self.obs.get_state()
                if state.rec:
                    await self.obs.stop_record()
                else:
                    await self.obs.start_record()
                return True, None
            if cmd_id in ("SCENE_NEXT", "SCENE_PREV"):
                state = await self.obs.get_state()
                if state.count <= 0:
                    return False, "NO_SCENES"
                step = 1 if cmd_id == "SCENE_NEXT" else -1
                await self.obs.set_scene_index((state.idx + step) % state.count)
                return True, None
            if cmd_id == "MUTE_TOGGLE":
                await self.obs.toggle_mute()
                return True, None
            log.warning("unknown command id %r", cmd_id)
            return False, "UNKNOWN_CMD"
        except ObsError as exc:
            log.warning("command %s failed: %s", cmd_id, exc)
            self._obs_ready = False if exc.code in ("OBS_DOWN", "OBS_TIMEOUT") else self._obs_ready
            return False, exc.code
        except Exception as exc:  # noqa: BLE001 - never let one command kill the bridge
            log.exception("command %s raised: %s", cmd_id, exc)
            return False, "INTERNAL"

    # ------------------------------------------------------------------ main loop
    async def start(self) -> None:
        self.link.start()
        self._last_device_rx = self.clock()
        if await self.ensure_obs():
            await self.push_state()

    async def step(self, timeout: float = 0.05) -> bool:
        """One loop iteration; returns False when the device link is gone."""
        line = await self.link.next_line(timeout)
        if line is None:
            if not getattr(self.link, "connected", True):
                return False
        else:
            log.debug("< %s", line)
            await self.on_device_line(line)

        # The device needs a fresh state even when it is quiet: this is what
        # keeps a recording that was started from OBS's own UI visible here.
        if self.clock() - self._last_state_push >= self.state_period:
            await self.push_state()
        return True

    async def run(self) -> None:
        await self.start()
        while not self._stop.is_set():
            alive = await self.step()
            if not alive:
                log.warning("device disappeared; waiting for it to come back")
                break
        self.link.stop()
        try:
            await self.obs.close()
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        return {
            "sid": self.sid,
            "obs_ready": self._obs_ready,
            "commands": self.stats.commands,
            "duplicates": self.stats.duplicates,
            "failures": self.stats.failures,
            "state_pushes": self.stats.state_pushes,
            "obs_errors": self.stats.obs_errors,
            "sessions": self.stats.sessions,
            "ack_cache": len(self.acks),
        }
