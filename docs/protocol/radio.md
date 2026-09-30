---
type: Protocol Reference
title: Radio link
description: "The 868 MHz link from the box to the receivers, reverse-engineered end to end: modulation, frame coding, the rolling-code algorithm, what was ruled out, and how it was captured. Plus the box memory map and firmware-update flow learned along the way."
tags: [teleco, radio, 868mhz, fsk, rolling-code, sdr, firmware, memory]
sources:
  - id: on-air
    title: On-air captures of a Daisy box with an RTL-SDR receiver, each correlated with a command sent through the SDK and with the box's own serial and counter memory
  - id: box-memory
    title: Box memory read with the MEMORY command
  - id: app
    title: Daisy Teleco Android app, static analysis (firmware-update flow, remote pairing)
---

# Radio link

The box drives the receivers (motors, lights) over 868 MHz. The app never sees this
link: it only sends commands to the box over the cloud or the LAN (see
[Commands](commands.md)), and the box emits the radio. Everything here comes from on-air
captures of commands sent one at a time through the SDK, each correlated with the box's
own memory (the transmitter serial and the per-device counter).

**Status: fully reverse-engineered for the cases seen so far.** The physical layer, the
frame coding, every field and the rolling-code algorithm are known and reproduce every
captured frame byte-exact, as well as frames predicted ahead of a live capture. The
rolling code is solved for counters 0..1023; two points are open: counters ≥ 1024, and
serials from outside the box's block (see [Open questions](#open-questions)).

## Physical layer

| | |
|---|---|
| Frequency | 868.30 MHz |
| Modulation | 2-FSK, the two tones about ±20 kHz around the carrier (deviation ~20 kHz) |
| Occupied bandwidth | about ±22 kHz at −20 dB |
| Symbol unit | 515 µs (about 1942 baud) |
| One command | ~1.6 s of continuous carrier, one frame repeated back to back |

The box starts transmitting about 2 s after it accepts a command. A command the box
refuses — for example a LAN connection on port 400 that it drops — is **not** transmitted,
and the device's counter does **not** advance.

### Burst

A command is one continuous carrier of about 1.6 s carrying the same frame 27 to 32
times, back to back. Every repetition in a burst is bit-identical, which makes decoding
reliable: a majority vote over the repetitions removes any single-frame bit error.

