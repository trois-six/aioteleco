"""868 MHz radio frames sent by the box to the receivers (motors, lights...).

Observed on air with an SDR receiver: 868.30 MHz, 2-FSK (tones about ±20 kHz around the
carrier). One command is about 1.6 s of carrier repeating the same frame back to back.
A frame is a sync (upper tone, 4 units), 64 segments alternating lower and upper tone
(starting with the lower one) that last one unit (bit 0) or two units (bit 1), then a
lower-tone gap. Bits are read MSB first into 8 bytes:

- bytes 0..4: rolling code, see :func:`rolling_code`. It carries the per-device
  transmission counter (the box keeps one per device, see
  :data:`~aioteleco.system.RADIO_COUNTERS_ADDRESS`) mixed with a value derived from the
  transmitter's serial (see :data:`~aioteleco.system.RADIO_SERIALS_ADDRESS`).
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

# -- rolling code (bytes 0..4, bits 0..39) --------------------------------------------
#
# Reverse-engineered from on-air captures correlated with the box's own memory (the
# transmitter serial and the per-device counter, see aioteleco.system). Confirmed exact
# against every captured frame and against live predictions for counters not yet seen
# when the model was built. Unknown above ROLLING_CODE_MAX_COUNTER: counter bits 9..15
# have never been observed on air, so their rotation amount and XOR key are unknown.
#
# The counter's ten low bits sit in the clear at these frame bit positions (bit k of the
# counter -> this frame bit):
_COUNTER_BITS = (6, 5, 3, 0, 39, 22, 20, 36, 35, 34)
ROLLING_CODE_MAX_COUNTER = (1 << len(_COUNTER_BITS)) - 1

# The other 24 bits of the rolling code are one 24-bit word, scattered into these frame
# bits in this order (cycle position -> frame bit):
_CYCLE_BITS = (
    1, 2, 4, 7, 8, 9, 24, 25, 10, 26, 11, 27, 12, 13, 30, 31, 32, 33, 18, 19, 21, 37, 38, 23,
)  # fmt: skip

# That word starts from a seed derived from the serial (bit p of the seed = bit
# (5 - p) mod 24 of the serial), XORed with a constant, then rotated and XORed once per
# set counter bit (highest counter bit first), and finally XORed with a mask:
_SEED_XOR = 0xD7D76C
_ROTATIONS = (1, -1, 1, -1, -1, 1, 1, 1, -1)  # per counter bit 0..8, +left/-right
_STEP_KEYS = (
    0x000000,
    0x75AADB,
    0xAEE77D,
    0x51389A,
    0x081400,
    0xF4D279,
    0x9D6AA2,
    0x31388A,
    0xF56A3E,
)
_OUTPUT_MASK = 0xDB8DC8
_WORD_BITS = 24
_WORD_MASK = (1 << _WORD_BITS) - 1


def _rotate_left(value: int, amount: int) -> int:
    amount %= _WORD_BITS
    if not amount:
        return value
    return (value << amount | value >> (_WORD_BITS - amount)) & _WORD_MASK


def _seed(serial: int) -> int:
    return sum(((serial >> ((5 - p) % _WORD_BITS)) & 1) << p for p in range(_WORD_BITS)) ^ _SEED_XOR


def _scramble(serial: int, counter: int) -> int:
    value = _seed(serial)
    for i in reversed(range(len(_STEP_KEYS))):
        if counter >> i & 1:
            value = _rotate_left(value, _ROTATIONS[i]) ^ _STEP_KEYS[i]
    return value ^ _OUTPUT_MASK


def rolling_code(serial: int, counter: int) -> bytes:
    """The 5-byte rolling code (frame bytes 0..4) for one transmission.

    ``serial`` is the transmitter's 24-bit radio serial (see
    :data:`~aioteleco.system.RADIO_SERIALS_ADDRESS`) and ``counter`` is that
    transmitter's transmission number (see :data:`~aioteleco.system.RADIO_COUNTERS_ADDRESS`,
    0..:data:`ROLLING_CODE_MAX_COUNTER`).
    """
    if not 0 <= serial < 1 << 24:
        raise ValueError("serial is a 24-bit value (0..16777215)")
    if not 0 <= counter <= ROLLING_CODE_MAX_COUNTER:
        raise ValueError(
            f"counter must be in 0..{ROLLING_CODE_MAX_COUNTER} "
            "(higher counter bits are not reverse-engineered yet)"
        )
    bits = [0] * (ROLLING_CODE_BYTES * 8)
    for k, frame_bit in enumerate(_COUNTER_BITS):
        bits[frame_bit] = counter >> k & 1
    word = _scramble(serial, counter)
    for position, frame_bit in enumerate(_CYCLE_BITS):
        bits[frame_bit] = word >> position & 1
    packed = int("".join(map(str, bits)), 2)
    return packed.to_bytes(ROLLING_CODE_BYTES, "big")


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
    def from_serial(cls, serial: int, counter: int, channel: int) -> RadioFrame:
        """The frame for a transmitter's ``counter``-th transmission (see
        :func:`rolling_code`)."""
        return cls.build(rolling_code(serial, counter), channel)

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
