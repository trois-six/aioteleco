# Getting started

## Install

aioteleco needs Python 3.12 or later.

```bash
pip install "aioteleco[cli]"   # SDK + command-line tool
pip install aioteleco          # SDK only
```

With [uv](https://docs.astral.sh/uv/), the command-line tool can also be run without
installing it: `uvx --from "aioteleco[cli]" teleco --help`.

## Command line

Use the email and password of your account in the brand app. Credentials are read, in
order, from `--email` / `--password`, from the `TELECO_EMAIL` / `TELECO_PASSWORD`
environment variables, or from `~/.config/aioteleco/config.toml`:

```toml
email = "me@example.com"
password = "…"
# local_ip = "192.0.2.10"   # optional: box address on your LAN
```

The box LAN address can also be given with `--local-ip` or `TELECO_LOCAL_IP`. Without it,
the SDK uses the address the box reports to the cloud.

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

Useful global options:

| Option | Meaning |
|---|---|
| `-i`, `--installation` | Box to use (id, code or name) when the account has several |
| `--transport auto\|cloud\|local` | How to deliver commands (default `auto`) |
| `--local-ip` | Box address on the LAN |
| `--json` | JSON output for every command |
| `--debug` | Verbose logs |

Run `teleco --help` or `teleco <command> --help` for the full list.

## Library

```python
import asyncio

import aiohttp

from aioteleco import Slats, TelecoHub


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

[`TelecoHub`][aioteleco.hub.TelecoHub] is the entry point: it logs in, lists the
installations (boxes) of the account and loads their rooms, devices and scenarios. Each
device is an instance of a class from [`aioteleco.devices`](reference/devices.md) with
methods matching what the app offers for that model.

### Transport

The `transport` argument of [`TelecoHub`][aioteleco.hub.TelecoHub] (and the
`--transport` option of the CLI) selects how commands are delivered:

* `auto`: the LAN when the box address is known (from the cloud, or `local_host=`), with
  a fallback to the cloud if that fails;
* `cloud`: the cloud only;
* `local`: the LAN only.

Every command returns a [`SendResult`][aioteleco.transport.SendResult] telling which
channel delivered it.

### State

Device state is only available from the cloud. The box's LAN channel accepts commands but
cannot report state, so `refresh()` always goes through the cloud.

### Errors

Every exception derives from [`TelecoError`][aioteleco.exceptions.TelecoError]; see
[Exceptions](reference/exceptions.md).

!!! danger "Motorised equipment"
    Commands move real equipment. Test with the pergola, awning or screen in sight, and
    never try box-level commands (Wi-Fi, firmware, unpairing, deletion) on an
    installation you depend on.
