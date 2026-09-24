"""Typed views of the cloud JSON payloads.

Field names on the wire are the Java field names of the app's Gson models
(no naming policy, nulls omitted). Yes/no flags are the strings "S"/"N".
Each model keeps the raw JSON it was built from so write endpoints (which often
re-post whole objects, e.g. room-setup) can echo unknown fields back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

JsonDict = dict[str, Any]


def yn(value: Any) -> bool:
    """Decode a Teleco "S"/"N" flag."""
    return bool(value == "S")


def to_yn(value: bool) -> str:
    return "S" if value else "N"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str(value: Any) -> str:
    return "" if value is None else str(value)


@dataclass(slots=True)
class Installation:
    """A Daisy box paired to the account (account-installation-list)."""

    id_installation: int
    id_installation_device: int  # the box itself, target of system commands
    inst_code: str  # used as `idInstallation` by the tmate20/* endpoints
    description: str
    firmware_version: str
    active_timer: bool
    workdays: str  # opaque; the app also reads it as the box hardware version
    installation_order: int
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> Installation:
        return cls(
            id_installation=_int(data.get("idInstallation")),
            id_installation_device=_int(data.get("idInstallationDevice")),
            inst_code=_str(data.get("instCode")),
            description=_str(data.get("instDescription")),
            firmware_version=_str(data.get("firmwareVersion")),
            active_timer=yn(data.get("activetimer")),
            workdays=_str(data.get("workdays")),
            installation_order=_int(data.get("installationOrder")),
            raw=data,
        )


@dataclass(slots=True)
class Command:
    """A command a device accepts (element of deviceCommandList / CommandCloud)."""

    id_installation_device_command: int
    id_installation_device: int
    id_devicetype_command_model: int
    command_action: str
    command_param: str
    lowlevel_command: str
    command_index: int
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> Command:
        return cls(
            id_installation_device_command=_int(data.get("idInstallationDeviceCommand")),
            id_installation_device=_int(data.get("idInstallationDevice")),
            id_devicetype_command_model=_int(data.get("idDevicetypeCommandModel")),
            command_action=_str(data.get("commandAction")),
            command_param=_str(data.get("commandParam")),
            lowlevel_command=_str(data.get("lowlevelCommand")),
            command_index=_int(data.get("commandIndex")),
            raw=data,
        )


@dataclass(slots=True)
class Timer:
    """A device timer (TimerCloud)."""

    id_installation_device_timer: int
    id_installation_device_command: int
    timer_order: int
    timer_date: str  # "yyyy-MM-dd HH:mm"
    active: bool
    days: str  # "S;S;S;S;S;N;N"
    twilight: bool  # crepuscolare
    sun_event: int  # albaTramonto: 0 none, 1 sunrise, 2 sunset
    twilight_offset: int  # crepuscolareOffset: -2..2
    command_param: str
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> Timer:
        return cls(
            id_installation_device_timer=_int(data.get("idInstallationDeviceTimer")),
            id_installation_device_command=_int(data.get("idInstallationDeviceCommand")),
            timer_order=_int(data.get("timerOrder")),
            timer_date=_str(data.get("timerDate")),
            active=yn(data.get("timerActive")),
            days=_str(data.get("giorni")),
            twilight=yn(data.get("crepuscolare")),
            sun_event=_int(data.get("albaTramonto")),
            twilight_offset=_int(data.get("crepuscolareOffset")),
            command_param=_str(data.get("commandParam")),
            raw=data,
        )

    def to_json(self) -> JsonDict:
        out = {k: v for k, v in self.raw.items() if v is not None}
        out.update(
            idInstallationDeviceTimer=self.id_installation_device_timer,
            idInstallationDeviceCommand=self.id_installation_device_command,
            timerOrder=self.timer_order,
            timerDate=self.timer_date,
            timerActive=to_yn(self.active),
            giorni=self.days,
            crepuscolare=to_yn(self.twilight),
            albaTramonto=self.sun_event,
            crepuscolareOffset=self.twilight_offset,
            commandParam=self.command_param,
        )
        return out


@dataclass(slots=True)
class DeviceInfo:
    """A device as configured in the cloud (DeviceCloud)."""

    id_installation_device: int
    id_devicemodel: int
    id_devicetype: int
    device_code: int
    device_index: int  # sent as `deviceCode` (string) in commands
    device_order: int
    label: str
    sub_model: str  # remoteControlCode
    favorite: bool
    feedback: bool
    direct_only: bool
    active_timer: bool
    commands: list[Command]
    timers: list[Timer]
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> DeviceInfo:
        return cls(
            id_installation_device=_int(data.get("idInstallationDevice")),
            id_devicemodel=_int(data.get("idDevicemodel")),
            id_devicetype=_int(data.get("idDevicetype")),
            device_code=_int(data.get("deviceCode")),
            device_index=_int(data.get("deviceIndex")),
            device_order=_int(data.get("deviceOrder")),
            label=_str(data.get("label")),
            sub_model=_str(data.get("remoteControlCode")),
            favorite=yn(data.get("favorite")),
            feedback=yn(data.get("feedback")),
            direct_only=yn(data.get("directOnly")),
            active_timer=yn(data.get("activetimer")),
            commands=[Command.from_json(c) for c in data.get("deviceCommandList") or []],
            timers=[Timer.from_json(t) for t in data.get("deviceTimersList") or []],
            raw=data,
        )

    def to_setup_json(self) -> JsonDict:
        """Device entry for a room-setup payload (commands and timers stripped)."""
        out = {
            k: v
            for k, v in self.raw.items()
            if v is not None and k not in ("deviceCommandList", "deviceTimersList")
        }
        out.update(
            idInstallationDevice=self.id_installation_device,
            idDevicemodel=self.id_devicemodel,
            idDevicetype=self.id_devicetype,
            deviceCode=self.device_code,
            deviceIndex=self.device_index,
            deviceOrder=self.device_order,
            label=self.label,
            remoteControlCode=self.sub_model,
            favorite=to_yn(self.favorite),
            feedback=to_yn(self.feedback),
            directOnly=to_yn(self.direct_only),
            activetimer=to_yn(self.active_timer),
        )
        return out


@dataclass(slots=True)
class Room:
    """A room and its devices (RoomCloud)."""

    id_installation_room: int
    id_roomtype: int
    description: str
    order: int
    devices: list[DeviceInfo]
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> Room:
        return cls(
            id_installation_room=_int(data.get("idInstallationRoom")),
            id_roomtype=_int(data.get("idRoomtype")),
            description=_str(data.get("roomDescription")),
            order=_int(data.get("roomOrder")),
            devices=[DeviceInfo.from_json(d) for d in data.get("deviceList") or []],
            raw=data,
        )

    def to_setup_json(self, id_installation: int) -> JsonDict:
        """Body for room-setup (session fields are added by the client)."""
        return {
            "idInstallation": id_installation,
            "idInstallationRoom": self.id_installation_room,
            "idRoomtype": self.id_roomtype,
            "roomDescription": self.description,
            "roomOrder": self.order,
            "deviceList": [d.to_setup_json() for d in self.devices],
        }


@dataclass(slots=True, frozen=True)
class StatusItem:
    """One entry of status-device-list."""

    status_item: str
    status_value: str
    statusitem_code: str
    lowlevel_statusitem: str
    id_installation_device_statusitem: int
    id_devicetype_statusitem_model: int

    @property
    def code(self) -> str:
        """The item name; the app switches on `statusItem`."""
        return self.status_item or self.statusitem_code

    @classmethod
    def from_json(cls, data: JsonDict) -> StatusItem:
        return cls(
            status_item=_str(data.get("statusItem")),
            status_value=_str(data.get("statusValue")),
            statusitem_code=_str(data.get("statusitemCode")),
            lowlevel_statusitem=_str(data.get("lowlevelStatusitem")),
            id_installation_device_statusitem=_int(data.get("idInstallationDeviceStatusitem")),
            id_devicetype_statusitem_model=_int(data.get("idDevicetypeStatusitemModel")),
        )


@dataclass(slots=True)
class ScenarioStep:
    """A step of a scenario (idInstallationDeviceCommand + value)."""

    id_installation_device_command: int
    command_index: int
    command_param: str

    @classmethod
    def from_json(cls, data: JsonDict) -> ScenarioStep:
        return cls(
            id_installation_device_command=_int(data.get("idInstallationDeviceCommand")),
            command_index=_int(data.get("commandIndex")),
            command_param=_str(data.get("commandParam")),
        )

    def to_json(self) -> JsonDict:
        return {
            "idInstallationDeviceCommand": self.id_installation_device_command,
            "commandIndex": self.command_index,
            "commandParam": self.command_param,
        }


@dataclass(slots=True)
class Scenario:
    """A scenario (ScenarioCloud)."""

    id_installation_scenario: int
    description: str
    icon: int
    order: int
    id_installation_room: int
    steps: list[ScenarioStep]
    raw: JsonDict = field(repr=False)

    @classmethod
    def from_json(cls, data: JsonDict) -> Scenario:
        return cls(
            id_installation_scenario=_int(data.get("idInstallationScenario")),
            description=_str(data.get("scenarioDescription")),
            icon=_int(data.get("icon")),
            order=_int(data.get("scenarioOrder")),
            id_installation_room=_int(data.get("idInstallationRoom")),
            steps=[ScenarioStep.from_json(c) for c in data.get("commandList") or []],
            raw=data,
        )


@dataclass(slots=True, frozen=True)
class NetParam:
    """Parsed NET_PARAM status item of the box: "IP: a.b.c.d NameNet: ssid"."""

    ip: str
    ssid: str

    @classmethod
    def parse(cls, value: str) -> NetParam | None:
        if "IP:" not in value:
            return None
        rest = value.split("IP:", 1)[1]
        ip, _, ssid_part = rest.partition("NameNet:")
        ip = ip.strip()
        if not ip:
            return None
        return cls(ip=ip, ssid=ssid_part.strip())
