---
okf_version: "0.2"
---

# Overview

* [Daisy Teleco protocol notes](README.md) - How the Daisy Teleco Android app talks to the Teleco cloud and to the Daisy box, with the overall architecture and the validation status of these notes.

# Protocol reference

* [Cloud API](cloud-api.md) - HTTP API of the Teleco cloud: transport, session, response formats, identifiers, every endpoint with its JSON shape, and the polling done by the app.
* [Commands](commands.md) - How a device command is selected from the cloud command list and encoded, delivered and acknowledged, plus scenarios, system (box) commands and timers.
* [Devices](devices.md) - Device models and sub-models with their app and SDK classes, device flags, and the status items reported by devices and by the box.
* [Local channels](local.md) - LAN channel to the box on TCP port 400 (payload, obfuscation, diagnostic) and the plain-text setup access point.
