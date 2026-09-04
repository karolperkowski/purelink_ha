"""Tests for the web UI names module (parsing, labeling, preset write)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from xml.etree import ElementTree

import aiohttp
import pytest

from custom_components.purelink.purelink_names import (
    PureLinkNamesError,
    _collect,
    async_write_preset,
    build_labels,
    build_preset_data,
)

SETALL = (
    '<Update name="setall" out1="1" outname1="TV1" inname1="CABLE" '
    'out2="1" outname2="TV2" inname2="BUZZTV" out3="1" outname3="PROJ" '
    'inname3="PROTECT" out4="2" outname4="2R-2" inname4="LAPTOP" '
    'out5="1" outname5="" inname5="EMPTY" out6="1" outname6="" inname6="EMPTY" '
    'out7="1" outname7="" inname7="EMPTY" out8="1" outname8="ENCODER" '
    'inname8="EMPTY">done</Update>'
)


PRESET_FRAME = (
    '<Update name="update" '
    'presetname1="CABLE" presetdata1="I01O01,I01O02" '
    'presetname2="preset2" presetdata2="I00O01,I00O02" '
    'presetname20="BAR TALK" presetdata20="I04O01,I04O02">done</Update>'
)


def _frame(xml: str) -> dict[str, str]:
    return {str(k): str(v) for k, v in ElementTree.fromstring(xml).attrib.items()}


def test_collect_names() -> None:
    frame = _frame(SETALL)
    inputs = _collect(frame, "inname")
    outputs = _collect(frame, "outname")
    assert inputs[1] == "CABLE"
    assert inputs[8] == "EMPTY"
    assert outputs[1] == "TV1"
    assert outputs[5] == ""
    # The digit-suffix filter keeps outnameN keys out of an "out" collection.
    assert _collect(frame, "out")[1] == "1"


def test_collect_preset_names() -> None:
    presets = _collect(_frame(PRESET_FRAME), "presetname")
    assert presets[1] == "CABLE"
    assert presets[2] == "preset2"  # default/unconfigured slot preserved as-is
    assert presets[20] == "BAR TALK"
    # presetdataN must not leak into a presetname collection.
    assert 3 not in presets


def test_build_labels_real_device_shape() -> None:
    frame = _frame(SETALL)
    inputs = build_labels(_collect(frame, "inname"), 8, "Input {n}")
    outputs = build_labels(_collect(frame, "outname"), 8, "Output {n}")

    # Unique names pass through untouched.
    assert inputs[1] == "CABLE"
    assert outputs[3] == "PROJ"
    # Duplicates (four EMPTY inputs) are disambiguated and stay unique.
    assert inputs[5] == "EMPTY (5)"
    assert inputs[8] == "EMPTY (8)"
    assert len(set(inputs.values())) == 8
    # Blank names fall back to the generic label.
    assert outputs[5] == "Output 5"
    assert outputs[6] == "Output 6"
    assert len(set(outputs.values())) == 8


def test_build_labels_no_names() -> None:
    labels = build_labels({}, 4, "Input {n}")
    assert labels == {1: "Input 1", 2: "Input 2", 3: "Input 3", 4: "Input 4"}


def test_build_labels_whitespace_names() -> None:
    labels = build_labels({1: "  ", 2: " TV "}, 2, "Output {n}")
    assert labels[1] == "Output 1"
    assert labels[2] == "TV"


def test_build_labels_pathological_collision() -> None:
    # A device name that literally matches another port's generated suffix
    # must not produce duplicate labels (which would corrupt reverse maps).
    labels = build_labels({3: "EMPTY", 5: "EMPTY", 7: "EMPTY (5)"}, 8, "Input {n}")
    assert labels[3] == "EMPTY (3)"
    assert labels[5] == "EMPTY (5)"
    assert labels[7] != labels[5]
    assert len(set(labels.values())) == 8


def test_build_labels_reserved() -> None:
    # An input named like the select platform's reserved option must be
    # suffixed so it cannot shadow the disconnect action.
    labels = build_labels(
        {1: "Disconnected", 2: "CABLE"},
        2,
        "Input {n}",
        reserved=frozenset({"Disconnected"}),
    )
    assert labels[1] == "Disconnected (1)"
    assert labels[2] == "CABLE"
    assert "Disconnected" not in labels.values()


# --- preset data + write ---------------------------------------------------


def test_build_preset_data() -> None:
    # Full mapping for an 8x8.
    assert build_preset_data({o: 1 for o in range(1, 9)}, 8) == (
        "I01O01,I01O02,I01O03,I01O04,I01O05,I01O06,I01O07,I01O08"
    )
    # Omitted outputs and input 0 both render as disconnected.
    assert build_preset_data({1: 4, 2: 3}, 4) == "I04O01,I03O02,I00O03,I00O04"
    # Empty mapping -> all disconnected (the delete/reset payload).
    assert build_preset_data({}, 4) == "I00O01,I00O02,I00O03,I00O04"


def _preset_frame(names: dict[int, str], datas: dict[int, str]) -> str:
    attrs = "".join(
        f'presetname{i}="{names[i]}" presetdata{i}="{datas[i]}" ' for i in range(1, 21)
    )
    return f'<Update name="update" {attrs}>done</Update>'


class _Msg:
    type = aiohttp.WSMsgType.TEXT

    def __init__(self, data: str) -> None:
        self.data = data


class _FakeWS:
    """Minimal websocket double returning queued frames and recording sends."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = list(frames)
        self.sent: list[str] = []

    async def send_str(self, data: str) -> None:
        self.sent.append(data)

    async def receive(self) -> _Msg:
        return _Msg(self._frames.pop(0))

    async def close(self) -> None:
        return None