The number of repetitions is not fixed: it drops as the frame carries more `1` bits.
Each frame lasts `(84 + popcount) × 515 µs` (sync + 64 segments + gap, see below), and
the ~1.6 s carrier holds however many fit. Across the captured bursts the frame count
correlates −0.80 with the frame's `1`-bit count, and for 92 % of bursts it is within ±1
of `1.609 s / ((84 + popcount) × 515 µs)`. This variable frame length is itself the proof
that the bit layer is pulse-width coded (see [Frame coding](#frame-coding)).

## Frame coding

```
sync      upper tone, 4 units (~2.06 ms)
64 × segment, alternating lower / upper tone, starting with the lower one:
          1 unit = bit 0, 2 units = bit 1
gap       lower tone, ~16 units (~8.1 ms)
```

The 64 bits are read MSB first into 8 bytes (frame bit 0 = the first segment after the
sync = the MSB of byte 0).

This is pulse-width coding on the per-segment duration. Every other line code was tested
on 100 frames and ruled out:

| Decoding tried | Result |
|---|---|
| **PWM, 1 unit = 0, 2 units = 1** (this one) | 100/100 valid; command and counter fall on fixed bit positions |
| Manchester (both phases, with/without sync and gap) | 0/100 — every frame has 3–30 invalid half-bit pairs |
| Biphase-mark, biphase-space, differential Manchester | 0/100 at every phase |
| PWM pairs forced to a 3-unit total | 0/100 — pair totals are 2, 3 or 4 units, not constant |
| NRZ at the unit rate, NRZI (with/without sync and gap, either bit order) | decode, but frames are not a fixed length, so the known fields land in a different place in each frame; only 1–17 bits stay constant and no command or counter field appears |
| 4b/5b- or 8b/10b-like block codes | none exists: at the best phase the stream already uses every word with no run longer than 2 units, so there is no smaller codebook to find |

Manchester, NRZ-with-a-block-code and n-b/m-b all run at a fixed rate and would give
constant-length frames; the frames are not constant length, so the transmitter really
sends variable-length, pulse-width-coded segments.

## Frame structure

| Bytes | Content |
|---|---|
| 0..4 | rolling code — counter + a value derived from the serial, see [Rolling code](#rolling-code) |
| 5 | always `00` |
| 6 | high nibble always `0`, low nibble = **channel** |
| 7 | **checksum** |

### Channel

The low nibble of byte 6 is the `CHn` of the device command's `lowlevelCommand` (see
[Devices](devices.md) for the full per-model list). The command's meaning is entirely in
this channel; bytes 0..4 are identical for two different commands sent at the same
counter. Examples observed:

| Device model | Command | Channel |
|---|---|---|
| Dimmer (17) | `POWER ON`, `LEVEL LEV4` | CH1 |
| Dimmer (17) | `LEVEL LEV3 / LEV2 / LEV1` | CH2 / CH3 / CH4 |
| Dimmer (17) | `POWER OFF` | CH8 |
| Rolling shutter (21) | `OPEN` / `STOP` / `CLOSE` | CH5 / CH7 / CH8 |
| Slats (27) | `CLOSE` / `OPEN` / `STOP` | CH1 / CH4 / CH7 |

`POWER ON` and `LEVEL LEV4` share CH1 on the dimmer, so the highest dimmer step and "on"
are the same on air.

### Checksum

Byte 7 makes the eight bytes sum to zero modulo 256:

```
byte7 = (-(byte0 + byte1 + … + byte6)) & 0xFF
```

It is an **arithmetic** checksum, not a CRC. This was confirmed on 100 frames across all
devices, and the CRC hypothesis was ruled out over the whole parameter space at once: a
CRC is affine over GF(2), so a least-squares test asking whether each frame bit is an
affine function of the others catches any CRC (planted CRC-8 and CRC-16 test bytes were
detected 8/8 and 16/16), and the real frames carry only this one additive relation —
no CRC-8 or CRC-16 with any polynomial, init, final XOR, reflection, span or bit order,
and no nibble sum or XOR. The MSB-first byte order is required; reading each byte
LSB-first breaks the sum.

SDK: [`frame_checksum`][aioteleco.radio.frame_checksum], and
[`RadioFrame.valid`][aioteleco.radio.RadioFrame] checks the sum and the always-zero bits.

## Transmitters and counters

The box behaves as one virtual transmitter per device, each **learned by its receiver**
like a physical remote would be (hence the app string "Did you delete the transmitter
from the receiver?"). The identity comes from the box, not the app: the app addresses a
device only by its `deviceIndex` (1, 2, 3, …) and a channel, and the box maps that index
to a transmitter serial and keeps its rolling-code counter. Both live in the box memory
(read-only, via the `MEMORY` command — see [Box memory](#box-memory-map)):

| Address | Size | Content |
|---|---|---|
| 0 | 50 × 3 bytes | transmitter serials, 24-bit little-endian, **consecutive** values (the app's debug screen calls the first one "first SN") |
| 158 + 2 × device index | 2 bytes | the last counter sent for that device, big-endian |

* **Serial per device:** `serial = firstSN + (deviceIndex − 1)`. The serials are one
  contiguous block, one per device slot.
* **Counter per device:** it increases by exactly 1 with each transmission of that
  device, and only that device (verified live: one command moved the target's counter by
  one and left the others unchanged). The box stores the last value used.
* **One transmission per command, not per frame or per step:** a burst repeats the same
  frame ~30 times but the counter moves by one. And the box **collapses repeated commands
  for the same device inside a single request** (one `feedthecommands`, or one scenario):
  N identical steps for one device still transmit once and move the counter by one.
  Advancing a counter by N therefore takes N separate requests, not one batch of N.

SDK: [`TelecoHub.radio_serials`][aioteleco.hub.TelecoHub.radio_serials],
[`TelecoHub.radio_counter`][aioteleco.hub.TelecoHub.radio_counter], and
`teleco radio-counter <device>`.

## Rolling code

Bytes 0..4 (frame bits 0..39) are a deterministic function of the **serial** and the
**counter** only — `F(serial, counter)`. It is not a CRC and matches no known format
(KeeLoq / HCS200-300-301, FAAC SLH, Nice FLOR-S, CAME Atomo, Somfy RTS and BFT Mitto were
all checked and ruled out, including under bit and byte reversal). It is a small
software scrambler: a seed derived from the serial, folded once per set counter bit.

### Layout

The counter's ten low bits are in the clear, each at a fixed frame bit (counter bit →
frame bit):

| Counter bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| Frame bit | 6 | 5 | 3 | 0 | 39 | 22 | 20 | 36 | 35 | 34 |

Bit 9 (frame bit 34) was confirmed by driving a transmitter past counter 512 on air and
reading its frames, on two different serials.

24 other bits hold a 24-bit word `W`, scattered into the frame in this order
(cycle position → frame bit): `1, 2, 4, 7, 8, 9, 24, 25, 10, 26, 11, 27, 12, 13, 30, 31,
32, 33, 18, 19, 21, 37, 38, 23`.

The remaining frame bits, 14..17, 28 and 29, are 0 in every capture. That is exactly
6 bits, as many as counter bits 10..15 of the 16-bit counter the box stores: consistent
with a 16-bit counter on air, with its high bits in the clear there, but unverified.

### Computing W

1. **Seed** from the 24-bit serial: seed bit `p` = serial bit `(5 − p) mod 24`, then XOR
   with `0xD7D76C`. This permutation is only proven on the low serial bits, the ones that
   varied across the fitted serials; on the others it is folded into the constant (see
   [Open questions](#open-questions)).
2. **Fold in the counter:** for each set counter bit, from bit 9 down to bit 0, rotate
   the 24-bit word and XOR it with that bit's key:

   | Counter bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
   |---|---|---|---|---|---|---|---|---|---|---|
   | Rotate (left +, right −) | +1 | −1 | +1 | −1 | −1 | +1 | +1 | +1 | −1 | −1 |
   | XOR key | `000000` | `75AADB` | `AEE77D` | `51389A` | `081400` | `F4D279` | `9D6AA2` | `31388A` | `F56A3E` | `563A96` |

3. **Output mask:** XOR the result with `0xDB8DC8`.

This is the binary "square-and-multiply" shape — one conditional step per counter bit,
most-significant first — with "rotate then XOR" as the step. For a fixed counter the
whole thing is affine over GF(2), which is why it fell to linear algebra rather than
needing side-channel work like KeeLoq did.

SDK: [`rolling_code(serial, counter)`][aioteleco.radio.rolling_code] and
[`RadioFrame.from_serial`][aioteleco.radio.RadioFrame.from_serial].

### How it was found

* Frames 16 counts apart (same low nibble) differ by a **constant** pattern that depends
  only on the low nibble, in five classes: `{0,3,6,9,12,15}`, `{1,4,7,13}`,
  `{2,8,11,14}`, `{5}`, `{10}`. That pointed at a per-counter-bit transform.
* Every "+1" step turned out to be a fixed rotation plus a constant XOR chosen by the
  number of trailing zeros of the new counter — no exceptions across 59 / 30 / 15 / 7
  transition pairs for 0 / 1 / 2 / 3 trailing zeros. Odd counters are a pure rotation of
  the frame before.
* Inverting every frame of a device back through the steps gives one seed per device
  (95/95 for the dimmer, 13/13 for each screen), and the six device seeds are all the
  same permuted-serial-XOR-constant. That fixed the constants and the permutation of the
  serial bits that vary across those six serials (one box's consecutive block, so only
  the low few), and the three rotation amounts with only one witness each were pinned by
  the serial.
* Counter bit 9 was then read directly: a transmitter was driven past counter 512 on air
  (repeating a no-op command so nothing moved), and the frames at 512 and above gave the
  bit-9 step. One serial cannot separate its rotation from its key, so a second serial —
  a handheld remote and the box, each driven past 512 — pinned the rotation to −1 and the
  key to `563A96`.

### Validation

* **126 / 126** captured frames (dimmer, three screens, their group, the slats)
  reproduce byte-exact.
* **6 / 6 live predictions** on counters never seen when the model was built came back
  byte-exact against fresh on-air captures (the dimmer at 285/286/287, the group at 274,
  two screens at 66 and 133), including a command on a different channel.
* **Held out:** a random 10-fold left every learnable frame exact; a whole device
  predicted from its serial alone (13/13, 8/8, 2/2, …) was exact. That serial was from
  the same block as the others, so for the seed it only checks the low serial bits.
* **Counter bit 9:** frames captured across counter 512 on two serials (a few dozen on a
  handheld remote, several on the box) reproduce byte-exact with the bit-9 step, and every
  counter 0..511 is unchanged.

A parity relation over a fixed set of bits appeared to hold on the captured sample, but
the exact model shows it does **not** hold for arbitrary serial and counter — it was a
coincidence of the specific values captured, and is fully explained away by `F`.

### Open questions

**Counters ≥ 1024.** Counter bits 10..15 have never been observed on air, so their frame
bit, rotation amount and XOR key are unknown and the SDK refuses a counter above
[`ROLLING_CODE_MAX_COUNTER`][aioteleco.radio.ROLLING_CODE_MAX_COUNTER] (1023). Bits 10..15
presumably live in the six always-zero frame bits (14..17, 28, 29; see [Layout](#layout)).
The keys for bits 0..9 show no pattern (no relation between them, no sparse form), so each
higher bit must be read the same way the first ten were: capture the frames around a
counter's first crossing of 1024, then 2048, and so on.

**Serials from another block.** The box's transmitter serials are consecutive
(`firstSN + deviceIndex − 1`) and the model was fitted on the handful of devices of one
box, so only the low serial bits varied across the fitted seeds. The rule "seed bit `p` =
serial bit `(5 − p) mod 24`" is proven on those bits only: a serial bit that is the same
for every fitted serial contributes a constant, so any permutation of it is
indistinguishable from the XOR constant `0xD7D76C`, which absorbs it. The model is exact
for serials that differ from the fitted ones only in those low bits, and untested for a
serial from another block — another box, a physical Teleco handheld remote, or a new
serial one would pair. A handheld remote has since been captured, and its frames are
self-consistent with a single serial under this rule; but that serial does not match the
code printed on the remote, so an independent serial has still not confirmed the
permutation — either the printed code is not the radio serial, or the rule is only one of
several that fit the block it was learned on.

## Capturing the radio

For anyone reproducing this:

* **Receiver:** an RTL-SDR (RTL2832U + R820T) tunes 868 MHz. On Linux the kernel DVB
  driver (`dvb_usb_rtl28xxu`, `rtl2832_sdr`) claims the dongle; `librtlsdr` detaches it
  automatically, or blacklist those modules.
* **Antenna:** a dipole with each leg ~8.5 cm (a quarter wavelength at 868 MHz), near the
  box.
* **Capture:** `rtl_sdr -f 868000000 -s 2400000 -g 40 out.cu8`, then send one known
  command through the SDK (`teleco --transport local light on "…"`) so each burst is
  labelled. Use only safe, reversible commands; the RTL-SDR can only receive.
* **Decode:** mix down to 868.30 MHz, an FSK discriminator gives the tone, re-center it
  per burst (the tuner drifts), then read the segment lengths as bits.
* **Transmitter offset:** the box carries at ~868.30 MHz, but a physical handheld remote
  sits about 30 kHz lower (~868.27 MHz). The coding is identical; only the centre to mix
  down to differs, so re-center per transmitter as well as per burst.
* **Reliability:** the box occasionally refuses the LAN connection on port 400; retry the
  send (a refused send transmits nothing and does not move the counter).
* **Driving the counter:** to reach a higher counter (e.g. to cross 512 and read a higher
  counter bit), repeat a no-op command — `STOP` on an idle cover, or a light already in
  the commanded state — one `feedthecommands` per step (see
  [Transmitters and counters](#transmitters-and-counters)), reading the counter back now
  and then. Each step is a real ~1.6 s transmission, so mind the 868 MHz duty cycle.

`teleco radio-decode <8 hex bytes>` decodes a frame you have captured.

## The box is a transceiver

The box does not only transmit: it also **receives and decodes** Teleco remotes on
868 MHz, so a physical remote speaks this same protocol to the receivers. The app can
pair and unpair remotes on the box (`PAIR_TX` / `UNPAIR_TX` / `RESET_TX`, and
`PAIR_BUTTON` / `UNPAIR_BUTTON`), and the box reports `TX_NUM` and `PAIRING_STATUS`
status items. This is the path a from-scratch transmitter would use to enrol itself with
a receiver.

---

## Related findings (not radio)

Discovered while chasing the radio, kept here for the record. The canonical reference for
the commands is [Commands](commands.md).

### Box memory map

`MEMORY` reads up to 50 bytes and the box writes the answer into its `DIAGNOSTIC` status
item as space-separated decimal bytes with a leading space (`" 152 8 50"`), or `ERROR`.
Over the setup access point the same read is `FMEMORY ADDR: %s NB: %sR` on
`10.10.10.1:23`. Addresses seen in the app's debug screen, plus the radio tables:

| Address | Bytes | Content |
|---|---|---|
| 0 | 150 | radio transmitter serials (50 × 24-bit LE) |
| 158 + 2 × device index | 2 | last radio counter of the device (big-endian) |
| 273 | 1 | time zone (`0`, `n` = +n h, `100 + n` = −n h) |
| 290 | 6 | daylight-saving rule |
| 576 / 640 / 950 | 50 each | Wi-Fi name / password / last Wi-Fi |
| 823 / 832 | 7 each | latitude / longitude |
| 842 / 876 / 910 | 10 / 10 / 15 | registration / account / virtual id |
| 940 | 1 | region (1 US, 2 EU, 3 Japan, 4 other) |

The command reads well past the debug screen's addresses — tens of thousands of bytes
answer rather than `ERROR`, holding config records (scenarios, timers) then filler and
zeros. But **address 0 is the serial table**, so `MEMORY` maps the box's **data NVM**, not
its program flash. The rolling-code key table is a code constant in flash, so it does not
appear in this space and cannot be read with `MEMORY` — a scan for the known keys finds
nothing. (It does expose the account and Wi-Fi fields above, so it reads more than the
debug screen shows.) Reading the keys would need a debug-port dump of the chip, same as
[the firmware images](#firmware-update).

SDK: [`TelecoHub.read_box_memory`][aioteleco.hub.TelecoHub.read_box_memory] and
`teleco memory <address> <count>`.

### Firmware update

**The box updates itself; the app never handles a firmware image.** It only sends one
`UPDATE_BOARD` cloud command whose parameter is a space-separated list of links, and the
box downloads and flashes the file on its own (over plain HTTP, from S3). The app triggers
this when the box's reported version is older than a version hard-coded in the app; the
one seen is `1.4.0.2` (firmware date 08-03-24).

The parameter carries three link triplets, one per radio variant, so the box picks the
file that matches its own radio:

```
L <url> N <file> V <version>   L916 <url> N916 <file> V916<version>   L8686 <url> N8686 <file> V8686<version>
```

`<version>` is the target with the dots removed (`1.4.0.2` → `1402`). `L*` is the URL,
`N*` the file name the box saves, `V*` the version. The plain (868 MHz) variant has no
suffix, `916` is the 916 MHz build, `8686` (file suffix `_P6`) an 868.6/"P6" model.

**Where the images are.** Public Amazon S3 buckets, plain `http`, one set per hardware
generation and region. HW2 is chosen when the cloud install's `workdays` field looks like
`x.y.z` (`2.0.0` = HW2); the region defaults from the phone's time zone (EU below +7 h,
else AU) and can be overridden in the app's advanced-update picker (EU / AU / two-step).

| Set | Bucket | File names (for `1402`) |
|---|---|---|
| EU HW1 | `http://tlc-frmw-upd.s3.eu-central-1.amazonaws.com/` | `UPG_1402.gbl`, `UPG_1402_9.gbl`, `UPG_1402_P6.gbl` |
| EU HW2 | `http://tlc-frmw-upd-hw2.s3.eu-central-1.amazonaws.com/` | `UPG_1402HW2.gbl`, `UPG_1402HW2_9.gbl`, `UPG_1402HW2_P6.gbl` |
| AU HW1 / HW2 | `…-au.s3.ap-southeast-2.amazonaws.com/` (`tlc-frmw-upd-au`, `tlc-frmw-upd-hw2-au`) | same file names |
| Two-step ("slim") | EU buckets | an `s` before the suffix: `UPG_1402s.gbl`, `UPG_1402s_9.gbl`, … |

The links are anonymously downloadable (the plain and `_9` files return HTTP 200; some
variants such as `_P6` are absent, HTTP 403). They are **Silicon Labs Gecko Bootloader
images** (`.gbl`), which puts the radio on an **EFR32-family** SoC and means the rolling
code runs in the box's own firmware, not in a licensed rolling-code chip.

**The images are encrypted, so they are a dead end for reading the algorithm.** The `.gbl`
is not plaintext: its tag structure is a header, an AES-CTR encryption init tag, the
encrypted program-data tags, and a 64-byte ECDSA-P256 signature:

```
03a617eb HEADER_V3                 8 B
fa0606fa ENC_INIT (AES-CTR nonce)  16 B
f90707f9 ENC_PROGRAM_DATA          36 B  + 228216 B   (encrypted)
f70a0af7 SIGNATURE_ECDSA_P256      64 B
fc0404fc END (+CRC32)              4 B
```

Without the AES key the program data cannot be read, and the ECDSA signature prevents
flashing a modified image, so recovering the rolling-code algorithm from the firmware
would need a debug-port dump of the chip itself — out of scope, and unnecessary, since the
[on-air analysis](#rolling-code) recovered the algorithm anyway.

Progress is reported in the box's `UPDATE_STATUS` status item (`Starting the upgrade...`,
`Downloading upgrade...`, `Loading upgrade...NN%`, `Applying the upgrade...`,
`Upgrade completed successfully!`, or an error); the box gives up downloading after about
6 minutes.

SDK: [`TelecoHub.update_firmware`][aioteleco.hub.TelecoHub.update_firmware].

### Other

* `TEST_SCAN` is a **Wi-Fi** scan of the box setup screen, not a radio scan.
* The "Memorize" button in the app targets model 16 sub-model 2 and only fires in a
  Gibus-branded build, so it is dead code in the Daisy app.
