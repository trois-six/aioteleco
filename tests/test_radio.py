"""868 MHz radio frame model.

The rolling-code vectors below use a throwaway serial (``0xABCDEF``), never a real
transmitter's; they pin the reverse-engineered algorithm, not any device's data.
"""

from __future__ import annotations

import pytest

from aioteleco.radio import (
    ROLLING_CODE_MAX_COUNTER,
    UNIT_US,
    RadioFrame,
    frame_checksum,
    rolling_code,
)

ROLLING = bytes.fromhex("0123456789")
TEST_SERIAL = 0xABCDEF
# (counter, expected frame for channel 1), spanning every counter bit at least once.
ROLLING_VECTORS = [
    (0, "41 B4 01 F1 06 00 01 12"),
    (1, "23 60 31 D3 84 00 01 F4"),
    (2, "65 9C 04 21 C4 00 01 15"),
    (7, "56 6C 11 32 06 00 01 F4"),
    (8, "A1 94 24 80 C0 00 01 66"),
    (15, "BE 54 20 12 C0 00 01 FB"),
    (16, "00 00 30 D0 43 00 01 BC"),
    (255, "D7 C4 3F C1 8B 00 01 D9"),
    (256, "29 DC 05 E2 D4 00 01 3F"),
    (300, "98 BC 07 70 56 00 01 DE"),
    (511, "9E 50 0F 83 59 00 01 26"),
]


def test_build_adds_the_checksum() -> None:
    frame = RadioFrame.build(ROLLING, 7)
    assert frame.data[:7] == ROLLING + b"\x00\x07"
    assert sum(frame.data) % 256 == 0
    assert frame.data[7] == frame_checksum(frame.data)
    assert (frame.rolling_code, frame.channel, frame.valid) == (ROLLING, 7, True)
    assert str(frame) == "01 23 45 67 89 00 07 " + f"{frame.data[7]:02X}"


def test_from_hex_and_validity() -> None:
    good = RadioFrame.build(ROLLING, 1)
    assert RadioFrame.from_hex(good.data.hex()) == good
    bad_sum = RadioFrame(good.data[:7] + bytes(((good.data[7] + 1) & 0xFF,)))
    assert not bad_sum.valid
    reserved = bytearray(good.data)
    reserved[5], reserved[7] = 0x10, (reserved[7] - 0x10) & 0xFF
    assert sum(reserved) % 256 == 0
    assert not RadioFrame(bytes(reserved)).valid


def test_segments_round_trip() -> None:
    frame = RadioFrame.build(ROLLING, 8)
    segments = frame.segments_us()
    assert len(segments) == 64
    assert set(segments) <= {UNIT_US, 2 * UNIT_US}
    assert segments[:8] == [UNIT_US] * 7 + [2 * UNIT_US]  # 0x01, MSB first
    jittered = [s + (30 if i % 2 else -30) for i, s in enumerate(segments)]
    assert RadioFrame.from_segments(jittered) == frame


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="8 bytes"):
        RadioFrame(b"\x00" * 7)
    with pytest.raises(ValueError, match="5 bytes"):
        RadioFrame.build(b"\x00", 1)
    with pytest.raises(ValueError, match="channel"):
        RadioFrame.build(ROLLING, 0)
    with pytest.raises(ValueError, match="64 segments"):
        RadioFrame.from_segments([UNIT_US] * 63)
    with pytest.raises(ValueError, match="neither"):
        RadioFrame.from_segments([UNIT_US] * 63 + [3 * UNIT_US])


# --- rolling code -----------------------------------------------------------------------


@pytest.mark.parametrize(("counter", "expected"), ROLLING_VECTORS)
def test_rolling_code_matches_the_reverse_engineered_algorithm(counter: int, expected: str) -> None:
    assert str(RadioFrame.from_serial(TEST_SERIAL, counter, 1)) == expected


def test_rolling_code_is_the_frames_first_five_bytes() -> None:
    frame = RadioFrame.from_serial(TEST_SERIAL, 42, 3)
    assert frame.rolling_code == rolling_code(TEST_SERIAL, 42)
    assert frame.channel == 3
    assert frame.valid


def test_rolling_code_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="24-bit"):
        rolling_code(1 << 24, 0)
    with pytest.raises(ValueError, match="24-bit"):
        rolling_code(-1, 0)
    with pytest.raises(ValueError, match=f"0..{ROLLING_CODE_MAX_COUNTER}"):
        rolling_code(TEST_SERIAL, ROLLING_CODE_MAX_COUNTER + 1)
    with pytest.raises(ValueError, match=f"0..{ROLLING_CODE_MAX_COUNTER}"):
        rolling_code(TEST_SERIAL, -1)
