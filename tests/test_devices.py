"""Device helpers: dimmer levels and cover positions."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from aioteleco.devices import Cover, Dimmer, TravelTimes, device_class
from aioteleco.exceptions import TelecoUnsupportedError
from aioteleco.hub import TelecoHub
from aioteleco.models import DeviceInfo, Installation, Room, StatusItem
from aioteleco.transport import Channel, SendResult


class RecordingHub:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_command(self, device: Any, action: str, param: str) -> SendResult:
        self.sent.append((action, param))
        return SendResult(Channel.CLOUD, "PROC")


def make(model: int, commands: list[tuple[str, str]]) -> tuple[Any, RecordingHub]:
    info = DeviceInfo.from_json(
        {
            "idInstallationDevice": 1,
            "idDevicemodel": model,
            "deviceIndex": 1,
            "label": "dev",
            "deviceCommandList": [
                {"idInstallationDeviceCommand": i, "commandAction": a, "commandParam": p}
                for i, (a, p) in enumerate(commands, 1)
            ],
        }
    )
    hub = RecordingHub()
    device = device_class(info)(
        cast(TelecoHub, hub), Installation.from_json({}), Room.from_json({}), info
    )
    return device, hub


STEPPED = [("POWER", "ON"), ("POWER", "OFF"), ("LEVEL", "0")] + [
    ("LEVEL", f"LEV{i}") for i in range(1, 5)
]


@pytest.mark.parametrize(
    ("level", "sent"),
    [
        (0, ("POWER", "OFF")),
        (1, ("POWER", "LEV1")),
        (30, ("POWER", "LEV1")),
        (40, ("POWER", "LEV2")),
        (70, ("POWER", "LEV3")),
        (100, ("POWER", "LEV4")),
    ],
)
async def test_stepped_dimmer_level_uses_the_nearest_step(
    level: int, sent: tuple[str, str]
) -> None:
    dimmer, hub = make(17, STEPPED)
    assert isinstance(dimmer, Dimmer)
    assert not dimmer.has_continuous_level
    await dimmer.set_level(level)
    assert hub.sent == [sent]


async def test_slider_dimmer_level_is_sent_as_is() -> None:
    dimmer, hub = make(34, STEPPED)
    assert isinstance(dimmer, Dimmer)
    assert dimmer.has_continuous_level
    await dimmer.set_level(42)
    await dimmer.set_level(0)
    assert hub.sent == [("LEVEL", "42"), ("POWER", "OFF")]


async def test_dimmer_level_range() -> None:
    dimmer, _ = make(17, STEPPED)
    with pytest.raises(ValueError, match=r"0\.\.100"):
        await dimmer.set_level(101)


@pytest.mark.parametrize(
    ("state", "level", "position"),
    [
        ("CLOSE", "100", 0),  # the app ignores LEVEL once closed
        ("OPEN", "100", 100),
        ("OPEN", "40", 40),
        ("OPEN", "", 100),
        ("STOP", "100", None),
        (None, None, None),
    ],
)
def test_cover_position_like_the_app(
    state: str | None, level: str | None, position: int | None
) -> None:
    cover, _ = make(21, [("OPEN_STOP_CLOSE", "OPEN")])
    assert isinstance(cover, Cover)
    items = [
        StatusItem.from_json({"statusItem": code, "statusValue": value})
        for code, value in (("OPEN_CLOSE", state), ("LEVEL", level))
        if value is not None
    ]
    cover.update_status(items)
    assert cover.position == position


# --- timed cover positions ------------------------------------------------------------


class TimedHub(RecordingHub):
    """Records (action, param, loop time) for timing assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.times: list[float] = []

    async def send_command(self, device: Any, action: str, param: str) -> SendResult:
        self.times.append(asyncio.get_running_loop().time())
        return await super().send_command(device, action, param)


def timed_cover(state: str | None = "CLOSE") -> tuple[Cover, TimedHub]:
    info = DeviceInfo.from_json(
        {
            "idInstallationDevice": 1,
            "idDevicemodel": 21,
            "deviceCommandList": [
                {
                    "idInstallationDeviceCommand": i,
                    "commandAction": "OPEN_STOP_CLOSE",
                    "commandParam": p,
                }
                for i, p in enumerate(("OPEN", "STOP", "CLOSE"), 1)
            ],
        }
    )
    hub = TimedHub()
    cover = Cover(cast(TelecoHub, hub), Installation.from_json({}), Room.from_json({}), info)
    if state:
        cover.update_status(
            [StatusItem.from_json({"statusItem": "OPEN_CLOSE", "statusValue": state})]
        )
    cover.travel_times = TravelTimes(open=0.4, close=0.2)
    return cover, hub


async def test_travel_needs_travel_times() -> None:
    cover, _ = timed_cover()
    cover.travel_times = None
    with pytest.raises(TelecoUnsupportedError, match="travel_times"):
        await cover.travel_to(50)


async def test_travel_to_from_closed() -> None:
    cover, hub = timed_cover("CLOSE")
    await cover.travel_to(50)
    assert [p for _, p in hub.sent] == ["OPEN", "STOP"]
    assert hub.times[1] - hub.times[0] == pytest.approx(0.2, abs=0.05)  # half of 0.4 s
    assert cover.position == pytest.approx(50, abs=10)


async def test_travel_back_down_uses_the_close_time() -> None:
    cover, hub = timed_cover("OPEN")
    await cover.travel_to(25)
    assert [p for _, p in hub.sent] == ["CLOSE", "STOP"]
    assert hub.times[1] - hub.times[0] == pytest.approx(0.15, abs=0.05)  # 75 % of 0.2 s


async def test_travel_to_an_end_needs_no_stop() -> None:
    cover, hub = timed_cover("CLOSE")
    await cover.travel_to(100)
    assert [p for _, p in hub.sent] == ["OPEN"]


async def test_travel_from_unknown_position_closes_first() -> None:
    cover, hub = timed_cover(None)
    assert cover.position is None
    await cover.travel_to(50)
    assert [p for _, p in hub.sent] == ["CLOSE", "OPEN", "STOP"]


async def test_stop_interrupts_a_travel() -> None:
    cover, hub = timed_cover("CLOSE")
    task = asyncio.create_task(cover.travel_to(90))
    await asyncio.sleep(0.1)
    await cover.stop()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [p for _, p in hub.sent] == ["OPEN", "STOP"]
    assert cover.position == pytest.approx(25, abs=10)  # 0.1 s of a 0.4 s travel
    assert cover.state == "CLOSE"  # the cloud status is only updated by refresh()
