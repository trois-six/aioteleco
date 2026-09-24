"""Device helpers: dimmer levels and cover positions."""

from __future__ import annotations

from typing import Any, cast

import pytest

from aioteleco.devices import Cover, Dimmer, device_class
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
