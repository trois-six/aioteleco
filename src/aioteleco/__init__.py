"""Async SDK for Teleco Automation Daisy boxes (pergolas, awnings, lights...)."""

from __future__ import annotations

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

__version__ = "1.0.0a1"

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
