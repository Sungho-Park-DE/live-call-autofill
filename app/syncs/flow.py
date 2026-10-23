"""Syncs from docs/concepts/syncs.md. One method per sync; concepts meet only here."""
from __future__ import annotations

import json
from typing import Sequence

from app import settings
from app.adapters.ports import Decider, Option, Question, Segment
from app.modules.accident_v1 import Companions
from app.modules.call_v1 import CallBook
from app.modules.catalog_v1 import Catalog, UnknownChoice
from app.modules.draft_v1 import DraftClosed, Drafts, MissingFields
from app.modules.quote_v1 import Quotes


class Flow:
    def __init__(self, decider: Decider, fields: Sequence[settings.Field] = settings.FIELDS,
                 required: Sequence[str] = settings.REQUIRED, zones_table: dict | None = None) -> None:
        self.decider = decider
        self.fields = tuple(fields)
        self.required = tuple(required)
        self.calls = CallBook()
        self.drafts = Drafts()
        self.catalog = Catalog()
        self.quotes = Quotes()
        self.companions = Companions(zones_table if zones_table is not None else load_zones_table())
        self.positions = {z["zone"]: z["position"] for z in self.catalog.zones()}

    # OpenDraftOnCallStart
    def start_call(self, caller: str) -> str:
        call = self.calls.start(caller)
        self.drafts.open(call)
        return call

    # SpeechIntoCall (+ DecideOnFinalSegment when final)
    async def hear(self, call: str, segment: Segment) -> None:
        version = self.calls.hear(call, segment.text, segment.final)
        if segment.final:
            await self.decide(call, version)

    def questions(self) -> list[Question]:
        catalog = self.catalog.options()
        out = []
        for f in self.fields:
            opts = f.options or tuple((o["value"], o["hint"]) for o in catalog[f.key])
            out.append(Question(f.key, f.prompt, tuple(Option(v, h) for v, h in opts)))
        return out

    # DecideOnFinalSegment -> SuggestConfidentAnswer / RetractUnsureAnswer
    async def decide(self, call: str, version: int) -> None:
        answers = await self.decider.decide(self.calls.transcript(call), self.questions())
        if self.calls.version(call) != version or self.drafts.view(call)["confirmed"]:
            return  # newer speech arrived or the person already confirmed
        for f in self.fields:
            a = answers.get(f.key)
            if a is not None and a.confidence >= f.threshold:
                self.drafts.suggest(call, f.key, a.value, a.confidence, self.decider.name)
            else:
                self.drafts.retract(call, f.key)

    # HumanEdits
    def set_field(self, call: str, field: str, value: str) -> None:
        self.drafts.set(call, field, value)

    def release_field(self, call: str, field: str) -> None:
        self.drafts.release(call, field)

    # ConfirmCreatesQuote
    def confirm(self, call: str) -> str:
        values = self.drafts.view(call)["fields"]
        current = {k: e["value"] for k, e in values.items() if e["value"]}
        missing = [f for f in self.required if f not in current]
        if missing:
            raise MissingFields(missing)
        lines = self.catalog.lines(current.get("car", ""), current.get("zone", ""),
                                   current.get("side"), current.get("severity", ""))
        lines = merge_lines(lines, [l for c in self.suggest_companions(call, current) if c["included"]
                                    for l in c["lines"]])
        fields = self.drafts.confirm(call, self.required)
        quote = self.quotes.create(call, fields, lines)
        self.calls.end(call)
        return quote

    # SuggestCompanions
    def suggest_companions(self, call: str, values: dict[str, str]) -> list[dict]:
        zone, severity, car = values.get("zone"), values.get("severity"), values.get("car")
        if not (settings.COMPANIONS and zone in self.positions and severity):
            return []
        out = []
        for c in self.companions.companions(call, car or "*", self.positions[zone], values.get("side"),
                                            severity, exclude={zone}):
            try:
                c["lines"] = self.catalog.lines(car, c["zone"], values.get("side"), severity) if car else []
            except UnknownChoice:
                c["lines"] = []
            out.append(c)
        return out

    # HumanTogglesCompanion
    def toggle_companion(self, call: str, zone: str, included: bool) -> None:
        if self.drafts.view(call)["confirmed"]:
            raise DraftClosed(call)
        if included:
            self.companions.accept(call, zone)
        else:
            self.companions.decline(call, zone)

    def view(self, call: str) -> dict:
        draft = self.drafts.view(call)
        values = {k: e["value"] for k, e in draft["fields"].items() if e["value"]}
        try:
            preview = self.catalog.lines(values.get("car", ""), values.get("zone", ""),
                                         values.get("side"), values.get("severity", ""))
        except UnknownChoice:
            preview = []
        return {
            "call": self.calls.get(call),
            "draft": draft,
            "preview": preview,
            "companions": self.suggest_companions(call, values),
            "missing": [f for f in self.required if f not in values],
            "quote": self.quotes.for_call(call),
        }


def load_zones_table() -> dict:
    path = settings.ZONES_TABLE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def merge_lines(main: list[dict], extra: list[dict]) -> list[dict]:
    seen = {l["number"] for l in main}
    out = list(main)
    for l in extra:
        if l["number"] not in seen:
            seen.add(l["number"])
            out.append(l)
    return out
