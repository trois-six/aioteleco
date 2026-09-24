---
type: Protocol Reference
title: Commands
description: "How a device command is selected from the cloud command list and encoded, delivered and acknowledged, plus scenarios, system (box) commands and timers."
tags: [teleco, commands, scenarios, timers]
sources:
  - id: daisy-app
    resource: https://play.google.com/store/apps/details?id=com.telecoautomation.daisy
    title: Daisy Teleco Android app (com.telecoautomation.daisy), static analysis
---

# Commands

## Where commands come from

The app does **not** hard-code command ids. `room-configuration-list` returns, for each
device, its `deviceCommandList`. The app caches it (ObjectBox `Command` entity) and, when
a button is pressed, asks for an `(action, param)` pair that is resolved against that
list. `CommandDao#mapCommands` contains per-model tables, but they are only used in
demo/direct mode.

Consequence for the SDK: `commandId` / `lowlevelCommand` values (e.g. `94`/`CH4`) are
never constants; they are read from the device's command list. Implemented in
`aioteleco/commands.py`.

## Actions and parameters sent by the device screens

| Action | Parameters |
|---|---|
| `POWER` | `ON`, `OFF`, `LEV1`…`LEV4` |
| `LEVEL` | `LEV1`…`LEV4`, an integer 0–100 (sliders), or 7 values joined by `§` (generic slider) |
| `OPEN_STOP_CLOSE` | `OPEN`, `STOP`, `CLOSE`, `LEV1`, `LEV4`, `START_O`, `START_C`, `END_O_A`, `END_O_M`, `END_C_A`, `END_C_M` |
| `COLOR` | `AxxxRxxxGxxxBxxx` (A = brightness 0–100), or a preset name + that string (model 26), optionally `;S` |
| `CYCLE` | `ON`, `PLAY`, `PAUSE` |
| `SPEED` | `33`, `67`, `100` |
| `CHANNEL` | `CHn`, `CH8-L` |
| `PAUSE_PLAY` | `PLAY`, `PAUSE` |
| `AUDIO_ACTION` | `VOLUME_UP`, `VOLUME_DOWN`, `REWIND`, `FORWARD` |

`START_*` / `END_*` implement hold-to-move buttons: `END_*_M` if the button was held
more than 1.5 s, `END_*_A` otherwise.

Pergola slats (model 27, `OpenStopCloseStepsDeviceActionFragment`): position 0 →
`OPEN_STOP_CLOSE CLOSE` (models 44/45: `LEVEL LEV1`), 33 → `LEVEL LEV2`,
66 → `LEVEL LEV3`, 100 → `LEVEL LEV4`.

Dimmers (`OnOffStepsDeviceActionFragment`, models 17–20 and 34): the step buttons send
`POWER LEV1`…`LEV4`, `ON` and `OFF`. Only model 34 shows the slider, which sends
`LEVEL <0-100>` (`POWER OFF` at 0); the Brustor app hides it too. Stepped dimmers also
list a parametric `LEVEL` command (`commandParam "0"`), but the box ignores a free
level sent to them: the SDK maps `Dimmer.set_level` to the nearest step there.

Open/stop/close devices (models 21–25, 31, 43, 47, `OpenStopCloseDeviceActionFragment`)
only take `OPEN`, `STOP` and `CLOSE`. The percentage the app shows is derived from the
status: `LEVEL` while `OPEN_CLOSE == "OPEN"`, 0 when `CLOSE` (a closed device can report
`LEVEL 100`), and "-" otherwise (`Cover.position`). The SDK can still reach any position
by timing a move and sending `STOP` (`Cover.travel_to`, `teleco cover travel`), from
full travel times measured once (`teleco cover calibrate`); the app does not do this.

## Selection algorithm (`DaisyApplication#sendCommand`, from smali)

```
send_command(device, action, param):
    flag_S = ";" in param;  p = param.split(";")[0] if flag_S else param
    flag_L = "-L" in p;     p = p.replace("-L", "")
    mapped = "OPEN"  if p in (START_O, END_O_M, END_O_A)
             "CLOSE" if p in (START_C, END_C_M, END_C_A)
             else p
    template = None; out = []
    for cmd in device.commands:                      # server order
        if (cmd.action == action and cmd.param == "0") or device.model == 42:
            template = cmd (with param := p); continue   # parametric command, last one wins
        match = (cmd.param in mapped                      # substring test, action NOT compared
                 and cmd.param not in ("25","50","75","100","0") and cmd.action != "SPEED")
             or (cmd.action == "SPEED" and p == cmd.param and p in ("100","33","67"))
        if match:
            low = f"CH{int(cmd.low[2:]) + 10}" if flag_S else ""
            out = [toCommandCloud(cmd)]
            if device.model == 26 and mapped != cmd.param:
                out[0].param = mapped.replace(cmd.param, "")   # "RED"+ARGB → ARGB
            break
    if not out: out = [toCommandCloud(template)]      # the app crashes when there is none
    c0 = out[0]
    if flag_S: c0.low = low
    if device.feedback: c0.action += "-F"
    if flag_L: c0.action += "-L"
    if p in (START_O, START_C): c0.param = "START"
    if p in (END_O_A, END_C_A): c0.param = "END_A"
    if p in (END_O_M, END_C_M): c0.param = "END_M"
    if device.model == 44 and device.sub_model in ("2", "3"): swap CH5 <-> CH8 in out
    → LAN (TCP 400) if at home and the box IP is known, else cloud feedthecommands
```

