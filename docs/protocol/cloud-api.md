---
type: API Reference
title: Cloud API
description: "HTTP API of the Teleco cloud: transport, session, response formats, identifiers, every endpoint with its JSON shape, and the polling done by the app."
resource: https://tmate.telecoautomation.com/
tags: [teleco, cloud, http, api]
sources:
  - id: daisy-app
    resource: https://play.google.com/store/apps/details?id=com.telecoautomation.daisy
    title: Daisy Teleco Android app (com.telecoautomation.daisy), static analysis
---

# Cloud API

## Transport

* Base URL `https://tmate.telecoautomation.com/` (`TMateApiClient#getClient`). A stage
  server `https://stage.tmate.telecoautomation.com` exists and is only used by the
  `daisystage` build flavor.
* Every endpoint is an HTTP **POST** with a JSON body (Retrofit + Gson with the default
  configuration: field names are the Java field names, **null fields are omitted**,
  `int`/`boolean` fields are always sent).
* Every request carries a static basic auth, `Authorization: Basic base64("teleco:tmate20")`
  (`AuthenticationInterceptor`).
* No certificate pinning, no custom headers. OkHttp default timeouts (10 s).

## Session

* `account-login` returns `{idSession: string, idAccount: int}`. Both are then sent **in
  the JSON body** of the other calls (`SessionBase` → `SessionCloud` → …).
* There is no client-side expiry and no refresh token. The app detects an invalid
  session through:
  * `msgEsito == "Session not valid"` (`ConfigurationActivity#handleRoomList`);
  * `nodestatus` returning `idSession: null` (`DaisyApplication#handleNodeStatus`).
  In both cases it logs out. The SDK logs in again once and retries the call.
* Login body (`CloudService#AccountLogin`):
  `{"email", "pwd", "deviceSerial": <ANDROID_ID>, "deviceDescription": "<Manufacturer Model>"}`.
  `idApp` is explicitly nulled, so it is not sent.
* Special `msgEsito` values on login: `"Wrong user name or password"`, and
  `"Request User registration not confirm"`, which comes **with `codEsito: "S"`** and
  must be treated as a failure.

## Response formats

1. Standard envelope, used by every `teleco/services/*` endpoint except `tmate20/*`:
   ```json
   {"codEsito": "S", "msgEsito": "…", "valRisultato": { … }}
   ```
   `codEsito` is `"S"` for success and `"E"` for an error; `msgEsito` is free text.
2. `tmate20/feedthecommands/` and `tmate20/getackcommand/` return PascalCase keys:
   ```json
   {"MessageType": "INFO", "MessageID": "…", "MessageText": "…", "ActionReference": "…"}
   ```
   `MessageType == "INFO"` means success. The app never reads `MessageID`.
3. `tmate20/nodestatus/` returns a bare object:
   `{"id", "idInstallation", "idSession", "nodeActive": bool}`.

## Identifiers

| Name | Meaning |
|---|---|
| `idAccount` | the user account |
| `idInstallation` | numeric id of a box (installation) for `teleco/services/*` |
| `instCode` | the box code (string); **used as `idInstallation` by the `tmate20/*` endpoints** |
| `idInstallationDevice` | a device; the box itself also has one (`Installation.idInstallationDevice`), which is the target of system commands |
| `deviceIndex` | the device's index in the box; sent as the **`deviceCode` string** in commands |
| `idInstallationDeviceCommand` | one command of one device |
| `idDevicetypeCommandModel` | the command model; sent as `commandId` |

## Endpoints

Request base types: `SessionBase {idSession}` ⊂ `SessionCloud {+idAccount}` ⊂
`InstallationPost {+idInstallation}` ⊂ `DevicePost {+idInstallationDevice}` /
`RoomPost {+idInstallationRoom}` / `ScenarioPost {+idInstallationScenario}`.

