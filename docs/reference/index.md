# API reference

Generated from the docstrings and type annotations of the `aioteleco` package. Everything
listed in `aioteleco.__all__` can be imported from the package root, e.g.
`from aioteleco import TelecoHub, Slats`.

| Page | Content |
|---|---|
| [TelecoHub](hub.md) | Entry point: login, installations, devices, scenarios, timers, box management |
| [Devices](devices.md) | One class per device family (`Cover`, `Slats`, `Light`, `Dimmer`, `ColorLight`…) |
| [Models](models.md) | Typed views of the cloud payloads (`Installation`, `Room`, `Scenario`, `Timer`…) |
| [Exceptions](exceptions.md) | `TelecoError` and its subclasses |
| [Transport](transport.md) | LAN / cloud selection, `TransportMode`, `SendResult` |
| [Commands, system and timers](commands.md) | Building device, box ("system") and timer commands |
| [Cloud API](cloud.md) | `CloudApi` (typed endpoints) and the low-level `CloudClient` |
| [Local channel](local.md) | LAN client (TCP port 400) and frame obfuscation |
| [Diagnostics and constants](misc.md) | Anonymised account dump, protocol constants |

The API is still alpha and may change between releases.
