"""Command selection (port of ``DaisyApplication#sendCommand``) and wire encodings."""

from __future__ import annotations

import json
from typing import Any

import pytest

from aioteleco.commands import (
    WireCommand,
    build_device_command,
    build_scenario_commands,
    feed_post,
    local_payload,
    system_command,
    to_wire,
)
from aioteleco.exceptions import TelecoUnsupportedError
from aioteleco.models import DeviceInfo


def make_device(
    model: int,
    commands: list[tuple[str, str, str, int]],
    *,
    feedback: bool = False,
    sub_model: str = "",
    device_id: int = 900,
    device_index: int = 4,
) -> DeviceInfo:
    """A device whose commands are ``(action, param, lowlevel, command model)``."""
    return DeviceInfo.from_json(
        {
            "idInstallationDevice": device_id,
            "idDevicemodel": model,
            "deviceIndex": device_index,
            "label": f"model {model}",
            "remoteControlCode": sub_model,
            "feedback": "S" if feedback else "N",
            "deviceCommandList": [
                {
                    "idInstallationDeviceCommand": 10_000 + i,
                    "idInstallationDevice": device_id,
                    "idDevicetypeCommandModel": cmd_model,
                    "commandAction": action,
                    "commandParam": param,
                    "lowlevelCommand": low,
                }
                for i, (action, param, low, cmd_model) in enumerate(commands)
            ],
        }
    )


def one(device: DeviceInfo, action: str, param: str) -> WireCommand:
    out = build_device_command(device, action, param)
    assert len(out) == 1
    return out[0]


# --- selection ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("param", "model_id", "low"),
    [("OPEN", 94, "CH4"), ("STOP", 95, "CH7"), ("CLOSE", 96, "CH1")],
)
def test_open_stop_close(
    device_infos: dict[str, DeviceInfo], param: str, model_id: int, low: str
) -> None:
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", param)
    assert cmd.command_id == model_id
    assert cmd.id_devicetype_command_model == model_id
    assert cmd.command_action == "OPEN_STOP_CLOSE"
    assert cmd.command_param == param
    assert cmd.lowlevel_command == low
    assert cmd.device_code == "1"
    assert cmd.id_installation_device == 2001
    assert cmd.id_installation_device_command == 3000 + model_id - 93


def test_match_ignores_action(device_infos: dict[str, DeviceInfo]) -> None:
    # Only the parameter is compared, like the app: a bogus action still hits OPEN.
    cmd = one(device_infos["slats"], "WHATEVER", "OPEN")
    assert cmd.command_id == 94
    assert cmd.command_action == "OPEN_STOP_CLOSE"


def test_match_by_containment(device_infos: dict[str, DeviceInfo]) -> None:
    # commandParam "OPEN" is contained in the requested value.
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", "XOPENX")
    assert cmd.command_id == 94
    assert cmd.command_param == "OPEN"


def test_first_match_wins() -> None:
    dev = make_device(
        16, [("POWER", "ON", "CH1", 1), ("POWER", "ON", "CH2", 2), ("POWER", "OFF", "CH8", 3)]
    )
    assert one(dev, "POWER", "ON").command_id == 1
    assert one(dev, "POWER", "OFF").command_id == 3


@pytest.mark.parametrize(
    ("step", "model_id", "low"),
    [(1, 97, "CH1"), (2, 98, "CH2"), (3, 99, "CH3"), (4, 100, "CH4")],
)
def test_level_steps(
    device_infos: dict[str, DeviceInfo], step: int, model_id: int, low: str
) -> None:
    cmd = one(device_infos["slats"], "LEVEL", f"LEV{step}")
    assert cmd.command_id == model_id
    assert cmd.command_action == "LEVEL"
    assert cmd.command_param == f"LEV{step}"
    assert cmd.lowlevel_command == low