| Path (`teleco/services/…`) | Body | `valRisultato` | SDK |
|---|---|---|---|
| `account-login` | `User` (see above) | `{idSession, idAccount}` | `CloudClient.login` |
| `account-logout` | `{idSession}` | — | `CloudClient.logout` |
| `account-registration` | `{email, pwd, idApp:"<FLAVOR>" (e.g. "DAISY"), firstname, lastname, accountSource:"APP", flgAdvert, flgBanner:"S"}` | `ConfirmationUser` | `CloudApi.register` |
| `change-password` | `{idSession, idAccount, pwdOld, pwdNew}` | — | `CloudApi.change_password` |
| `reset-password` | `{email}` | — | `CloudApi.reset_password` |
| `account-installation-list` | `SessionCloud` | `{idAccount, installationList: [Install]}` | `CloudApi.installations` |
| `account-installation-pair` | `{…session, instCode, instDescription, installationOrder, activetimer, weekend, workdays, firmwareVersion}` | `InstallationPair` | `CloudApi.pair_installation` |
| `account-installation-unpair` | `InstallationPost` | `InstallationUnpair` | `CloudApi.unpair_installation` |
| `/teleco/services/installation-setup` | `InstallationPost` + `instCode, instDescription, installationOrder, activetimer, workdays, firmwareVersion` | `InstallationCloud` | `CloudApi.rename_installation` |
| `room-list` | `InstallationPost` | `{idAccount, idInstallation, roomList: [Room]}` | `CloudApi.rooms(full=False)` |
| `room-configuration-list` | `InstallationPost` | same, devices include `deviceCommandList` and `deviceTimersList` | `CloudApi.rooms()` |
| `room-setup` | `RoomCloud` (**the whole room with all its devices**) | `RoomSetup` | `CloudApi.save_room` |
| `room-delete` | `RoomPost` | — | `CloudApi.delete_room`, `TelecoHub.delete_room` |
| `scenario-list` | `InstallationPost` | `{scenarioList: [Scenario]}` | `CloudApi.scenarios` |
| `scenario-setup` | `ScenarioPost` + `icon, idInstallationRoom, scenarioDescription, scenarioOrder, commandList: [{idInstallationDeviceCommand, commandIndex, commandParam}]` | `ScenarioCloud` | `CloudApi.save_scenario` |
| `scenario-delete` | `ScenarioPost` | — | `CloudApi.delete_scenario` |
| `command-device-list` | `DevicePost` | `{commandList: [CommandCloud], …}` | `CloudApi.device_commands` |
| `command-scenario-list` | `ScenarioPost` | same | `CloudApi.scenario_commands` |
| `command-device-setup` | `DevicePost` | declared, never called by the app | — |
| `status-device-list` | `DevicePost` | `{statusitemList: [StatusItem]}` | `CloudApi.device_status` |
| `timer-device-list/` | `DevicePost` | `TimerSetup {timerList}` (has been seen empty for a device with timers) | `CloudApi.timers` |
| `timer-device-setup/` | `DevicePost` + `timerList` (**complete list**; a missing timer is deleted) | `TimerSetup` | `CloudApi.save_timers` |
| `tmate20/feedthecommands/` | `{idSession, idInstallation: instCode, idScenario, isScenario, commandsList: [CommandCloud]}` | tmate format | `CloudApi.feed_commands` |
| `tmate20/getackcommand/` | `{idSession, idInstallation: instCode, id: ActionReference}` | tmate format | `CloudApi.get_ack` |
| `tmate20/nodestatus/` | `{idSession, idInstallation: instCode}` | bare | `CloudApi.node_active` |

Paths with a trailing `/` must keep it.

### Main objects

```jsonc
// Install (element of installationList)
{"idInstallation": 456, "idInstallationDevice": 789, "instCode": "…", "instDescription": "Home",
 "installationOrder": 1, "activetimer": "S", "workdays": "2.0.0", "firmwareVersion": "1.4.0.1",
 "pairingdate": 0, "status": "…"}
// RoomCloud
{"idInstallationRoom": 10, "idRoomtype": 3, "roomDescription": "Garden", "roomOrder": 0,
 "deviceList": [DeviceCloud…]}
// DeviceCloud
{"idInstallationDevice": 20, "idDevicemodel": 27, "idDevicetype": 24, "deviceCode": 5, "deviceIndex": 5,
 "deviceOrder": 0, "label": "Pergola", "remoteControlCode": "", "favorite": "S", "feedback": "N",
 "directOnly": "N", "activetimer": "N", "deviceCommandList": [CommandCloud…], "deviceTimersList": [TimerCloud…]}
// CommandCloud
{"idInstallationDeviceCommand": 30, "idInstallationDevice": 20, "deviceCode": "5",
 "commandAction": "OPEN_STOP_CLOSE", "commandParam": "OPEN", "lowlevelCommand": "CH4",
 "commandId": 94, "idDevicetypeCommandModel": 94, "commandIndex": 0,
 "commandStatus": 0, "commandreceived": 0, "commandReceivedUR": "0", "commandProcessed": 0}
// StatusItem
{"statusItem": "LEVEL", "statusitemCode": "LEVEL", "statusValue": "66", "lowlevelStatusitem": "…",
 "idDevicetypeStatusitemModel": 1, "idInstallationDeviceStatusitem": 1}
// TimerCloud
{"idInstallationDeviceTimer": 40, "idInstallationDeviceCommand": 30, "timerOrder": 0,
 "timerDate": "2026-09-24 18:30", "timerDateExpire": null, "timerActive": "S", "giorni": "S;S;S;S;S;N;N",
 "crepuscolare": "N", "crepuscolareOffset": 0, "albaTramonto": 0, "commandParam": "OPEN", "info": null}
```

Notes:
* Yes/no flags are the strings `"S"` / `"N"`.
* The app switches on `statusItem`; `statusitemCode` is never read by the app. Real
  responses carry the same value in both.
* Commands returned by `room-configuration-list` and `command-device-list` also carry
  `commandCode`, a readable name the app does not use: `OPEN`, `STOP`, `POWERON`,
  `LEVEL25`…`LEVEL100` for `LEV1`…`LEV4`, `LEVEL_CUST` for the free level (`commandParam`
  `"0"`).
* `Install.workdays` is also read by the app as the box **hardware version** when it
  looks like `x.y.z` (`Install#getHardwareVersion`); treat it as opaque and echo it back.
* Saving a device (label, favorite, order) posts **the whole room** through `room-setup`
  (`DaisyApplication#saveCloudDevice`), with `deviceCommandList` removed. The app then
  sends an `UP_DEV` system command (firmware ≥ 1.3.3).
* Installation sharing is implemented by the app with a "mailbox" hack on
  `room-setup` / `room-list` using the fixed ids `idAccount 207`, `idInstallation 162`.
  Out of scope for the SDK.

## Polling done by the app

| What | Period |
|---|---|
| `status-device-list` of the open device screen | 500 ms |
| `status-device-list` of the box (`NET_PARAM`, home detection) | 5 s |
| `tmate20/nodestatus` | 30 s |
| full sync (installations → room-configuration-list → scenario-list) | 1 min … 24 h (default 1 h) |