def _session(ws: _FakeWS) -> AsyncMock:
    session = AsyncMock()
    session.ws_connect = AsyncMock(return_value=ws)
    return session


GREET = '<Update name="connected">temp</Update>'
LOGIN_OK = '<Update name="update" result="good"/>'


def test_write_preset_happy_path() -> None:
    names = {i: f"preset{i}" for i in range(1, 21)}
    datas = {i: build_preset_data({}, 8) for i in range(1, 21)}
    after_names = {**names, 4: "MOVIE"}
    after_datas = {**datas, 4: build_preset_data({1: 2}, 8)}
    ws = _FakeWS(
        [GREET, LOGIN_OK, _preset_frame(names, datas), _preset_frame(after_names, after_datas)]
    )
    asyncio.run(
        async_write_preset(
            _session(ws), "h", "admin", "pw", 4, "MOVIE", build_preset_data({1: 2}, 8)
        )
    )
    # The updatepreset frame must carry all 20 slots with slot 4 changed.
    update = next(s for s in ws.sent if "updatepreset" in s)
    assert 'presetname4="MOVIE"' in update
    assert update.count("presetname") == 20 and update.count("presetdata") == 20


def test_write_preset_aborts_on_incomplete_table() -> None:
    # A table missing slots must NEVER be written back (would blank presets).
    partial = {i: f"preset{i}" for i in range(1, 21)}
    partial_data = {i: build_preset_data({}, 8) for i in range(1, 21)}
    frame = _preset_frame(partial, partial_data).replace(
        'presetname7="preset7" presetdata7="I00O01,I00O02,I00O03,I00O04,I00O05,I00O06,I00O07,I00O08" ',
        "",
    )
    ws = _FakeWS([GREET, LOGIN_OK, frame])
    with pytest.raises(PureLinkNamesError, match="Incomplete preset table"):
        asyncio.run(
            async_write_preset(_session(ws), "h", "admin", "pw", 4, "X", build_preset_data({}, 8))
        )
    assert not any("updatepreset" in s for s in ws.sent)  # nothing written


def test_write_preset_aborts_on_empty_slot() -> None:
    # A slot present but with an EMPTY data value must also abort the write.
    names = {i: f"preset{i}" for i in range(1, 21)}
    datas = {i: build_preset_data({}, 8) for i in range(1, 21)}
    datas[7] = ""
    ws = _FakeWS([GREET, LOGIN_OK, _preset_frame(names, datas)])
    with pytest.raises(PureLinkNamesError, match="Incomplete preset table"):
        asyncio.run(
            async_write_preset(_session(ws), "h", "admin", "pw", 4, "X", build_preset_data({}, 8))
        )
    assert not any("updatepreset" in s for s in ws.sent)
