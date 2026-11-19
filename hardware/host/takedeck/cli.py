"""Command line entry point for the TakeDeck host bridge.

    python -m takedeck --list-ports
    python -m takedeck --port /dev/ttyACM0 --mute-input "Mic/Aux"
    TAKEDECK_OBS_PASSWORD=... python -m takedeck   # password from the environment

No credential is ever written to a file by this program; the OBS password is
read from --obs-password or the TAKEDECK_OBS_PASSWORD environment variable.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time

from . import protocol
from .bridge import ACK_CACHE_FILE, Bridge, AckCache
from .link import DeviceLink, LinkClosed, SerialLink, list_candidate_ports
from .obs import SimpleObsBackend

log = logging.getLogger("takedeck")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="takedeck",
        description="Bridge between the TakeDeck USB controller and OBS Studio (obs-websocket v5).",
    )
    p.add_argument("--port", help="serial port of the controller (default: auto detect)")
    p.add_argument("--list-ports", action="store_true", help="list candidate ports and exit")
    p.add_argument("--probe", type=float, default=2.0,
                   help="seconds to wait for the device handshake when auto detecting (0 = off)")
    p.add_argument("--obs-host", default="127.0.0.1")
    p.add_argument("--obs-port", type=int, default=4455)
    p.add_argument("--obs-password", default=None,
                   help="obs-websocket password (or set TAKEDECK_OBS_PASSWORD)")
    p.add_argument("--mute-input", default="",
                   help='OBS audio input name for the MUTE key, e.g. "Mic/Aux"')
    p.add_argument("--ack-cache", default=ACK_CACHE_FILE,
                   help="file that remembers executed command ids (empty string disables)")
    p.add_argument("--state-period", type=float, default=0.25,
                   help="seconds between state updates pushed to the device")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def detect_port(probe_seconds: float) -> str | None:
    """Open each candidate port and wait for D HELLO to be sure it is us."""
    import serial

    candidates = list_candidate_ports()
    if not candidates:
        return None
    for port in candidates:
        if probe_seconds <= 0:
            return port
        try:
            with serial.Serial(port, 115200, timeout=0.2) as ser:
                ser.reset_input_buffer()
                ser.write((protocol.hello() + "\n").encode())
                end = time.monotonic() + probe_seconds
                while time.monotonic() < end:
                    line = ser.readline().decode("utf-8", "replace").strip()
                    if line.startswith("D HELLO"):
                        return port
        except Exception as exc:  # noqa: BLE001
            log.debug("probe of %s failed: %s", port, exc)
    return None


async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def run_forever(args: argparse.Namespace, password: str) -> int:
    ack_cache = AckCache(args.ack_cache or None)
    obs = SimpleObsBackend(
        host=args.obs_host,
        port=args.obs_port,
        password=password,
        mute_input=args.mute_input,
    )
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows
            pass

    while not stop.is_set():
        port = args.port or detect_port(args.probe)
        if not port:
            log.error("no TakeDeck found. Available ports: %s",
                      ", ".join(list_candidate_ports()) or "none")
            await sleep_or_stop(stop, 5.0)
            continue

        link: DeviceLink = SerialLink(port)
        bridge = Bridge(obs, link, state_period=args.state_period, ack_cache=ack_cache)
        try:
            log.info("bridging %s <-> OBS %s:%s", port, args.obs_host, args.obs_port)
            run_task = asyncio.create_task(bridge.run())
            stop_task = asyncio.create_task(stop.wait())
            done, pending = await asyncio.wait(
                {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if run_task in done:
                exc = run_task.exception()
                if exc:
                    log.error("bridge stopped: %s", exc)
        except LinkClosed as exc:
            log.warning("link closed: %s", exc)
        finally:
            bridge.stop()
            try:
                await obs.close()
            except Exception:  # noqa: BLE001
                pass
        if not stop.is_set():
            log.info("reconnecting in 2 s")
            await sleep_or_stop(stop, 2.0)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.list_ports:
        ports = list_candidate_ports()
        print("candidate ports (VID:PID 2E8A:000A):")
        for p in ports:
            print("  ", p)
        if not ports:
            print("   none")
        return 0

    password = args.obs_password
    if password is None:
        password = os.environ.get("TAKEDECK_OBS_PASSWORD", "")
    if password:
        log.info("using OBS password from %s",
                 "--obs-password" if args.obs_password else "TAKEDECK_OBS_PASSWORD")

    return asyncio.run(run_forever(args, password))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
