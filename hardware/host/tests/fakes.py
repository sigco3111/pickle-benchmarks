"""Test doubles: a fake OBS backend, an in-memory device link and a link
that drives the real firmware simulator (firmware/test/host_sim) over pipes."""
from __future__ import annotations

import asyncio
import queue
import subprocess
import threading
import time
from pathlib import Path

from takedeck.link import DeviceLink
from takedeck.obs import ObsError, ObsState


class MutableClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeObs:
    """ObsBackend implementation that records calls instead of talking to OBS."""

    def __init__(self, scenes: list[str] | None = None, mute_input: str = "") -> None:
        self.scenes = list(scenes or ["Standby", "Wide Shot", "Close Up"])
        self.idx = 0
        self.rec = False
        self.elapsed = 0
        self.mute_input = mute_input
        self.muted = False
        self.calls: list[str] = []
        self.connect_failures = 0
        self.state_failures = 0
        self.connected = False
        self.toggled = 0

    async def connect(self) -> None:
        self.calls.append("connect")
        if self.connect_failures > 0:
            self.connect_failures -= 1
            raise ObsError("OBS_CONNECT", "refused")
        self.connected = True

    async def close(self) -> None:
        self.calls.append("close")
        self.connected = False

    async def get_state(self) -> ObsState:
        if self.state_failures > 0:
            self.state_failures -= 1
            raise ObsError("OBS_TIMEOUT", "no answer")
        return ObsState(
            rec=self.rec,
            elapsed_s=self.elapsed,
            scene=self.scenes[self.idx],
            idx=self.idx,
            count=len(self.scenes),
            mute=self.muted,
        )

    async def start_record(self) -> None:
        self.calls.append("start_record")
        self.rec = True

    async def stop_record(self) -> None:
        self.calls.append("stop_record")
        self.rec = False

    async def set_scene_index(self, index: int) -> None:
        self.calls.append(f"set_scene:{index % len(self.scenes)}")
        self.idx = index % len(self.scenes)

    async def toggle_mute(self) -> None:
        if not self.mute_input:
            raise ObsError("NO_MUTE_SRC", "no input configured")
        self.calls.append("toggle_mute")
        self.muted = not self.muted
        self.toggled += 1


class FakeLink:
    """DeviceLink that keeps everything in memory."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._connected = True

    def stop(self) -> None:
        self._connected = False

    def send(self, line: str) -> None:
        self.sent.append(line)

    async def next_line(self, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    # helpers
    def push(self, line: str) -> None:
        self._queue.put_nowait(line)

    def sent_matching(self, prefix: str) -> list[str]:
        return [line for line in self.sent if line.startswith(prefix)]

    def last(self, prefix: str) -> str | None:
        matches = self.sent_matching(prefix)
        return matches[-1] if matches else None


SIM_BINARY = Path(__file__).resolve().parents[2] / "firmware" / "test" / "build" / "host_sim"


class SimDeviceLink:
    """DeviceLink driving firmware/test/host_sim — the real firmware logic."""

    def __init__(self, binary: Path = SIM_BINARY, extra_args: list[str] | None = None) -> None:
        self.binary = binary
        self.proc: subprocess.Popen | None = None
        self._queue: "queue.Queue[str | None]" = queue.Queue()
        self._diag: "queue.Queue[str | None]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._connected = False
        self.extra_args = extra_args or []
        self.lines: list[str] = []
        self.diag_log: list[str] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if not self.binary.exists():
            raise FileNotFoundError(
                f"{self.binary} not found - build it with firmware/test/run_host_tests.sh"
            )
        self.proc = subprocess.Popen(
            [str(self.binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._connected = True
        self._thread = threading.Thread(target=self._reader, name="sim-rx", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            # '#' lines are simulator diagnostics, not protocol traffic
            if line.startswith("#"):
                self.diag_log.append(line)
                self._diag.put_nowait(line)
            else:
                self._queue.put_nowait(line)
        self._connected = False
        self._queue.put(None)

    def stop(self) -> None:
        self._connected = False
        if self.proc is not None:
            try:
                self.proc.stdin.write("QUIT\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=1.0)
            except Exception:  # noqa: BLE001
                self.proc.kill()
            self.proc = None

    def send(self, line: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("simulator not running")
        self.lines.append(line)
        # host->device protocol lines are injected with the simulator's HOST
        # command; everything the bridge writes is exactly what a serial port
        # would carry.
        payload = f"HOST {line}" if line.startswith("H ") else line
        self.proc.stdin.write(payload + "\n")
        self.proc.stdin.flush()

    def command(self, text: str) -> None:
        """Send a simulator control command (PRESS REC, LED, ...)."""
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("simulator not running")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    async def next_line(self, timeout: float) -> str | None:
        return await self._get(self._queue, timeout)

    async def next_diag(self, timeout: float) -> str | None:
        return await self._get(self._diag, timeout)

    @staticmethod
    async def _get(q: "queue.Queue[str | None]", timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                item = await loop.run_in_executor(None, q.get, True, remaining)
            except queue.Empty:
                return None
            if item is None:
                q.put(None)
                return None
            return item
