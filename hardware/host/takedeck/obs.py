"""OBS Studio access through obs-websocket 5.x (OBS Studio 28 and newer).

Two backends live here:

* ``SimpleObsBackend`` - the real one, built on the ``simpleobsws`` client
  (obs-websocket v5 protocol, authentication included).
* ``ObsBackend`` - the small interface the bridge codes against, so tests can
  run the bridge against a fake without opening a socket.

Only obs-websocket v5 requests are used. Scene cycling is done here on
purpose: obs-websocket has no "next scene" request, OBS itself keeps that
logic in its own UI.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)


class ObsError(Exception):
    """Raised when OBS cannot fulfil a request; codes are stable for the UI."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class ObsState:
    rec: bool = False
    elapsed_s: int = 0
    scene: str = ""
    idx: int = 0
    count: int = 0
    mute: bool = False


class ObsBackend(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def get_state(self) -> ObsState: ...
    async def start_record(self) -> None: ...
    async def stop_record(self) -> None: ...
    async def set_scene_index(self, index: int) -> None: ...
    async def toggle_mute(self) -> None: ...


class SimpleObsBackend:
    """obs-websocket v5 client used in production.

    Parameters mirror what obs-websocket shows in OBS: Tools -> WebSocket
    Server Settings (port 4455 by default, password optional).
    """

    SCENE_CACHE_S = 1.0
    MUTE_CACHE_S = 0.5

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4455,
        password: str = "",
        mute_input: str = "",
        request_timeout: float = 3.0,
    ) -> None:
        self._url = f"ws://{host}:{port}"
        self._password = password
        self._mute_input = mute_input
        self._timeout = request_timeout
        self._ws = None
        self._scenes: list[str] = []
        self._scenes_at = 0.0
        self._mute: bool = False
        self._mute_at = 0.0
        self._loop = 0.0

    # ------------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        try:
            import simpleobsws  # imported lazily so the tests can stub it out
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise ObsError("NO_LIB", "pip install simpleobsws") from exc

        self._ws = simpleobsws.WebSocketClient(
            url=self._url, password=self._password
        )
        try:
            await self._ws.connect()
            if not await self._ws.wait_until_identified(timeout=int(self._timeout) + 2):
                raise ObsError("OBS_AUTH", "obs-websocket did not complete the handshake")
        except Exception as exc:  # noqa: BLE001 - surfaced as a stable code
            await self.close()
            raise ObsError("OBS_CONNECT", str(exc)) from exc
        log.info("connected to OBS at %s", self._url)
        await self._refresh_scenes()

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.disconnect()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass

    # ------------------------------------------------------------------ requests
    async def _request(self, request_type: str, data: dict | None = None) -> dict:
        import simpleobsws

        if self._ws is None:
            raise ObsError("OBS_DOWN", "not connected")
        try:
            response = await self._ws.call(
                simpleobsws.Request(request_type, data or {}), timeout=self._timeout
            )
        except Exception as exc:  # noqa: BLE001
            raise ObsError("OBS_TIMEOUT", str(exc)) from exc
        if not response.ok():
            status = response.requestStatus
            raise ObsError(
                "OBS_REJECTED",
                f"{request_type} code={getattr(status, 'code', '?')} {getattr(status, 'comment', '')}".strip(),
            )
        return response.responseData or {}

    async def _refresh_scenes(self) -> None:
        data = await self._request("GetSceneList")
        scenes = data.get("scenes") or []
        # obs-websocket returns scenes newest first; the UI order is the reverse
        names = [s.get("sceneName", "") for s in scenes]
        names.reverse()
        self._scenes = names
        self._scenes_at = asyncio.get_running_loop().time()

    async def get_state(self) -> ObsState:
        now = asyncio.get_running_loop().time()
        record = await self._request("GetRecordStatus")
        if now - self._scenes_at > self.SCENE_CACHE_S or not self._scenes:
            await self._refresh_scenes()

        current = await self._request("GetCurrentProgramScene")
        # obs-websocket 5.x returns currentProgramSceneName; newer builds also
        # include sceneName. Accept either so a version change is not fatal.
        scene_name = current.get("currentProgramSceneName") or current.get("sceneName", "")
        idx = self._scenes.index(scene_name) if scene_name in self._scenes else 0

        mute = False
        if self._mute_input:
            if now - self._mute_at > self.MUTE_CACHE_S:
                data = await self._request("GetInputMute", {"inputName": self._mute_input})
                self._mute = bool(data.get("inputMuted", False))
                self._mute_at = now
            mute = self._mute

        duration_ms = int(record.get("outputDuration", 0) or 0)
        return ObsState(
            rec=bool(record.get("outputActive", False)),
            elapsed_s=duration_ms // 1000,
            scene=scene_name,
            idx=idx,
            count=len(self._scenes),
            mute=mute,
        )

    async def start_record(self) -> None:
        await self._request("StartRecord")

    async def stop_record(self) -> None:
        await self._request("StopRecord")

    async def set_scene_index(self, index: int) -> None:
        if not self._scenes:
            await self._refresh_scenes()
        if not self._scenes:
            raise ObsError("NO_SCENES", "OBS has no scenes")
        index %= len(self._scenes)
        await self._request(
            "SetCurrentProgramScene", {"sceneName": self._scenes[index]}
        )

    async def toggle_mute(self) -> None:
        if not self._mute_input:
            raise ObsError("NO_MUTE_SRC", "start the bridge with --mute-input")
        data = await self._request("ToggleInputMute", {"inputName": self._mute_input})
        # ToggleInputMute answers with the resulting state
        self._mute = bool(data.get("inputMuted", not self._mute))
        self._mute_at = asyncio.get_running_loop().time()
