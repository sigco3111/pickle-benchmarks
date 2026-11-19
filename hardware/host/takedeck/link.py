"""Serial link to the controller (USB CDC) plus a transport interface.

The firmware enumerates as a USB CDC device (VID 0x2E8A, PID 0x000A - the
Raspberry Pi SDK values, see firmware/CMakeLists.txt). On Linux this shows up
as /dev/ttyACM*, on macOS as /dev/cu.usbmodem*, on Windows as COMx.

``SerialLink`` is the production transport. ``LoopbackLink`` is used by tests
and by ``--demo`` so the bridge can be exercised without hardware.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Protocol

log = logging.getLogger(__name__)

VID_PID = (0x2E8A, 0x000A)
DEFAULT_BAUD = 115200  # ignored by CDC-ACM, kept for older drivers


class LinkClosed(Exception):
    pass


class DeviceLink(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def send(self, line: str) -> None: ...
    async def next_line(self, timeout: float) -> str | None: ...
    @property
    def connected(self) -> bool: ...


def list_candidate_ports() -> list[str]:
    """Ports whose USB descriptor matches the board (best effort)."""
    try:
        from serial.tools import list_ports
    except ImportError:  # pragma: no cover
        return []
    found: list[str] = []
    for port in list_ports.comports():
        if (port.vid, port.pid) == VID_PID:
            found.append(port.device)
    return found


class SerialLink:
    """pyserial transport with a reader thread feeding an asyncio friendly queue."""

    def __init__(self, port: str, baud: int = DEFAULT_BAUD) -> None:
        self._port = port
        self._baud = baud
        self._serial = None
        self._thread: threading.Thread | None = None
        self._queue: "queue.Queue[str | None]" = queue.Queue()
        self._closing = threading.Event()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str:
        return self._port

    def start(self) -> None:
        import serial

        # timeout keeps the reader thread from blocking forever at shutdown.
        # reset_input_buffer() drops whatever the firmware printed before the
        # bridge attached (the D HELLO burst), the handshake below re-syncs.
        self._serial = serial.Serial(
            self._port, self._baud, timeout=0.1, write_timeout=1.0
        )
        try:
            self._serial.reset_input_buffer()
        except Exception:  # noqa: BLE001
            pass
        self._closing.clear()
        self._connected = True
        self._thread = threading.Thread(target=self._reader, name="takedeck-rx", daemon=True)
        self._thread.start()
        log.info("serial port %s open", self._port)

    def _reader(self) -> None:
        assert self._serial is not None
        buf = bytearray()
        while not self._closing.is_set():
            try:
                chunk = self._serial.read(256)
            except Exception as exc:  # noqa: BLE001 - device unplugged
                log.warning("serial read failed: %s", exc)
                break
            if not chunk:
                continue
            for byte in chunk:
                if byte in (0x0A, 0x0D):
                    if buf:
                        try:
                            self._queue.put_nowait(buf.decode("utf-8", "replace"))
                        except queue.Full:  # pragma: no cover
                            pass
                        buf.clear()
                elif len(buf) < 256:
                    buf.append(byte)
        self._connected = False
        self._queue.put(None)  # sentinel: link is gone

    def stop(self) -> None:
        self._closing.set()
        self._connected = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # noqa: BLE001
                pass
            self._serial = None
        self._queue.put(None)

    def send(self, line: str) -> None:
        if self._serial is None:
            raise LinkClosed("serial port is not open")
        self._serial.write((line + "\n").encode("ascii", "replace"))
        self._serial.flush()

    async def next_line(self, timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                item = await loop.run_in_executor(None, self._queue.get, True, remaining)
            except queue.Empty:
                return None
            if item is None:
                # put the sentinel back for the next caller
                self._queue.put(None)
                return None
            return item


class LoopbackLink:
    """In-memory link used by --demo and by unit tests.

    Whatever the bridge sends is answered by a very small scripted device: it
    only exists to make the bridge runnable without hardware. The real
    behaviour is covered by firmware/test/host_sim.c.
    """

    def __init__(self) -> None:
        self._incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self._connected = True
        self.sent: list[str] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._connected = True
        self._incoming.put_nowait("D HELLO v=1 fw=demo sid=DEMO0001")

    def stop(self) -> None:
        self._connected = False
        self._incoming.put_nowait(None)

    def send(self, line: str) -> None:
        if not self._connected:
            raise LinkClosed("demo link closed")
        self.sent.append(line)
        if line.startswith("H PONG"):
            return
        if line.startswith("H ACK"):
            return

    async def next_line(self, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(self._incoming.get(), timeout)
        except asyncio.TimeoutError:
            return None

    def push(self, line: str) -> None:
        """Test helper: pretend the device said something."""
        self._incoming.put_nowait(line)