def test_template_substitution(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["light"], "COLOR", "A100R255G000B000")
    assert cmd.command_id == 137
    assert cmd.command_action == "COLOR"
    assert cmd.command_param == "A100R255G000B000"
    assert cmd.id_installation_device_command == 3023
    assert cmd.device_code == "3"


def test_template_needs_same_action(device_infos: dict[str, DeviceInfo]) -> None:
    # The "0" command is only a template for its own action.
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(device_infos["light"], "LEVEL", "50")


def test_last_template_wins() -> None:
    dev = make_device(34, [("LEVEL", "0", "CH1", 1), ("LEVEL", "0", "CH2", 2)])
    cmd = one(dev, "LEVEL", "42")
    assert cmd.command_id == 2
    assert cmd.command_param == "42"


def test_match_preferred_over_template() -> None:
    dev = make_device(32, [("COLOR", "0", "", 137), ("POWER", "ON", "CH1", 146)])
    assert one(dev, "POWER", "ON").command_id == 146


def test_power_on_off(device_infos: dict[str, DeviceInfo]) -> None:
    assert one(device_infos["light"], "POWER", "ON").command_id == 146
    off = one(device_infos["light"], "POWER", "OFF")
    assert (off.command_id, off.lowlevel_command) == (147, "CH8")


def test_feedback_suffix(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["awning"], "OPEN_STOP_CLOSE", "OPEN")
    assert cmd.command_action == "OPEN_STOP_CLOSE-F"
    assert cmd.command_param == "OPEN"
    assert (cmd.command_id, cmd.lowlevel_command) == (75, "CH5")


def test_feedback_does_not_alter_the_device(device_infos: dict[str, DeviceInfo]) -> None:
    one(device_infos["awning"], "OPEN_STOP_CLOSE", "OPEN")
    one(device_infos["awning"], "OPEN_STOP_CLOSE", "OPEN")
    assert device_infos["awning"].commands[0].command_action == "OPEN_STOP_CLOSE"


