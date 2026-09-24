"""Typed wrappers around every cloud endpoint used by the Daisy app."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..commands import WireCommand, feed_post
from ..const import ACK_ACCEPTED, ACK_POLL_INTERVAL, ACK_PROCESSED, Endpoint
from ..exceptions import TelecoAckTimeoutError, TelecoCommandError
from ..models import Command, Installation, Room, Scenario, ScenarioStep, StatusItem, Timer
from .client import CloudClient, SessionFields, TmateResponse

_LOGGER = logging.getLogger(__name__)

JsonDict = dict[str, Any]


class CloudApi:
    """High-level access to the Teleco cloud endpoints."""

    def __init__(self, client: CloudClient) -> None:
        self.client = client

    # -- account -------------------------------------------------------------

    async def change_password(self, old: str, new: str) -> None:
        await self.client.call(Endpoint.CHANGE_PASSWORD, {"pwdOld": old, "pwdNew": new})

    async def reset_password(self, email: str) -> None:
        await self.client.call(Endpoint.RESET_PASSWORD, {"email": email}, fields=SessionFields.NONE)

    async def register(
        self,
        email: str,
        password: str,
        *,
        firstname: str,
        lastname: str,
        advertising: bool = False,
        app: str = "DAISY",
    ) -> Any:
        """Create an account (account-registration); the e-mail must then be confirmed.

        ``app`` is the brand app's id (its build flavor in upper case: ``DAISY``,
        ``BIOSSUN``, ``GIBUS``...).
        """
        body = {
            "idApp": app,
            "email": email,
            "pwd": password,
            "firstname": firstname,
            "lastname": lastname,
            "accountSource": "APP",
            "flgAdvert": "S" if advertising else "N",
            "flgBanner": "S",
        }
        return await self.client.call(
            Endpoint.ACCOUNT_REGISTRATION, body, fields=SessionFields.NONE
        )

    # -- installations ---------------------------------------------------------

    async def installations(self) -> list[Installation]:
        result = await self.client.call(Endpoint.INSTALLATION_LIST, {})
        return [Installation.from_json(i) for i in (result or {}).get("installationList") or []]

    async def node_active(self, installation: Installation) -> bool:
        """Is the box online for the cloud (``tmate20/nodestatus``)."""
        data = await self.client.call_raw(
            Endpoint.NODE_STATUS,
            {"idInstallation": installation.inst_code},
            fields=SessionFields.SESSION,
        )
        if data.get("idInstallation") is None:
            return False
        return bool(data.get("nodeActive"))

    async def pair_installation(
        self,
        inst_code: str,
        description: str,
        *,
        order: int = 0,
        active_timer: bool = True,
        workdays: str = "",
        firmware_version: str = "",
    ) -> Any:
        """Add a box to the account by its code (account-installation-pair)."""
        body = {
            "instCode": inst_code,
            "instDescription": description,
            "installationOrder": order,
            "activetimer": "S" if active_timer else "N",
            "workdays": workdays,
            "firmwareVersion": firmware_version,
        }
        result = await self.client.call(Endpoint.INSTALLATION_PAIR, body)
        return (result or {}).get("installationPair", result)

    async def unpair_installation(self, installation: Installation) -> Any:
        """Remove the box from the account (account-installation-unpair)."""
        result = await self.client.call(
            Endpoint.INSTALLATION_UNPAIR, {"idInstallation": installation.id_installation}
        )
        return (result or {}).get("installationUnpair", result)

    async def rename_installation(self, installation: Installation, description: str) -> None:
        body = {
            "idInstallation": installation.id_installation,
            "instCode": installation.inst_code,
            "instDescription": description,
            "installationOrder": installation.installation_order,
            "activetimer": "S" if installation.active_timer else "N",
            "workdays": installation.workdays,
            "firmwareVersion": installation.firmware_version,
        }
        await self.client.call(Endpoint.INSTALLATION_SETUP, body)

    # -- rooms / devices ---------------------------------------------------------

    async def rooms(self, installation: Installation, *, full: bool = True) -> list[Room]:
        """Rooms and devices. ``full`` also returns each device's commands and timers."""
        endpoint = Endpoint.ROOM_CONFIGURATION_LIST if full else Endpoint.ROOM_LIST
        result = await self.client.call(endpoint, {"idInstallation": installation.id_installation})
        return [Room.from_json(r) for r in (result or {}).get("roomList") or []]

    async def save_room(self, installation: Installation, room: Room) -> Room:
        """room-setup: re-posts the whole room with all of its devices."""
        result = await self.client.call(
            Endpoint.ROOM_SETUP, room.to_setup_json(installation.id_installation)
        )
        return Room.from_json(result or {})

    async def delete_room(self, installation: Installation, id_room: int) -> None:
        await self.client.call(
            Endpoint.ROOM_DELETE,
            {"idInstallation": installation.id_installation, "idInstallationRoom": id_room},
        )

    async def device_commands(
        self, installation: Installation, id_installation_device: int
    ) -> list[Command]:
        """command-device-list: the commands of one device."""
        result = await self.client.call(
            Endpoint.COMMAND_DEVICE_LIST,
            {
                "idInstallation": installation.id_installation,
                "idInstallationDevice": id_installation_device,
            },
        )
        return [Command.from_json(c) for c in (result or {}).get("commandList") or []]

    async def scenario_commands(
        self, installation: Installation, id_scenario: int
    ) -> list[Command]:
        """command-scenario-list: the commands of one scenario."""
        result = await self.client.call(
            Endpoint.COMMAND_SCENARIO_LIST,
            {
                "idInstallation": installation.id_installation,
                "idInstallationScenario": id_scenario,
            },
        )
        return [Command.from_json(c) for c in (result or {}).get("commandList") or []]

    async def device_status(
        self, installation: Installation, id_installation_device: int
    ) -> list[StatusItem]:
        result = await self.client.call(
            Endpoint.STATUS_DEVICE_LIST,
            {
                "idInstallation": installation.id_installation,
                "idInstallationDevice": id_installation_device,
            },
        )
        return [StatusItem.from_json(s) for s in (result or {}).get("statusitemList") or []]

    # -- scenarios --------------------------------------------------------------

    async def scenarios(self, installation: Installation) -> list[Scenario]:
        result = await self.client.call(
            Endpoint.SCENARIO_LIST, {"idInstallation": installation.id_installation}
        )
        return [Scenario.from_json(s) for s in (result or {}).get("scenarioList") or []]

    async def save_scenario(
        self,
        installation: Installation,
        *,
        description: str,
        steps: list[ScenarioStep],
        id_installation_scenario: int = 0,
        icon: int = 0,
        order: int = 0,
        id_installation_room: int = 0,
    ) -> Scenario:
        """Create (id 0) or update a scenario."""
        body = {
            "idInstallation": installation.id_installation,
            "idInstallationScenario": id_installation_scenario,
            "idInstallationRoom": id_installation_room,
            "scenarioDescription": description,
            "icon": icon,
            "scenarioOrder": order,
            "commandList": [s.to_json() for s in steps],
        }
        return Scenario.from_json(await self.client.call(Endpoint.SCENARIO_SETUP, body) or {})

    async def delete_scenario(self, installation: Installation, id_scenario: int) -> None:
        await self.client.call(
            Endpoint.SCENARIO_DELETE,
            {
                "idInstallation": installation.id_installation,
                "idInstallationScenario": id_scenario,
            },
        )

    # -- timers -----------------------------------------------------------------

    async def timers(self, installation: Installation, id_installation_device: int) -> list[Timer]:
        result = await self.client.call(
            Endpoint.TIMER_DEVICE_LIST,
            {
                "idInstallation": installation.id_installation,
                "idInstallationDevice": id_installation_device,
            },
        )
        return [Timer.from_json(t) for t in (result or {}).get("timerList") or []]

    async def save_timers(
        self, installation: Installation, id_installation_device: int, timers: list[Timer]
    ) -> list[Timer]:
        """Replace the device's full timer list (a timer left out is deleted)."""
        result = await self.client.call(
            Endpoint.TIMER_DEVICE_SETUP,
            {
                "idInstallation": installation.id_installation,
                "idInstallationDevice": id_installation_device,
                "timerList": [t.to_json() for t in timers],
            },
        )
        return [Timer.from_json(t) for t in (result or {}).get("timerList") or []]

    # -- commands ---------------------------------------------------------------

    async def feed_commands(
        self,
        installation: Installation,
        commands: list[WireCommand],
        *,
        scenario_id: int = 0,
        is_scenario: bool | None = None,
    ) -> TmateResponse:
        body = feed_post(
            installation.inst_code, commands, scenario_id=scenario_id, is_scenario=is_scenario
        )
        response = await self.client.call_tmate(Endpoint.FEED_THE_COMMANDS, body)
        if not response.ok:
            raise TelecoCommandError(response.message_text or "Command rejected by the cloud")
        return response

    async def get_ack(self, installation: Installation, action_reference: str) -> TmateResponse:
        return await self.client.call_tmate(
            Endpoint.GET_ACK_COMMAND,
            {"id": action_reference, "idInstallation": installation.inst_code},
        )

    async def send_and_wait(
        self,
        installation: Installation,
        commands: list[WireCommand],
        *,
        scenario_id: int = 0,
        is_scenario: bool | None = None,
        ack_timeout: float = 15.0,
        until: tuple[str, ...] = (ACK_PROCESSED, ACK_ACCEPTED),
    ) -> TmateResponse:
        """Send commands and poll ``getackcommand`` until the box confirms.

        Device screens stop on ``PROC``; timer/schedule flows wait for ``ACK``.
        """
        response = await self.feed_commands(
            installation, commands, scenario_id=scenario_id, is_scenario=is_scenario
        )
        reference = response.action_reference
        if reference is None:
            return response  # the app treats a missing reference as "done"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ack_timeout
        while True:
            await asyncio.sleep(ACK_POLL_INTERVAL)
            ack = await self.get_ack(installation, reference)
            _LOGGER.debug("ack %s: %s/%s", reference, ack.message_id, ack.message_text)
            if ack.message_text in until:
                return ack
            if not ack.ok and ack.message_type is not None:
                raise TelecoCommandError(ack.message_text or "Command rejected by the box")
            if loop.time() >= deadline:
                raise TelecoAckTimeoutError(
                    f"No confirmation for {reference} after {ack_timeout}s "
                    f"(last: {ack.message_text})"
                )
