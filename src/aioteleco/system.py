"""Box-level ("system") commands and the scenario string the box stores.

All of them are built like ``CommandDao#commandTo*``: ``commandId`` 122 (except the
remote pairing commands), target the box device unless noted, and are always sent
through the cloud.
"""

from __future__ import annotations

from .commands import WireCommand, system_command
from .models import Command, DeviceInfo

# CommandDao#getBoardDeviceCodeName: the short name of a device model on the box.
BOARD_CODE_NAMES: dict[int, str] = {
    16: "LMP",
    17: "DIM",
    18: "HEA",
    19: "FAN",
    20: "HEQ",
    21: "PER",
    22: "CAN",
    23: "SER",
    24: "SOL",
    25: "TEN",
    26: "RGB",
    27: "PEG",
    28: "AUD",
    31: "PEQ",
    32: "COP",
    33: "DYP",
    34: "DMS",
    43: "GAK",
    44: "RAS",
    45: "ARS",
    46: "CRP",
    47: "WIN",
}

# CommandDao#commandToTx: remote pairing commands carry their own commandId.
TX_COMMAND_IDS: dict[str, int] = {
    "PAIR_BUTTON": 108,
    "UNPAIR_BUTTON": 109,
    "PAIR_TX": 127,
    "UNPAIR_TX": 128,
    "RESET_TX": 129,
}

_COLOR_CHANNELS = {"PURPLE": 13, "YELLOW": 12, "CYAN": 11, "WHITE": 14}

# Commands that only ask the box to refresh one of its status items.
QUERY_ACTIONS = ("GET_TIME", "GET_SIGNAL", "GET_VERSION", "GET_INFO", "GET_DIAGNOSTIC")


def box_command(box_device_id: int, action: str, param: str = "") -> WireCommand:
    """A parameterless-style box command (GET_*, TEST_SCAN, SYNC_BOARD, END_SYNC...)."""
    return system_command(box_device_id, action, param)


def get_feedback_command(device: DeviceInfo) -> WireCommand:
    """Ask the box for a device's feedback (``GET_FEEDBACK``), targeting the device."""
    return system_command(
        device.id_installation_device,
        "GET_FEEDBACK",
        BOARD_CODE_NAMES.get(device.id_devicemodel, ""),
        device_code=str(device.device_index),
    )


def update_device_command(device: DeviceInfo, box_device_id: int) -> WireCommand:
    """Push a device's options to the box (``UP_DEV``, firmware >= 1.3.3)."""
    feedback = "S" if device.feedback else "N"
    return system_command(
        device.id_installation_device,
        "UP_DEV",
        f"Feedback: {feedback} Timers: S",
        device_code=str(device.device_index),
        lowlevel=str(box_device_id),
    )


def update_installation_name_command(box_device_id: int, name: str) -> WireCommand:
    return system_command(box_device_id, "UP_INST_NAME", name)


def set_wifi_command(box_device_id: int, ssid: str, password: str) -> WireCommand:
    return system_command(box_device_id, "SET_WIFI", f"SSID: {ssid} PASS: {password}")


def read_ap_channel_command(box_device_id: int) -> WireCommand:
    return system_command(box_device_id, "AP_CHANNEL_CMD", "00R")


def set_ap_channel_command(box_device_id: int, *, static: bool) -> WireCommand:
    """Access point channel: ``static`` writes ``20W``, otherwise ``06W``."""
    return system_command(box_device_id, "AP_CHANNEL_CMD", "20W" if static else "06W")


def read_memory_command(box_device_id: int, address: str, count: str) -> WireCommand:
    return system_command(box_device_id, "MEMORY", f"ADDR: {address} NB: {count}R")


def set_time_command(box_device_id: int, value: str) -> WireCommand:
    return system_command(box_device_id, "SET_TIME", value)


def update_firmware_command(box_device_id: int, url: str) -> WireCommand:
    return system_command(box_device_id, "UPDATE_BOARD", url)


def update_scenario_command(box_device_id: int, scenario_string: str) -> WireCommand:
    return system_command(box_device_id, "UP_SCEN", scenario_string)


def delete_scenario_command(box_device_id: int, id_scenario: int) -> WireCommand:
    return system_command(box_device_id, "DEL_SCEN", str(id_scenario))


def tx_command(action: str, param: str, id_installation_device: int) -> WireCommand:
    """Remote pairing (``CommandDao#commandToTx``), sent to the scenario's device."""
    if action not in TX_COMMAND_IDS:
        raise ValueError(f"unknown remote command {action!r}")
    return WireCommand(
        id_installation_device=id_installation_device,
        device_code="0",
        id_installation_device_command=0,
        command_action=action,
        command_param=param,
        lowlevel_command="",
        id_devicetype_command_model=TX_COMMAND_IDS[action],
    )


def _hex2(value: str) -> str:
    return f"{int(value):x}".rjust(2, "0")


def _scenario_value(param: str, command: Command) -> str:
    if all(ch in param for ch in "ARGB"):
        return "R" + _hex2(param[1:4]) + _hex2(param[5:8]) + _hex2(param[9:12]) + _hex2(param[13:])
    if param.lstrip("-").isdigit():
        return "L" + f"{int(param):x}".rjust(2, "0") + "000000"
    if command.lowlevel_command:
        channel = _COLOR_CHANNELS.get(
            command.command_param, int(command.lowlevel_command.replace("CH", ""))
        )
    else:
        channel = 8
    return f"C{channel:02d}000000"


def scenario_string(id_scenario: int, steps: list[tuple[Command, DeviceInfo, str]]) -> str:
    """The scenario as stored by the box (``ScenarioDao#toScenarioString``).

    ``<id>N<count, 2 digits>`` then, per step, `` <device index, 2 digits><value>
    <command model, hex><device id, 8 hex>`` (no separators inside a step).
    """
    out = f"{id_scenario}N{len(steps):02d}"
    for command, device, param in steps:
        out += (
            f" {device.device_index:02d}"
            + _scenario_value(param, command)
            + f"{command.id_devicetype_command_model:x}"
            + f"{device.id_installation_device:x}".rjust(8, "0")
        )
    return out
