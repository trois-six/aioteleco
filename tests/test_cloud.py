"""Cloud client (envelope, session, re-login, errors) and the command/ack API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses

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

JsonDict = dict[str, Any]

LOGIN = "https://tmate.telecoautomation.com/teleco/services/account-login"
INSTALLATIONS = "https://tmate.telecoautomation.com/teleco/services/account-installation-list"
ROOMS = "https://tmate.telecoautomation.com/teleco/services/room-configuration-list"
FEED = "https://tmate.telecoautomation.com/teleco/services/tmate20/feedthecommands/"
ACK = "https://tmate.telecoautomation.com/teleco/services/tmate20/getackcommand/"
NODE = "https://tmate.telecoautomation.com/teleco/services/tmate20/nodestatus/"
SESSION_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def tmate(text: str, kind: str = "INFO", reference: str | None = "ref1") -> JsonDict:
    return {
        "MessageType": kind,
        "MessageID": "1",
        "MessageText": text,
        "ActionReference": reference,
    }


def bodies(mock: aioresponses, url: str) -> list[JsonDict]:
    return [
        call.kwargs["json"]
        for (method, u), calls in mock.requests.items()
        if method == "POST" and str(u) == url
        for call in calls
    ]


@pytest.fixture
async def client() -> AsyncIterator[CloudClient]:
    async with aiohttp.ClientSession() as http:
        yield CloudClient(http, "user@example.com", "not-a-real-password")


@pytest.fixture
def api(client: CloudClient) -> CloudApi:
    return CloudApi(client)


@pytest.fixture
def installation(fixture_json: Callable[[str], Any]) -> Installation:
    data = fixture_json("account-installation-list")["valRisultato"]["installationList"][0]
    return Installation.from_json(data)


@pytest.fixture
def logged_in(mock_http: aioresponses, fixture_json: Callable[[str], Any]) -> aioresponses:
    mock_http.post(LOGIN, payload=fixture_json("account-login"), repeat=True)
    return mock_http


# --- login -------------------------------------------------------------------------


async def test_login(logged_in: aioresponses, client: CloudClient) -> None:
    session = await client.login()
    assert session.id_session == SESSION_ID
    assert session.id_account == 1234
    assert client.id_account == 1234
    (body,) = bodies(logged_in, LOGIN)
    assert body == {
        "email": "user@example.com",
        "pwd": "not-a-real-password",
        "deviceSerial": "0000000000000000",
        "deviceDescription": "aioteleco",
    }


async def test_basic_auth(logged_in: aioresponses, client: CloudClient) -> None:
    await client.login()
    ((call,),) = logged_in.requests.values()
    auth = call.kwargs.get("auth")
    headers = call.kwargs.get("headers") or {}
    header = auth.encode() if auth is not None else headers.get("Authorization")
    assert header == "Basic dGVsZWNvOnRtYXRlMjA="


async def test_login_wrong_credentials(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(
        LOGIN,
        payload={"codEsito": "E", "msgEsito": "Wrong user name or password", "valRisultato": None},
    )
    with pytest.raises(TelecoAuthError, match="Wrong user name or password"):
        await client.login()
    assert client.session is None


async def test_login_error_without_message(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(LOGIN, payload={"codEsito": "E"})
    with pytest.raises(TelecoAuthError, match="Wrong user name or password"):
        await client.login()


async def test_login_registration_not_confirmed(
    mock_http: aioresponses, client: CloudClient
) -> None:
    mock_http.post(
        LOGIN,
        payload={
            "codEsito": "S",
            "msgEsito": "Request User registration not confirm",
            "valRisultato": {"idSession": "x", "idAccount": 1},
        },
    )
    with pytest.raises(TelecoAuthError, match="registration not confirm"):
        await client.login()
    assert client.session is None


async def test_login_ok_without_session(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(LOGIN, payload={"codEsito": "S", "msgEsito": "", "valRisultato": None})
    with pytest.raises(TelecoError):
        await client.login()


def test_not_logged_in(client: CloudClient) -> None:
    with pytest.raises(TelecoSessionExpiredError):
        _ = client.id_account


# --- session fields / envelope ----------------------------------------------------------


async def test_session_fields_injected(
    logged_in: aioresponses, client: CloudClient, fixture_json: Callable[[str], Any]
) -> None:
    logged_in.post(INSTALLATIONS, payload=fixture_json("account-installation-list"))
    result = await client.call(Endpoint.INSTALLATION_LIST, {"foo": 1})
    assert result["installationList"][0]["instCode"] == "TESTCODE01"
    (body,) = bodies(logged_in, INSTALLATIONS)
    assert body == {"foo": 1, "idSession": SESSION_ID, "idAccount": 1234}


async def test_session_only_for_tmate(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(FEED, payload=tmate("queued"))
    response = await client.call_tmate(Endpoint.FEED_THE_COMMANDS, {"idInstallation": "X"})
    assert response.ok
    assert response.action_reference == "ref1"
    (body,) = bodies(logged_in, FEED)
    assert body == {"idInstallation": "X", "idSession": SESSION_ID}


async def test_no_session_fields(mock_http: aioresponses, client: CloudClient) -> None:
    reset = "https://tmate.telecoautomation.com/teleco/services/reset-password"
    mock_http.post(reset, payload={"codEsito": "S", "msgEsito": "", "valRisultato": None})
    await CloudApi(client).reset_password("user@example.com")
    assert bodies(mock_http, reset) == [{"email": "user@example.com"}]
    assert client.session is None  # never logged in


async def test_caller_body_not_mutated(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(INSTALLATIONS, payload={"codEsito": "S", "valRisultato": {}})
    body: JsonDict = {"a": 1}
    await client.call(Endpoint.INSTALLATION_LIST, body)
    assert body == {"a": 1}


async def test_lazy_login(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(INSTALLATIONS, payload={"codEsito": "S", "valRisultato": {}}, repeat=True)
    await client.call(Endpoint.INSTALLATION_LIST, {})
    await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(bodies(logged_in, LOGIN)) == 1


async def test_relogin_on_invalid_session(
    logged_in: aioresponses, client: CloudClient, fixture_json: Callable[[str], Any]
) -> None:
    await client.login()
    logged_in.post(
        INSTALLATIONS,
        payload={"codEsito": "E", "msgEsito": "Session not valid", "valRisultato": None},
    )
    logged_in.post(INSTALLATIONS, payload=fixture_json("account-installation-list"))
    result = await client.call(Endpoint.INSTALLATION_LIST, {})
    assert result["installationList"][0]["idInstallation"] == 456
    assert len(bodies(logged_in, LOGIN)) == 2
    assert len(bodies(logged_in, INSTALLATIONS)) == 2


async def test_relogin_gives_up(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(
        INSTALLATIONS,
        payload={"codEsito": "E", "msgEsito": "Session not valid"},
        repeat=True,
    )
    with pytest.raises(TelecoSessionExpiredError):
        await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(bodies(logged_in, LOGIN)) == 2


async def test_no_relogin_when_disabled(logged_in: aioresponses) -> None:
    logged_in.post(INSTALLATIONS, payload={"codEsito": "E", "msgEsito": "Session not valid"})
    async with aiohttp.ClientSession() as http:
        client = CloudClient(http, "user@example.com", "pw", auto_relogin=False)
        with pytest.raises(TelecoApiError, match="Session not valid"):
            await client.call(Endpoint.INSTALLATION_LIST, {})
    assert len(bodies(logged_in, LOGIN)) == 1


async def test_api_error(logged_in: aioresponses, client: CloudClient) -> None:
    payload = {"codEsito": "E", "msgEsito": "Installation not found", "valRisultato": None}
    logged_in.post(ROOMS, payload=payload)
    with pytest.raises(TelecoApiError, match="Installation not found") as info:
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {"idInstallation": 1})
    assert info.value.code == "E"
    assert info.value.payload == payload


async def test_api_error_without_message(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(ROOMS, payload={"codEsito": "E"})
    with pytest.raises(TelecoApiError, match="Unknown cloud error"):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_non_object_response(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(ROOMS, payload=[1, 2])
    with pytest.raises(TelecoApiError, match="unexpected response"):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_non_json_response(logged_in: aioresponses, client: CloudClient) -> None:
    logged_in.post(ROOMS, body="<html>maintenance</html>", content_type="text/html")
    with pytest.raises(TelecoError):
        await client.call(Endpoint.ROOM_CONFIGURATION_LIST, {})


async def test_http_500(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(LOGIN, status=500)
    with pytest.raises(TelecoConnectionError):
        await client.login()


async def test_connection_error(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(LOGIN, exception=aiohttp.ClientConnectionError("boom"))
    with pytest.raises(TelecoConnectionError, match="boom"):
        await client.login()


async def test_timeout(mock_http: aioresponses, client: CloudClient) -> None:
    mock_http.post(LOGIN, exception=TimeoutError())
    with pytest.raises(TelecoConnectionError):
        await client.login()


async def test_logout(logged_in: aioresponses, client: CloudClient) -> None:
    logout = "https://tmate.telecoautomation.com/teleco/services/account-logout"
    logged_in.post(logout, payload={"codEsito": "S"})
    await client.logout()  # not logged in: no request
    assert bodies(logged_in, logout) == []
    await client.login()
    await client.logout()
    assert bodies(logged_in, logout) == [{"idSession": SESSION_ID}]
    assert client.session is None


# --- api ----------------------------------------------------------------------------------


async def test_installations(
    logged_in: aioresponses, api: CloudApi, fixture_json: Callable[[str], Any]
) -> None:
    logged_in.post(INSTALLATIONS, payload=fixture_json("account-installation-list"))
    (inst,) = await api.installations()
    assert (inst.id_installation, inst.id_installation_device, inst.inst_code) == (
        456,
        789,
        "TESTCODE01",
    )
    assert inst.active_timer is True


async def test_rooms(
    logged_in: aioresponses,
    api: CloudApi,
    installation: Installation,
    fixture_json: Callable[[str], Any],
) -> None:
    logged_in.post(ROOMS, payload=fixture_json("room-configuration-list"))
    (room,) = await api.rooms(installation)
    assert [d.id_devicemodel for d in room.devices] == [27, 24, 32]
    assert bodies(logged_in, ROOMS)[0]["idInstallation"] == 456


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
    logged_in: aioresponses,
    api: CloudApi,
    installation: Installation,
    payload: JsonDict,
    expected: bool,
) -> None:
    logged_in.post(NODE, payload=payload)
    assert await api.node_active(installation) is expected
    assert bodies(logged_in, NODE) == [{"idInstallation": "TESTCODE01", "idSession": SESSION_ID}]


@pytest.fixture
def slats(fixture_json: Callable[[str], Any]) -> DeviceInfo:
    room = fixture_json("room-configuration-list")["valRisultato"]["roomList"][0]
    return DeviceInfo.from_json(room["deviceList"][0])


@pytest.mark.usefixtures("no_poll_delay")
async def test_send_and_wait(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    commands = build_device_command(slats, "LEVEL", "LEV3")
    logged_in.post(FEED, payload=tmate("queued"))
    logged_in.post(ACK, payload=tmate("RCV"))
    logged_in.post(ACK, payload=tmate("PROC"))
    ack = await api.send_and_wait(installation, commands)
    assert ack.message_text == "PROC"
    (feed,) = bodies(logged_in, FEED)
    assert feed == {
        "idInstallation": "TESTCODE01",
        "idScenario": 0,
        "isScenario": False,
        "commandsList": [commands[0].to_cloud()],
        "idSession": SESSION_ID,
    }
    assert (
        bodies(logged_in, ACK)
        == [{"id": "ref1", "idInstallation": "TESTCODE01", "idSession": SESSION_ID}] * 2
    )


@pytest.mark.usefixtures("no_poll_delay")
async def test_send_and_wait_until_ack(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    commands = build_device_command(slats, "OPEN_STOP_CLOSE", "OPEN")
    logged_in.post(FEED, payload=tmate("queued"))
    logged_in.post(ACK, payload=tmate("PROC"))
    logged_in.post(ACK, payload=tmate("ACK"))
    ack = await api.send_and_wait(installation, commands, until=("ACK",))
    assert ack.message_text == "ACK"
    assert len(bodies(logged_in, ACK)) == 2


async def test_send_without_reference(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.post(FEED, payload=tmate("queued", reference=None))
    response = await api.send_and_wait(
        installation, build_device_command(slats, "OPEN_STOP_CLOSE", "STOP")
    )
    assert response.message_text == "queued"
    assert bodies(logged_in, ACK) == []


@pytest.mark.usefixtures("no_poll_delay")
async def test_ack_timeout(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.post(FEED, payload=tmate("queued"))
    logged_in.post(ACK, payload=tmate("RCV"), repeat=True)
    with pytest.raises(TelecoAckTimeoutError, match="ref1"):
        await api.send_and_wait(
            installation, build_device_command(slats, "LEVEL", "LEV1"), ack_timeout=0.01
        )


@pytest.mark.usefixtures("no_poll_delay")
async def test_ack_error(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.post(FEED, payload=tmate("queued"))
    logged_in.post(ACK, payload=tmate("Box offline", kind="ERROR"))
    with pytest.raises(TelecoCommandError, match="Box offline"):
        await api.send_and_wait(installation, build_device_command(slats, "LEVEL", "LEV1"))


async def test_feed_rejected(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.post(FEED, payload=tmate("Installation offline", kind="ERROR", reference=None))
    with pytest.raises(TelecoCommandError, match="Installation offline"):
        await api.send_and_wait(installation, build_device_command(slats, "LEVEL", "LEV1"))
    assert bodies(logged_in, ACK) == []


async def test_feed_scenario(
    logged_in: aioresponses, api: CloudApi, installation: Installation, slats: DeviceInfo
) -> None:
    logged_in.post(FEED, payload=tmate("queued"))
    await api.feed_commands(
        installation, build_device_command(slats, "LEVEL", "LEV1"), scenario_id=7001
    )
    (feed,) = bodies(logged_in, FEED)
    assert (feed["idScenario"], feed["isScenario"]) == (7001, True)
