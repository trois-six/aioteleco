"""LAN channel: one TCP exchange per command with a fake box on 127.0.0.1."""

from __future__ import annotations

import json

import pytest

from aioteleco.commands import WireCommand, system_command
from aioteleco.exceptions import TelecoConnectionError, TelecoLocalError
from aioteleco.local.client import LocalClient
from aioteleco.local.crypto import decrypt
from conftest import FakeBox

EXPECTED = (
    '{"idIn":"TESTCODE01","idSc":0,"isSc":false,"cL":[{"idInDe":2001,"deCo":"1",'
    '"cmId":94,"coAc":"OPEN_STOP_CLOSE","coPa":"OPEN","low":"CH4","coSta":0}]}'
)


def open_command() -> WireCommand:
    return WireCommand(
        id_installation_device=2001,
        device_code="1",
        id_installation_device_command=3001,
        command_action="OPEN_STOP_CLOSE",
        command_param="OPEN",
        lowlevel_command="CH4",
        id_devicetype_command_model=94,
    )


async def test_send_ack(box: FakeBox) -> None:
    reply = await LocalClient("127.0.0.1", port=box.port).send("TESTCODE01", [open_command()])
    assert reply == "ACK"
    (frame,) = box.frames
    assert frame[0] == "M"
    message, timestamp, scenario = decrypt(frame)
    assert message == EXPECTED
    assert timestamp > 1_700_000_000
    assert scenario is False


async def test_reply_line_containing_ack(box: FakeBox) -> None:
    box.reply = b"OK ACK 12\r\nignored\n"
    reply = await LocalClient("127.0.0.1", port=box.port).send("TESTCODE01", [open_command()])
    assert reply == "OK ACK 12"


async def test_scenario_frame(box: FakeBox) -> None:
    client = LocalClient("127.0.0.1", port=box.port)
    await client.send("TESTCODE01", [open_command(), open_command()], scenario_id=7001)
    (frame,) = box.frames
    assert frame[0] == "S"
    message, _, scenario = decrypt(frame)
    assert scenario is True
    payload = json.loads(message)
    assert (payload["idSc"], payload["isSc"], len(payload["cL"])) == (7001, True, 2)


async def test_refused_by_box(box: FakeBox) -> None:
    box.reply = b"NOK\n"
    with pytest.raises(TelecoLocalError, match="NOK"):
        await LocalClient("127.0.0.1", port=box.port).send("TESTCODE01", [open_command()])
    assert len(box.frames) == 1


async def test_connection_closed_without_reply(box: FakeBox) -> None:
    box.reply = b""
    with pytest.raises(TelecoLocalError):
        await LocalClient("127.0.0.1", port=box.port).send("TESTCODE01", [open_command()])


async def test_no_reply_is_reported_as_sent(box: FakeBox, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aioteleco.local.client.LOCAL_READ_TIMEOUT", 0.2)
    box.reply = None
    reply = await LocalClient("127.0.0.1", port=box.port).send("TESTCODE01", [open_command()])
    assert reply == ""
    assert len(box.frames) == 1


async def test_connection_refused(closed_port: int) -> None:
    client = LocalClient("127.0.0.1", port=closed_port)
    with pytest.raises(TelecoLocalError, match="cannot connect") as info:
        await client.send("TESTCODE01", [open_command()])
    assert isinstance(info.value, TelecoConnectionError)


async def test_no_command() -> None:
    with pytest.raises(ValueError, match="no command"):
        await LocalClient("127.0.0.1", port=1).send("TESTCODE01", [])


async def test_system_command_frame(box: FakeBox) -> None:
    await LocalClient("127.0.0.1", port=box.port).send(
        "TESTCODE01", [system_command(789, "GET_SIGNAL")]
    )
    (payload,) = box.payloads
    assert payload["cL"][0] == {
        "idInDe": 789,
        "deCo": "0",
        "cmId": 122,
        "coAc": "GET_SIGNAL",
        "coPa": "",
        "low": "",
        "coSta": 0,
    }


async def test_diagnostic(box: FakeBox) -> None:
    box.reply = b"0000000001,0000000002\n"
    reply = await LocalClient("127.0.0.1", port=box.port).diagnostic()
    assert reply == "0000000001,0000000002"
    assert box.messages == ["DIAGNOSTIC" * 10]
