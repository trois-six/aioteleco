"""Local-channel obfuscation, checked against vectors produced by running the app's
own ``DaisyApplication#encrypt`` Java code with a fixed rotation and timestamp."""

from __future__ import annotations

import pytest

from aioteleco.local.crypto import decrypt, encrypt

# (rotation, timestamp, scenario, message, expected frame)
JAVA_VECTORS = [
    (
        3,
        1790212345,
        False,
        '{"idIn":"ABC123","idSc":0,"isSc":false,"cL":[{"idInDe":4567,"deCo":"12","cmId":89,"coAc":"OPEN","coPa":"0","low":"CH1","coSta":0}]}',
        "MdY0pSPQUkX3FOEgIjGUt9YEcaEwcjIQJGClQfYRtCIzdDV1cyGEMmTXgZA3FfbUpMLhYoPl4gVmFIBUViVkETNxFzLENgWH5hcBQdTCQfKAASXgt6XhMTOyAOE2lWJwwxHzRtf0dVXj4mUFtGAEYfYR5eB3ZbT3IbRRJvQzkVHCcEFAteOi8cSQ==",
    ),
    (
        0,
        1790212345,
        False,
        "DIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTICDIAGNOSTIC",
        "MadXcKM3Y+GzI5eBAweQImFDUcByx1dScGNS8rYzB6ADZ4MRMvImIHPXMHKBs9ARw2YngtHTYoJXcqfBAmeDMQKCx2HTtjFygZbwsaJHF/IRQmKCd0LXIEPH4jACguJhc9cQQvFSkbGiYb",
    ),
    (27, 1700000000, False, '{"a":1}', "M1IR8RIlALQSlh"),
    (
        10,
        1712345678,
        False,
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "MkQgxIOxkiAjcrHU5JFj8KGRxIHEs7CkkILBkVSSsMSDsZIgI3Kx1OSRY/ChkcSBxLOwpJPg==",
    ),
    (
        15,
        1799999999,
        True,
        '{"idIn":"ZZ9","idSc":7,"isSc":true,"cL":[{"idInDe":1,"deCo":"3","cmId":195,"coAc":"COLOR","coPa":"255-128-000-","low":"","coSta":0}]}',
        "SpSwFtOgF/X0x9UDs+CUYfYRtVIzdDVwZ/VlkwMjlYdScXQ1RCZREtRgo/SGEbVTk6JQgTME4Bb0M+Hww8RwwTXWVeQwddLVdhEQtBbVRBEzAbcSBDYFgMHCl5Y0xrEUMHXzRSYUgTQmFUQABhTB1zUWpXbX9HWl4ZZUhDRhxGUCwhRRF2W11MDglT",
    ),
    (
        0,
        1000000000,
        False,
        '{"idIn":"ABC123","idSc":0,"isSc":false,"cL":[{"idInDe":4567,"deCo":"12","cmId":89,"coAc":"OPEN","coPa":"0","low":"CH1","coSta":0}]}',
        "MabkhhG1U5OkNXExI2c3JTaVhjcQxSYg1lSFFIEg1AEBETSjIAAUI2WBIgLXhAFChHX1UnRxwlARJeB3ZEBlx2BQhyPFYKYVBoem1/R1VcJyNQW1wJSBEgHXATdltPMRwkdQ1DdlgsPDVXE1RlQkNIEghcNFALUhcpXBN/VlMsMi4bbWlVS2wTRw==",
    ),
]


@pytest.mark.parametrize(("rotation", "timestamp", "scenario", "message", "expected"), JAVA_VECTORS)
def test_encrypt_matches_java(
    rotation: int, timestamp: int, scenario: bool, message: str, expected: str
) -> None:
    frame = encrypt(message, scenario=scenario, rotation=rotation, timestamp=timestamp)
    assert frame == expected


@pytest.mark.parametrize(("rotation", "timestamp", "scenario", "message", "expected"), JAVA_VECTORS)
def test_decrypt_roundtrip(
    rotation: int, timestamp: int, scenario: bool, message: str, expected: str
) -> None:
    decoded, ts, is_scenario = decrypt(expected)
    assert decoded == message
    assert is_scenario is scenario
    if len(message) > 90:
        assert ts == timestamp


def test_random_rotation_roundtrip() -> None:
    frame = encrypt('{"idIn":"X"}')
    assert frame[0] == "M"
    assert decrypt(frame)[0] == '{"idIn":"X"}'


def test_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="frame"):
        decrypt("hello")
