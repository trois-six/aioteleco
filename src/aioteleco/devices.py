"""Device objects, one class per family of ``idDevicemodel``.

The app picks a device's screen from ``idDevicemodel`` (and ``remoteControlCode``,
the sub-model), never from ``idDevicetype``. Every action ends up as an
``(action, param)`` request resolved against the device's own command list
(see :mod:`aioteleco.commands`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from .const import CommandAction, StatusItemCode
from .models import DeviceInfo, Installation, Room, StatusItem

if TYPE_CHECKING:
    from .hub import TelecoHub
    from .transport import SendResult

_MODEL_SLIDER_DIMMER = 34


class DeviceFamily(StrEnum):
    SWITCH = "switch"
    LIGHT = "light"
    DIMMER = "dimmer"
    RGB_LIGHT = "rgb_light"
    WHITE_LIGHT = "white_light"
    HEATER = "heater"
    FAN = "fan"
    COVER = "cover"
    SLATS = "slats"
    AUDIO = "audio"
    GENERIC = "generic"


# idDevicemodel -> (box short code, human name). From DeviceFactory / CommandDao.
DEVICE_MODELS: dict[int, tuple[str, str]] = {
    16: ("LMP", "On/off"),
    17: ("DIM", "Dimmer"),
    18: ("HEA", "Heater"),
    19: ("FAN", "Fan"),
    20: ("HEQ", "Heater 4 channels"),
    21: ("PER", "Rolling shutter"),
    22: ("CAN", "Gate"),
    23: ("SER", "Garage door"),
    24: ("SOL", "Awning"),
    25: ("TEN", "Screen"),
    26: ("RGB", "RGB light (presets)"),
    27: ("PEG", "Pergola adjustable slats"),
    28: ("AUD", "Audio"),
    31: ("PEQ", "Pergola slats (open/stop/close)"),
    32: ("COP", "RGB light"),
    33: ("DYP", "Tunable white light"),
    34: ("DMS", "Dimmer (slider)"),
    41: ("", "Generic remote (buttons)"),
    42: ("", "Generic remote (sliders)"),
    43: ("GAK", "Garage door (ask)"),
    44: ("RAS", "Retractable slats"),
    45: ("ARS", "Automatic retractable slats"),
    46: ("CRP", "RGB light (color rotation)"),
    47: ("WIN", "Window"),
}

RGB_PRESETS = ("RED", "GREEN", "BLUE", "MILK", "CYAN", "YELLOW", "PURPLE", "WHITE")


def color_string(rgb: tuple[int, int, int], brightness: int) -> str:
    """``AxxxRxxxGxxxBxxx`` (A = brightness 0-100), as built by ``Utils``."""
    if not 0 <= brightness <= 100:
        raise ValueError("brightness must be within 0..100")
    if any(not 0 <= c <= 255 for c in rgb):
        raise ValueError("color components must be within 0..255")
    r, g, b = rgb
    return f"A{brightness:03d}R{r:03d}G{g:03d}B{b:03d}"


def parse_color(value: str) -> tuple[tuple[int, int, int], int] | None:
    """Parse ``AxxxRxxxGxxxBxxx`` into ``((r, g, b), brightness)``."""
    try:
        a, r, g, b = (int(value[i + 1 : i + 4]) for i in (0, 4, 8, 12))
    except (ValueError, IndexError):
        return None
    if value[0::4][:4] != "ARGB":
        return None
    return (r, g, b), a


class Device:
    """Any device of an installation."""

    family: ClassVar[DeviceFamily] = DeviceFamily.GENERIC

    def __init__(
        self, hub: TelecoHub, installation: Installation, room: Room, info: DeviceInfo
    ) -> None:
        self.hub = hub
        self.installation = installation
        self.room = room
        self.info = info
        self.status: dict[str, str] = {}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.info.label!r} model={self.model}>"

    @property
    def id(self) -> int:
        return self.info.id_installation_device

    @property
    def name(self) -> str:
        return self.info.label

    @property
    def model(self) -> int:
        return self.info.id_devicemodel

    @property
    def model_name(self) -> str:
        return DEVICE_MODELS.get(self.model, ("", f"Unknown model {self.model}"))[1]

    @property
    def unique_id(self) -> str:
        return f"{self.installation.inst_code}-{self.id}"

    def supports(self, action: str, param: str | None = None) -> bool:
        """Does the device's command list contain this action (and param)?"""
        return any(
            c.command_action == action and (param is None or c.command_param in (param, "0"))
            for c in self.info.commands
        )

    async def send(self, action: str, param: str) -> SendResult:
        """Send a raw ``(action, param)`` request."""
        return await self.hub.send_command(self, action, param)

    async def refresh(self) -> dict[str, str]:
        items = await self.hub.api.device_status(self.installation, self.id)
        self.update_status(items)
        return self.status

    def update_status(self, items: list[StatusItem]) -> None:
        self.status = {item.code: item.status_value for item in items}

    def _status(self, code: StatusItemCode) -> str | None:
        return self.status.get(code)


