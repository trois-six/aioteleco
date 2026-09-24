"""Read-only probe of a real Teleco account: dump anonymised cloud responses.

Only the read endpoints in ``READ_ONLY`` can be called: any other endpoint (commands,
setup, delete, pair/unpair...) raises before a request is sent. Nothing is sent to
the box.

Usage (credentials from ``TELECO_EMAIL`` / ``TELECO_PASSWORD``)::

    uv run --env-file .env scripts/probe.py [--out probe-output] [--installation ID]

Each response is written, anonymised, to ``<out>/<endpoint>[-<id>].json``: e-mail,
password, instCode, session, account and node ids, installation name, coordinates, SSID, IP
and MAC addresses are replaced by fixed placeholders. The files are then checked
for leftovers of those values. Review them before copying any into
``tests/fixtures/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import aiohttp

from aioteleco.cloud.client import CloudClient, SessionFields
from aioteleco.const import Endpoint
from aioteleco.models import NetParam

READ_ONLY = frozenset(
    {
        Endpoint.ACCOUNT_LOGIN,
        Endpoint.ACCOUNT_LOGOUT,
        Endpoint.INSTALLATION_LIST,
        Endpoint.ROOM_LIST,
        Endpoint.ROOM_CONFIGURATION_LIST,
        Endpoint.SCENARIO_LIST,
        Endpoint.COMMAND_DEVICE_LIST,
        Endpoint.COMMAND_SCENARIO_LIST,
        Endpoint.STATUS_DEVICE_LIST,
        Endpoint.TIMER_DEVICE_LIST,
        Endpoint.NODE_STATUS,
    }
)

DOCS = Path(__file__).resolve().parent.parent / "docs" / "protocol"
IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
VERSION_KEYS = {"firmwareVersion", "workdays"}

JsonDict = dict[str, Any]


class ReadOnlyClient(CloudClient):
    """A CloudClient that refuses every endpoint outside ``READ_ONLY``."""

    async def _post_json(self, endpoint: Endpoint | str, body: JsonDict) -> JsonDict:
        if endpoint not in READ_ONLY:
            raise RuntimeError(f"probe is read-only, refusing {endpoint}")
        return await super()._post_json(endpoint, body)


class Anonymiser:
    """Replace personal values by stable placeholders, by key and by substring."""

    def __init__(self, email: str, password: str) -> None:
        self.secrets: dict[str, str] = {email: "user@example.com", password: "********"}
        self.ips: dict[str, str] = {}
        self.macs: dict[str, str] = {}
        self.versions: set[str] = set()  # dotted versions that look like IPs

    def learn_installation(self, inst: JsonDict, n: int) -> None:
        self.versions.update(str(inst[k]) for k in VERSION_KEYS if inst.get(k))
        for key, placeholder in (
            ("instCode", f"INSTCODE{n:02d}"),
            ("instDescription", f"Installation {n}"),
        ):
            if value := inst.get(key):
                self.secrets[str(value)] = placeholder

    def learn_session(self, id_session: str) -> None:
        self.secrets[id_session] = "SESSION"

    def learn_ssid(self, ssid: str) -> None:
        if ssid:
            self.secrets[ssid] = "MyWifi"

    def __call__(self, data: Any, key: str | None = None) -> Any:
        if isinstance(data, dict):
            return {k: self(v, k) for k, v in data.items()}
        if isinstance(data, list):
            return [self(v) for v in data]
        if key == "idAccount" and data is not None:
            return 1
        if key == "id" and isinstance(data, str):  # nodestatus object id
            return "0" * len(data)
        if key == "latitude" and data:
            return "45.000000"
        if key == "longitude" and data:
            return "7.000000"
        if isinstance(data, str):
            return self._text(data, key)
        return data

    def _text(self, value: str, key: str | None) -> str:
        # Longest first, so a secret containing another one is replaced whole.
        for secret in sorted(self.secrets, key=len, reverse=True):
            if len(secret) >= 3:
                value = value.replace(secret, self.secrets[secret])
        if key not in VERSION_KEYS:
            value = IP_RE.sub(self._ip, value)
        return MAC_RE.sub(lambda m: self._map(self.macs, m.group(), "00:00:5E:00:53:{:02X}"), value)

    def _ip(self, match: re.Match[str]) -> str:
        if match.group() in self.versions:
            return match.group()
        return self._map(self.ips, match.group(), "192.0.2.{}")

    @staticmethod
    def _map(table: dict[str, str], value: str, fmt: str) -> str:
        if value not in table:
            table[value] = fmt.format(len(table) + 1)
        return table[value]

    def leaks(self, text: str) -> list[str]:
        """Which learnt secrets, IPs or MACs still appear in ``text``."""
        found = [p for s, p in self.secrets.items() if len(s) >= 3 and s in text]
        found += [f"IP {p}" for ip, p in self.ips.items() if ip in text]
        found += [f"MAC {p}" for mac, p in self.macs.items() if mac in text]
        return found


class Probe:
    def __init__(self, client: CloudClient, anon: Anonymiser, out: Path) -> None:
        self.client = client
        self.anon = anon
        self.out = out
        self.raw: dict[str, Any] = {}  # name -> raw response, anonymised at the end

    async def call(
        self,
        name: str,
        endpoint: Endpoint,
        body: JsonDict,
        *,
        fields: SessionFields = SessionFields.ACCOUNT,
    ) -> JsonDict:
        data = await self.client.call_raw(endpoint, body, fields=fields)
        self.raw[name] = data
        if "codEsito" in data and data["codEsito"] != "S":
            print(f"  ! {name}: {data.get('msgEsito')!r}")
        return data

    def write(self) -> list[Path]:
        self.out.mkdir(parents=True, exist_ok=True)
        paths = []
        for name, data in self.raw.items():
            path = self.out / f"{name}.json"
            path.write_text(json.dumps(self.anon(data), indent=2, ensure_ascii=False) + "\n")
            paths.append(path)
        return paths


def _result(data: JsonDict) -> JsonDict:
    return data.get("valRisultato") or {}


def _keys(data: Any, out: set[str]) -> set[str]:
    if isinstance(data, dict):
        for k, v in data.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(data, list):
        for v in data:
            _keys(v, out)
    return out


async def run(email: str, password: str, out: Path, installation: str | None) -> int:
    anon = Anonymiser(email, password)
    async with aiohttp.ClientSession() as http:
        client = ReadOnlyClient(http, email, password)
        probe = Probe(client, anon, out)
        session = await client.login()
        anon.learn_session(session.id_session)
        try:
            await explore(probe, installation)
        finally:
            await client.logout()

    paths = probe.write()
    leaks = {p.name: anon.leaks(p.read_text()) for p in paths}
    leaks = {name: found for name, found in leaks.items() if found}
    if leaks:
        for p in paths:
            p.unlink()
        print(f"\nABORTED: personal data left in {leaks}; files deleted.", file=sys.stderr)
        return 1

    documented = "\n".join(p.read_text() for p in DOCS.glob("*.md"))
    undocumented = sorted(k for k in _keys(list(probe.raw.values()), set()) if k not in documented)
    print(f"\n{len(paths)} files written to {out}/ (anonymised, leak check passed)")
    if undocumented:
        print(f"Fields not mentioned in docs/protocol: {', '.join(undocumented)}")
    return 0


async def explore(probe: Probe, installation: str | None) -> None:
    data = await probe.call("account-installation-list", Endpoint.INSTALLATION_LIST, {})
    installations = _result(data).get("installationList") or []
    for n, inst in enumerate(installations, 1):
        probe.anon.learn_installation(inst, n)
    if installation is not None:
        installations = [
            i
            for i in installations
            if installation in (str(i.get("idInstallation")), i.get("instCode"))
        ]
    for n, inst in enumerate(installations, 1):
        await explore_installation(probe, inst, n)


async def explore_installation(probe: Probe, inst: JsonDict, n: int) -> None:
    id_inst, box_device = inst["idInstallation"], inst.get("idInstallationDevice")
    print(f"Installation {n}: firmware {inst.get('firmwareVersion')}, box device {box_device}")

    node = await probe.call(
        f"nodestatus-{id_inst}",
        Endpoint.NODE_STATUS,
        {"idInstallation": inst["instCode"]},
        fields=SessionFields.SESSION,
    )
    print(f"  node active: {node.get('nodeActive')}")

    if box_device:
        box = await probe.call(
            f"status-device-list-box-{box_device}",
            Endpoint.STATUS_DEVICE_LIST,
            {"idInstallation": id_inst, "idInstallationDevice": box_device},
        )
        for item in _result(box).get("statusitemList") or []:
            if item.get("statusItem") == "NET_PARAM" and (
                net := NetParam.parse(str(item.get("statusValue") or ""))
            ):
                probe.anon.learn_ssid(net.ssid)
                print("  local IP known: yes" if net.ip != "0" else "  local IP known: no")
        items = [i.get("statusItem") for i in _result(box).get("statusitemList") or []]
        print(f"  box status items: {', '.join(map(str, items))}")

    await probe.call(f"room-list-{id_inst}", Endpoint.ROOM_LIST, {"idInstallation": id_inst})
    rooms = await probe.call(
        f"room-configuration-list-{id_inst}",
        Endpoint.ROOM_CONFIGURATION_LIST,
        {"idInstallation": id_inst},
    )
    for room in _result(rooms).get("roomList") or []:
        print(f"  room {room.get('roomDescription')!r}")
        for dev in room.get("deviceList") or []:
            await explore_device(probe, id_inst, dev)

    scenarios = await probe.call(
        f"scenario-list-{id_inst}", Endpoint.SCENARIO_LIST, {"idInstallation": id_inst}
    )
    for scen in _result(scenarios).get("scenarioList") or []:
        id_scen = scen.get("idInstallationScenario")
        print(f"  scenario {id_scen} {scen.get('scenarioDescription')!r}")
        await probe.call(
            f"command-scenario-list-{id_scen}",
            Endpoint.COMMAND_SCENARIO_LIST,
            {"idInstallation": id_inst, "idInstallationScenario": id_scen},
        )


async def explore_device(probe: Probe, id_inst: int, dev: JsonDict) -> None:
    id_dev = dev.get("idInstallationDevice")
    body = {"idInstallation": id_inst, "idInstallationDevice": id_dev}
    print(
        f"    device {id_dev} {dev.get('label')!r}: model {dev.get('idDevicemodel')}"
        f" sub-model {dev.get('remoteControlCode')!r} type {dev.get('idDevicetype')}"
        f" index {dev.get('deviceIndex')} feedback {dev.get('feedback')}"
    )
    for cmd in dev.get("deviceCommandList") or []:
        print(
            f"      {cmd.get('commandAction')}/{cmd.get('commandParam') or '*'}"
            f" -> {cmd.get('idDevicetypeCommandModel')} {cmd.get('lowlevelCommand')!r}"
        )

    status = await probe.call(f"status-device-list-{id_dev}", Endpoint.STATUS_DEVICE_LIST, body)
    for item in _result(status).get("statusitemList") or []:
        name, code = item.get("statusItem"), item.get("statusitemCode")
        differs = "" if name == code else f"  (statusitemCode {code!r})"
        print(f"      status {name} = {item.get('statusValue')!r}{differs}")

    commands = await probe.call(f"command-device-list-{id_dev}", Endpoint.COMMAND_DEVICE_LIST, body)
    listed = {c.get("idInstallationDeviceCommand") for c in dev.get("deviceCommandList") or []}
    fetched = {
        c.get("idInstallationDeviceCommand") for c in _result(commands).get("commandList") or []
    }
    if listed != fetched:
        print(f"      command-device-list differs: {sorted(map(str, fetched ^ listed))}")

    timers = await probe.call(f"timer-device-list-{id_dev}", Endpoint.TIMER_DEVICE_LIST, body)
    if count := len(_result(timers).get("timerList") or []):
        print(f"      {count} timer(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("probe-output"))
    parser.add_argument("--installation", help="idInstallation or instCode (default: all)")
    args = parser.parse_args()
    email, password = os.environ.get("TELECO_EMAIL"), os.environ.get("TELECO_PASSWORD")
    if not email or not password:
        print("Set TELECO_EMAIL and TELECO_PASSWORD (e.g. uv run --env-file .env ...)")
        return 2
    return asyncio.run(run(email, password, args.out, args.installation))


if __name__ == "__main__":
    sys.exit(main())
