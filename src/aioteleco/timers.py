"""Timer helpers: the UP_TIMERS / UP_SCHED / DEL_TIM box commands.

Saving timers is a two-step dance in the app (``SetupDeviceTimersActivity``):
first an ``UP_TIMERS`` system command per timer is sent to the box and acked
(``MessageText == "ACK"``), then the device's *complete* timer list is posted to
``timer-device-setup/``.
"""

from __future__ import annotations

import re

from .commands import WireCommand, system_command
from .models import Command, DeviceInfo, Timer

_COLOR_CHANNELS = {"PURPLE": 13, "YELLOW": 12, "CYAN": 11, "WHITE": 14}
_OFFSET_BITS = {-2: "001", -1: "010", 0: "000", 1: "011", 2: "100"}
_SUN_BITS = {1: "01", 2: "10"}


def _pad3(prefix: str, value: int) -> str:
    return f"{prefix}{value:03d}"


def _hex2(value: str) -> str:
    return f"{int(value):x}".rjust(2, "0")


def _value_field(param: str, command: Command) -> str:
    if all(ch in param for ch in "ARGB"):
        return "R" + _hex2(param[1:4]) + _hex2(param[5:8]) + _hex2(param[9:12]) + _hex2(param[13:])
    if re.fullmatch(r"-?\d+", param):
        x = f"{int(param):x}"
        return ("0" if len(x) == 1 else "L") + x + "000000"
    if command.lowlevel_command:
        channel = _COLOR_CHANNELS.get(
            command.command_param, int(command.lowlevel_command.replace("CH", "") or 0)
        )
    else:
        channel = 8
    return ("C" if channel >= 10 else "C0") + str(channel) + "000000"


def days_mask(days: str) -> int:
    """``giorni`` ("S;S;S;S;S;N;N", Monday first) -> bit mask (Mon=64 ... Sun=1)."""
    return int("0" + "".join("1" if d == "S" else "0" for d in days.split(";")), 2)


def up_timers_param(timer: Timer, device: DeviceInfo, command: Command) -> str:
    """``CommandDao#commandToUpdateTimer`` commandParam."""
    value = _value_field(timer.command_param, command)
    date, _, hm = timer.timer_date.partition(" ")
    year, month, day = date.split("-")
    del year
    sun = _SUN_BITS.get(timer.sun_event, "") if timer.twilight else "00"
    astro = int(sun + "000" + _OFFSET_BITS.get(timer.twilight_offset, ""), 2)
    return " ".join(
        [
            value,
            "HS" + hm.replace(":", ""),
            "DS" + day + month,
            "HE0000",
            "DE0000",
            _pad3("G", days_mask(timer.days)),
            _pad3("A", astro),
            f"{device.id_installation_device:x}".rjust(8, "0"),
            f"M{command.id_devicetype_command_model:x}",
            f"{timer.id_installation_device_timer:x}".rjust(8, "0"),
            "T" + ("S" if timer.active else "N"),
        ]
    )


def up_timers_command(
    box_device_id: int, timer: Timer, device: DeviceInfo, command: Command
) -> WireCommand:
    return system_command(
        box_device_id,
        "UP_TIMERS",
        up_timers_param(timer, device, command),
        device_code=str(device.device_index),
    )


def up_schedule_command(box_device_id: int, enabled: bool) -> WireCommand:
    """Master switch for all the box timers (``UP_SCHED``)."""
    return system_command(box_device_id, "UP_SCHED", f"Timers: {'S' if enabled else 'N'}")
