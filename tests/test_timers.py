"""UP_TIMERS / UP_SCHED encodings (``CommandDao#commandToUpdateTimer``)."""

from __future__ import annotations

from typing import Any

import pytest

from aioteleco.models import Command, DeviceInfo, Timer
from aioteleco.timers import days_mask, up_schedule_command, up_timers_command, up_timers_param


def make_timer(**overrides: Any) -> Timer:
    data: dict[str, Any] = {
        "idInstallationDeviceTimer": 5001,
        "idInstallationDeviceCommand": 3006,
        "timerOrder": 1,
        "timerDate": "2026-09-24 18:30",
        "timerActive": "S",
        "giorni": "S;S;S;S;S;N;N",
        "crepuscolare": "N",
        "albaTramonto": 0,
        "crepuscolareOffset": 0,
        "commandParam": "66",
    }
    data.update(overrides)
    return Timer.from_json(data)


def make_command(param: str = "LEV3", low: str = "CH3", model: int = 99) -> Command:
    return Command.from_json(
        {
            "idInstallationDeviceCommand": 3006,
            "idInstallationDevice": 2001,
            "idDevicetypeCommandModel": model,
            "commandAction": "LEVEL",
            "commandParam": param,
            "lowlevelCommand": low,
        }
    )


def make_device(device_id: int = 789, index: int = 1) -> DeviceInfo:
    return DeviceInfo.from_json(
        {"idInstallationDevice": device_id, "idDevicemodel": 27, "deviceIndex": index}
    )


def fields(
    timer: Timer, command: Command | None = None, device: DeviceInfo | None = None
) -> list[str]:
    return up_timers_param(timer, device or make_device(), command or make_command()).split(" ")


@pytest.mark.parametrize(
    ("days", "mask"),
    [
        ("S;S;S;S;S;N;N", 124),
        ("S;N;N;N;N;N;N", 64),
        ("N;N;N;N;N;N;S", 1),
        ("S;S;S;S;S;S;S", 127),
        ("N;N;N;N;N;N;N", 0),
        ("N;N;N;N;N;S;S", 3),
    ],
)
def test_days_mask(days: str, mask: int) -> None:
    assert days_mask(days) == mask


@pytest.mark.parametrize(
    ("param", "command", "expected"),
    [
        ("66", make_command(), "L42000000"),
        ("100", make_command(), "L64000000"),
        ("15", make_command(), "0f000000"),
        ("5", make_command(), "05000000"),
        ("0", make_command(), "00000000"),
        ("A100R255G000B010", make_command(), "R64ff000a"),
        ("A050R001G128B255", make_command(), "R3201" + "80ff"),
        ("OPEN", make_command("OPEN", "CH4", 94), "C04000000"),
        ("WHITE", make_command("WHITE", "CH1"), "C14000000"),
        ("PURPLE", make_command("PURPLE", "CH1"), "C13000000"),
        ("YELLOW", make_command("YELLOW", "CH1"), "C12000000"),
        ("CYAN", make_command("CYAN", "CH1"), "C11000000"),
        ("CLOSE", make_command("CLOSE", "CH12"), "C12000000"),
        ("OPEN", make_command("OPEN", ""), "C08000000"),
    ],
)
def test_value_field(param: str, command: Command, expected: str) -> None:
    assert fields(make_timer(commandParam=param), command)[0] == expected


def test_full_param() -> None:
    timer = make_timer()
    assert up_timers_param(timer, make_device(), make_command()) == (
        "L42000000 HS1830 DS2409 HE0000 DE0000 G124 A000 00000315 M63 00001389 TS"
    )


def test_time_and_date_fields() -> None:
    out = fields(make_timer(timerDate="2026-01-05 07:05"))
    assert out[1:5] == ["HS0705", "DS0501", "HE0000", "DE0000"]


def test_days_field() -> None:
    assert fields(make_timer(giorni="N;N;N;N;N;N;S"))[5] == "G001"
    assert fields(make_timer(giorni="S;S;S;S;S;S;S"))[5] == "G127"


@pytest.mark.parametrize(
    ("twilight", "sun", "offset", "expected"),
    [
        ("N", 0, 0, "A000"),
        ("N", 1, 0, "A000"),  # sun event ignored without twilight
        ("S", 1, 0, "A064"),
        ("S", 1, 2, "A068"),
        ("S", 1, 1, "A067"),
        ("S", 1, -2, "A065"),
        ("S", 2, 0, "A128"),
        ("S", 2, -1, "A130"),
    ],
)
def test_astro_field(twilight: str, sun: int, offset: int, expected: str) -> None:
    timer = make_timer(crepuscolare=twilight, albaTramonto=sun, crepuscolareOffset=offset)
    assert fields(timer)[6] == expected


def test_device_command_model_and_timer_ids() -> None:
    timer = make_timer(idInstallationDeviceTimer=0x1A2B3C)
    out = fields(timer, make_command(model=137), make_device(device_id=0x12345678))
    assert out[7:10] == ["12345678", "M89", "001a2b3c"]


def test_device_id_padding() -> None:
    assert fields(make_timer(), device=make_device(device_id=2001))[7] == "000007d1"


@pytest.mark.parametrize(("active", "flag"), [("S", "TS"), ("N", "TN")])
def test_active_flag(active: str, flag: str) -> None:
    assert fields(make_timer(timerActive=active))[10] == flag


def test_up_timers_command() -> None:
    timer = make_timer()
    cmd = up_timers_command(789, timer, make_device(device_id=2001, index=7), make_command())
    assert cmd.command_id == 122
    assert cmd.id_installation_device == 789
    assert cmd.command_action == "UP_TIMERS"
    assert cmd.device_code == "7"
    assert cmd.command_param == up_timers_param(timer, make_device(2001, 7), make_command())


@pytest.mark.parametrize(("enabled", "param"), [(True, "Timers: S"), (False, "Timers: N")])
def test_up_schedule_command(enabled: bool, param: str) -> None:
    cmd = up_schedule_command(789, enabled)
    assert (cmd.command_id, cmd.command_action, cmd.command_param) == (122, "UP_SCHED", param)
    assert cmd.device_code == "0"
