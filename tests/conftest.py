"""Shared fixtures: fake JSON payloads, a routed fake cloud and a fake box on TCP."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioteleco.const import Endpoint
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


def envelope(value: Any = None, *, ok: bool = True, msg: str = "") -> JsonDict:
    return {"codEsito": "S" if ok else "E", "msgEsito": msg, "valRisultato": value}


def tmate(text: str, *, kind: str = "INFO", reference: str | None = "ref1") -> JsonDict:
    return {
        "MessageType": kind,
        "MessageID": "1",
        "MessageText": text,
        "ActionReference": reference,
    }


# What an endpoint answers: a JSON payload (object or array), or a callable taking the
# posted body and returning (or awaiting) a JSON payload or a ready-made ``web.Response``.
Handler = JsonDict | list[Any] | Callable[[JsonDict], Any]


def sequence(*responses: Any) -> Callable[[JsonDict], Any]:
    """A handler answering each response in turn, then repeating the last one."""
    pending = list(responses)

    def handler(_body: JsonDict) -> Any:
        return pending.pop(0) if len(pending) > 1 else pending[0]

    return handler


class FakeCloud:
    """A local HTTP server routing every cloud endpoint and recording the posted bodies.

    Point the SDK at it with ``base_url=cloud.url`` (the ``cloud`` fixture starts it).
    """

    def __init__(self) -> None:
        self.url = ""  # set once the server listens
        self.calls: list[tuple[Endpoint, JsonDict]] = []
        self.auth: list[str | None] = []  # the Authorization header of each request
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
        self.app = web.Application()
        for endpoint in Endpoint:
            self.app.router.add_post(f"/{endpoint}", self._route(endpoint))

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

    def _route(self, endpoint: Endpoint) -> Callable[[web.Request], Any]:
        async def route(request: web.Request) -> web.StreamResponse:
            body: JsonDict = await request.json() if request.can_read_body else {}
            self.calls.append((endpoint, body))
            self.auth.append(request.headers.get("Authorization"))
            handler = self.handlers.get(endpoint, envelope(ok=False, msg="not mocked"))
            payload = handler(body) if callable(handler) else handler
            if inspect.isawaitable(payload):
                payload = await payload
            if isinstance(payload, web.StreamResponse):
                return payload
            return web.json_response(payload)

        return route


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
async def cloud() -> AsyncIterator[FakeCloud]:
    """The fake cloud, served on 127.0.0.1 (ephemeral port) at ``cloud.url``."""
    fake = FakeCloud()
    server = TestServer(fake.app, host="127.0.0.1")
    await server.start_server()
    fake.url = str(server.make_url("/"))
    yield fake
    await server.close()


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
        return TelecoHub(http, EMAIL, PASSWORD, transport=transport, base_url=cloud.url, **kwargs)

    return factory


@pytest.fixture
def hub(make_hub: HubFactory) -> TelecoHub:
    """A hub (auto transport) talking to the fake cloud."""
    return make_hub()
