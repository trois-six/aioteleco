"""Async SDK for Teleco Automation Daisy boxes (pergolas, awnings, lights...)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

from .devices import (
    Audio,
    ColorLight,
    Cover,
    Device,
    DeviceFamily,
    Dimmer,
    Fan,
    Heater,
    Light,
    OnOffDevice,
    PresetRgbLight,
    Slats,
    WhiteLight,
)
from .exceptions import (
    TelecoAckTimeoutError,
    TelecoApiError,
    TelecoAuthError,
    TelecoCommandError,
    TelecoConnectionError,
    TelecoError,
    TelecoLocalError,
    TelecoSessionExpiredError,
    TelecoUnsupportedError,
)
from .hub import BoxInfo, InstallationData, TelecoHub
from .models import Installation, Room, Scenario, StatusItem, Timer
from .transport import Channel, SendResult, TransportMode

try:
    # Single source of truth: the version in pyproject.toml (installed metadata).
    __version__ = _dist_version("aioteleco")
except PackageNotFoundError:  # pragma: no cover - imported from a source tree, not installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "Audio",
    "BoxInfo",
    "Channel",
    "ColorLight",
    "Cover",
    "Device",
    "DeviceFamily",
    "Dimmer",
    "Fan",
    "Heater",
    "Installation",
    "InstallationData",
    "Light",
    "OnOffDevice",
    "PresetRgbLight",
    "Room",
    "Scenario",
    "SendResult",
    "Slats",
    "StatusItem",
    "TelecoAckTimeoutError",
    "TelecoApiError",
    "TelecoAuthError",
    "TelecoCommandError",
    "TelecoConnectionError",
    "TelecoError",
    "TelecoHub",
    "TelecoLocalError",
    "TelecoSessionExpiredError",
    "TelecoUnsupportedError",
    "Timer",
    "TransportMode",
    "WhiteLight",
]
