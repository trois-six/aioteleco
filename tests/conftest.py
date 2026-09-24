"""Shared fixtures: fake JSON payloads, a routed fake cloud and a fake box on TCP."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from yarl import URL

from aioteleco.const import BASE_URL, Endpoint
from aioteleco.hub import TelecoHub
from aioteleco.local.crypto import decrypt
from aioteleco.models import DeviceInfo, Room
from aioteleco.transport import TransportMode

JsonDict = dict[str, Any]
FIXTURES = Path(__file__).parent / "fixtures"

EMAIL = "user@example.com"
PASSWORD = "not-a-real-password"


def load_json(name: str) -> Any:
    """Load ``tests/fixtures/<name>.json``."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def url(endpoint: Endpoint | str) -> str:
    return f"{BASE_URL}/{endpoint}"


def envelope(value: Any = None, *, ok: bool = True, msg: str = "") -> JsonDict:
    return {"codEsito": "S" if ok else "E", "msgEsito": msg, "valRisultato": value}


def tmate(text: str, *, kind: str = "INFO", reference: str | None = "ref1") -> JsonDict:
    return {
        "MessageType": kind,
        "MessageID": "1",
        "MessageText": text,
        "ActionReference": reference,
    }


Handler = JsonDict | Callable[[JsonDict], JsonDict]


class FakeCloud:
    """Routes every cloud endpoint (repeatable) and records the posted bodies."""

    def __init__(self, mock: aioresponses) -> None:
        self.calls: list[tuple[Endpoint, JsonDict]] = []
        self.auth: list[Any] = []
        self.acks: list[JsonDict] = []  # consumed first, then ``default_ack``
        self.default_ack = tmate("PROC")
        self.handlers: dict[Endpoint, Handler] = {
            Endpoint.ACCOUNT_LOGIN: load_json("account-login"),
            Endpoint.ACCOUNT_LOGOUT: envelope(),
            Endpoint.INSTALLATION_LIST: load_json("account-installation-list"),
            Endpoint.ROOM_CONFIGURATION_LIST: load_json("room-configuration-list"),
            Endpoint.SCENARIO_LIST: load_json("scenario-list"),
            Endpoint.STATUS_DEVICE_LIST: self._status,
            Endpoint.NODE_STATUS: {
                "id": 1,
                "idInstallation": "TESTCODE01",
                "idSession": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
                "nodeActive": True,
            },
            Endpoint.FEED_THE_COMMANDS: tmate("Command queued"),
            Endpoint.GET_ACK_COMMAND: self._ack,
        }
        for endpoint in Endpoint:
            mock.post(url(endpoint), callback=self._callback(endpoint), repeat=True)

    def bodies(self, endpoint: Endpoint) -> list[JsonDict]:
        return [body for ep, body in self.calls if ep is endpoint]

    def count(self, endpoint: Endpoint) -> int:
        return len(self.bodies(endpoint))

    def _ack(self, body: JsonDict) -> JsonDict:
        return self.acks.pop(0) if self.acks else self.default_ack

    @staticmethod
    def _status(body: JsonDict) -> JsonDict:
        name = {789: "status-device-list-box", 2001: "status-device-list-slats"}.get(
            body.get("idInstallationDevice", 0)
        )
        return load_json(name) if name else envelope({"statusitemList": []})

    def _callback(self, endpoint: Endpoint) -> Callable[..., Any]:
        def callback(_url: Any, **kwargs: Any) -> Any:
            body: JsonDict = kwargs.get("json") or {}
            self.calls.append((endpoint, body))
            self.auth.append(kwargs.get("auth"))
            handler = self.handlers.get(endpoint, envelope(ok=False, msg="not mocked"))
            payload = handler(body) if callable(handler) else handler
            return CallbackResult(payload=payload)

        return callback


class _CompatClientResponse(aiohttp.ClientResponse):
    """aioresponses 0.7.9 does not pass ``stream_writer``, required since aiohttp 3.14."""

    def __init__(self, method: str, url: URL, **kwargs: Any) -> None:
        kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
        super().__init__(method, url, **kwargs)


_NEEDS_STREAM_WRITER = "stream_writer" in inspect.signature(aiohttp.ClientResponse).parameters


class FakeBox:
    """A Daisy box listening on 127.0.0.1 (ephemeral port)."""

    def __init__(self) -> None:
        self.reply: bytes | None = b"ACK\n"  # None: never answer
        self.frames: list[str] = []
        self.messages: list[str] = []
        self.port = 0
        self._server: asyncio.Server | None = None

    @property
    def payloads(self) -> list[JsonDict]:
        return [json.loads(m) for m in self.messages]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = b""
        try:
            while True:  # the frame has no terminator: read until it decodes
                chunk = await reader.read(4096)
                if not chunk:
                    return
                data += chunk
                frame = data.decode("ascii")
                try:
                    message, _ts, _scenario = decrypt(frame)
                    if not message.startswith("DIAGNOSTIC"):
                        json.loads(message)
                except ValueError:
                    continue
                break
            self.frames.append(frame)
            self.messages.append(message)
            if self.reply is None:
                await reader.read()  # hold the connection until the client gives up
            else:
                writer.write(self.reply)
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    """Loader for the JSON files of ``tests/fixtures``."""
    return load_json


@pytest.fixture
def rooms() -> list[Room]:
    return [
        Room.from_json(r) for r in load_json("room-configuration-list")["valRisultato"]["roomList"]
    ]


@pytest.fixture
def device_infos(rooms: list[Room]) -> dict[str, DeviceInfo]:
    """The fixture devices by short name: slats, awning, light."""
    by_id = {d.id_installation_device: d for room in rooms for d in room.devices}
    return {"slats": by_id[2001], "awning": by_id[2002], "light": by_id[2003]}


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Iterator[aioresponses]:
    if _NEEDS_STREAM_WRITER:
        monkeypatch.setattr("aioresponses.core.ClientResponse", _CompatClientResponse)
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def cloud(mock_http: aioresponses) -> FakeCloud:
    return FakeCloud(mock_http)


@pytest.fixture
async def http() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def no_poll_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aioteleco.cloud.api.ACK_POLL_INTERVAL", 0)


@pytest.fixture
async def box() -> AsyncIterator[FakeBox]:
    fake = FakeBox()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def closed_port() -> int:
    """A local port nothing listens on (connection refused)."""
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port: int = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


HubFactory = Callable[..., TelecoHub]


@pytest.fixture
def make_hub(http: aiohttp.ClientSession, cloud: FakeCloud, no_poll_delay: None) -> HubFactory:
    def factory(transport: TransportMode = TransportMode.AUTO, **kwargs: Any) -> TelecoHub:
        kwargs.setdefault("ack_timeout", 1.0)
        return TelecoHub(http, EMAIL, PASSWORD, transport=transport, **kwargs)

    return factory


@pytest.fixture
def hub(make_hub: HubFactory) -> TelecoHub:
    """A hub (auto transport) talking to the fake cloud."""
    return make_hub()
