"""``teleco`` command line: drive and diagnose Daisy installations.

Credentials come from ``--email/--password``, the ``TELECO_EMAIL`` /
``TELECO_PASSWORD`` environment variables, or ``~/.config/aioteleco/config.toml``::

    email = "me@example.com"
    password = "..."
    local_ip = "192.168.1.50"   # optional
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any

try:
    import typer
except ImportError:  # pragma: no cover
    sys.exit("The CLI needs the 'cli' extra: pip install 'aioteleco[cli]'")

import aiohttp

from .devices import ColorLight, Cover, Device, Dimmer, OnOffDevice, PresetRgbLight, Slats
from .diagnostics import collect
from .exceptions import TelecoError
from .hub import TelecoHub
from .local.crypto import decrypt
from .models import Installation
from .transport import SendResult, TransportMode

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / (
    "aioteleco/config.toml"
)

app = typer.Typer(help="Control Teleco Automation Daisy boxes.", no_args_is_help=True)
cover_app = typer.Typer(help="Covers, awnings and pergola slats.", no_args_is_help=True)
light_app = typer.Typer(help="Lights.", no_args_is_help=True)
scenario_app = typer.Typer(help="Scenarios.", no_args_is_help=True)
app.add_typer(cover_app, name="cover")
app.add_typer(light_app, name="light")
app.add_typer(scenario_app, name="scenario")


@dataclass
class Options:
    email: str | None = None
    password: str | None = None
    installation: str | None = None
    transport: TransportMode = TransportMode.AUTO
    local_ip: str | None = None
    as_json: bool = False


OPTS = Options()


@app.callback()
def main_options(
    email: Annotated[str | None, typer.Option(envvar="TELECO_EMAIL")] = None,
    password: Annotated[str | None, typer.Option(envvar="TELECO_PASSWORD")] = None,
    installation: Annotated[
        str | None, typer.Option("--installation", "-i", help="id, code or name")
    ] = None,
    transport: Annotated[TransportMode, typer.Option(help="how to send commands")] = (
        TransportMode.AUTO
    ),
    local_ip: Annotated[
        str | None, typer.Option(envvar="TELECO_LOCAL_IP", help="box IP on the LAN")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
    debug: Annotated[bool, typer.Option(help="verbose logs")] = False,
) -> None:
    config: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        config = tomllib.loads(CONFIG_PATH.read_text())
    OPTS.email = email or config.get("email")
    OPTS.password = password or config.get("password")
    OPTS.installation = installation or config.get("installation")
    OPTS.transport = transport
    OPTS.local_ip = local_ip or config.get("local_ip")
    OPTS.as_json = as_json
    logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING)


def _run[T](func: Callable[[TelecoHub, Installation], Awaitable[T]], *, load: bool = True) -> T:
    if not OPTS.email or not OPTS.password:
        typer.echo(
            "Missing credentials (--email/--password, TELECO_EMAIL/TELECO_PASSWORD).", err=True
        )
        raise typer.Exit(2)
    email, password = OPTS.email, OPTS.password

    async def runner() -> T:
        async with aiohttp.ClientSession() as http:
            hub = TelecoHub(
                http, email, password, transport=OPTS.transport, local_host=OPTS.local_ip
            )
            try:
                await hub.connect()
                inst = hub.installation(OPTS.installation)
                if load:
                    await hub.load(inst)
                return await func(hub, inst)
            finally:
                await hub.close()

    try:
        return asyncio.run(runner())
    except TelecoError as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err


def _print(data: Any, text: str | None = None) -> None:
    if OPTS.as_json or text is None:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        typer.echo(text)


def _result(result: SendResult) -> None:
    _print(asdict(result), f"sent via {result.channel} ({result.detail or 'no reply'})")


def _device[D: Device](hub: TelecoHub, key: str, kind: type[D]) -> D:
    dev = hub.device(key)
    if not isinstance(dev, kind):
        raise TelecoError(f"{dev.name!r} is a {dev.model_name}, not a {kind.__name__}")
    return dev


@app.command()
def installations() -> None:
    """List the boxes of the account."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        rows = [
            {
                "id": i.id_installation,
                "code": i.inst_code,
                "name": i.description,
                "firmware": i.firmware_version,
                "online": await hub.api.node_active(i),
            }
            for i in hub.installations
        ]
        _print(
            rows,
            "\n".join(
                f"{r['id']}\t{r['code']}\t{r['name']}\tfw {r['firmware']}\t"
                f"{'online' if r['online'] else 'OFFLINE'}"
                for r in rows
            ),
        )

    _run(go, load=False)


@app.command()
def devices(
    status: Annotated[bool, typer.Option(help="also fetch each device status")] = False,
) -> None:
    """List rooms and devices."""

    async def go(hub: TelecoHub, inst: Installation) -> None:
        rows = []
        for dev in hub.devices(inst):
            if status:
                await dev.refresh()
            rows.append(
                {
                    "id": dev.id,
                    "name": dev.name,
                    "room": dev.room.description,
                    "model": dev.model,
                    "model_name": dev.model_name,
                    "sub_model": dev.info.sub_model,
                    "family": dev.family.value,
                    "commands": [
                        f"{c.command_action}={c.command_param}" for c in dev.info.commands
                    ],
                    "status": dev.status,
                }
            )
        _print(
            rows,
            "\n".join(
                f"{r['id']}\t{r['name']}\t[{r['room']}]\t{r['model_name']} ({r['model']})"
                + (f"\t{r['status']}" if status else "")
                for r in rows
            ),
        )

    _run(go)


