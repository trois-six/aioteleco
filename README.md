# aioteleco

[![PyPI](https://img.shields.io/pypi/v/aioteleco?logo=pypi&logoColor=white)](https://pypi.org/project/aioteleco/)
[![Docs](https://img.shields.io/badge/docs-trois--six.github.io%2Faioteleco-blue)](https://trois-six.github.io/aioteleco/)

Unofficial async Python SDK and command-line tool for **Teleco Automation** boxes, the
home-automation box behind the *Daisy Teleco* app and the apps Teleco builds for other
brands (Biossun, Brustor, Gibus, Pratic, Kettal, Wise…). It drives pergolas (slats,
retractable roofs), awnings, screens, shutters, lights (on/off, dimmers, RGB, tunable
white), heaters and more.

It talks to the Teleco cloud (`tmate.telecoautomation.com`) like the official apps do
and, when the box is reachable on your network, sends commands **directly to the box
over the LAN**.

> ⚠️ This project is not affiliated with, nor endorsed by, Teleco Automation or any of
> the brands listed below. It is based on the analysis of the Android app for
> interoperability. Brand names are trademarks of their respective owners. The devices
> it drives are motorised: test with the equipment in sight.

Full documentation (getting started, API reference, protocol notes):
<https://trois-six.github.io/aioteleco/>

## Supported apps / brands

Teleco builds one app per brand from a single codebase. Every brand app that uses a
cloud account talks to the same Teleco cloud and the same box, so an account created in
any of them works with aioteleco:

* Daisy Teleco
* Biossun
* Brustor
* Durmi
* Gibus
* Hardtop
* Kettal
* Pratic
* Wise

Each app enables its own subset of device models and a few brand-specific tweaks; the
SDK follows the Daisy app's behaviour. Reports are welcome (see `teleco diagnose`).

The same codebase also builds "direct" apps (Wi-Fi Products, Wise Direct) that work
without a cloud account; they are not covered.

## Status

Alpha: the protocol is fully mapped (see [docs/protocol](docs/protocol/README.md)) and
implemented; the API may still change.

## Install

```bash
pip install "aioteleco[cli]"   # SDK + command-line tool
pip install aioteleco          # SDK only
```

## Command line

Use the email and password of your account in the brand app. Credentials:
`--email/--password`, `TELECO_EMAIL`/`TELECO_PASSWORD`, or
`~/.config/aioteleco/config.toml` (the box LAN address can also be given with
`--local-ip` or `TELECO_LOCAL_IP`):

```toml
email = "me@example.com"
password = "…"
# local_ip = "192.0.2.10"   # optional: box address on your LAN
```

```bash
teleco installations            # your boxes, online or not
teleco devices --status          # rooms, devices, current state
teleco box                       # box LAN address, signal, firmware
teleco cover open "Pergola"      # open / close / stop
teleco cover position "Pergola" 66
teleco cover calibrate "Screen" # measure full travel times (interactive)
teleco cover travel "Screen" 40   # timed move to any position, then STOP
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
        inst = hub.installation()  # first box of the account
        data = await hub.load(inst)  # rooms, devices, scenarios
        for device in data.devices.values():
            await device.refresh()
            print(device, device.status)
        slats = next(d for d in data.devices.values() if isinstance(d, Slats))
        result = await slats.set_position(66)
        print(result.channel)  # "local" or "cloud"
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
