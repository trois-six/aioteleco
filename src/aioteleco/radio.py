"""868 MHz radio frames sent by the box to the receivers (motors, lights...).

Observed on air with an SDR receiver: 868.30 MHz, 2-FSK (tones about ±20 kHz around the
carrier). One command is about 1.6 s of carrier repeating the same frame back to back.
A frame is a sync (upper tone, 4 units), 64 segments alternating lower and upper tone
(starting with the lower one) that last one unit (bit 0) or two units (bit 1), then a
lower-tone gap. Bits are read MSB first into 8 bytes:

- bytes 0..4: rolling code. It carries the per-device transmission counter (the box
  keeps one per device, see :data:`~aioteleco.system.RADIO_COUNTERS_ADDRESS`) mixed with
  other data; the mixing is not fully understood yet.
- byte 5 and the high nibble of byte 6: always 0.
- low nibble of byte 6: the command channel, the ``CHn`` of the device command's
  ``lowlevel_command`` (e.g. a dimmer's ``POWER ON`` is ``CH1``, ``STOP`` is ``CH7``).
- byte 7: checksum, the eight bytes sum to 0 modulo 256.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

FREQUENCY_HZ = 868_300_000
UNIT_US = 515  # one segment unit
SYNC_UNITS = 4  # upper tone before the first segment
GAP_US = 8120  # lower tone after the last segment
FRAME_BYTES = 8
ROLLING_CODE_BYTES = 5


def frame_checksum(payload: bytes) -> int:
    """The last byte of a frame: minus the sum of the first seven, modulo 256."""
    return -sum(payload[:7]) & 0xFF


@dataclass(frozen=True, slots=True)
class RadioFrame:
    """One 64-bit frame as sent on air."""

    data: bytes

    def __post_init__(self) -> None:
        if len(self.data) != FRAME_BYTES:
            raise ValueError(f"a radio frame is {FRAME_BYTES} bytes, got {len(self.data)}")

    @classmethod
    def build(cls, rolling_code: bytes, channel: int) -> RadioFrame:
        """Assemble a frame from its rolling code and channel, adding the checksum."""
        if len(rolling_code) != ROLLING_CODE_BYTES:
            raise ValueError(f"the rolling code is {ROLLING_CODE_BYTES} bytes")
        if not 1 <= channel <= 15:
            raise ValueError(f"channel {channel} is not in 1..15")
        payload = rolling_code + bytes((0, channel))
        return cls(payload + bytes((frame_checksum(payload),)))

    @classmethod
    def from_hex(cls, text: str) -> RadioFrame:
        return cls(bytes.fromhex(text))

    @classmethod
    def from_segments(cls, durations_us: Sequence[float], unit_us: float = UNIT_US) -> RadioFrame:
        """Decode the 64 segment durations that follow the sync (gap excluded)."""
        if len(durations_us) != FRAME_BYTES * 8:
            raise ValueError(f"expected {FRAME_BYTES * 8} segments, got {len(durations_us)}")
        bits = 0
        for duration in durations_us:
            units = round(duration / unit_us)
            if units not in (1, 2):
                raise ValueError(f"segment of {duration} us is neither 1 nor 2 units")
            bits = bits << 1 | (units - 1)
        return cls(bits.to_bytes(FRAME_BYTES, "big"))

    def segments_us(self, unit_us: float = UNIT_US) -> list[float]:
        """The 64 segment durations to transmit after the sync (lower tone first)."""
        bits = int.from_bytes(self.data, "big")
        return [unit_us * (1 + (bits >> shift & 1)) for shift in range(FRAME_BYTES * 8 - 1, -1, -1)]

    @property
    def rolling_code(self) -> bytes:
        return self.data[:ROLLING_CODE_BYTES]

    @property
    def channel(self) -> int:
        return self.data[6] & 0x0F

    @property
    def valid(self) -> bool:
        """Checksum right and the always-zero bits (byte 5, high nibble of byte 6) clear."""
        return self.data[7] == frame_checksum(self.data) and self.data[5] == self.data[6] >> 4 == 0

    def __str__(self) -> str:
        return self.data.hex(" ").upper()