@app.command()
def status(device: str) -> None:
    """Show a device status."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        dev = hub.device(device)
        values = await dev.refresh()
        _print(values, "\n".join(f"{k}: {v}" for k, v in values.items()))

    _run(go)


@app.command()
def box() -> None:
    """Show the box state (online, local IP, signal...)."""

    async def go(hub: TelecoHub, inst: Installation) -> None:
        info = await hub.box_info(inst)
        _print(
            asdict(info),
            f"online: {info.online}\nlocal ip: {info.net.ip if info.net else '?'}"
            f"\nssid: {info.net.ssid if info.net else '?'}\nsignal: {info.signal}"
            f"\ntime: {info.current_time}\nfirmware: {info.firmware_version}",
        )

    _run(go, load=False)


@app.command()
def send(device: str, action: str, param: str) -> None:
    """Send a raw (action, param) request, e.g. `send Pergola OPEN_STOP_CLOSE STOP`."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        _result(await hub.device(device).send(action, param))

    _run(go)


@cover_app.command("open")
def cover_open(device: str) -> None:
    _run(lambda hub, _: _then(_device(hub, device, Cover).open()))


@cover_app.command("close")
def cover_close(device: str) -> None:
    _run(lambda hub, _: _then(_device(hub, device, Cover).close()))


@cover_app.command("stop")
def cover_stop(device: str) -> None:
    _run(lambda hub, _: _then(_device(hub, device, Cover).stop()))


@cover_app.command("position")
def cover_position(device: str, percent: int) -> None:
    """Move slats to the nearest step (0/33/66/100)."""
    _run(lambda hub, _: _then(_device(hub, device, Slats).set_position(percent)))


@light_app.command("on")
def light_on(device: str) -> None:
    _run(lambda hub, _: _then(_device(hub, device, OnOffDevice).turn_on()))


@light_app.command("off")
def light_off(device: str) -> None:
    _run(lambda hub, _: _then(_device(hub, device, OnOffDevice).turn_off()))


@light_app.command("color")
def light_color(
    device: str,
    red: int,
    green: int,
    blue: int,
    brightness: Annotated[int, typer.Option(min=0, max=100)] = 100,
) -> None:
    _run(
        lambda hub, _: _then(
            _device(hub, device, ColorLight).set_color((red, green, blue), brightness)
        )
    )


@light_app.command("preset")
def light_preset(device: str, name: str) -> None:
    """Preset color of an RGB light with presets (model 26)."""
    _run(lambda hub, _: _then(_device(hub, device, PresetRgbLight).set_preset(name.upper())))


@light_app.command("step")
def light_step(device: str, step: int) -> None:
    """Dimmer step 1..4."""
    _run(lambda hub, _: _then(_device(hub, device, Dimmer).set_step(step)))


@light_app.command("level")
def light_level(device: str, level: Annotated[int, typer.Argument(min=0, max=100)]) -> None:
    """Free dimmer level 0..100 (the device's parametric LEVEL command)."""
    _run(lambda hub, _: _then(_device(hub, device, Dimmer).set_level(level)))


async def _then(coro: Awaitable[SendResult]) -> None:
    _result(await coro)


@scenario_app.command("list")
def scenario_list() -> None:
    async def go(hub: TelecoHub, inst: Installation) -> None:
        scenarios = hub.data[inst.id_installation].scenarios
        _print(
            [{"id": s.id_installation_scenario, "name": s.description} for s in scenarios],
            "\n".join(f"{s.id_installation_scenario}\t{s.description}" for s in scenarios),
        )

    _run(go)


@scenario_app.command("run")
def scenario_run(scenario: str) -> None:
    async def go(hub: TelecoHub, inst: Installation) -> None:
        for s in hub.data[inst.id_installation].scenarios:
            if scenario in (str(s.id_installation_scenario), s.description):
                _result(await hub.run_scenario(inst, s))
                return
        raise TelecoError(f"unknown scenario {scenario!r}")

    _run(go)


@app.command()
def timers(device: str) -> None:
    """List a device's timers."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        dev: Device = hub.device(device)
        rows = [
            {
                "id": t.id_installation_device_timer,
                "date": t.timer_date,
                "days": t.days,
                "active": t.active,
                "param": t.command_param,
                "sun_event": t.sun_event if t.twilight else None,
                "offset": t.twilight_offset,
            }
            for t in dev.info.timers
        ]
        _print(rows)

    _run(go)


@app.command()
def raw(endpoint: str, body: str = "{}") -> None:
    """POST a raw JSON body to an endpoint (session fields are added)."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        _print(await hub.client.call_raw(endpoint, json.loads(body)))

    _run(go, load=False)


@app.command()
def diagnose(
    status: Annotated[bool, typer.Option(help="include device status")] = True,
) -> None:
    """Anonymised dump to attach to bug reports."""

    async def go(hub: TelecoHub, _: Installation) -> None:
        _print(await collect(hub, with_status=status))

    _run(go)


@app.command("decode-frame")
def decode_frame(frame: str) -> None:
    """Decode a captured LAN frame (port 400)."""
    message, timestamp, scenario = decrypt(frame)
    _print({"message": message, "timestamp": timestamp, "scenario": scenario})


def main() -> None:
    app()


if __name__ == "__main__":
    main()
