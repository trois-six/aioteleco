"""Box-level command builders and the scenario string stored by the box."""

from __future__ import annotations

from typing import Any

import pytest

from aioteleco.commands import feed_post, system_command
from aioteleco.models import Installation, Room
from aioteleco.system import (
    get_feedback_command,
    read_memory_command,
    scenario_string,
    set_ap_channel_command,
    set_wifi_command,
    tx_command,
    update_device_command,
)
from conftest import load_json


def rooms() -> list[Room]:
    data: Any = load_json("room-configuration-list")
    return [Room.from_json(r) for r in data["valRisultato"]["roomList"]]


def devices() -> dict[int, Any]:
    return {d.id_installation_device: d for r in rooms() for d in r.devices}


def command(device: Any, id_command: int) -> Any:
    return next(c for c in device.commands if c.id_installation_device_command == id_command)


def test_scenario_string_channel_and_argb() -> None:
    devs = devices()
    slats, light = devs[2001], devs[2003]
    steps = [
        (command(slats, 3005), slats, "LEV2"),
        (command(light, 3023), light, "A080R255G128B000"),
    ]
    assert scenario_string(7001, steps) == "7001N02 01C0200000062000007d1 03R50ff800089000007d3"


def test_scenario_string_numeric_and_default_channel() -> None:
    light = devices()[2003]
    color = command(light, 3023)  # no lowlevel command
    assert scenario_string(1, [(color, light, "5")]) == "1N01 03L0500000089000007d3"
    assert scenario_string(1, [(color, light, "PARTY")]) == "1N01 03C0800000089000007d3"
    assert scenario_string(2, []) == "2N00"


def test_get_feedback_targets_the_device() -> None:
    slats = devices()[2001]
    cmd = get_feedback_command(slats)
    assert (cmd.id_installation_device, cmd.device_code) == (2001, "1")
    assert (cmd.command_action, cmd.command_param, cmd.command_id) == ("GET_FEEDBACK", "PEG", 122)


def test_update_device() -> None:
    awning = devices()[2002]  # feedback S
    cmd = update_device_command(awning, 789)
    assert cmd.command_param == "Feedback: S Timers: S"
    assert (cmd.id_installation_device, cmd.device_code, cmd.lowlevel_command) == (2002, "2", "789")


def test_misc_box_commands() -> None:
    assert set_wifi_command(789, "Net", "pw").command_param == "SSID: Net PASS: pw"
    assert set_ap_channel_command(789, static=True).command_param == "20W"
    assert set_ap_channel_command(789, static=False).command_param == "06W"
    assert read_memory_command(789, "0100", "16").command_param == "ADDR: 0100 NB: 16R"


@pytest.mark.parametrize(
    ("action", "command_id"),
    [
        ("PAIR_BUTTON", 108),
        ("UNPAIR_BUTTON", 109),
        ("PAIR_TX", 127),
        ("UNPAIR_TX", 128),
        ("RESET_TX", 129),
    ],
)
def test_tx_command_ids(action: str, command_id: int) -> None:
    cmd = tx_command(action, "7", 9001)
    assert (cmd.command_id, cmd.id_installation_device, cmd.device_code) == (command_id, 9001, "0")


def test_tx_command_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="unknown remote command"):
        tx_command("FORMAT", "", 1)


def test_feed_post_forced_scenario_flag() -> None:
    body = feed_post("CODE", [system_command(789, "SYNC_BOARD")], is_scenario=True)
    assert (body["idScenario"], body["isScenario"]) == (0, True)
    assert feed_post("CODE", [])["isScenario"] is False


@pytest.mark.parametrize(
    ("firmware", "workdays", "expected"),
    [
        ("1.3.3", "", True),
        ("1.4.0.2", "1.0.0", True),
        ("1.3.2", "1.0.0", False),
        ("1.2.9", "2.0.0", True),  # hardware 2 always qualifies
        ("V2.10", "2", True),
    ],
)
def test_firmware_at_least(firmware: str, workdays: str, expected: bool) -> None:
    inst = Installation.from_json({"firmwareVersion": firmware, "workdays": workdays})
    assert inst.firmware_at_least("1.3.3") is expected
