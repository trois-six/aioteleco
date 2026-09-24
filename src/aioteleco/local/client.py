"""LAN channel to the Daisy box (``DaisyApplication#sendDM``).

One TCP connection per command to ``<box ip>:400``: write the obfuscated frame
(no newline), read one plaintext line. A line containing ``"ACK"`` means the box
accepted the command. The box's IP is only known through the cloud status item
``NET_PARAM`` of the box device, or can be configured by the user.

This channel only *sends* commands: device state is never readable locally.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..commands import WireCommand, local_payload
from ..const import (
    LOCAL_ACK,
    LOCAL_CONNECT_TIMEOUT,
    LOCAL_PORT,
    LOCAL_READ_TIMEOUT,
    LOCAL_READ_TIMEOUT_CHANNEL,
    LOCAL_READ_TIMEOUT_SCENARIO,
)
from ..exceptions import TelecoLocalError
from .crypto import encrypt

_LOGGER = logging.getLogger(__name__)


class LocalClient:
    """Send commands to a Daisy box on the local network."""

    def __init__(
        self,
        host: str,
        *,
        port: int = LOCAL_PORT,
        connect_timeout: float = LOCAL_CONNECT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout

    async def send(
        self, inst_code: str, commands: list[WireCommand], *, scenario_id: int = 0
    ) -> str:
        """Send commands; return the box's reply line. Raises on failure or refusal."""
        if not commands:
            raise ValueError("no command to send")
        if scenario_id:
            read_timeout = LOCAL_READ_TIMEOUT_SCENARIO
        elif commands[0].command_action == "CHANNEL":
            read_timeout = LOCAL_READ_TIMEOUT_CHANNEL
        else:
            read_timeout = LOCAL_READ_TIMEOUT
        frame = encrypt(
            local_payload(inst_code, commands, scenario_id=scenario_id),
            scenario=scenario_id != 0,
        )
        reply = await self.exchange(frame, read_timeout=read_timeout)
        if reply is None:
            # Like the app: the frame was delivered but not confirmed in time. It is
            # reported as sent, never re-sent through the cloud (no double action).
            _LOGGER.warning("box %s did not confirm the command in %ss", self.host, read_timeout)
            return ""
        if LOCAL_ACK not in reply:
            raise TelecoLocalError(f"box refused the command: {reply!r}")
        return reply

    async def diagnostic(self) -> str:
        """Read the box's diagnostic log (comma-separated 10-char entries)."""
        reply = await self.exchange(encrypt("DIAGNOSTIC" * 10), read_timeout=LOCAL_READ_TIMEOUT)
        if reply is None:
            raise TelecoLocalError(f"no diagnostic from {self.host}")
        return reply

    async def exchange(self, frame: str, *, read_timeout: float) -> str | None:
        """Send one frame and read one line; ``None`` if the reply timed out."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout
            )
        except (OSError, TimeoutError) as err:
            raise TelecoLocalError(f"cannot connect to {self.host}:{self.port}: {err}") from err
        try:
            writer.write(frame.encode("ascii"))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), read_timeout)
        except TimeoutError:
            return None
        except OSError as err:
            raise TelecoLocalError(f"no answer from {self.host}:{self.port}: {err}") from err
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        reply = line.decode("utf-8", "replace").strip()
        _LOGGER.debug("box %s replied %r", self.host, reply)
        return reply
