# aioteleco

Unofficial async Python SDK and command-line tool for **Teleco Automation Daisy** boxes:
pergolas (slats, retractable roofs), awnings, screens, shutters, lights (on/off, dimmers,
RGB, tunable white), heaters and more.

It talks to the Teleco cloud like the official *Daisy Teleco* app does and, when the box
is reachable on your network, sends commands **directly to the box over the LAN**.

> ⚠️ This project is not affiliated with Teleco Automation. It is based on the
> analysis of the Android app for interoperability. The devices it drives are
> motorised: test with the equipment in sight.

## Status

`1.0.0a1`: the protocol is fully mapped (see [docs/protocol](docs/protocol/README.md))
and implemented, but not yet validated on every device type. Reports from real
installations are welcome (see `teleco diagnose`).

## Install

```bash
pip install "aioteleco[cli]"   # SDK + command-line tool
pip install aioteleco          # SDK only
```

## Command line

Credentials: `--email/--password`, `TELECO_EMAIL`/`TELECO_PASSWORD`, or
`~/.config/aioteleco/config.toml`:

```toml
email = "me@example.com"
password = "…"
# local_ip = "192.168.1.50"   # optional: box address on your LAN
```

```bash
teleco installations            # your boxes, online or not
teleco devices --status          # rooms, devices, current state
teleco box                       # box LAN address, signal, firmware
teleco cover open "Pergola"      # open / close / stop
teleco cover position "Pergola" 66
teleco light color "LED" 255 120 0 --brightness 80
teleco scenario run "Evening"
teleco send "Pergola" OPEN_STOP_CLOSE STOP      # raw (action, param)
teleco --transport cloud cover stop "Pergola"   # force the cloud
teleco diagnose > teleco-diagnostics.json        # anonymised dump for bug reports
```

`--json` switches every command to JSON output.

## Library

```python
import asyncio
import aiohttp
from aioteleco import TelecoHub, Slats

async def main() -> None:
    async with aiohttp.ClientSession() as http:
        hub = TelecoHub(http, "me@example.com", "secret")  # transport="auto" by default
        await hub.connect()
        inst = hub.installation()          # first box of the account
        data = await hub.load(inst)        # rooms, devices, scenarios
        for device in data.devices.values():
            await device.refresh()
            print(device, device.status)
        slats = next(d for d in data.devices.values() if isinstance(d, Slats))
        result = await slats.set_position(66)
        print(result.channel)              # "local" or "cloud"
        await hub.close()

asyncio.run(main())
```

How it works:

* Every device receives its own list of commands from the cloud. The SDK picks the
  right one the way the app does, so no command id is hard-coded.
* **Transport**:
  * `auto`: the SDK tries the LAN when the box address is known (from the cloud, or
    `local_host=`) and falls back to the cloud if that fails.
  * `cloud`: the cloud only.
  * `local`: the LAN only.
* **State** is only available from the cloud (`status-device-list`). The box's LAN
  channel accepts commands but cannot report state.

## Development

```bash
uv sync
uv run pytest            # unit tests (no network)
uv run ruff check src tests && uv run mypy
```

## License

MIT
