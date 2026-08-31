"""Protocol-parsing tests for the PureLink UX-8800 client.

These exercise the HA-agnostic client with canned frames captured from a real
device — no network or Home Assistant required.
"""

from __future__ import annotations

import pytest

from custom_components.purelink_ux8800.client import (
    INPUT_NONE,
    PureLinkClient,
    _build_command,
)

SETALL = (
    '<Update name="setall" out1="1" outname1="TV1" inname1="CABLE" '
    'out2="1" outname2="TV2" inname2="BUZZTV" out3="1" outname3="PROJ" '
    'inname3="PROTECT" out4="2" outname4="2R-2" inname4="LAPTOP" '
    'out5="1" outname5="" inname5="EMPTY" out6="1" outname6="" inname6="EMPTY" '
    'out7="1" outname7="" inname7="EMPTY" out8="1" outname8="ENCODER" '
    'inname8="EMPTY">done</Update>'
)

INFO = (
    '<Update in1data1="1920x1080 @60" in1data2="HDCP 1.x" '
    'in2data1="1920x1080 @60" in2data2="HDCP off" in4data1="No signal" '
    'in4data2="-" out1data2="1920x1080 @60" out5data2="Not connected" '
    'name="update">done</Update>'
)

PRESETS = (
    '<Update presetname1="CABLE" '
    'presetdata1="I01O01,I01O02,I01O03,I01O04,I01O05,I01O06,I01O07,I01O08" '
    'presetname20="BAR TALK" '
    'presetdata20="I04O01,I04O02,I01O03,I01O04,I01O05,I01O06,I01O07,I01O08" '
    'name="update">done</Update>'
)


@pytest.fixture
def client() -> PureLinkClient:
    """A client with no real session (parsing does not touch the socket)."""
    return PureLinkClient(session=None, host="192.168.11.9", username="admin", password="x")


def _dispatch(client: PureLinkClient, xml: str) -> None:
    client._dispatch(client._parse_frame(xml))


def test_parse_setall(client: PureLinkClient) -> None:
    _dispatch(client, SETALL)
    assert client.state.routing[1] == 1
    assert client.state.routing[4] == 2
    assert client.state.output_names[1] == "TV1"
    assert client.state.output_names[8] == "ENCODER"
    assert client.state.input_names[4] == "LAPTOP"


def test_source_options_dedup(client: PureLinkClient) -> None:
    _dispatch(client, SETALL)
    options = dict((idx, label) for idx, label in client.state.source_options())
    # Distinct names stay as-is.
    assert options[1] == "CABLE"
    # Inputs 5-8 all read "EMPTY" -> disambiguated with (IN n).
    assert options[5] == "EMPTY (IN5)"
    assert options[8] == "EMPTY (IN8)"
    # Round-trips.
    assert client.state.input_for_label("CABLE") == 1
    assert client.state.input_for_label("EMPTY (IN7)") == 7


def test_parse_info_signal(client: PureLinkClient) -> None:
    _dispatch(client, INFO)
    assert client.state.input_signal[1] is True
    assert client.state.input_signal[4] is False
    assert client.state.input_resolution[1] == "1920x1080 @60"
    assert client.state.input_hdcp[2] == "HDCP off"
    assert client.state.output_sync[5] == "Not connected"


def test_parse_presets(client: PureLinkClient) -> None:
    _dispatch(client, PRESETS)
    assert client.state.preset_names[1] == "CABLE"
    assert client.state.preset_names[20] == "BAR TALK"
    assert client.state.preset_data[20].startswith("I04O01")


def test_getout_and_resetout(client: PureLinkClient) -> None:
    _dispatch(client, '<Update name="GetOut" swap="Off" id="8">3</Update>')
    assert client.state.routing[8] == 3
    _dispatch(client, '<Update name="ResetOut" id="8">3</Update>')
    assert client.state.routing[8] == INPUT_NONE


def test_setchanel_compact(client: PureLinkClient) -> None:
    _dispatch(
        client,
        '<Update name="SetChanel">I02O01,I03O02,I01O03,I04O04,'
        'I01O05,I01O06,I01O07,I01O08</Update>',
    )
    assert client.state.routing[1] == 2
    assert client.state.routing[2] == 3
    assert client.state.routing[4] == 4


def test_mastervolume(client: PureLinkClient) -> None:
    _dispatch(client, '<Update name="MasterVolume">10</Update>')
    assert client.state.master_volume == 10


def test_build_command_escaping() -> None:
    frame = _build_command("update", "GetNames", "temp", data="A&B", kind="input", id="1")
    assert 'name="GetNames"' in frame
    assert "A&amp;B" in frame  # attribute value is XML-escaped
    assert frame.endswith(">temp</command>")


def test_setting_frame_never_exposes_password(client: PureLinkClient) -> None:
    # The device leaks passwords in the setting frame; we only keep versions.
    _dispatch(
        client,
        '<Update name="update" dhcp="off" ipaddress="192.168.11.9" '
        'vercontroller="UX-8800-CT-V1.4.2" verwebui="UX-8800-UI-V1.1.1" '
        'name1="admin" pass1="coldbeer">done</Update>',
    )
    assert client.state.sw_version == "UX-8800-CT-V1.4.2"
    assert client.state.web_version == "UX-8800-UI-V1.1.1"
    # Nothing password-shaped is retained anywhere in state.
    assert "coldbeer" not in repr(client.state)
