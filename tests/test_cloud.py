"""Cloud client (envelope, session, re-login, errors) and the command/ack API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp
import pytest
from aiohttp import web

from aioteleco.cloud.api import CloudApi
from aioteleco.cloud.client import CloudClient
from aioteleco.commands import build_device_command
from aioteleco.const import Endpoint
from aioteleco.exceptions import (
    TelecoAckTimeoutError,
    TelecoApiError,
    TelecoAuthError,
    TelecoCommandError,
    TelecoConnectionError,
    TelecoError,
    TelecoSessionExpiredError,
)
from aioteleco.models import DeviceInfo, Installation
from conftest import FakeCloud, sequence

JsonDict = dict[str, Any]

LOGIN = Endpoint.ACCOUNT_LOGIN
INSTALLATIONS = Endpoint.INSTALLATION_LIST
ROOMS = Endpoint.ROOM_CONFIGURATION_LIST
FEED = Endpoint.FEED_THE_COMMANDS
ACK = Endpoint.GET_ACK_COMMAND
NODE = Endpoint.NODE_STATUS
SESSION_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def tmate(text: str, kind: str = "INFO", reference: str | None = "ref1") -> JsonDict:
    return {
        "MessageType": kind,
        "MessageID": "1",
        "MessageText": text,
        "ActionReference": reference,
    }


@pytest.fixture
async def client(cloud: FakeCloud) -> AsyncIterator[CloudClient]:
    async with aiohttp.ClientSession() as http:
        yield CloudClient(http, "user@example.com", "not-a-real-password", base_url=cloud.url)


@pytest.fixture
def api(client: CloudClient) -> CloudApi:
    return CloudApi(client)


@pytest.fixture
def installation(fixture_json: Callable[[str], Any]) -> Installation:
    data = fixture_json("account-installation-list")["valRisultato"]["installationList"][0]
    return Installation.from_json(data)


@pytest.fixture
def logged_in(cloud: FakeCloud, fixture_json: Callable[[str], Any]) -> FakeCloud:
    """The fake cloud, accepting the login (its default, made explicit here)."""
    cloud.handlers[LOGIN] = fixture_json("account-login")
    return cloud


# --- login -------------------------------------------------------------------------


async def test_login(logged_in: FakeCloud, client: CloudClient) -> None:
    session = await client.login()
    assert session.id_session == SESSION_ID
    assert session.id_account == 1234
    assert client.id_account == 1234
    (body,) = logged_in.bodies(LOGIN)
    assert body == {
        "email": "user@example.com",
        "pwd": "not-a-real-password",
        "deviceSerial": "0000000000000000",
        "deviceDescription": "aioteleco",
    }


async def test_basic_auth(logged_in: FakeCloud, client: CloudClient) -> None:
    await client.login()
    assert logged_in.auth == ["Basic dGVsZWNvOnRtYXRlMjA="]  # teleco:tmate20, read server side


async def test_login_wrong_credentials(cloud: FakeCloud, client: CloudClient) -> None:
    cloud.handlers[LOGIN] = {
        "codEsito": "E",
        "msgEsito": "Wrong user name or password",
        "valRisultato": None,
    }
    with pytest.raises(TelecoAuthError, match="Wrong user name or password"):
        await client.login()
    assert client.session is None


async def test_login_error_without_message(cloud: FakeCloud, client: CloudClient) -> None:
    cloud.handlers[LOGIN] = {"codEsito": "E"}
    with pytest.raises(TelecoAuthError, match="Wrong user name or password"):
        await client.login()


async def test_login_registration_not_confirmed(cloud: FakeCloud, client: CloudClient) -> None:
    cloud.handlers[LOGIN] = {
        "codEsito": "S",
        "msgEsito": "Request User registration not confirm",
        "valRisultato": {"idSession": "x", "idAccount": 1},
    }
    with pytest.raises(TelecoAuthError, match="registration not confirm"):
        await client.login()
    assert client.session is None


async def test_login_ok_without_session(cloud: FakeCloud, client: CloudClient) -> None:
    cloud.handlers[LOGIN] = {"codEsito": "S", "msgEsito": "", "valRisultato": None}
    with pytest.raises(TelecoError):
        await client.login()


def test_not_logged_in(client: CloudClient) -> None:
    with pytest.raises(TelecoSessionExpiredError):
        _ = client.id_account


# --- session fields / envelope ----------------------------------------------------------


async def test_session_fields_injected(
    logged_in: FakeCloud, client: CloudClient, fixture_json: Callable[[str], Any]
) -> None:
    logged_in.handlers[INSTALLATIONS] = fixture_json("account-installation-list")
    result = await client.call(Endpoint.INSTALLATION_LIST, {"foo": 1})
    assert result["installationList"][0]["instCode"] == "TESTCODE01"
    (body,) = logged_in.bodies(INSTALLATIONS)
    assert body == {"foo": 1, "idSession": SESSION_ID, "idAccount": 1234}


async def test_session_only_for_tmate(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[FEED] = tmate("queued")
    response = await client.call_tmate(Endpoint.FEED_THE_COMMANDS, {"idInstallation": "X"})
    assert response.ok
    assert response.action_reference == "ref1"
    (body,) = logged_in.bodies(FEED)
    assert body == {"idInstallation": "X", "idSession": SESSION_ID}


async def test_no_session_fields(cloud: FakeCloud, client: CloudClient) -> None:
    reset = Endpoint.RESET_PASSWORD
    cloud.handlers[reset] = {"codEsito": "S", "msgEsito": "", "valRisultato": None}
    await CloudApi(client).reset_password("user@example.com")
    assert cloud.bodies(reset) == [{"email": "user@example.com"}]
    assert cloud.count(LOGIN) == 0
    assert client.session is None  # never logged in


async def test_caller_body_not_mutated(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[INSTALLATIONS] = {"codEsito": "S", "valRisultato": {}}
    body: JsonDict = {"a": 1}
    await client.call(Endpoint.INSTALLATION_LIST, body)
    assert body == {"a": 1}


async def test_lazy_login(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[INSTALLATIONS] = {"codEsito": "S", "valRisultato": {}}
    await client.call(Endpoint.INSTALLATION_LIST, {})
    await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(logged_in.bodies(LOGIN)) == 1


async def test_relogin_on_invalid_session(
    logged_in: FakeCloud, client: CloudClient, fixture_json: Callable[[str], Any]
) -> None:
    await client.login()
    logged_in.handlers[INSTALLATIONS] = sequence(
        {"codEsito": "E", "msgEsito": "Session not valid", "valRisultato": None},
        fixture_json("account-installation-list"),
    )
    result = await client.call(Endpoint.INSTALLATION_LIST, {})
    assert result["installationList"][0]["idInstallation"] == 456
    assert len(logged_in.bodies(LOGIN)) == 2
    assert len(logged_in.bodies(INSTALLATIONS)) == 2


async def test_relogin_gives_up(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[INSTALLATIONS] = {"codEsito": "E", "msgEsito": "Session not valid"}
    with pytest.raises(TelecoSessionExpiredError):
        await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(logged_in.bodies(LOGIN)) == 2


async def test_no_relogin_when_disabled(logged_in: FakeCloud) -> None:
    logged_in.handlers[INSTALLATIONS] = {"codEsito": "E", "msgEsito": "Session not valid"}
    async with aiohttp.ClientSession() as http:
        client = CloudClient(
            http, "user@example.com", "pw", base_url=logged_in.url, auto_relogin=False
        )
        with pytest.raises(TelecoApiError, match="Session not valid"):
            await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(logged_in.bodies(LOGIN)) == 1


async def test_api_error(logged_in: FakeCloud, client: CloudClient) -> None:
    payload = {"codEsito": "E", "msgEsito": "Installation not found", "valRisultato": None}
    logged_in.handlers[ROOMS] = payload
    with pytest.raises(TelecoApiError, match="Installation not found") as info:
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {"idInstallation": 1})
    assert info.value.code == "E"
    assert info.value.payload == payload


async def test_api_error_without_message(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[ROOMS] = {"codEsito": "E"}
    with pytest.raises(TelecoApiError, match="Unknown cloud error"):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_non_object_response(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[ROOMS] = [1, 2]
    with pytest.raises(TelecoApiError, match="unexpected response"):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_non_json_response(logged_in: FakeCloud, client: CloudClient) -> None:
    logged_in.handlers[ROOMS] = lambda _body: web.Response(
        text="<html>maintenance</html>", content_type="text/html"
    )
    with pytest.raises(TelecoError):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_http_500(cloud: FakeCloud, client: CloudClient) -> None:
    cloud.handlers[LOGIN] = lambda _body: web.Response(status=500)
    with pytest.raises(TelecoConnectionError, match="500"):
        await client.login()


async def test_connection_error(closed_port: int) -> None:
    async with aiohttp.ClientSession() as http:
        client = CloudClient(
            http, "user@example.com", "pw", base_url=f"http://127.0.0.1:{closed_port}"
        )
        with pytest.raises(TelecoConnectionError, match="account-login"):
            await client.login()


async def test_timeout(cloud: FakeCloud) -> None:
    released = asyncio.Event()

    async def stall(_body: JsonDict) -> JsonDict:
        await released.wait()
        return {"codEsito": "E"}

    cloud.handlers[LOGIN] = stall
    async with aiohttp.ClientSession() as http:
        client = CloudClient(
            http, "user@example.com", "pw", base_url=cloud.url, request_timeout=0.05
        )
        try:
            with pytest.raises(TelecoConnectionError):
                await client.login()
        finally:
            released.set()


async def test_logout(logged_in: FakeCloud, client: CloudClient) -> None:
    logout = Endpoint.ACCOUNT_LOGOUT
    logged_in.handlers[logout] = {"codEsito": "S"}
    await client.logout()  # not logged in: no request
    assert logged_in.bodies(logout) == []
    await client.login()
    await client.logout()
    assert logged_in.bodies(logout) == [{"idSession": SESSION_ID}]
    assert client.session is None


# --- api ----------------------------------------------------------------------------------


async def test_installations(
    logged_in: FakeCloud, api: CloudApi, fixture_json: Callable[[str], Any]
) -> None:
    logged_in.handlers[INSTALLATIONS] = fixture_json("account-installation-list")
    (inst,) = await api.installations()
    assert (inst.id_installation, inst.id_installation_device, inst.inst_code) == (
        456,
        789,
        "TESTCODE01",
    )
    assert inst.active_timer is True


async def test_rooms(
    logged_in: FakeCloud,
    api: CloudApi,
    installation: Installation,
    fixture_json: Callable[[str], Any],
) -> None:
    logged_in.handlers[ROOMS] = fixture_json("room-configuration-list")
    (room,) = await api.rooms(installation)
    assert [d.id_devicemodel for d in room.devices] == [27, 24, 32]
    assert logged_in.bodies(ROOMS)[0]["idInstallation"] == 456


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"id": 1, "idInstallation": "TESTCODE01", "idSession": "s", "nodeActive": True}, True),
        ({"id": 1, "idInstallation": "TESTCODE01", "idSession": "s", "nodeActive": False}, False),
        ({"id": 0, "idInstallation": None, "idSession": "s", "nodeActive": True}, False),
        ({"id": 0, "idSession": "s", "nodeActive": True}, False),
    ],
)
async def test_node_active(
    logged_in: FakeCloud,
    api: CloudApi,
    installation: Installation,
    payload: JsonDict,
    expected: bool,
) -> None:
    logged_in.handlers[NODE] = payload
    assert await api.node_active(installation) is expected
    assert logged_in.bodies(NODE) == [{"idInstallation": "TESTCODE01", "idSession": SESSION_ID}]


@pytest.fixture
def slats(fixture_json: Callable[[str], Any]) -> DeviceInfo:
    room = fixture_json("room-configuration-list")["valRisultato"]["roomList"][0]
    return DeviceInfo.from_json(room["deviceList"][0])


@pytest.mark.usefixtures("no_poll_delay")
async def test_send_and_wait(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    commands = build_device_command(slats, "LEVEL", "LEV3")
    logged_in.handlers[FEED] = tmate("queued")
    logged_in.acks = [tmate("RCV"), tmate("PROC")]
    ack = await api.send_and_wait(installation, commands)
    assert ack.message_text == "PROC"
    (feed,) = logged_in.bodies(FEED)
    assert feed == {
        "idInstallation": "TESTCODE01",
        "idScenario": 0,
        "isScenario": False,
        "commandsList": [commands[0].to_cloud()],
        "idSession": SESSION_ID,
    }
    assert (
        logged_in.bodies(ACK)
        == [{"id": "ref1", "idInstallation": "TESTCODE01", "idSession": SESSION_ID}] * 2
    )


@pytest.mark.usefixtures("no_poll_delay")
async def test_send_and_wait_until_ack(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    commands = build_device_command(slats, "OPEN_STOP_CLOSE", "OPEN")
    logged_in.handlers[FEED] = tmate("queued")
    logged_in.acks = [tmate("PROC"), tmate("ACK")]
    ack = await api.send_and_wait(installation, commands, until=("ACK",))
    assert ack.message_text == "ACK"
    assert len(logged_in.bodies(ACK)) == 2


async def test_send_without_reference(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.handlers[FEED] = tmate("queued", reference=None)
    response = await api.send_and_wait(
        installation, build_device_command(slats, "OPEN_STOP_CLOSE", "STOP")
    )
    assert response.message_text == "queued"
    assert logged_in.bodies(ACK) == []


@pytest.mark.usefixtures("no_poll_delay")
async def test_ack_timeout(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.handlers[FEED] = tmate("queued")
    logged_in.default_ack = tmate("RCV")
    with pytest.raises(TelecoAckTimeoutError, match="ref1"):
        await api.send_and_wait(
            installation, build_device_command(slats, "LEVEL", "LEV1"), ack_timeout=0.01
        )


@pytest.mark.usefixtures("no_poll_delay")
async def test_ack_error(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.handlers[FEED] = tmate("queued")
    logged_in.acks = [tmate("Box offline", kind="ERROR")]
    with pytest.raises(TelecoCommandError, match="Box offline"):
        await api.send_and_wait(installation, build_device_command(slats, "LEVEL", "LEV1"))


async def test_feed_rejected(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.handlers[FEED] = tmate("Installation offline", kind="ERROR", reference=None)
    with pytest.raises(TelecoCommandError, match="Installation offline"):
        await api.send_and_wait(installation, build_device_command(slats, "LEVEL", "LEV1"))
    assert logged_in.bodies(ACK) == []


async def test_feed_scenario(
    logged_in: FakeCloud, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.handlers[FEED] = tmate("queued")
    await api.feed_commands(
        installation, build_device_command(slats, "LEVEL", "LEV1"), scenario_id=7001
    )
    (feed,) = logged_in.bodies(FEED)
    assert (feed["idScenario"], feed["isScenario"]) == (7001, True)