def test_l_flag(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", "OPEN-L")
    assert cmd.command_id == 94
    assert cmd.command_param == "OPEN"
    assert cmd.command_action == "OPEN_STOP_CLOSE-L"


def test_l_flag_after_feedback(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["awning"], "OPEN_STOP_CLOSE", "CLOSE-L")
    assert cmd.command_action == "OPEN_STOP_CLOSE-F-L"
    assert cmd.command_param == "CLOSE"
    assert cmd.command_id == 77


def test_l_flag_on_template(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["light"], "COLOR", "A050R001G002B003-L")
    assert cmd.command_param == "A050R001G002B003"
    assert cmd.command_action == "COLOR-L"


@pytest.mark.parametrize(
    ("param", "model_id", "low"),
    [("OPEN;S", 94, "CH14"), ("CLOSE;S", 96, "CH11"), ("STOP;anything", 95, "CH17")],
)
def test_semicolon_flag(
    device_infos: dict[str, DeviceInfo], param: str, model_id: int, low: str
) -> None:
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", param)
    assert cmd.command_id == model_id
    assert cmd.command_param == param.split(";")[0]
    assert cmd.lowlevel_command == low


def test_semicolon_flag_does_not_alter_the_device(device_infos: dict[str, DeviceInfo]) -> None:
    one(device_infos["slats"], "OPEN_STOP_CLOSE", "OPEN;S")
    assert device_infos["slats"].commands[0].lowlevel_command == "CH4"


@pytest.mark.parametrize(
    ("param", "model_id", "wire_param"),
    [
        ("START_O", 94, "START"),
        ("END_O_A", 94, "END_A"),
        ("END_O_M", 94, "END_M"),
        ("START_C", 96, "START"),
        ("END_C_A", 96, "END_A"),
        ("END_C_M", 96, "END_M"),
    ],
)
def test_start_end_aliases(
    device_infos: dict[str, DeviceInfo], param: str, model_id: int, wire_param: str
) -> None:
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", param)
    assert cmd.command_id == model_id
    assert cmd.command_param == wire_param
    assert cmd.command_action == "OPEN_STOP_CLOSE"


def test_alias_with_feedback(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["awning"], "OPEN_STOP_CLOSE", "END_C_M")
    assert (cmd.command_id, cmd.command_param, cmd.command_action) == (
        77,
        "END_M",
        "OPEN_STOP_CLOSE-F",
    )


FAN = [
    ("POWER", "ON", "CH1", 1),
    ("POWER", "OFF", "CH8", 2),
    ("SPEED", "33", "CH2", 3),
    ("SPEED", "67", "CH3", 4),
    ("SPEED", "100", "CH4", 5),
]


@pytest.mark.parametrize(("speed", "model_id"), [("33", 3), ("67", 4), ("100", 5)])
def test_speed(speed: str, model_id: int) -> None:
    cmd = one(make_device(19, FAN), "SPEED", speed)
    assert cmd.command_id == model_id
    assert cmd.command_param == speed


@pytest.mark.parametrize("speed", ["50", "3", "1000", "x33"])
def test_speed_needs_exact_value(speed: str) -> None:
    # SPEED commands are never matched by containment.
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(make_device(19, FAN), "SPEED", speed)


def test_speed_value_is_not_in_speed_list() -> None:
    dev = make_device(19, [("SPEED", "50", "CH2", 3)])
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(dev, "SPEED", "50")


@pytest.mark.parametrize("percent", ["25", "50", "75", "100", "0"])
def test_percent_params_not_matched_by_containment(percent: str) -> None:
    dev = make_device(17, [("LEVEL", percent, "CH1", 1), ("LEVEL", "0", "CH2", 2)])
    cmd = one(dev, "LEVEL", percent)
    # The "percent" command is skipped; the LEVEL template takes the value.
    assert cmd.command_id == 2
    assert cmd.command_param == percent


@pytest.mark.parametrize("percent", ["25", "50", "75", "100"])
def test_percent_params_without_template(percent: str) -> None:
    dev = make_device(17, [("LEVEL", percent, "CH1", 1)])
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(dev, "LEVEL", percent)


def test_non_percent_numeric_is_matched() -> None:
    dev = make_device(17, [("LEVEL", "33", "CH1", 1)])
    assert one(dev, "LEVEL", "33").command_id == 1


PRESETS = [
    ("POWER", "ON", "CH1", 1),
    ("POWER", "OFF", "CH8", 2),
    ("COLOR", "RED", "CH2", 3),
    ("COLOR", "BLUE", "CH4", 4),
    ("CYCLE", "CYCLE", "CH5", 5),
]


def test_model26_preset_name() -> None:
    cmd = one(make_device(26, PRESETS), "COLOR", "RED")
    assert (cmd.command_id, cmd.command_param, cmd.lowlevel_command) == (3, "RED", "CH2")


def test_model26_preset_with_argb_is_stripped() -> None:
    cmd = one(make_device(26, PRESETS), "COLOR", "BLUEA100R000G000B255")
    assert cmd.command_id == 4
    assert cmd.command_param == "A100R000G000B255"


def test_preset_not_stripped_on_other_models() -> None:
    cmd = one(make_device(32, PRESETS), "COLOR", "BLUEA100R000G000B255")
    assert cmd.command_id == 4
    assert cmd.command_param == "BLUE"


RETRACTABLE = [
    ("OPEN_STOP_CLOSE", "OPEN", "CH5", 1),
    ("OPEN_STOP_CLOSE", "STOP", "CH7", 2),
    ("OPEN_STOP_CLOSE", "CLOSE", "CH8", 3),
]


@pytest.mark.parametrize("sub_model", ["2", "3"])
@pytest.mark.parametrize(("param", "low"), [("OPEN", "CH8"), ("CLOSE", "CH5"), ("STOP", "CH7")])
def test_model44_channel_swap(sub_model: str, param: str, low: str) -> None:
    dev = make_device(44, RETRACTABLE, sub_model=sub_model)
    assert one(dev, "OPEN_STOP_CLOSE", param).lowlevel_command == low
    # The device's own command list is untouched.
    assert [c.lowlevel_command for c in dev.commands] == ["CH5", "CH7", "CH8"]


@pytest.mark.parametrize("sub_model", ["", "1", "4"])
def test_model44_no_swap_for_other_submodels(sub_model: str) -> None:
    dev = make_device(44, RETRACTABLE, sub_model=sub_model)
    assert one(dev, "OPEN_STOP_CLOSE", "OPEN").lowlevel_command == "CH5"


def test_swap_only_on_model44() -> None:
    dev = make_device(45, RETRACTABLE, sub_model="2")
    assert one(dev, "OPEN_STOP_CLOSE", "OPEN").lowlevel_command == "CH5"


def test_model42_every_command_is_a_template() -> None:
    dev = make_device(42, [("SLIDER", "OPEN", "CH1", 195), ("SLIDER", "ON", "CH2", 196)])
    cmd = one(dev, "ANY", "OPEN")
    # No containment match at all: the last command takes the raw value.
    assert cmd.command_id == 196
    assert cmd.command_param == "OPEN"
    assert cmd.command_action == "SLIDER"
    assert cmd.lowlevel_command == "CH2"


def test_model42_without_commands() -> None:
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(make_device(42, []), "ANY", "1")


def test_no_match_no_template(device_infos: dict[str, DeviceInfo]) -> None:
    with pytest.raises(TelecoUnsupportedError, match="Pergola slats"):
        build_device_command(device_infos["slats"], "POWER", "ON")


def test_no_match_on_empty_device() -> None:
    with pytest.raises(TelecoUnsupportedError):
        build_device_command(make_device(16, []), "POWER", "ON")


def test_id_installation_device_falls_back_to_device() -> None:
    dev = make_device(16, [("POWER", "ON", "CH1", 1)], device_id=321)
    dev.commands[0].id_installation_device = 0
    assert one(dev, "POWER", "ON").id_installation_device == 321


# --- scenario / system commands -----------------------------------------------------


def test_build_scenario_commands(device_infos: dict[str, DeviceInfo]) -> None:
    slats, light = device_infos["slats"], device_infos["light"]
    out = build_scenario_commands(
        [(slats.commands[4], slats, "ignored"), (light.commands[2], light, "A010R020G030B040")]
    )
    assert [(c.command_id, c.command_param) for c in out] == [
        (98, "LEV2"),
        (137, "A010R020G030B040"),
    ]
    assert [c.device_code for c in out] == ["1", "3"]


def test_system_command() -> None:
    cmd = system_command(789, "GET_SIGNAL")
    assert cmd.command_id == 122
    assert cmd.to_cloud() == {
        "idInstallationDevice": 789,
        "deviceCode": "0",
        "idInstallationDeviceCommand": 0,
        "commandAction": "GET_SIGNAL",
        "commandParam": "",
        "lowlevelCommand": "",
        "commandId": 122,
        "idDevicetypeCommandModel": 122,
        "commandIndex": 0,
        "commandStatus": 0,
        "commandreceived": 0,
        "commandReceivedUR": "0",
        "commandProcessed": 0,
    }


def test_system_command_options() -> None:
    cmd = system_command(789, "UP_TIMERS", "x", device_code="5", lowlevel="CH1")
    assert (cmd.device_code, cmd.command_param, cmd.lowlevel_command) == ("5", "x", "CH1")


# --- wire encodings ------------------------------------------------------------------


def test_to_cloud(device_infos: dict[str, DeviceInfo]) -> None:
    cloud = one(device_infos["awning"], "OPEN_STOP_CLOSE", "OPEN").to_cloud()
    assert list(cloud) == [
        "idInstallationDevice",
        "deviceCode",
        "idInstallationDeviceCommand",
        "commandAction",
        "commandParam",
        "lowlevelCommand",
        "commandId",
        "idDevicetypeCommandModel",
        "commandIndex",
        "commandStatus",
        "commandreceived",
        "commandReceivedUR",
        "commandProcessed",
    ]
    assert cloud["idInstallationDevice"] == 2002
    assert cloud["deviceCode"] == "2"
    assert cloud["idInstallationDeviceCommand"] == 3011
    assert cloud["commandAction"] == "OPEN_STOP_CLOSE-F"
    assert cloud["commandParam"] == "OPEN"
    assert cloud["lowlevelCommand"] == "CH5"
    assert cloud["commandId"] == cloud["idDevicetypeCommandModel"] == 75


def test_feed_post(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["slats"], "LEVEL", "LEV3")
    body = feed_post("TESTCODE01", [cmd])
    assert body == {
        "idInstallation": "TESTCODE01",
        "idScenario": 0,
        "isScenario": False,
        "commandsList": [cmd.to_cloud()],
    }
    assert "idSession" not in body


def test_feed_post_scenario(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["slats"], "LEVEL", "LEV3")
    body = feed_post("TESTCODE01", [cmd, cmd], scenario_id=7001)
    assert body["idScenario"] == 7001
    assert body["isScenario"] is True
    assert len(body["commandsList"]) == 2


def test_local_payload_exact(device_infos: dict[str, DeviceInfo]) -> None:
    cmd = one(device_infos["slats"], "OPEN_STOP_CLOSE", "OPEN")
    assert local_payload("TESTCODE01", [cmd]) == (
        '{"idIn":"TESTCODE01","idSc":0,"isSc":false,"cL":[{"idInDe":2001,"deCo":"1",'
        '"cmId":94,"coAc":"OPEN_STOP_CLOSE","coPa":"OPEN","low":"CH4","coSta":0}]}'
    )


def test_local_payload_scenario(device_infos: dict[str, DeviceInfo]) -> None:
    slats, light = device_infos["slats"], device_infos["light"]
    cmds = build_scenario_commands(
        [(slats.commands[4], slats, "LEV2"), (light.commands[2], light, "A080R255G128B000")]
    )
    payload = local_payload("TESTCODE01", cmds, scenario_id=7001)
    assert payload == (
        '{"idIn":"TESTCODE01","idSc":7001,"isSc":true,"cL":['
        '{"idInDe":2001,"deCo":"1","cmId":98,"coAc":"LEVEL","coPa":"LEV2","low":"CH2","coSta":0},'
        '{"idInDe":2003,"deCo":"3","cmId":137,"coAc":"COLOR","coPa":"A080R255G128B000",'
        '"low":"","coSta":0}]}'
    )
    assert json.loads(payload)["isSc"] is True


def _slider(model_id: int, param: str) -> WireCommand:
    dev = make_device(42, [("SLIDER", "0", "CH1", model_id)])
    return to_wire(dev.commands[0], dev, param=param)


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        ("5§120§0", "05-120-000-"),
        ("0", "000-"),
        ("99§100§255", "099-100-255-"),
        ("50", "050-"),
    ],
)
@pytest.mark.parametrize("model_id", [195, 198, 201])
def test_local_payload_slider_reencoding(model_id: int, param: str, expected: str) -> None:
    payload: dict[str, Any] = json.loads(local_payload("TESTCODE01", [_slider(model_id, param)]))
    assert payload["cL"][0]["coPa"] == expected
    assert payload["cL"][0]["cmId"] == model_id


@pytest.mark.parametrize("model_id", [194, 202])
def test_local_payload_outside_slider_models(model_id: int) -> None:
    payload: dict[str, Any] = json.loads(
        local_payload("TESTCODE01", [_slider(model_id, "5§120§0")])
    )
    assert payload["cL"][0]["coPa"] == "5§120§0"


def test_local_payload_is_not_json_escaped() -> None:
    # Built by concatenation like the app: quotes are not escaped.
    cmd = system_command(789, "SET", 'a"b')
    assert '"coPa":"a"b"' in local_payload("TESTCODE01", [cmd])
