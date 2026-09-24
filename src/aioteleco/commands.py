"""Building device commands the way the Daisy app does.

The cloud gives every device its own list of commands (``deviceCommandList``).
The app never hard-codes command ids: a screen asks for an ``(action, param)``
pair (e.g. ``("OPEN_STOP_CLOSE", "OPEN")``) and ``DaisyApplication#sendCommand``
picks the matching command from that list. This module is a port of that
selection, plus the wire
encodings of a command for the cloud (``CommandCloud``) and for the LAN channel
(``DaisyApplication#convertForDM``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .const import SYSTEM_COMMAND_ID
from .exceptions import TelecoUnsupportedError
from .models import Command, DeviceInfo

JsonDict = dict[str, Any]

_OPEN_ALIASES = ("START_O", "END_O_M", "END_O_A")
_CLOSE_ALIASES = ("START_C", "END_C_M", "END_C_A")
_PERCENT_PARAMS = ("25", "50", "75", "100", "0")
_SPEED_PARAMS = ("100", "33", "67")
_SLIDER_COMMAND_MODELS = range(195, 202)  # "§"-separated values re-encoded for the LAN
_MODEL_GENERIC_SLIDER = 42
_MODEL_RGB_PRESETS = 26
_MODEL_RETRACTABLE_SLATS = 44
_CH5_CH8_SWAP_SUBMODELS = ("2", "3")


@dataclass(slots=True)
class WireCommand:
    """One entry of ``commandsList`` (the app's ``CommandCloud``)."""

    id_installation_device: int
    device_code: str  # the device *index*, as a string
    id_installation_device_command: int
    command_action: str
    command_param: str
    lowlevel_command: str
    id_devicetype_command_model: int
    command_index: int = 0

    @property
    def command_id(self) -> int:
        return self.id_devicetype_command_model

    def to_cloud(self) -> JsonDict:
        return {
            "idInstallationDevice": self.id_installation_device,
            "deviceCode": self.device_code,
            "idInstallationDeviceCommand": self.id_installation_device_command,
            "commandAction": self.command_action,
            "commandParam": self.command_param,
            "lowlevelCommand": self.lowlevel_command,
            "commandId": self.command_id,
            "idDevicetypeCommandModel": self.id_devicetype_command_model,
            "commandIndex": self.command_index,
            "commandStatus": 0,
            "commandreceived": 0,
            "commandReceivedUR": "0",
            "commandProcessed": 0,
        }


def to_wire(command: Command, device: DeviceInfo, param: str | None = None) -> WireCommand:
    """``CommandDao#toCommandCloud``."""
    return WireCommand(
        id_installation_device=command.id_installation_device or device.id_installation_device,
        device_code=str(device.device_index),
        id_installation_device_command=command.id_installation_device_command,
        command_action=command.command_action,
        command_param=command.command_param if param is None else param,
        lowlevel_command=command.lowlevel_command,
        id_devicetype_command_model=command.id_devicetype_command_model,
    )


def _map_open_close(param: str) -> str:
    if param in _OPEN_ALIASES:
        return "OPEN"
    if param in _CLOSE_ALIASES:
        return "CLOSE"
    return param


def _matches(command: Command, param: str, mapped: str) -> bool:
    # NB: like the app, the action is not compared here, only the parameter.
    if (
        command.command_param in mapped
        and command.command_param not in _PERCENT_PARAMS
        and command.command_action != "SPEED"
    ):
        return True
    return (
        command.command_action == "SPEED"
        and param == command.command_param
        and param in _SPEED_PARAMS
    )


def build_device_command(device: DeviceInfo, action: str, param: str) -> list[WireCommand]:
    """Select and build the command(s) for ``(action, param)`` on ``device``.

    Port of ``DaisyApplication#sendCommand`` (minus the transport choice).
    Raises :class:`TelecoUnsupportedError` when the device has no matching command.
    """
    flag_s = ";" in param
    value = param.split(";")[0] if flag_s else param
    flag_l = "-L" in value
    if flag_l:
        value = value.replace("-L", "")
    mapped = _map_open_close(value)

    template: Command | None = None
    out: list[WireCommand] = []
    low = ""
    for command in device.commands:
        if (
            command.command_action == action and command.command_param == "0"
        ) or device.id_devicemodel == _MODEL_GENERIC_SLIDER:
            template = command  # parametric command, last one wins
            continue
        if not _matches(command, value, mapped):
            continue
        if flag_s:
            channel = int(command.lowlevel_command.replace("CH", "") or 0)
            low = f"CH{channel + 10}"
        wire = to_wire(command, device)
        if device.id_devicemodel == _MODEL_RGB_PRESETS and mapped != command.command_param:
            # "RED" + "A100R255G000B000" -> the ARGB part only
            wire.command_param = mapped.replace(command.command_param, "")
        out.append(wire)
        break

    if not out:
        if template is None:
            raise TelecoUnsupportedError(
                f"{device.label!r} (model {device.id_devicemodel}) has no command for "
                f"{action}={param}"
            )
        out.append(to_wire(template, device, param=value))

    first = out[0]
    if flag_s:
        first.lowlevel_command = low
    if device.feedback:
        first.command_action += "-F"
    if flag_l:
        first.command_action += "-L"
    if value in ("START_O", "START_C"):
        first.command_param = "START"
    elif value in ("END_O_A", "END_C_A"):
        first.command_param = "END_A"
    elif value in ("END_O_M", "END_C_M"):
        first.command_param = "END_M"
    if (
        device.id_devicemodel == _MODEL_RETRACTABLE_SLATS
        and device.sub_model in _CH5_CH8_SWAP_SUBMODELS
    ):
        swap = {"CH5": "CH8", "CH8": "CH5"}
        out = [
            replace(c, lowlevel_command=swap.get(c.lowlevel_command, c.lowlevel_command))
            for c in out
        ]
    return out


def build_scenario_commands(
    steps: list[tuple[Command, DeviceInfo, str]],
) -> list[WireCommand]:
    """``ScenarioDao#toFeedCommandPost``: parametric commands ("0") take the step value."""
    return [
        to_wire(cmd, dev, param=value if cmd.command_param == "0" else None)
        for cmd, dev, value in steps
    ]


def system_command(
    box_device_id: int,
    action: str,
    param: str = "",
    *,
    device_code: str = "0",
    lowlevel: str = "",
) -> WireCommand:
    """A box-level command (``CommandDao#commandTo*``), always ``commandId`` 122."""
    return WireCommand(
        id_installation_device=box_device_id,
        device_code=device_code,
        id_installation_device_command=0,
        command_action=action,
        command_param=param,
        lowlevel_command=lowlevel,
        id_devicetype_command_model=SYSTEM_COMMAND_ID,
    )


def feed_post(
    inst_code: str,
    commands: list[WireCommand],
    *,
    scenario_id: int = 0,
    is_scenario: bool | None = None,
) -> JsonDict:
    """Body of ``tmate20/feedthecommands`` (without ``idSession``).

    ``is_scenario`` defaults to ``scenario_id != 0``; the board sync forces it on.
    """
    return {
        "idInstallation": inst_code,
        "idScenario": scenario_id,
        "isScenario": scenario_id != 0 if is_scenario is None else is_scenario,
        "commandsList": [c.to_cloud() for c in commands],
    }


def _java_str(value: object) -> str:
    return "null" if value is None else str(value)


def _local_param(command: WireCommand) -> str:
    if command.id_devicetype_command_model not in _SLIDER_COMMAND_MODELS:
        return _java_str(command.command_param)
    out = ""
    for part in command.command_param.split("§"):
        number = int(part)
        out += ("000" if number == 0 else f"0{part}" if number < 100 else part) + "-"
    return out


def local_payload(inst_code: str, commands: list[WireCommand], *, scenario_id: int = 0) -> str:
    """Compact JSON sent over the LAN (``DaisyApplication#convertForDM``).

    Built by string concatenation exactly like the app (no JSON escaping).
    """
    entries = [
        f'{{"idInDe":{c.id_installation_device},"deCo":"{c.device_code}",'
        f'"cmId":{c.command_id},"coAc":"{_java_str(c.command_action)}",'
        f'"coPa":"{_local_param(c)}","low":"{_java_str(c.lowlevel_command)}","coSta":0}}'
        for c in commands
    ]
    is_scenario = "true" if scenario_id != 0 else "false"
    return (
        f'{{"idIn":"{inst_code}","idSc":{scenario_id},"isSc":{is_scenario},'
        f'"cL":[{",".join(entries)}]}}'
    )
