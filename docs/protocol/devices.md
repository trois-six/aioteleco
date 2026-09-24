---
type: Reference
title: Devices
description: "Device models and sub-models with their app and SDK classes, device flags, and the status items reported by devices and by the box."
tags: [teleco, devices, status]
sources:
  - id: daisy-app
    resource: https://play.google.com/store/apps/details?id=com.telecoautomation.daisy
    title: Daisy Teleco Android app (com.telecoautomation.daisy), static analysis
---

# Devices

## Models

The app picks a device's class and screen from **`idDevicemodel`** and its sub-model
**`remoteControlCode`** (`DeviceFactory#castDevice`, `DeviceActionActivity#onCreate`).
It never reads `idDevicetype`: `DeviceDao#saveFromApi` does not even copy it. The values
seen by the previous version of this library (21 white LED, 22 awning, 23 RGB LED,
24 slats) are `idDevicetype` values and use a different numbering from the models below.

| Model | Box code | App class (sub-model) | Meaning | SDK class |
|---|---|---|---|---|
| 16 | LMP | `LightDevice` (`1` / empty), `OnOffReadOnlyDevice` (`2`), `DeicingDevice` (`3`), `AntiSnowDevice` (`4`), `NebulizerDevice` (`5`) | on/off | `Light` / `OnOffDevice` |
| 17 | DIM | `LightDimmerDevice` | dimmer with steps | `Dimmer` |
| 18 | HEA | `HeaterDevice` | heater with steps | `Heater` |
| 19 | FAN | `FanDevice` | fan | `Fan` |
| 20 | HEQ | `Heater4ChannelsDevice` | heater, 4 channels | `Heater` |
| 21 | PER | `RollingShutterDevice` | rolling shutter | `Cover` |
| 22 | CAN | `GateDevice` | gate | `Cover` |
| 23 | SER | `GarageDevice` | garage door | `Cover` |
| 24 | SOL | `SunWingDevice` | awning | `Cover` |
| 25 | TEN | `ScreenDevice` | vertical screen | `Cover` |
| 26 | RGB | `LightRgbDevice` | RGB light, 8 presets + cycle | `PresetRgbLight` |
| 27 | PEG | `AdjustableSlatsDevice` | pergola slats, steps close/33/66/100 | `Slats` |
| 28 | AUD | `AudioDevice` | audio | `Audio` |
| 31 | PEQ | `AdjustableSlatsOpenStopCloseDevice` | slats, open/stop/close only | `Cover` |
| 32 | COP | `RgbColorPickerDevice` | RGB color wheel | `ColorLight` |
| 33 | DYP | `DynamicWhitePickerDevice` | tunable white | `WhiteLight` |
| 34 | DMS | `LightDimmerSliderDevice` | dimmer with slider | `Dimmer` |
| 41 | — | `GenericDevice1..7` (count of `§` in the label) | 1–7 button remote | `Device` |
| 42 | — | `GenericSlider` | 7-slider remote | `Device` |
| 43 | GAK | `GarageAskDevice` | garage door with "ask" | `Cover` |
| 44 | RAS | `RetractableSlatsDevice` (`""`/`1`/`2`/`3`), `RetractableSlats4Gibus` (`4`, `5`) | retractable slats | `Slats` |
| 45 | ARS | `AutomaticRetractableSlatsDevice` | automatic retractable slats | `Slats` |
| 46 | CRP | `RgbColorRotationPickerDevice` | RGB with color rotation | `ColorLight` |
| 47 | WIN | `WindowDevice` | window | `Cover` |

Models allowed for the Daisy brand (`Utils.COMPATIBLE_DEVICES_ID`): 16–28, 31–34, 43, 44,
47; sub-models `16: ["1"]`, `44: ["", "1", "2", "3"]`.

Device flags (strings `"S"`/`"N"`): `favorite`, `feedback` (the box reports the real
state; adds the `-F` suffix to the action), `directOnly` (the UI refuses to drive it
when not on the home network; it does not change the transport), `activetimer`.

## Status items

`status-device-list` returns `statusitemList`; the app switches on `statusItem`.

| Item | Values | Read by |
|---|---|---|
| `POWER` | `ON` / `OFF` | lights, heaters, audio, room list |
| `LEVEL` | integer 0–100; generic slider: 7 values joined by `§` | steps screens, covers |
| `OPEN_CLOSE` | `OPEN` / `CLOSE` / `STOP` / other (moving) | covers, slats |
| `RETR` | `YES` = slats retracted (models 44/45) | slats |
| `COLOR` | `AxxxRxxxGxxxBxxx`, 3-digit zero-padded, A = brightness 0–100; model 26: preset name | color lights |
| `CYCLE` | `ON` / `PAUSE` / `PLAY` / `OFF` | RGB lights |
| `SPEED` | `33` / `67` / `100` | RGB lights, fans |
| `AUDIO_PLAY_PAUSE` | `PLAY` / `PAUSE` | audio |

Status items of the box device (`Installation.idInstallationDevice`):

| Item | Value |
|---|---|
| `NET_PARAM` | `IP: a.b.c.d NameNet: <ssid>`, the box's LAN address |
| `SIGNAL` | Wi-Fi signal |
| `CURRENT_TIME` | box clock |
| `DIAGNOSTIC` | log, CRLF-separated text or JSON |
| `UPDATE_STATUS`, `RES_VAL`, `PAIRING_STATUS`, `TX_NUM` | firmware update and remote pairing |

RGB presets of model 26 (`LightRgbDeviceActionFragment#setupPresetColors`): RED, GREEN,
BLUE, MILK, CYAN, YELLOW, PURPLE, WHITE.