`CommandDao#toCommandCloud(cmd)`:
`{idInstallationDevice, deviceCode: str(device.index), idInstallationDeviceCommand,
commandAction, commandParam, lowlevelCommand, commandId: idDevicetypeCommandModel,
idDevicetypeCommandModel, commandStatus: 0, commandreceived: 0, commandReceivedUR: "0",
commandProcessed: 0}`.

Before sending, the app checks `(no internet and at home) or nodeStatus`, otherwise it
shows "board not reachable".

## Cloud delivery and acknowledgement

1. `tmate20/feedthecommands/` → `{MessageType: "INFO", ActionReference: "…"}`. A null
   `ActionReference` means "done".
2. Poll `tmate20/getackcommand/ {id: ActionReference}`:
   * device screens: every 500 ms until `MessageText == "PROC"` (processed by the box);
   * timer / schedule / scenario-upload flows: every 1 s until `MessageText == "ACK"`,
     5 tries;
   * room/scenario lists: every 1 s, 7 tries;
   * any other `MessageText` means "not yet"; a `MessageType` other than `INFO` is an
     error (`handleAckCommand`).
3. The device screen then reads `status-device-list`.

## Scenarios

Running a scenario (`ScenarioDao#toFeedCommandPost`, `DaisyApplication#sendScenario`)
sends **every step as a full command** in one `feedthecommands` with
`isScenario: true` and `idScenario: <idInstallationScenario>`. For a parametric step
(cached `commandParam == "0"`), the step's `commandParam` is substituted. On the LAN the
frame is prefixed with `S` and the read timeout is 10 s.

`CommandDao#isCommandCompatible` (commands allowed in a scenario): never `STOP`;
models 26/46 exclude PLAY, 33, 67, 100, PAUSE, audio and OPEN/CLOSE; model 28 excludes
audio and OPEN/CLOSE; model 44 excludes OPEN/CLOSE.

## System (box) commands

Built by `CommandDao#commandTo*`: `commandId = 122`, `idInstallationDevice` = the box's
device id, `deviceCode = "0"` unless noted, `lowlevelCommand = ""`. Always sent through
the cloud.

