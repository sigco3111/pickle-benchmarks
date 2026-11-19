"""A small obs-websocket v5 server used for tests and for trying the bridge.

It is **not** OBS. It implements just enough of protocol version 5 (Hello /
Identify / Identified / Request / RequestResponse / Event, password
authentication included) for the real ``simpleobsws`` client to talk to it, so
that the bridge can be tested end to end without installing OBS.

Use it to develop without a camera:

    python mock_obs.py --port 4455 --password test
    TAKEDECK_OBS_PASSWORD=test python -m takedeck --port /dev/ttyACM0

Requests implemented: GetVersion, GetRecordStatus, StartRecord, StopRecord,
ToggleRecord, GetSceneList, GetCurrentProgramScene, SetCurrentProgramScene,
GetInputList, GetInputMute, ToggleInputMute.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import time
import uuid

log = logging.getLogger("mock_obs")

SCENE_LIST = ["Standby", "Wide Shot", "Close Up"]


def _auth_string(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class MockOBS:
    """Minimal OBS state plus a websocket server around it."""

    def __init__(self, port: int = 0, password: str = "", scenes: list[str] | None = None) -> None:
        self.port = port
        self.password = password
        self.scenes = list(scenes or SCENE_LIST)
        self.current = 0
        self.recording = False
        self.record_started = 0.0
        self.muted = False
        self.requests: list[str] = []
        self._server = None
        self._clients: set = set()
        self._host = "127.0.0.1"

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> "MockOBS":
        from websockets.asyncio.server import serve

        # obs-websocket negotiates a subprotocol: JSON (default) or MessagePack.
        # simpleobsws uses the msgpack one, so the mock must speak both.
        self._server = await serve(
            self._handler,
            self._host,
            self.port,
            subprotocols=["obswebsocket.msgpack", "obswebsocket.json"],
        )
        self.port = self._server.sockets[0].getsockname()[1]
        log.info("mock obs-websocket listening on ws://%s:%s", self._host, self.port)
        return self

    async def stop(self) -> None:
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> "MockOBS":
        return await self.start()

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    # ------------------------------------------------------------------ state used by tests
    def duration_ms(self) -> int:
        if not self.recording:
            return 0
        return int((time.monotonic() - self.record_started) * 1000)

    async def set_recording(self, on: bool) -> None:
        if on == self.recording:
            return
        self.recording = on
        if on:
            self.record_started = time.monotonic()
        await self._broadcast(
            "RecordStateChanged",
            {
                "outputActive": on,
                "outputPath": "/tmp/mock-takedeck.mkv" if on else None,
                "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED" if on else "OBS_WEBSOCKET_OUTPUT_STOPPED",
            },
        )

    async def set_scene(self, index: int) -> None:
        index %= len(self.scenes)
        if index == self.current:
            return
        self.current = index
        await self._broadcast("CurrentProgramSceneChanged", {"sceneName": self.scenes[index]})

    async def _broadcast(self, event_type: str, data: dict) -> None:
        message = {"op": 5, "d": {"eventType": event_type, "eventIntent": 0, "eventData": data}}
        for ws in list(self._clients):
            try:
                await self._send(ws, message)
            except Exception:  # noqa: BLE001
                self._clients.discard(ws)

    @staticmethod
    def _codec(ws):
        """Return (encode, decode) for the negotiated subprotocol."""
        if getattr(ws, "subprotocol", None) == "obswebsocket.msgpack":
            import msgpack

            return (lambda obj: msgpack.packb(obj), lambda raw: msgpack.unpackb(raw))
        return (lambda obj: json.dumps(obj), lambda raw: json.loads(raw))

    async def _send(self, ws, message: dict) -> None:
        encode, _ = self._codec(ws)
        await ws.send(encode(message))

    # ------------------------------------------------------------------ protocol
    async def _handler(self, ws) -> None:
        challenge = str(uuid.uuid4())
        salt = str(uuid.uuid4())
        hello = {"obsWebSocketVersion": "5.5.2-mock", "rpcVersion": 1}
        if self.password:
            hello["authentication"] = {"challenge": challenge, "salt": salt}
        await self._send(ws, {"op": 0, "d": hello})

        _, decode = self._codec(ws)
        try:
            first = decode(await asyncio.wait_for(ws.recv(), timeout=10))
        except Exception:  # noqa: BLE001
            await ws.close()
            return
        if first.get("op") != 1:
            await ws.close()
            return

        identify = first.get("d", {})
        if self.password:
            expected = _auth_string(self.password, salt, challenge)
            if identify.get("authentication") != expected:
                await ws.close(code=4009, reason="Authentication failed.")
                return
        await self._send(ws, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
        self._clients.add(ws)

        try:
            async for raw in ws:
                message = decode(raw)
                if message.get("op") != 6:
                    continue
                await self._handle_request(ws, message.get("d", {}))
        except Exception as exc:  # noqa: BLE001
            log.debug("client closed: %s", exc)
        finally:
            self._clients.discard(ws)

    async def _handle_request(self, ws, data: dict) -> None:
        req_type = data.get("requestType", "")
        req_id = data.get("requestId", "")
        req_data = data.get("requestData") or {}
        self.requests.append(req_type)

        result, code, comment, response = await self._dispatch(req_type, req_data)
        await self._send(
            ws,
            {
                "op": 7,
                "d": {
                    "requestType": req_type,
                    "requestId": req_id,
                    "requestStatus": {"result": result, "code": code, "comment": comment},
                    "responseData": response,
                },
            },
        )

    async def _dispatch(self, req_type: str, data: dict):
        if req_type == "GetVersion":
            return True, 100, "", {
                "obsVersion": "30.2.3-mock",
                "obsWebSocketVersion": "5.5.2-mock",
                "rpcVersion": 1,
                "availableRequests": [],
                "supportedImageFormats": ["png", "jpg"],
                "platform": "linux-mock",
                "platformDescription": "MockOBS",
            }
        if req_type == "GetRecordStatus":
            duration = self.duration_ms()
            return True, 100, "", {
                "outputActive": self.recording,
                "outputPaused": False,
                "outputTimecode": "00:00:00.000",
                "outputDuration": duration,
                "outputBytes": duration * 300,
            }
        if req_type == "StartRecord":
            if self.recording:
                return False, 500, "output already active", {}
            await self.set_recording(True)
            return True, 100, "", {}
        if req_type == "StopRecord":
            if not self.recording:
                return False, 501, "output not running", {}
            path = "/tmp/mock-takedeck.mkv"
            await self.set_recording(False)
            return True, 100, "", {"outputPath": path}
        if req_type == "ToggleRecord":
            await self.set_recording(not self.recording)
            return True, 100, "", {"outputActive": self.recording}
        if req_type == "GetSceneList":
            return True, 100, "", {
                "currentProgramSceneName": self.scenes[self.current],
                "currentPreviewSceneName": None,
                # obs-websocket returns the list newest-first
                "scenes": [
                    {"sceneIndex": i, "sceneName": name}
                    for i, name in reversed(list(enumerate(self.scenes)))
                ],
            }
        if req_type == "GetCurrentProgramScene":
            return True, 100, "", {
                "currentProgramSceneName": self.scenes[self.current],
                "sceneName": self.scenes[self.current],
                "sceneIndex": self.current,
            }
        if req_type == "SetCurrentProgramScene":
            name = data.get("sceneName")
            if name not in self.scenes:
                return False, 600, "no source was found by the name of `%s`" % name, {}
            await self.set_scene(self.scenes.index(name))
            return True, 100, "", {}
        if req_type == "GetInputList":
            return True, 100, "", {"inputs": [{"inputName": "Mic/Aux", "inputKind": "pulse_input_capture"}]}
        if req_type == "GetInputMute":
            if data.get("inputName") != "Mic/Aux":
                return False, 600, "no input", {}
            return True, 100, "", {"inputMuted": self.muted}
        if req_type == "ToggleInputMute":
            if data.get("inputName") != "Mic/Aux":
                return False, 600, "no input", {}
            self.muted = not self.muted
            return True, 100, "", {"inputMuted": self.muted}

        return False, 204, "unknown request type: %s" % req_type, {}


async def _main_async(args: argparse.Namespace) -> None:
    obs = await MockOBS(port=args.port, password=args.password).start()
    print(f"mock obs-websocket on ws://127.0.0.1:{obs.port} (password: {'yes' if args.password else 'no'})")
    print("scenes:", ", ".join(obs.scenes))
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await obs.stop()


def main() -> None:
    p = argparse.ArgumentParser(description="Mock obs-websocket v5 server for TakeDeck development")
    p.add_argument("--port", type=int, default=4455)
    p.add_argument("--password", default=os.environ.get("MOCK_OBS_PASSWORD", ""))
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    random.seed(0)
    main()
