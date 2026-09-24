"""High-level entry point: :class:`TelecoHub`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiohttp

from .cloud.api import CloudApi
from .cloud.client import CloudClient
from .commands import WireCommand, build_device_command, build_scenario_commands, system_command
from .const import ACK_ACCEPTED, BASE_URL, StatusItemCode
from .devices import Device, device_class
from .exceptions import TelecoError, TelecoUnsupportedError
from .local.client import LocalClient
from .models import (
    Command,
    DeviceInfo,
    Installation,
    NetParam,
    Room,
    Scenario,
    ScenarioStep,
    StatusItem,
    Timer,
)
from .system import (
    QUERY_ACTIONS,
    box_command,
    delete_scenario_command,
    get_feedback_command,
    read_ap_channel_command,
    read_memory_command,
    scenario_string,
    set_ap_channel_command,
    set_time_command,
    set_wifi_command,
    tx_command,
    update_device_command,
    update_firmware_command,
    update_installation_name_command,
    update_scenario_command,
)
from .timers import del_timer_command, up_schedule_command, up_timers_command
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

    async def _resolve_steps(
        self, installation: Installation, steps: list[ScenarioStep], name: str = ""
    ) -> list[tuple[Command, DeviceInfo, str]]:
        """Scenario steps -> (command, device, value), in step order."""
        data = self.data.get(installation.id_installation) or await self.load(installation)
        by_command: dict[int, tuple[Command, DeviceInfo]] = {
            cmd.id_installation_device_command: (cmd, dev.info)
            for dev in data.devices.values()
            for cmd in dev.info.commands
        }
        out = []
        for step in sorted(steps, key=lambda s: s.command_index):
            if step.id_installation_device_command not in by_command:
                raise TelecoUnsupportedError(
                    f"scenario {name!r} uses unknown command {step.id_installation_device_command}"
                )
            cmd, info = by_command[step.id_installation_device_command]
            out.append((cmd, info, step.command_param))
        return out

    async def run_scenario(self, installation: Installation, scenario: Scenario) -> SendResult:
        steps = await self._resolve_steps(installation, scenario.steps, scenario.description)
        return await self.sender.send(
            installation,
            build_scenario_commands(steps),
            scenario_id=scenario.id_installation_scenario,
        )

    # -- scenarios -----------------------------------------------------------------

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
        """Create (id 0) or update a scenario in the cloud, then on the box.

        Like ``SetupScenarioActivity``: once the cloud has saved it, the box gets
        ``UP_SCEN`` with the scenario string, or ``DEL_SCEN`` if it has no step.
        """
        resolved = await self._resolve_steps(installation, steps, description)
        saved = await self.api.save_scenario(
            installation,
            description=description,
            steps=steps,
            id_installation_scenario=id_installation_scenario,
            icon=icon,
            order=order,
            id_installation_room=id_installation_room,
        )
        id_scenario = saved.id_installation_scenario or id_installation_scenario
        await self._send_scenario_to_box(installation, id_scenario, resolved)
        return saved

    async def delete_scenario(self, installation: Installation, scenario: Scenario) -> None:
        """Delete a scenario from the cloud, then from the box (``DEL_SCEN``)."""
        await self.api.delete_scenario(installation, scenario.id_installation_scenario)
        await self._box(
            installation,
            delete_scenario_command(
                installation.id_installation_device, scenario.id_installation_scenario
            ),
        )

    async def _send_scenario_to_box(
        self,
        installation: Installation,
        id_scenario: int,
        steps: list[tuple[Command, DeviceInfo, str]],
    ) -> None:
        box = installation.id_installation_device
        if steps:
            command = update_scenario_command(box, scenario_string(id_scenario, steps))
        else:
            command = delete_scenario_command(box, id_scenario)
        await self._box(installation, command)

    # -- remote controls (paired to a scenario) --------------------------------------

    async def pair_remote(self, installation: Installation, scenario: Scenario) -> SendResult:
        """Put the box in pairing mode for a remote bound to this scenario (``PAIR_TX``)."""
        steps = await self._resolve_steps(installation, scenario.steps, scenario.description)
        return await self.send_remote_command(
            installation,
            "PAIR_TX",
            scenario_string(scenario.id_installation_scenario, steps),
            scenario.id_installation_device,
        )

    async def unpair_remote(self, installation: Installation, scenario: Scenario) -> SendResult:
        """Forget the remote bound to this scenario (``UNPAIR_TX``)."""
        return await self.send_remote_command(
            installation,
            "UNPAIR_TX",
            str(scenario.id_installation_scenario),
            scenario.id_installation_device,
        )

    async def reset_remotes(self, installation: Installation, scenario: Scenario) -> SendResult:
        """Forget every remote bound to this scenario (``RESET_TX``)."""
        return await self.send_remote_command(
            installation,
            "RESET_TX",
            str(scenario.id_installation_scenario),
            scenario.id_installation_device,
        )

    async def send_remote_command(
        self, installation: Installation, action: str, param: str, id_installation_device: int
    ) -> SendResult:
        """Any remote pairing command (``PAIR_TX``, ``UNPAIR_TX``, ``RESET_TX``,
        ``PAIR_BUTTON``, ``UNPAIR_BUTTON``)."""
        return await self._box(installation, tx_command(action, param, id_installation_device))

    async def send_system(
        self, installation: Installation, action: str, param: str = ""
    ) -> SendResult:
        """Send any box-level command (GET_SIGNAL, GET_VERSION, SYNC_BOARD...) via the cloud."""
        return await self.sender.send(
            installation,
            [system_command(installation.id_installation_device, action, param)],
            cloud_only=True,
        )

    async def _box(
        self,
        installation: Installation,
        command: WireCommand,
        *,
        until: tuple[str, ...] = (ACK_ACCEPTED,),
    ) -> SendResult:
        """Send one box command through the cloud and wait for the box's ``ACK``."""
        return await self.sender.send(installation, [command], cloud_only=True, until=until)

    # -- box queries: the answer lands in the box's status items (see box_info) -------

    async def query_box(self, installation: Installation, action: str) -> SendResult:
        """Ask the box to refresh a status item: one of ``QUERY_ACTIONS``
        (GET_TIME, GET_SIGNAL, GET_VERSION, GET_INFO, GET_DIAGNOSTIC)."""
        if action not in QUERY_ACTIONS:
            raise ValueError(f"{action!r} is not one of {QUERY_ACTIONS}")
        return await self._box(
            installation, box_command(installation.id_installation_device, action)
        )

    async def request_feedback(self, device: Device) -> SendResult:
        """Ask the box for a device's feedback (``GET_FEEDBACK``)."""
        return await self._box(device.installation, get_feedback_command(device.info))

    async def read_ap_channel(self, installation: Installation) -> SendResult:
        return await self._box(
            installation, read_ap_channel_command(installation.id_installation_device)
        )

    async def test_scan(self, installation: Installation) -> SendResult:
        """``TEST_SCAN`` (radio scan test of the box setup screen)."""
        return await self._box(
            installation, box_command(installation.id_installation_device, "TEST_SCAN")
        )

    # -- box configuration --------------------------------------------------------------

    async def rename_installation(self, installation: Installation, name: str) -> None:
        """Rename the installation in the cloud, then on the box (``UP_INST_NAME``)."""
        await self.api.rename_installation(installation, name)
        installation.description = name
        await self._box(
            installation,
            update_installation_name_command(installation.id_installation_device, name),
        )

    async def update_device(self, device: Device) -> SendResult | None:
        """Push a device's options to the box (``UP_DEV``); only firmware >= 1.3.3."""
        inst = device.installation
        if not inst.firmware_at_least("1.3.3"):
            return None
        return await self._box(
            inst, update_device_command(device.info, inst.id_installation_device)
        )

    async def set_ap_channel(self, installation: Installation, *, static: bool) -> SendResult:
        return await self._box(
            installation,
            set_ap_channel_command(installation.id_installation_device, static=static),
        )

    async def set_wifi(self, installation: Installation, ssid: str, password: str) -> SendResult:
        """Change the Wi-Fi network the box joins (``SET_WIFI``)."""
        return await self._box(
            installation, set_wifi_command(installation.id_installation_device, ssid, password)
        )

    async def set_box_time(self, installation: Installation, value: str) -> SendResult:
        return await self._box(
            installation, set_time_command(installation.id_installation_device, value)
        )

    async def update_firmware(self, installation: Installation, url: str) -> SendResult:
        """Flash the box with the firmware at ``url`` (``UPDATE_BOARD``)."""
        return await self._box(
            installation, update_firmware_command(installation.id_installation_device, url)
        )

    async def read_memory(self, installation: Installation, address: str, count: str) -> SendResult:
        return await self._box(
            installation, read_memory_command(installation.id_installation_device, address, count)
        )

    async def sync_box(self, installation: Installation) -> None:
        """Re-send the whole configuration to the box (``DaisyApplication#syncBoard``).

        ``SYNC_BOARD``, ``UP_INST_NAME``, ``UP_SCHED``, then ``UP_DEV`` per device
        (firmware >= 1.3.3), ``UP_SCEN`` per scenario bound to a remote, ``UP_TIMERS``
        per timer and ``END_SYNC``; sent as ``isScenario`` batches of 30, each acked.
        """
        data = await self.load(installation)
        box = installation.id_installation_device
        commands = [
            box_command(box, "SYNC_BOARD"),
            update_installation_name_command(box, installation.description),
            up_schedule_command(box, installation.active_timer),
        ]
        if installation.firmware_at_least("1.3.3"):
            commands += [update_device_command(d.info, box) for d in data.devices.values()]
        for scenario in data.scenarios:
            if await self._has_remote(installation, scenario):
                steps = await self._resolve_steps(
                    installation, scenario.steps, scenario.description
                )
                commands.append(
                    update_scenario_command(
                        box, scenario_string(scenario.id_installation_scenario, steps)
                    )
                )
        for device in data.devices.values():
            by_id = {c.id_installation_device_command: c for c in device.info.commands}
            for timer in device.info.timers:
                if (command := by_id.get(timer.id_installation_device_command)) is not None:
                    commands.append(up_timers_command(box, timer, device.info, command))
        commands.append(box_command(box, "END_SYNC"))
        for start in range(0, len(commands), 30):
            await self.api.send_and_wait(
                installation,
                commands[start : start + 30],
                is_scenario=True,
                ack_timeout=self.sender.ack_timeout,
                until=(ACK_ACCEPTED,),
            )

    async def _has_remote(self, installation: Installation, scenario: Scenario) -> bool:
        """A remote is bound to the scenario (its ``TX_NUM`` > 0 or ``PAIRING_STATUS`` ON)."""
        if not scenario.id_installation_device:
            return False
        items = await self.api.device_status(installation, scenario.id_installation_device)
        for item in items:
            if item.code == StatusItemCode.TX_NUM and item.status_value.isdigit():
                if int(item.status_value) > 0:
                    return True
            elif item.code == StatusItemCode.PAIRING_STATUS and item.status_value == "ON":
                return True
        return False

    # -- rooms ----------------------------------------------------------------------

    async def delete_room(self, installation: Installation, room: Room) -> None:
        """Delete a room like ``SetupRoomsListActivity``: cloud first, then the box.

        The box forgets the timers of the room's devices (``DEL_TIM``), and scenarios
        that used those devices are re-sent without them (or deleted if now empty).
        """
        data = self.data.get(installation.id_installation) or await self.load(installation)
        gone = {d.id_installation_device for d in room.devices}
        await self.api.delete_room(installation, room.id_installation_room)
        box = installation.id_installation_device
        for info in room.devices:
            for timer in info.timers:
                await self._box(
                    installation, del_timer_command(box, timer.id_installation_device_timer)
                )
        for scenario in data.scenarios:
            steps = await self._resolve_steps(installation, scenario.steps, scenario.description)
            kept = [s for s in steps if s[1].id_installation_device not in gone]
            if len(kept) != len(steps):
                await self._send_scenario_to_box(
                    installation, scenario.id_installation_scenario, kept
                )
        await self.load(installation)

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

    async def delete_timer(self, device: Device, id_timer: int) -> list[Timer]:
        """Delete one timer of a device, the way the app does.

        ``DEL_TIM`` is sent to the box and acked first; only then is the device's
        current cloud list saved back without that timer.
        """
        inst = device.installation
        await self.sender.send(
            inst,
            [del_timer_command(inst.id_installation_device, id_timer)],
            cloud_only=True,
            until=(ACK_ACCEPTED,),
        )
        # timer-device-list/ has been seen returning [] for a device that has timers:
        # take the current list from room-configuration-list instead.
        current = next(
            (
                info.timers
                for room in await self.api.rooms(inst, full=True)
                for info in room.devices
                if info.id_installation_device == device.id
            ),
            None,
        )
        if current is None:
            raise TelecoError(f"device {device.id} not found in the cloud configuration")
        remaining = [t for t in current if t.id_installation_device_timer != id_timer]
        device.info.timers = await self.api.save_timers(inst, device.id, remaining)
        return device.info.timers

    async def set_timer_active(self, device: Device, timer: Timer, active: bool) -> list[Timer]:
        """Enable or disable one timer (``SetupTimerListActivity#timerActive``).

        Disabling on firmware >= 1.3.3 removes it from the box (``DEL_TIM``); otherwise
        the box gets ``UP_TIMERS`` with the new flag. The cloud list is saved after the ack.
        """
        inst = device.installation
        timer.active = active
        if not active and inst.firmware_at_least("1.3.3"):
            command = del_timer_command(
                inst.id_installation_device, timer.id_installation_device_timer
            )
        else:
            cmd = next(
                (
                    c
                    for c in device.info.commands
                    if c.id_installation_device_command == timer.id_installation_device_command
                ),
                None,
            )
            if cmd is None:
                raise TelecoUnsupportedError("timer command not found on the device")
            command = up_timers_command(inst.id_installation_device, timer, device.info, cmd)
        await self._box(inst, command)
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
