"""TelecoHub end to end: fake cloud (aioresponses) + fake box (TCP on 127.0.0.1)."""

from __future__ import annotations

import functools
import json

import pytest

from aioteleco import diagnostics
from aioteleco.const import Endpoint
from aioteleco.devices import ColorLight, Cover, Slats
from aioteleco.exceptions import TelecoLocalError, TelecoUnsupportedError
from aioteleco.hub import InstallationData, TelecoHub
from aioteleco.local.client import LocalClient
from aioteleco.transport import Channel, TransportMode
from conftest import FakeBox, FakeCloud, HubFactory


def use_port(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    """Make the transport's LocalClient connect to ``port`` instead of 400."""
    monkeypatch.setattr(
        "aioteleco.transport.LocalClient", functools.partial(LocalClient, port=port)
    )


async def loaded(hub: TelecoHub) -> InstallationData:
    await hub.connect()
    return await hub.load(hub.installation())


async def local_hub(hub: TelecoHub, monkeypatch: pytest.MonkeyPatch, port: int) -> InstallationData:
    data = await loaded(hub)
    hub.sender.set_local_host(data.installation, "127.0.0.1")
    use_port(monkeypatch, port)
    return data


def slats_of(data: InstallationData) -> Slats:
    device = data.devices[2001]
    assert isinstance(device, Slats)
    return device


def awning_of(data: InstallationData) -> Cover:
    device = data.devices[2002]
    assert isinstance(device, Cover)
    return device


# --- loading --------------------------------------------------------------------------


async def test_connect_and_load(hub: TelecoHub, cloud: FakeCloud) -> None:
    (inst,) = await hub.connect()
    assert (inst.id_installation, inst.inst_code) == (456, "TESTCODE01")
    data = await hub.load(inst)
    assert {i: type(d) for i, d in data.devices.items()} == {
        2001: Slats,
        2002: Cover,
        2003: ColorLight,
    }
    assert [d.name for d in hub.devices()] == ["Pergola slats", "Awning", "Pergola light"]
    assert hub.device("Awning") is data.devices[2002]
    assert hub.device("2003") is data.devices[2003]
    assert data.devices[2001].unique_id == "TESTCODE01-2001"
    assert data.devices[2001].family == "slats"
    (scenario,) = data.scenarios
    assert scenario.description == "Evening"
    assert cloud.bodies(Endpoint.ROOM_CONFIGURATION_LIST)[0]["idInstallation"] == 456


async def test_installation_lookup(hub: TelecoHub) -> None:
    await hub.connect()
    inst = hub.installation()
    assert hub.installation(456) is inst
    assert hub.installation("456") is inst
    assert hub.installation("TESTCODE01") is inst
    assert hub.installation("Test house") is inst


async def test_box_info_registers_local_host(hub: TelecoHub, cloud: FakeCloud) -> None:
    data = await loaded(hub)  # load() reads the box status in auto mode
    inst = data.installation
    assert hub.sender.local_host(inst) == "192.0.2.10"
    info = await hub.box_info(inst)
    assert info.online is True
    assert info.net is not None
    assert (info.net.ip, info.net.ssid) == ("192.0.2.10", "TestWifi")
    assert info.signal == "-60"
    assert info.current_time == "2026-09-24 18:30"
    assert info.firmware_version == "V2.10"
    box_status = [
        b for b in cloud.bodies(Endpoint.STATUS_DEVICE_LIST) if b["idInstallationDevice"] == 789
    ]
    assert len(box_status) == 2


async def test_configured_host_wins(make_hub: HubFactory) -> None:
    hub = make_hub(local_host="192.0.2.99")
    data = await loaded(hub)
    await hub.box_info(data.installation)
    assert hub.sender.local_host(data.installation) == "192.0.2.99"


async def test_cloud_mode_skips_box_discovery(make_hub: HubFactory, cloud: FakeCloud) -> None:
    hub = make_hub(TransportMode.CLOUD)
    data = await loaded(hub)
    assert hub.sender.local_host(data.installation) is None
    assert cloud.count(Endpoint.STATUS_DEVICE_LIST) == 0


# --- transport ------------------------------------------------------------------------


async def test_auto_uses_local_when_box_acks(
    hub: TelecoHub, cloud: FakeCloud, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    result = await slats_of(data).open()
    assert result.channel is Channel.LOCAL
    assert result.detail == "ACK"
    (payload,) = box.payloads
    assert payload["idIn"] == "TESTCODE01"
    assert payload["cL"][0]["coPa"] == "OPEN"
    assert cloud.count(Endpoint.FEED_THE_COMMANDS) == 0


async def test_auto_falls_back_to_cloud(
    hub: TelecoHub, cloud: FakeCloud, closed_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, closed_port)
    cloud.acks = [{"MessageType": "INFO", "MessageText": "RCV", "ActionReference": "ref1"}]
    result = await slats_of(data).stop()
    assert result.channel is Channel.CLOUD
    assert result.detail == "PROC"
    (feed,) = cloud.bodies(Endpoint.FEED_THE_COMMANDS)
    assert feed["commandsList"][0]["commandParam"] == "STOP"
    assert cloud.count(Endpoint.GET_ACK_COMMAND) == 2


async def test_auto_falls_back_when_box_refuses(
    hub: TelecoHub, cloud: FakeCloud, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    box.reply = b"NOK\n"
    data = await local_hub(hub, monkeypatch, box.port)
    result = await slats_of(data).close()
    assert result.channel is Channel.CLOUD
    assert len(box.frames) == 1
    assert cloud.count(Endpoint.FEED_THE_COMMANDS) == 1


async def test_local_mode_never_falls_back(
    make_hub: HubFactory, cloud: FakeCloud, closed_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = make_hub(TransportMode.LOCAL)
    data = await local_hub(hub, monkeypatch, closed_port)
    with pytest.raises(TelecoLocalError):
        await slats_of(data).open()
    assert cloud.count(Endpoint.FEED_THE_COMMANDS) == 0


async def test_local_mode_without_ip(make_hub: HubFactory, cloud: FakeCloud) -> None:
    hub = make_hub(TransportMode.LOCAL, discover_local_ip=False)
    data = await loaded(hub)
    with pytest.raises(TelecoLocalError, match="unknown"):
        await slats_of(data).open()


async def test_cloud_mode_never_touches_the_socket(
    make_hub: HubFactory, cloud: FakeCloud, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = make_hub(TransportMode.CLOUD)
    data = await local_hub(hub, monkeypatch, box.port)
    result = await slats_of(data).open()
    assert result.channel is Channel.CLOUD
    assert box.frames == []
    assert cloud.count(Endpoint.FEED_THE_COMMANDS) == 1


async def test_system_commands_are_cloud_only(
    hub: TelecoHub, cloud: FakeCloud, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    result = await hub.send_system(data.installation, "GET_SIGNAL")
    assert result.channel is Channel.CLOUD
    assert box.frames == []
    (feed,) = cloud.bodies(Endpoint.FEED_THE_COMMANDS)
    assert feed["commandsList"][0]["commandId"] == 122
    assert feed["commandsList"][0]["idInstallationDevice"] == 789


# --- device actions ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "param", "model_id"),
    [(66, "LEV3", 99), (100, "LEV4", 100), (40, "LEV2", 98), (60, "LEV3", 99)],
)
async def test_slats_set_position(
    hub: TelecoHub,
    box: FakeBox,
    monkeypatch: pytest.MonkeyPatch,
    percent: int,
    param: str,
    model_id: int,
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    await slats_of(data).set_position(percent)
    (payload,) = box.payloads
    (cmd,) = payload["cL"]
    assert (cmd["coAc"], cmd["coPa"], cmd["cmId"]) == ("LEVEL", param, model_id)
    assert (cmd["idInDe"], cmd["deCo"]) == (2001, "1")


async def test_slats_position_zero_closes(
    hub: TelecoHub, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    await slats_of(data).set_position(0)
    (cmd,) = box.payloads[0]["cL"]
    assert (cmd["coAc"], cmd["coPa"], cmd["low"]) == ("OPEN_STOP_CLOSE", "CLOSE", "CH1")


async def test_slats_position_out_of_range(hub: TelecoHub) -> None:
    data = await loaded(hub)
    with pytest.raises(ValueError, match="position"):
        await slats_of(data).set_position(101)


async def test_awning_open_with_feedback(make_hub: HubFactory, cloud: FakeCloud) -> None:
    hub = make_hub(TransportMode.CLOUD)
    data = await loaded(hub)
    await awning_of(data).open()
    (feed,) = cloud.bodies(Endpoint.FEED_THE_COMMANDS)
    (cmd,) = feed["commandsList"]
    assert cmd["commandAction"] == "OPEN_STOP_CLOSE-F"
    assert (cmd["commandParam"], cmd["lowlevelCommand"], cmd["commandId"]) == ("OPEN", "CH5", 75)
    assert feed["idInstallation"] == "TESTCODE01"
    assert "idAccount" not in feed
    assert feed["idSession"] == "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


async def test_awning_open_local_with_feedback(
    hub: TelecoHub, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    await awning_of(data).open()
    (cmd,) = box.payloads[0]["cL"]
    assert (cmd["coAc"], cmd["coPa"], cmd["low"]) == ("OPEN_STOP_CLOSE-F", "OPEN", "CH5")


async def test_color_light(hub: TelecoHub, box: FakeBox, monkeypatch: pytest.MonkeyPatch) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    light = data.devices[2003]
    assert isinstance(light, ColorLight)
    await light.set_color((255, 128, 0), 80)
    await light.turn_off()
    assert [(p["cL"][0]["cmId"], p["cL"][0]["coPa"]) for p in box.payloads] == [
        (137, "A080R255G128B000"),
        (147, "OFF"),
    ]


async def test_unsupported_action(hub: TelecoHub) -> None:
    data = await loaded(hub)
    with pytest.raises(TelecoUnsupportedError):
        await data.devices[2002].send("POWER", "ON")


# --- state ------------------------------------------------------------------------------


async def test_refresh(hub: TelecoHub, cloud: FakeCloud) -> None:
    data = await loaded(hub)
    slats = slats_of(data)
    assert slats.position is None
    assert slats.retracted is None
    await hub.refresh(data.installation)
    assert slats.status == {"OPEN_CLOSE": "OPEN", "LEVEL": "66", "RETR": "NO"}
    assert slats.position == 66
    assert slats.retracted is False
    assert slats.state == "OPEN"
    assert slats.is_closed is False
    assert awning_of(data).status == {}
    assert awning_of(data).is_closed is None
    queried = {b["idInstallationDevice"] for b in cloud.bodies(Endpoint.STATUS_DEVICE_LIST)}
    assert queried == {789, 2001, 2002, 2003}


async def test_device_refresh(hub: TelecoHub) -> None:
    data = await loaded(hub)
    assert await slats_of(data).refresh() == {"OPEN_CLOSE": "OPEN", "LEVEL": "66", "RETR": "NO"}


async def test_refresh_loads_when_needed(hub: TelecoHub) -> None:
    await hub.connect()
    await hub.refresh(hub.installation())
    assert slats_of(hub.data[456]).position == 66


# --- scenarios --------------------------------------------------------------------------


async def test_run_scenario_cloud(make_hub: HubFactory, cloud: FakeCloud) -> None:
    hub = make_hub(TransportMode.CLOUD)
    data = await loaded(hub)
    result = await hub.run_scenario(data.installation, data.scenarios[0])
    assert result.channel is Channel.CLOUD
    (feed,) = cloud.bodies(Endpoint.FEED_THE_COMMANDS)
    assert feed["isScenario"] is True
    assert feed["idScenario"] == 7001
    # Sorted by commandIndex; the COLOR template takes the step value.
    assert [
        (c["idInstallationDeviceCommand"], c["commandParam"], c["deviceCode"])
        for c in feed["commandsList"]
    ] == [(3005, "LEV2", "1"), (3023, "A080R255G128B000", "3")]


async def test_run_scenario_local(
    hub: TelecoHub, box: FakeBox, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await local_hub(hub, monkeypatch, box.port)
    result = await hub.run_scenario(data.installation, data.scenarios[0])
    assert result.channel is Channel.LOCAL
    assert box.frames[0][0] == "S"
    (payload,) = box.payloads
    assert (payload["idSc"], payload["isSc"]) == (7001, True)
    assert [c["cmId"] for c in payload["cL"]] == [98, 137]


async def test_run_scenario_unknown_command(hub: TelecoHub) -> None:
    data = await loaded(hub)
    scenario = data.scenarios[0]
    scenario.steps[0].id_installation_device_command = 424242
    with pytest.raises(TelecoUnsupportedError, match="424242"):
        await hub.run_scenario(data.installation, scenario)


# --- diagnostics ------------------------------------------------------------------------


async def test_diagnostics_redacted(hub: TelecoHub) -> None:
    await hub.connect()
    dump = await diagnostics.collect(hub)
    text = json.dumps(dump)
    for secret in ("TESTCODE01", "user@example.com", "192.0.2.10", "TestWifi", "Test house"):
        assert secret not in text
    (entry,) = dump["installations"]
    assert entry["installation"]["instCode"].startswith("**")
    assert entry["installation"]["idInstallation"] == 456
    assert entry["installation"]["latitude"].startswith("**")
    assert entry["box_status"]["NET_PARAM"] == "IP: x.x.x.x NameNet: **"
    assert entry["box_status"]["SIGNAL"] == "-60"
    assert entry["local_ip_known"] is True
    assert entry["node_active"] is True
    assert entry["device_status"]["2001"]["LEVEL"] == "66"
    assert len(entry["rooms"][0]["deviceList"]) == 3


async def test_diagnostics_without_status(hub: TelecoHub, cloud: FakeCloud) -> None:
    await hub.connect()
    dump = await diagnostics.collect(hub, with_status=False)
    assert "box_status" not in dump["installations"][0]
    # Only load()'s own box discovery hit status-device-list.
    assert cloud.count(Endpoint.STATUS_DEVICE_LIST) == 1


async def test_close_logs_out(hub: TelecoHub, cloud: FakeCloud) -> None:
    await hub.connect()
    await hub.close()
    assert cloud.count(Endpoint.ACCOUNT_LOGOUT) == 1
    assert hub.client.session is None
