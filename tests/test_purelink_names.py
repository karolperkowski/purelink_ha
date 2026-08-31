"""Tests for the web UI names module (parsing and labeling; no network)."""

from __future__ import annotations

from xml.etree import ElementTree

from custom_components.purelink.purelink_names import _collect, build_labels

SETALL = (
    '<Update name="setall" out1="1" outname1="TV1" inname1="CABLE" '
    'out2="1" outname2="TV2" inname2="BUZZTV" out3="1" outname3="PROJ" '
    'inname3="PROTECT" out4="2" outname4="2R-2" inname4="LAPTOP" '
    'out5="1" outname5="" inname5="EMPTY" out6="1" outname6="" inname6="EMPTY" '
    'out7="1" outname7="" inname7="EMPTY" out8="1" outname8="ENCODER" '
    'inname8="EMPTY">done</Update>'
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
