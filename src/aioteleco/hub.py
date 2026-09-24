"""High-level entry point: :class:`TelecoHub`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiohttp

from .cloud.api import CloudApi
from .cloud.client import CloudClient
from .commands import build_device_command, build_scenario_commands, system_command
from .const import ACK_ACCEPTED, BASE_URL, StatusItemCode
from .devices import Device, device_class
from .exceptions import TelecoError, TelecoUnsupportedError
from .local.client import LocalClient
from .models import Command, DeviceInfo, Installation, NetParam, Room, Scenario, StatusItem, Timer
from .timers import up_schedule_command, up_timers_command
from .transport import CommandSender, SendResult, TransportMode

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BoxInfo:
    """What the cloud knows about a Daisy box (status of its own device)."""

    online: bool
    net: NetParam | None
    signal: str | None
    current_time: str | None
    firmware_version: str
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class InstallationData:
    installation: Installation
    rooms: list[Room]
    devices: dict[int, Device]
    scenarios: list[Scenario]


class TelecoHub:
    """Account-level access to Daisy installations, devices and scenarios.

    >>> async with aiohttp.ClientSession() as http:
    ...     hub = TelecoHub(http, "me@example.com", "secret")
    ...     await hub.connect()
    ...     data = await hub.load(hub.installations[0])
    ...     slats = next(d for d in data.devices.values() if d.family == "slats")
    ...     await slats.set_position(66)
    """

    def __init__(
        self,
        http: aiohttp.ClientSession,
        email: str,
        password: str,
        *,
        transport: TransportMode | str = TransportMode.AUTO,
        local_host: str | None = None,
        discover_local_ip: bool = True,
        base_url: str = BASE_URL,
        ack_timeout: float = 15.0,
    ) -> None:
        self.client = CloudClient(http, email, password, base_url=base_url)
        self.api = CloudApi(self.client)
        self.sender = CommandSender(
            self.api, mode=TransportMode(transport), ack_timeout=ack_timeout
        )
        self._configured_host = local_host
        self._discover_local_ip = discover_local_ip
        self.installations: list[Installation] = []
        self.data: dict[int, InstallationData] = {}

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> list[Installation]:
        """Log in and list the installations (boxes) of the account."""
        await self.client.login()
        self.installations = await self.api.installations()
        return self.installations

    async def close(self) -> None:
        try:
            await self.client.logout()
        except TelecoError as err:
            _LOGGER.debug("logout failed: %s", err)

    def installation(self, key: int | str | None = None) -> Installation:
        """Find an installation by id, instCode or description (default: first)."""
        if not self.installations:
            raise TelecoError("no installation on this account (call connect() first)")
        if key is None:
            return self.installations[0]
        for inst in self.installations:
            if key in (inst.id_installation, inst.inst_code, inst.description) or str(key) == str(
                inst.id_installation
            ):
                return inst
        raise TelecoError(f"unknown installation {key!r}")

    async def load(self, installation: Installation) -> InstallationData:
        """Fetch rooms, devices (with their commands) and scenarios."""
        rooms = await self.api.rooms(installation, full=True)
        scenarios = await self.api.scenarios(installation)
        devices: dict[int, Device] = {}
        for room in rooms:
            for info in room.devices:
                devices[info.id_installation_device] = device_class(info)(
                    self, installation, room, info
                )
        data = InstallationData(installation, rooms, devices, scenarios)
        self.data[installation.id_installation] = data
        if self._configured_host:
            self.sender.set_local_host(installation, self._configured_host)
        elif self._discover_local_ip and self.sender.mode is not TransportMode.CLOUD:
            try:
                await self.box_info(installation)
            except TelecoError as err:
                _LOGGER.debug("could not read the box network parameters: %s", err)
        return data

    def devices(self, installation: Installation | None = None) -> list[Device]:
        insts = [installation] if installation else self.installations
        return [
            dev
            for inst in insts
            if (data := self.data.get(inst.id_installation))
            for dev in data.devices.values()
        ]

    def device(self, key: int | str) -> Device:
        """Find a loaded device by id or label."""
        for dev in self.devices():
            if key in (dev.id, dev.name) or str(key) == str(dev.id):
                return dev
        raise TelecoError(f"unknown device {key!r}")

    # -- state -------------------------------------------------------------------

    async def refresh(self, installation: Installation) -> None:
        """Refresh the status of every device of an installation."""
        data = self.data.get(installation.id_installation) or await self.load(installation)
        for device in data.devices.values():
            device.update_status(await self.api.device_status(installation, device.id))

    async def box_info(self, installation: Installation) -> BoxInfo:
        items: list[StatusItem] = await self.api.device_status(
            installation, installation.id_installation_device
        )
        status = {item.code: item.status_value for item in items}
        net = NetParam.parse(status.get(StatusItemCode.NET_PARAM, ""))
        if net and net.ip not in ("0", "") and not self._configured_host:
            self.sender.set_local_host(installation, net.ip)
        return BoxInfo(
            online=await self.api.node_active(installation),
            net=net,
            signal=status.get(StatusItemCode.SIGNAL),
            current_time=status.get(StatusItemCode.CURRENT_TIME),
            firmware_version=installation.firmware_version,
            raw=status,
        )

    # -- commands ----------------------------------------------------------------

    async def send_command(self, device: Device, action: str, param: str) -> SendResult:
        commands = build_device_command(device.info, action, param)
        return await self.sender.send(device.installation, commands)

    async def run_scenario(self, installation: Installation, scenario: Scenario) -> SendResult:
        data = self.data.get(installation.id_installation) or await self.load(installation)
        by_command: dict[int, tuple[Command, DeviceInfo]] = {
            cmd.id_installation_device_command: (cmd, dev.info)
            for dev in data.devices.values()
            for cmd in dev.info.commands
        }
        steps = []
        for step in sorted(scenario.steps, key=lambda s: s.command_index):
            if step.id_installation_device_command not in by_command:
                raise TelecoUnsupportedError(
                    f"scenario {scenario.description!r} uses unknown command "
                    f"{step.id_installation_device_command}"
                )
            cmd, info = by_command[step.id_installation_device_command]
            steps.append((cmd, info, step.command_param))
        return await self.sender.send(
            installation,
            build_scenario_commands(steps),
            scenario_id=scenario.id_installation_scenario,
        )

    async def send_system(
        self, installation: Installation, action: str, param: str = ""
    ) -> SendResult:
        """Send a box-level command (GET_SIGNAL, GET_VERSION, SYNC_BOARD...) via the cloud."""
        return await self.sender.send(
            installation,
            [system_command(installation.id_installation_device, action, param)],
            cloud_only=True,
        )

    async def local_diagnostic(self, installation: Installation) -> str:
        host = self.sender.local_host(installation)
        if host is None:
            raise TelecoError("box IP unknown")
        return await LocalClient(host).diagnostic()

    # -- timers ----------------------------------------------------------------

    async def save_timer(self, device: Device, timer: Timer) -> list[Timer]:
        """Create (id 0) or update one timer of a device, the way the app does."""
        inst = device.installation
        timers = [t for t in device.info.timers if t.id_installation_device_timer != 0]
        if timer.id_installation_device_timer == 0:
            known = {t.id_installation_device_timer for t in timers}
            device.info.timers = await self.api.save_timers(inst, device.id, [*timers, timer])
            created = [t for t in device.info.timers if t.id_installation_device_timer not in known]
            if len(created) != 1:
                raise TelecoError(f"cannot tell which timer was created: {created}")
            timer = created[0]
        command = next(
            (
                c
                for c in device.info.commands
                if c.id_installation_device_command == timer.id_installation_device_command
            ),
            None,
        )
        if command is None:
            raise TelecoUnsupportedError("timer command not found on the device")
        await self.sender.send(
            inst,
            [up_timers_command(inst.id_installation_device, timer, device.info, command)],
            cloud_only=True,
            until=(ACK_ACCEPTED,),
        )
        merged = [
            timer if t.id_installation_device_timer == timer.id_installation_device_timer else t
            for t in device.info.timers
        ]
        device.info.timers = await self.api.save_timers(inst, device.id, merged)
        return device.info.timers

    async def set_timers_enabled(self, installation: Installation, enabled: bool) -> None:
        """Master switch of all the box timers (UP_SCHED, then installation-setup)."""
        await self.sender.send(
            installation,
            [up_schedule_command(installation.id_installation_device, enabled)],
            cloud_only=True,
            until=(ACK_ACCEPTED,),
        )
        installation.active_timer = enabled
        await self.api.rename_installation(installation, installation.description)
