"""Obfuscation used on the Daisy box LAN channel (TCP port 400).

Port of ``DaisyApplication#encrypt``:

1. pick ``r`` in ``0..27`` and rotate the 28-char key left by ``r``;
2. take the epoch seconds as a 10-digit string ``ts`` and turn each pair of digits
   into one character (``chr(int("12")) == "\\x0c"``);
3. plaintext = ``chr(ts[0:2])`` + message, with ``chr(ts[2:4])``, ``chr(ts[4:6])``
   and ``chr(ts[6:8])`` inserted *before* the characters at indexes 50, 70 and 90
   of the original message (only if the message is long enough), + ``chr(ts[8:10])``;
4. XOR every UTF-16 code unit with the rotated key, encode as UTF-8, Base64 it;
5. prefix ``"S"`` (scenario) or ``"M"`` (anything else) and ``ALPHABET[r]``.

The box answers with a plaintext line; a line containing ``"ACK"`` means success.
"""

from __future__ import annotations

import base64
import secrets
import time
from typing import Final

KEY: Final = "d3Cr1pTam1St0CaZzOSe61nGrad0"
ALPHABET: Final = "abcdefghijklmnopqrstuvwxyz0123456789"
_INSERT_AT: Final = {50: (2, 4), 70: (4, 6), 90: (6, 8)}


def _rotated_key(r: int) -> str:
    return KEY[r:] + KEY[:r]


def _ts_char(ts: str, start: int, end: int) -> str:
    return chr(int(ts[start:end]))


def encrypt(
    message: str,
    *,
    scenario: bool = False,
    rotation: int | None = None,
    timestamp: int | None = None,
) -> str:
    """Obfuscate ``message`` the way the app does before sending it to port 400.

    ``rotation`` and ``timestamp`` are only meant for tests; by default they are
    random and the current time, like the app.
    """
    r = secrets.randbelow(len(KEY)) if rotation is None else rotation
    if not 0 <= r < len(KEY):
        raise ValueError(f"rotation must be in 0..{len(KEY) - 1}")
    ts = str(int(time.time()) if timestamp is None else timestamp)
    if len(ts) < 10:
        raise ValueError("timestamp must have at least 10 digits")

    parts = [_ts_char(ts, 0, 2)]
    for index, char in enumerate(message):
        if index in _INSERT_AT:
            parts.append(_ts_char(ts, *_INSERT_AT[index]))
        parts.append(char)
    parts.append(_ts_char(ts, 8, 10))
    plain = "".join(parts)

    key = _rotated_key(r)
    xored = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(plain))
    payload = base64.b64encode(xored.encode("utf-8")).decode("ascii")
    return ("S" if scenario else "M") + ALPHABET[r] + payload


def decrypt(frame: str) -> tuple[str, int, bool]:
    """Invert :func:`encrypt`.

    Returns ``(message, timestamp, scenario)``. Mainly useful for tests and for
    debugging captured frames.
    """
    if len(frame) < 3 or frame[0] not in "MS" or frame[1] not in ALPHABET:
        raise ValueError("not a Daisy local frame")
    scenario = frame[0] == "S"
    r = ALPHABET.index(frame[1])
    if r >= len(KEY):
        raise ValueError("invalid key rotation")
    key = _rotated_key(r)
    xored = base64.b64decode(frame[2:]).decode("utf-8")
    plain = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(xored))
    if len(plain) < 2:
        raise ValueError("frame too short")

    ts_chars = [plain[0], plain[-1]]
    body = plain[1:-1]
    message: list[str] = []
    inserted: dict[int, str] = {}
    i = 0
    for char in body:
        if i in _INSERT_AT and i not in inserted:
            inserted[i] = char
            continue
        message.append(char)
        i += 1
    pairs = [ts_chars[0], inserted.get(50), inserted.get(70), inserted.get(90), ts_chars[1]]
    ts = "".join(f"{ord(p):02d}" if p is not None else "??" for p in pairs)
    timestamp = int(ts) if "?" not in ts else -1
    return "".join(message), timestamp, scenario
