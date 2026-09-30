"""868 MHz radio frame model (synthetic frames: no real rolling code here)."""

from __future__ import annotations

import pytest

from aioteleco.radio import UNIT_US, RadioFrame, frame_checksum

ROLLING = bytes.fromhex("0123456789")


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
