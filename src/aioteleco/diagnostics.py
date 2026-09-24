"""Anonymised dump of an account, to attach to bug reports (and HA diagnostics)."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .hub import TelecoHub

_REDACTED_KEYS = {
    "email",
    "pwd",
    "idSession",
    "idAccount",
    "instCode",
    "instDescription",
    "latitude",
    "longitude",
}
# Dotted numbers that are versions, not addresses.
_VERSION_KEYS = {"firmwareVersion", "workdays", "sdk_version"}
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_SSID_RE = re.compile(r"(NameNet:\s*)(.*)$")


def _fingerprint(value: Any) -> str:
    return "**" + hashlib.sha256(str(value).encode()).hexdigest()[:8]


def redact(data: Any) -> Any:
    """Recursively hide personal fields, IPs and SSIDs."""
    if isinstance(data, dict):
        return {
            k: _fingerprint(v)
            if k in _REDACTED_KEYS and v not in (None, "")
            else v
            if k in _VERSION_KEYS
            else redact(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact(v) for v in data]
    if isinstance(data, str):
        return _SSID_RE.sub(r"\1**", _IP_RE.sub("x.x.x.x", data))
    return data


async def collect(hub: TelecoHub, *, with_status: bool = True) -> dict[str, Any]:
    """Collect the raw cloud data of every installation, redacted."""
    from . import __version__

    out: dict[str, Any] = {"sdk_version": __version__, "installations": []}
    for inst in hub.installations:
        data = hub.data.get(inst.id_installation) or await hub.load(inst)
        entry: dict[str, Any] = {
            "installation": inst.raw,
            "node_active": await hub.api.node_active(inst),
            "local_ip_known": hub.sender.local_host(inst) is not None,
            "rooms": [room.raw for room in data.rooms],
            "scenarios": [s.raw for s in data.scenarios],
        }
        if with_status:
            box = await hub.api.device_status(inst, inst.id_installation_device)
            entry["box_status"] = {s.code: s.status_value for s in box}
            entry["device_status"] = {
                str(dev.id): await dev.refresh() for dev in data.devices.values()
            }
        out["installations"].append(entry)
    return redact(out)  # type: ignore[no-any-return]
