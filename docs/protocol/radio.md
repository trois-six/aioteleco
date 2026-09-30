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

Status: the physical layer, the frame coding and the fixed fields are confirmed on
hundreds of frames from several devices. The rolling code is only partly understood.

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

What is known about bytes 0..4 (bits 0..39 of the frame):

* the four low bits of the counter are in clear at bits 6, 5, 3 and 0 (counter bit 0 to
  bit 3) for most devices; for a device acting as a group of three, bit 5 was inverted;
* higher counter bits change bits 20, 22, 34..36 and 39 when the low nibble wraps;
* bits 14..17 and 28..29 are always 0;
* the remaining bits change on every transmission. They are not a CRC of the rest (no
  affine relation over GF(2) beyond the checksum and one parity relation) and do not
  match any known rolling-code format (KeeLoq, FAAC SLH, Nice FLOR-S, CAME Atomo, Somfy
  RTS).

A transmitter emulation therefore still needs the function that turns (serial, counter,
channel) into these five bytes.
