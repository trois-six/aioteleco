---
type: Protocol Reference
title: Radio link
description: "868 MHz link from the box to the receivers: modulation, frame coding, frame fields (rolling code, channel, checksum) and the per-device transmitter serials and counters kept in the box memory."
tags: [teleco, radio, 868mhz, fsk, rolling-code, sdr]
sources:
  - id: on-air
    title: On-air captures of a Daisy box with an RTL-SDR receiver, correlated with commands sent through the SDK
  - id: box-memory
    title: Box memory read with the MEMORY command
---

# Radio link

The box drives the receivers (motors, lights) over 868 MHz. The app never sees this
link: it only sends commands to the box (see [Commands](commands.md)). Everything below
comes from on-air captures of commands sent through the SDK, one command at a time.

Status: the physical layer, the frame coding, the fixed fields and the rolling code are
all confirmed: hundreds of captured frames decode exactly, and live predictions for
counters not yet seen (including a whole device held out and predicted from its serial
alone) came back byte-exact against new on-air captures. The rolling code is only
confirmed for counters 0..511 (see [Rolling code](#rolling-code)).

## Physical layer

| | |
|---|---|
| Frequency | 868.30 MHz |
| Modulation | 2-FSK, tones about ±20 kHz around the carrier |
| Unit | 515 µs |
| One command | about 1.6 s of continuous carrier, the same frame repeated back to back (27 to 32 times) |

The box transmits about 2 s after it accepts a command. A command the box refuses (for
example a LAN connection it rejects) is not transmitted.

## Frame coding

```
sync      upper tone, 4 units
64 × segment, alternating lower / upper tone, starting with the lower one:
          1 unit = bit 0, 2 units = bit 1
gap       lower tone, about 8.1 ms
```

This is pulse-width coding: the frame length depends on its number of 1 bits, and a burst
holds fewer frames when they carry more 1 bits. Manchester, biphase and NRZ readings of
the same signal are all invalid or scatter the fields.

The 64 bits are read MSB first into 8 bytes.

| Bytes | Content |
|---|---|
| 0..4 | rolling code, see below |
| 5 | always `00` |
| 6 | high nibble `0`, low nibble = **channel** |
| 7 | **checksum**: the eight bytes sum to 0 modulo 256 |

The channel is the `CHn` of the device command's `lowlevelCommand` (see
[Devices](devices.md)): for example a dimmer sends `CH1` for `POWER ON` and for
`LEVEL LEV4`, `CH4` for `LEV1`, `CH8` for `POWER OFF`; a rolling shutter sends `CH5` to
open, `CH7` to stop, `CH8` to close.

SDK: [`RadioFrame`][aioteleco.radio.RadioFrame] decodes and builds frames;
`teleco radio-decode <hex>` decodes one.

## Transmitters and counters

The box acts as one virtual transmitter per device, each learned by its receiver ("Did
you delete the transmitter from the receiver?" in the app). Its memory holds:

| Address | Size | Content |
|---|---|---|
| 0 | 50 × 3 bytes | transmitter serials, 24-bit little-endian, consecutive values (the app's debug screen shows the first one as "first SN") |
| 158 + 2 × device index | 2 bytes | last transmission counter sent for that device, big-endian |

The counter is per device: it increases by exactly 1 with each transmission of that
device (checked live: one command moves the device's counter by one and leaves the
others alone). SDK: `TelecoHub.radio_serials`, `TelecoHub.radio_counter`,
`teleco radio-counter <device>`.

## Rolling code

Bytes 0..4 (bits 0..39 of the frame) are `F(serial, counter)`, not a CRC or a known
rolling-code format (KeeLoq, FAAC SLH, Nice FLOR-S, CAME Atomo and Somfy RTS were all
ruled out): it is a small scrambler seeded from the serial and folded once per set
counter bit.

The counter's ten low bits sit in the clear, directly at these frame bit positions
(counter bit → frame bit):

| Counter bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| Frame bit | 6 | 5 | 3 | 0 | 39 | 22 | 20 | 36 | 35 | 34 |

Counter bits above 9 have never been observed on air (the counters seen so far stay
under 512), so their frame bit, rotation amount and XOR key are unknown; bits 14..17,
28 and 29 are always 0 and are presumably among them.

The other 24 bits are one 24-bit word, built like this:

1. **Seed:** permute the 24-bit serial (seed bit `p` = serial bit `(5 - p) mod 24`),
   then XOR it with `0xD7D76C`.
2. **Fold in the counter:** for each set counter bit, from bit 8 down to bit 0, rotate
   the word and XOR it with that bit's key:

   | Counter bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
   |---|---|---|---|---|---|---|---|---|---|
   | Rotation | +1 | −1 | +1 | −1 | −1 | +1 | +1 | +1 | −1 |
   | XOR key | `000000` | `75AADB` | `AEE77D` | `51389A` | `081400` | `F4D279` | `9D6AA2` | `31388A` | `F56A3E` |

3. **Output mask:** XOR the result with `0xDB8DC8`.
4. **Scatter** the 24 bits into the frame, cycle position → frame bit: `1, 2, 4, 7, 8, 9,
   24, 25, 10, 26, 11, 27, 12, 13, 30, 31, 32, 33, 18, 19, 21, 37, 38, 23`.

This was found from the counter-difference pattern (two frames 2ⁿ apart differ by a
fixed rotation-and-XOR that depends only on `n`), confirmed by inverting every captured
frame back to the same seed per device, and the seeds across devices all being the same
permuted-serial-XOR-constant. It reproduces every captured frame exactly (LED, three
screens, their group and the slats) and every frame predicted ahead of a live capture,
including for a device whose frames were entirely held out and predicted from its serial
alone.

SDK: [`rolling_code`][aioteleco.radio.rolling_code] computes these five bytes;
[`RadioFrame.from_serial`][aioteleco.radio.RadioFrame.from_serial] builds the whole
frame. Both raise for a counter above
[`ROLLING_CODE_MAX_COUNTER`][aioteleco.radio.ROLLING_CODE_MAX_COUNTER] (511): capturing
frames around a counter's first crossing of 512, 1024, and so on, would reveal each new
counter bit's rotation and key the same way the first ten were found.
