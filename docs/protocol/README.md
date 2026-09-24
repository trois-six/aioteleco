---
type: Overview
title: Daisy Teleco protocol notes
description: "How the Daisy Teleco Android app talks to the Teleco cloud and to the Daisy box, with the overall architecture and the validation status of these notes."
tags: [teleco, daisy, protocol, architecture]
sources:
  - id: daisy-app
    resource: https://play.google.com/store/apps/details?id=com.telecoautomation.daisy
    title: Daisy Teleco Android app (com.telecoautomation.daisy), static analysis
---

# Daisy Teleco protocol notes

These notes document how the **Daisy Teleco** Android app (package
`com.telecoautomation.daisy`) talks to the Teleco cloud and to the Daisy box. They were
obtained by static analysis of the app, for interoperability purposes. The same codebase
also builds apps for other brands (Biossun, Brustor, Gibus, Kettal, Pratic…); their
specific code paths are disabled in the Daisy build and not covered here.

| File | Content |
|---|---|
| [cloud-api.md](cloud-api.md) | HTTP API: transport, session, every endpoint and its JSON shape |
| [commands.md](commands.md) | How a command is selected and encoded, system commands, acks, timers |
| [devices.md](devices.md) | Device models, sub-models, status items |
| [local.md](local.md) | LAN channel to the box (TCP 400), box setup access point |

References such as `DaisyApplication#sendCommand` point to the class and method of the
app. Methods jadx cannot decompile (`sendCommand`, `DeviceFactory#castDevice`,
`Utils#customGraphicCommandParam`) were read from smali.

Validation status: everything here comes from the app's code. Items confirmed on real
hardware are marked **✅ verified**; the rest is **not yet verified**.

## Architecture in one picture

```
 phone app ──HTTPS──▶ tmate.telecoautomation.com ──(box's own link)──▶ Daisy box ──radio──▶ motors / lights
     │                                                                    ▲
     └──────────── TCP :400 on the home LAN (commands only) ──────────────┘
```

* The cloud is the source of truth for configuration (rooms, devices, **the list of
  commands each device accepts**, scenarios, timers) and the only place where device
  **state** can be read (`status-device-list`).
* Commands can be delivered either through the cloud (`tmate20/feedthecommands` + ack
  polling) or directly to the box on the LAN (TCP port 400). The app prefers the LAN
  when the phone is on the box's Wi-Fi network.
* There is no push channel (no Firebase Cloud Messaging): the app polls.
