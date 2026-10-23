import pytest

from app.modules.catalog_v1 import Catalog, UnknownChoice


def numbers(lines):
    return [l["number"] for l in lines]


def test_operational_principle_moderate_bumper_both_sides():
    lines = Catalog().lines("Atto", "front bumper", "both", "moderate")
    assert numbers(lines) == ["AT-FB01", "AT-FB02L", "AT-FB02R", "AT-FB03"]


def test_beam_only_when_severe():
    assert "VR-FB04" in numbers(Catalog().lines("Vera", "front bumper", None, "severe"))
    assert "VR-FB04" not in numbers(Catalog().lines("Vera", "front bumper", None, "moderate"))


def test_side_selects_one_side_and_unknown_includes_both():
    cat = Catalog()
    assert numbers(cat.lines("Ridge", "headlamp", "right", "minor")) == ["RG-HL01R"]
    assert numbers(cat.lines("Ridge", "headlamp", "left", "minor")) == ["RG-HL01L"]
    assert numbers(cat.lines("Ridge", "headlamp", None, "minor")) == ["RG-HL01L", "RG-HL01R"]


def test_unknown_choice():
    with pytest.raises(UnknownChoice):
        Catalog().lines("Nope", "front bumper", None, "minor")


def test_options_cover_every_question():
    assert set(Catalog().options()) == {"car", "zone", "side", "severity"}


def test_zones_expose_position_and_parts():
    zones = {z["zone"]: z for z in Catalog().zones()}
    assert len(zones) == 14
    assert {z["position"] for z in zones.values()} == {"front", "rear", "side"}
    assert zones["tail lamp"]["position"] == "rear"
    assert zones["front bumper"]["parts"][3] == {
        "name": "Front bumper beam", "sided": False, "min_severity": "severe"}
