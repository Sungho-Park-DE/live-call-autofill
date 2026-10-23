import pytest

from app.modules.draft_v1 import DraftClosed, Drafts, MissingFields


def test_operational_principle_human_has_last_word():
    d = Drafts()
    d.open("c1")
    assert d.suggest("c1", "car", "Atto", 0.91, "jev") == "applied"
    assert d.view("c1")["fields"]["car"]["origin"] == "suggested"
    d.set("c1", "car", "Vera")
    assert d.suggest("c1", "car", "Atto", 0.99, "jev") == "kept-human"
    assert d.confirm("c1", ["car"]) == {"car": "Vera"}
    with pytest.raises(DraftClosed):
        d.suggest("c1", "car", "Atto", 0.99, "jev")
    with pytest.raises(DraftClosed):
        d.set("c1", "car", "Ridge")


def test_retract_only_removes_machine_values():
    d = Drafts()
    d.open("c1")
    d.suggest("c1", "side", "left", 0.8, "jev")
    assert d.retract("c1", "side") is True
    d.set("c1", "side", "right")
    assert d.retract("c1", "side") is False
    assert d.view("c1")["fields"]["side"]["value"] == "right"


def test_release_hands_field_back():
    d = Drafts()
    d.open("c1")
    d.set("c1", "zone", "")
    assert d.suggest("c1", "zone", "front bumper", 0.9, "jev") == "kept-human"
    d.release("c1", "zone")
    assert d.suggest("c1", "zone", "front bumper", 0.9, "jev") == "applied"


def test_confirm_needs_required_fields():
    d = Drafts()
    d.open("c1")
    d.set("c1", "car", "")
    with pytest.raises(MissingFields) as e:
        d.confirm("c1", ["car", "zone"])
    assert e.value.fields == ["car", "zone"]
    assert d.view("c1")["confirmed"] is False
