# Local channels

There is no BLE, mDNS, UDP or multicast in the app. The box is reached over TCP only:

* in normal operation, on the **home network**, port **400**: obfuscated commands;
* during setup, on the box's own **access point**, `10.10.10.1:23`: plain-text commands.

The `rcl/` package (relays reached at `192.168.4.1:3001`) belongs to other products
built from the same codebase. It is disabled in the Daisy app (`Utils#isDirectApp()` is
false) and is not covered here.

## Home network: TCP port 400 (`DaisyApplication#sendDM`)

**Finding the box.** Its address comes only from the cloud: the status item `NET_PARAM`
of the box device (`status-device-list` with `idInstallationDevice =
Installation.idInstallationDevice`) holds `IP: a.b.c.d NameNet: <ssid>`
(`DaisyApplication#saveNetParam`). The phone is considered "at home" when its current
SSID equals `NameNet`. An IP of `0` means unknown.

**Exchange.** One TCP connection per command (connect timeout 500 ms). The client
writes the frame (no newline) and reads one line:

* the line contains `ACK` → success;
* another line → the app clears the stored IP and re-sends through the cloud;
* no line within the read timeout (5 s; 10 s for a scenario; 2 s when the first
  command's action is `CHANNEL`) → the app reports success and does **not** re-send
  (avoids executing twice);
* connection error → the app clears the stored IP and falls back to the cloud.

The LAN only accepts commands. Device state is never read locally.

**Payload** (`DaisyApplication#convertForDM`), built by string concatenation without
JSON escaping:

```
{"idIn":"<instCode>","idSc":<idScenario>,"isSc":<true|false>,"cL":[{"idInDe":<idInstallationDevice>,"deCo":"<deviceCode>","cmId":<commandId>,"coAc":"<commandAction>","coPa":"<commandParam>","low":"<lowlevelCommand>","coSta":0},…]}
```

For command models 195–201 (generic sliders), `coPa` is re-encoded: each `§`-separated
value `v` becomes `000` if 0, `0v` if < 100, else `v`, each followed by `-`
(`5§120§0` → `05-120-000-`).

**Obfuscation** (`DaisyApplication#encrypt`):

```
KEY      = "d3Cr1pTam1St0CaZzOSe61nGrad0"             # 28 chars
ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
r   = random 0..27;  k = KEY[r:] + KEY[:r]            # rotate left by r
ts  = str(epoch_seconds)                              # 10 digits
d(i) = chr(int(ts[i:i+2]))                            # one char per pair of digits
plain = d(0) + message with d(2), d(4), d(6) inserted BEFORE message[50], [70], [90]
        (only when the message is that long) + d(8)
x   = chars(plain) XOR k[i % 28]                      # per UTF-16 code unit
frame = ("S" if scenario else "M") + ALPHABET[r] + base64(utf8(x))   # standard alphabet, padded, no wrap
```

The SDK's implementation (`aioteleco/local/crypto.py`) is checked against vectors
produced by running the app's own Java method with a fixed `r` and timestamp
(`tests/test_local_crypto.py`). Whether the box enforces a time window on the embedded
timestamp is **not yet verified**.

**Diagnostic.** `DaisyApplication#getDiagnostic` sends `encrypt("DIAGNOSTIC" × 10)` on
port 400 (firmware ≥ 1.34). The box answers a plain-text, comma-separated log of
10-character entries (`0000000000` = filler, `5555555555` = rotation marker).

## Setup access point: `10.10.10.1:23`

During installation the box opens an open Wi-Fi network `Daisy_<instCode>`. The app
connects to `10.10.10.1:23` (`BoxWifiConfigurationActivity`, `SetupWifiActivity`,
`DaisyApplication#openApSocket`) and exchanges plain-text lines:

| Command | Purpose |
|---|---|
| `TEST_SCAN` | list the Wi-Fi networks seen by the box (2 header lines, then one per network) |
| `GET_INFO`, `PING_CMD`, `DIAGNOSTIC` | information |
| `AP_CHANNEL_CMD 00R` / `06W` / `20W` | read / set the Wi-Fi channel |
| `FMEMORY ADDR: %s NB: %sR\r\n` | memory dump |

Provisioning line (`BoxWifiConfigurationActivity#sendDataSocket`):

```
SSID: <ssid> |Pass: <password> |Acco: <idAccount> |Name: <instDescription> |Code: <instCode> |Titu: <latitude> |Gitu: <longitude>
```

It is sent in clear text when the box first sends a banner line, and through
`encrypt()` when no line arrives within 2 s (newer boards). The box then registers itself
with the cloud for that account, so adding a box needs no REST call. Not implemented by
the SDK.
