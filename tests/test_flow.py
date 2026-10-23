import asyncio

import pytest

from app.adapters.fakes import KeywordDecider
from app.adapters.ports import Answer, Segment
from app.modules.draft_v1 import DraftClosed, MissingFields
from app.syncs.flow import Flow


def run(coro):
    return asyncio.run(coro)


def fields(flow, call):
    return {k: (e["value"], e["origin"]) for k, e in flow.drafts.view(call)["fields"].items()}


def test_call_fills_draft_then_person_confirms_quote():
    flow = Flow(KeywordDecider(), zones_table={})
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("Atto front bum", final=False)))
    assert fields(flow, call) == {}  # partials do not trigger decisions
    run(flow.hear(call, Segment("It's an Atto SUV, we scratched the front bumper a little.", final=True)))
    assert fields(flow, call)["car"] == ("Atto", "suggested")
    assert fields(flow, call)["zone"] == ("front bumper", "suggested")
    assert fields(flow, call)["severity"] == ("minor", "suggested")

    flow.set_field(call, "severity", "moderate")  # the person knows better
    run(flow.hear(call, Segment("Just a little, a little.", final=True)))
    assert fields(flow, call)["severity"] == ("moderate", "human")

    quote = flow.confirm(call)
    q = flow.quotes.get(quote)
    assert q["header"]["severity"] == "moderate"
    assert [l["number"] for l in q["lines"]] == ["AT-FB01", "AT-FB02L", "AT-FB02R", "AT-FB03"]
    assert flow.calls.get(call)["ended"] is True


def test_last_mention_wins_on_correction():
    flow = Flow(KeywordDecider())
    call = flow.start_call("demo")
    for text in ["I need a fender for the Vera.", "Left side.", "No wait, passenger side, the right one."]:
        run(flow.hear(call, Segment(text, final=True)))
    assert fields(flow, call)["side"] == ("right", "suggested")


class ScriptedDecider:
    name = "scripted"

    def __init__(self, answers):
        self.answers = list(answers)

    async def decide(self, transcript, questions):
        return self.answers.pop(0)


def test_unsure_answer_is_retracted():
    flow = Flow(ScriptedDecider([{"car": Answer("Atto", 0.95)}, {"car": Answer("Atto", 0.2)}]))
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("one", final=True)))
    assert "car" in fields(flow, call)
    run(flow.hear(call, Segment("two", final=True)))
    assert "car" not in fields(flow, call)


def test_stale_decision_is_dropped():
    flow = Flow(ScriptedDecider([{"car": Answer("Atto", 0.95)}]))
    call = flow.start_call("demo")
    version = flow.calls.hear(call, "one", final=True)
    flow.calls.hear(call, "two", final=True)  # newer speech before the answer comes back
    run(flow.decide(call, version))
    assert fields(flow, call) == {}


def test_confirm_refuses_missing_fields_and_keeps_draft_open():
    flow = Flow(KeywordDecider())
    call = flow.start_call("demo")
    flow.set_field(call, "car", "Atto")
    with pytest.raises(MissingFields):
        flow.confirm(call)
    assert flow.drafts.view(call)["confirmed"] is False


def test_questions_offer_catalog_options():
    keys = {q.key: [o.value for o in q.options] for q in Flow(KeywordDecider()).questions()}
    assert keys["car"] == ["Atto", "Vera", "Ridge"]
    assert keys["intent"] == ["parts quote", "other"]


TABLE = {"threshold": 0.3, "cells": [
    {"model": "Atto", "position": "front", "side": "none", "severity": "moderate", "n": 40, "scope": "model",
     "zones": [{"zone": "front bumper", "share": 0.95}, {"zone": "grille", "share": 0.45},
               {"zone": "fog lamp", "share": 0.31}]},
]}


def test_companions_suggested_included_by_default_and_person_can_untick():
    flow = Flow(KeywordDecider(), zones_table=TABLE)
    call = flow.start_call("demo")
    assert flow.view(call)["companions"] == []  # no zone and severity yet
    flow.set_field(call, "car", "Atto")
    flow.set_field(call, "zone", "front bumper")
    flow.set_field(call, "severity", "moderate")
    comp = flow.view(call)["companions"]
    assert [(c["zone"], c["share"], c["included"]) for c in comp] == [
        ("grille", 0.45, True), ("fog lamp", 0.31, True)]
    assert [l["number"] for l in comp[0]["lines"]] == ["AT-GR01", "AT-GR02"]

    flow.toggle_companion(call, "fog lamp", False)
    q = flow.quotes.get(flow.confirm(call))
    numbers = [l["number"] for l in q["lines"]]
    assert numbers == ["AT-FB01", "AT-FB02L", "AT-FB02R", "AT-FB03", "AT-GR01", "AT-GR02"]
    with pytest.raises(DraftClosed):
        flow.toggle_companion(call, "fog lamp", True)


def test_companions_off_by_setting(monkeypatch):
    from app import settings

    monkeypatch.setattr(settings, "COMPANIONS", False)
    flow = Flow(KeywordDecider(), zones_table=TABLE)
    call = flow.start_call("demo")
    for k, v in {"car": "Atto", "zone": "front bumper", "severity": "moderate"}.items():
        flow.set_field(call, k, v)
    assert flow.view(call)["companions"] == []
