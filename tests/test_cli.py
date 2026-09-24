"""CLI helpers that do not need a network."""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

from aioteleco.cli import save_travel_times


def test_save_travel_times_creates_a_private_file(tmp_path: Path) -> None:
    path = tmp_path / "aioteleco" / "config.toml"
    save_travel_times(path, "SCREEN 3", 24.46, 22.04)
    assert tomllib.loads(path.read_text()) == {
        "travel": {"SCREEN 3": {"open": 24.5, "close": 22.0}}
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_travel_times_keeps_other_settings_and_replaces_its_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'email = "me@example.com"\n'
        "\n"
        '[travel."SCREEN 1"]\nopen = 10.0\nclose = 9.0\n'
        "\n"
        '[travel."SCREEN 3"]\nopen = 1.0\nclose = 1.0\n'
    )
    save_travel_times(path, "SCREEN 3", 24.5, 22.0)
    save_travel_times(path, "SCREEN 2", 20.0, 19.0)
    assert tomllib.loads(path.read_text()) == {
        "email": "me@example.com",
        "travel": {
            "SCREEN 1": {"open": 10.0, "close": 9.0},
            "SCREEN 3": {"open": 24.5, "close": 22.0},
            "SCREEN 2": {"open": 20.0, "close": 19.0},
        },
    }