class OnOffDevice(Device):
    family = DeviceFamily.SWITCH

    @property
    def is_on(self) -> bool | None:
        value = self._status(StatusItemCode.POWER)
        return None if value is None else value == "ON"

    async def turn_on(self) -> SendResult:
        return await self.send(CommandAction.POWER, "ON")

    async def turn_off(self) -> SendResult:
        return await self.send(CommandAction.POWER, "OFF")


class Light(OnOffDevice):
    family = DeviceFamily.LIGHT


class Dimmer(Light):
    """Dimmers / heaters with 4 steps (POWER LEV1..LEV4) or a 0-100 LEVEL."""

    family = DeviceFamily.DIMMER

    @property
    def level(self) -> int | None:
        value = self._status(StatusItemCode.LEVEL)
        return int(value) if value and value.isdigit() else None

    async def set_step(self, step: int) -> SendResult:
        if not 1 <= step <= 4:
            raise ValueError("step must be within 1..4")
        return await self.send(CommandAction.POWER, f"LEV{step}")

    @property
    def has_continuous_level(self) -> bool:
        """Only slider dimmers (model 34) take a free 0-100 level; the others have 4 steps."""
        return self.model == _MODEL_SLIDER_DIMMER

    async def set_level(self, level: int) -> SendResult:
        """Brightness 0..100; 0 turns the device off.

        Slider dimmers (model 34) get the value itself (``LEVEL <n>``), like the app's
        slider. Stepped dimmers get the nearest step (25/50/75/100): they also list a
        parametric ``LEVEL`` command, but the box ignores it for them.
        """
        if not 0 <= level <= 100:
            raise ValueError("level must be within 0..100")
        if level == 0:
            return await self.turn_off()
        if self.has_continuous_level:
            return await self.send(CommandAction.LEVEL, str(level))
        return await self.set_step(min(4, max(1, round(level / 25))))


class Heater(Dimmer):
    family = DeviceFamily.HEATER


class Fan(OnOffDevice):
    family = DeviceFamily.FAN

    async def set_speed(self, speed: int) -> SendResult:
        if speed not in (33, 67, 100):
            raise ValueError("speed must be 33, 67 or 100")
        return await self.send(CommandAction.SPEED, str(speed))


class ColorLight(Light):
    """RGB (32, 46) and tunable-white (33) lights driven by an ARGB string."""

    family = DeviceFamily.RGB_LIGHT

    @property
    def color(self) -> tuple[tuple[int, int, int], int] | None:
        value = self._status(StatusItemCode.COLOR)
        return parse_color(value) if value else None

    async def set_color(self, rgb: tuple[int, int, int], brightness: int = 100) -> SendResult:
        return await self.send(CommandAction.COLOR, color_string(rgb, brightness))


class WhiteLight(ColorLight):
    family = DeviceFamily.WHITE_LIGHT


