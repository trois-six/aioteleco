"""Choosing between the LAN and the cloud to deliver commands.

Mirrors the app: when the box's local IP is known, commands go to ``<ip>:400``
and fall back to the cloud if the box cannot be reached or refuses the frame.
Otherwise they go through ``tmate20/feedthecommands`` + ack polling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from .cloud.api import CloudApi
from .commands import WireCommand
from .const import ACK_ACCEPTED, ACK_PROCESSED
from .exceptions import TelecoLocalError
from .local.client import LocalClient
from .models import Installation

_LOGGER = logging.getLogger(__name__)


class TransportMode(StrEnum):
    AUTO = "auto"  # local when an IP is known, cloud otherwise / as fallback
    CLOUD = "cloud"
    LOCAL = "local"  # local only, never the cloud


class Channel(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(slots=True, frozen=True)
class SendResult:
    channel: Channel
    detail: str  # box reply line (local) or last MessageText (cloud)


class CommandSender:
    """Deliver commands to a Daisy box."""

    def __init__(
        self,
        api: CloudApi,
        *,
        mode: TransportMode = TransportMode.AUTO,
        ack_timeout: float = 15.0,
    ) -> None:
        self.api = api
        self.mode = mode
        self.ack_timeout = ack_timeout
        self._local_hosts: dict[str, str] = {}

    def set_local_host(self, installation: Installation, host: str | None) -> None:
        if host:
            self._local_hosts[installation.inst_code] = host
        else:
            self._local_hosts.pop(installation.inst_code, None)

    def local_host(self, installation: Installation) -> str | None:
        return self._local_hosts.get(installation.inst_code)

    async def send(
        self,
        installation: Installation,
        commands: list[WireCommand],
        *,
        scenario_id: int = 0,
        cloud_only: bool = False,
        until: tuple[str, ...] = (ACK_PROCESSED, ACK_ACCEPTED),
    ) -> SendResult:
        """Send device/scenario commands.

        ``cloud_only`` is used for box-level commands (timers, schedule...), which
        the app always sends through the cloud and whose ack it waits for.
        """
        host = self.local_host(installation)
        if self.mode is not TransportMode.CLOUD and not cloud_only:
            if host is None and self.mode is TransportMode.LOCAL:
                raise TelecoLocalError("local transport requested but the box IP is unknown")
            if host is not None:
                try:
                    reply = await LocalClient(host).send(
                        installation.inst_code, commands, scenario_id=scenario_id
                    )
                    return SendResult(Channel.LOCAL, reply)
                except TelecoLocalError as err:
                    if self.mode is TransportMode.LOCAL:
                        raise
                    _LOGGER.info("local send to %s failed (%s), using the cloud", host, err)
        ack = await self.api.send_and_wait(
            installation,
            commands,
            scenario_id=scenario_id,
            ack_timeout=self.ack_timeout,
            until=until,
        )
        return SendResult(Channel.CLOUD, ack.message_text or "")