| Action | Param | Notes | SDK (`TelecoHub`) |
|---|---|---|---|
| `GET_FEEDBACK` | box short code of the device model (`PER`, `PEG`…, `CommandDao#getBoardDeviceCodeName`) | `idInstallationDevice` = the device, `deviceCode` = device index | `request_feedback` |
| `UP_DEV` | `Feedback: S\|N Timers: S` | `idInstallationDevice` = the device, `deviceCode` = device index, `lowlevelCommand` = box device id; firmware ≥ 1.3.3 only | `update_device` |
| `UP_SCHED` | `Timers: S\|N` | master switch for timers | `set_timers_enabled` |
| `UP_TIMERS` | see [Timers](#timers) | `deviceCode` = device index | `save_timer`, `set_timer_active` |
| `DEL_TIM` | timer id, 8 hex digits | | `delete_timer`, `set_timer_active` |
| `UP_SCEN` | scenario string, see [Scenarios on the box](#scenarios-on-the-box) | | `save_scenario` |
| `DEL_SCEN` | scenario id (decimal) | | `delete_scenario` |
| `UP_INST_NAME` | installation name | | `rename_installation` |
| `GET_TIME`, `GET_SIGNAL`, `GET_VERSION`, `GET_INFO`, `GET_DIAGNOSTIC` | — | the box refreshes its status items (`CURRENT_TIME`, `SIGNAL`, `DIAGNOSTIC`…); the ack is `ACK` | `query_box` |
| `TEST_SCAN` | — | | `test_scan` |
| `SYNC_BOARD`, `END_SYNC` | — | frame a full re-send, see [Board sync](#board-sync) | `sync_box` |
| `SET_TIME` | value (no caller in the app) | | `set_box_time` |
| `SET_WIFI` | `SSID: x PASS: y` | | `set_wifi` |
| `AP_CHANNEL_CMD` | `00R` read; write `20W` (static) or `06W` | | `read_ap_channel`, `set_ap_channel` |
| `MEMORY` | `ADDR: %s NB: %sR` | debug screen | `read_memory` |
| `UPDATE_BOARD` | firmware URL | flashes the box | `update_firmware` |

Any action can also be sent with `TelecoHub.send_system(installation, action, param)`.

### Remote controls

Remote pairing (`CommandDao#commandToTx`) uses its own `commandId` and targets the
**scenario's** `idInstallationDevice` (every scenario has one), `deviceCode = "0"`:

| Action | `commandId` | Param | SDK (`TelecoHub`) |
|---|---|---|---|
| `PAIR_TX` | 127 | scenario string | `pair_remote` |
| `UNPAIR_TX` | 128 | scenario id | `unpair_remote` |
| `RESET_TX` | 129 | scenario id | `reset_remotes` |
| `PAIR_BUTTON`, `UNPAIR_BUTTON` | 108, 109 | (no caller in the app) | `send_remote_command` |

A scenario has a remote bound when its own device reports `TX_NUM > 0` or
`PAIRING_STATUS == "ON"` (`SetupScenariosListActivity#handleStatusDeviceList`).

## Scenarios on the box

After `scenario-setup` succeeds, the app sends `UP_SCEN` with the scenario string, or
`DEL_SCEN` when the scenario has no step left (`SetupScenarioActivity`). Deleting a
scenario sends `DEL_SCEN` after `scenario-delete`. Scenario string
(`ScenarioDao#toScenarioString`):

```
<scenario id>N<step count, 2 digits>( <device index, 2 digits><V><command model, hex><device id, 8 hex>)*
```

`V` is as for timers, except that an integer is always `L` + hex (at least 2 digits) +
`000000`. Example: `7001N02 01C0200000062000007d1 03R50ff800089000007d3`.

## Board sync

`DaisyApplication#syncBoard` re-sends the whole configuration as `isScenario: true`
feeds of at most 30 commands, each waiting for `ACK`: `SYNC_BOARD`, `UP_INST_NAME`,
`UP_SCHED`, then `UP_DEV` per device (firmware ≥ 1.3.3), `UP_SCEN` per scenario bound
to a remote, `UP_TIMERS` per timer, and `END_SYNC`.

## Rooms

Deleting a room (`SetupRoomsListActivity`): `room-delete`, then `DEL_TIM` for every
timer of its devices, then `UP_SCEN` (or `DEL_SCEN`) for the scenarios that used them.

## Timers

A timer is saved in two steps (`SetupDeviceTimersActivity`, `DaisyApplication#updateTimers`):

1. send `UP_TIMERS` (one per timer) and wait for `MessageText == "ACK"`;
2. post the device's **complete** timer list to `timer-device-setup/`.

A new timer is first created with `idInstallationDeviceTimer: 0` through
`timer-device-setup/` to obtain its id. Disabling a timer on firmware ≥ 1.3.3 sends
`DEL_TIM` instead of `UP_TIMERS`.

Deleting a timer (`SetupTimerListActivity#deleteTimer`): send `DEL_TIM` (timer id on 8
hex digits, `DaisyBaseActivity#delTimerString`), wait for `ACK`, then post the device's
timer list without it to `timer-device-setup/`. The box runs timers on its own clock,
which is local time (`CURRENT_TIME`), so `timerDate` is local time too.

`timer-device-list/` has been seen returning an empty `timerList` for a device that
has timers; `room-configuration-list` (`deviceTimersList`) is the reliable source.

`UP_TIMERS` parameter (`CommandDao#commandToUpdateTimer`):

```
<V> HShhmm DSddMM HE0000 DE0000 Gnnn Annn <device id, 8 hex> M<command model, hex> <timer id, 8 hex> T<S|N>
```

* `V` (value): ARGB param → `R` + 4 hex bytes (`A100R255G000B010` → `R64ff000a`);
  integer → `L` + hex + `000000` (single hex digit: `0` + digit + `000000`);
  otherwise `C` + channel (2 digits) + `000000`, where the channel comes from the
  command's `CHn` (colors: PURPLE 13, YELLOW 12, CYAN 11, WHITE 14; no channel → 8).
* `HS`/`DS`: time and day/month of `timerDate` (local time, `yyyy-MM-dd HH:mm`).
* `G`: day mask, `int("0" + bits(giorni), 2)` with Monday first (Mon = 64 … Sun = 1),
  3 digits.
* `A`: astronomical flags, `int(sun + "000" + offset, 2)` with `sun` = `00` (no twilight),
  `01` (sunrise) or `10` (sunset) and `offset` −2 → `001`, −1 → `010`, 0 → `000`,
  +1 → `011`, +2 → `100` (hours); 3 digits. Examples: sunrise → `A064`,
  sunrise +2 h → `A068`, sunset −1 h → `A130`.