class PresetRgbLight(Light):
    """Model 26: 8 preset colors + color cycle."""

    family = DeviceFamily.RGB_LIGHT

    @property
    def preset(self) -> str | None:
        return self._status(StatusItemCode.COLOR)

    async def set_preset(self, name: str) -> SendResult:
        if name not in RGB_PRESETS:
            raise ValueError(f"preset must be one of {', '.join(RGB_PRESETS)}")
        return await self.send(CommandAction.COLOR, name)

    async def cycle(self) -> SendResult:
        return await self.send(CommandAction.CYCLE, "ON")


class Cover(Device):
    """Open/stop/close devices: shutters, awnings, screens, gates, windows..."""

    family = DeviceFamily.COVER

    @property
    def state(self) -> str | None:
        """``OPEN``, ``CLOSE``, ``STOP`` or ``None`` (unknown / moving)."""
        return self._status(StatusItemCode.OPEN_CLOSE)

    @property
    def position(self) -> int | None:
        """Open percentage as the app shows it (``OpenStopCloseDeviceActionFragment``).

        ``LEVEL`` while ``OPEN``, 0 when ``CLOSE`` (whatever ``LEVEL`` says), ``None``
        when stopped midway or moving. These devices only take open/stop/close.
        """
        state = self.state
        if state == "CLOSE":
            return 0
        if state == "OPEN":
            value = self._status(StatusItemCode.LEVEL)
            return int(value) if value and value.isdigit() else 100
        return None

    @property
    def is_closed(self) -> bool | None:
        state = self.state
        if state == "CLOSE":
            return True
        if state == "OPEN":
            return False
        return None

    async def open(self) -> SendResult:
        return await self.send(CommandAction.OPEN_STOP_CLOSE, "OPEN")

    async def close(self) -> SendResult:
        return await self.send(CommandAction.OPEN_STOP_CLOSE, "CLOSE")

    async def stop(self) -> SendResult:
        return await self.send(CommandAction.OPEN_STOP_CLOSE, "STOP")


class Slats(Cover):
    """Pergola slats with steps 0/33/66/100 (models 27, 44, 45)."""

    family = DeviceFamily.SLATS
    STEPS: ClassVar[tuple[int, ...]] = (0, 33, 66, 100)

    @property
    def position(self) -> int | None:
        value = self._status(StatusItemCode.LEVEL)
        return int(value) if value and value.isdigit() else None

    @property
    def retracted(self) -> bool | None:
        value = self._status(StatusItemCode.RETR)
        return None if value is None else value == "YES"

    async def set_position(self, percent: int) -> SendResult:
        """Move to the nearest step (the app only offers 0/33/66/100)."""
        if not 0 <= percent <= 100:
            raise ValueError("position must be within 0..100")
        step = min(range(len(self.STEPS)), key=lambda i: abs(self.STEPS[i] - percent))
        if step == 0 and self.model == 27:
            return await self.close()
        return await self.send(CommandAction.LEVEL, f"LEV{step + 1}")


class Audio(OnOffDevice):
    family = DeviceFamily.AUDIO

    async def play_pause(self, play: bool) -> SendResult:
        return await self.send(CommandAction.PAUSE_PLAY, "PLAY" if play else "PAUSE")

    async def action(self, name: str) -> SendResult:
        """VOLUME_UP, VOLUME_DOWN, REWIND or FORWARD."""
        return await self.send(CommandAction.AUDIO_ACTION, name)


_MODEL_CLASSES: dict[int, type[Device]] = {
    16: Light,
    17: Dimmer,
    18: Heater,
    19: Fan,
    20: Heater,
    21: Cover,
    22: Cover,
    23: Cover,
    24: Cover,
    25: Cover,
    26: PresetRgbLight,
    27: Slats,
    28: Audio,
    31: Cover,
    32: ColorLight,
    33: WhiteLight,
    34: Dimmer,
    43: Cover,
    44: Slats,
    45: Slats,
    46: ColorLight,
    47: Cover,
}


def device_class(info: DeviceInfo) -> type[Device]:
    """Pick the class for a device (``DeviceFactory#castDevice``)."""
    if info.id_devicemodel == 16 and info.sub_model not in ("", "1"):
        return OnOffDevice  # read-only status, deicing, antisnow, nebulizer
    return _MODEL_CLASSES.get(info.id_devicemodel, Device)
