"""Exceptions raised by aioteleco."""

from __future__ import annotations

from typing import Any


class TelecoError(Exception):
    """Base class for every SDK error."""


class TelecoConnectionError(TelecoError):
    """The cloud or the box could not be reached."""


class TelecoAuthError(TelecoError):
    """Login failed (wrong credentials, unconfirmed account...)."""


class TelecoSessionExpiredError(TelecoError):
    """The cloud session is no longer valid and re-login failed or is disabled."""


class TelecoApiError(TelecoError):
    """The cloud answered with an error envelope."""

    def __init__(self, message: str, *, code: str | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload


class TelecoCommandError(TelecoError):
    """A command was rejected or could not be built."""


class TelecoAckTimeoutError(TelecoCommandError):
    """The box did not confirm a command in time."""


class TelecoLocalError(TelecoConnectionError):
    """The local (LAN) channel to the box failed."""


class TelecoUnsupportedError(TelecoError):
    """The device does not support the requested action."""
