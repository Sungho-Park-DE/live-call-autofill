"""Syncs from docs/concepts/syncs.md. One method per sync; concepts meet only here."""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import time
from typing import Callable, Sequence

from app import settings
from app.adapters.ports import Answer, Decider, DeciderError, Option, Question, Segment
from app.modules.accident_v1 import Companions
from app.modules.call_v1 import CallBook, CallClosed
from app.modules.catalog_v1 import Catalog, UnknownChoice
from app.modules.draft_v1 import DraftClosed, Drafts, MissingFields
from app.modules.quote_v1 import Quotes


log = logging.getLogger(__name__)


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


class Flow:
    def __init__(self, decider: Decider, fields: Sequence[settings.Field] = settings.FIELDS,
                 required: Sequence[str] = settings.REQUIRED, zones_table: dict | None = None,
                 partial_secs: float | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.decider = decider
        self.partial_secs = settings.PARTIAL_DECIDE_SECS if partial_secs is None else partial_secs
        self._clock = clock
        self._seq = itertools.count(1)
        self._applied: dict[str, int] = {}  # call -> sequence number of the newest answer that was used
        self._decided: dict[str, str] = {}  # call -> words of the transcript behind that answer
        self._started: dict[str, float] = {}  # call -> clock time of the newest decider request
        self._trailing: dict[str, asyncio.Task] = {}
        self._unsure: dict[str, dict[str, Answer]] = {}
        self._problems: dict[str, dict[str, str]] = {}
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

    # SpeechIntoCall (+ DecideOnFinalSegment when final, DecideOnPartialSegment when partial)
    async def hear(self, call: str, segment: Segment) -> None:
        version = self.calls.hear(call, segment.text, segment.final)
        if segment.final:
            await self.decide(call, version)
        elif self.partial_secs > 0:
            await self._decide_on_partial(call, version)

    async def _decide_on_partial(self, call: str, version: int) -> None:
        wait = self._started.get(call, float("-inf")) + self.partial_secs - self._clock()
        if wait <= 0:
            await self.decide(call, version)
            return
        task = self._trailing.get(call)
        if task is None or task.done():  # speech may stop here: one later decision covers the newest partial
            self._trailing[call] = asyncio.create_task(self._decide_later(call, wait))

    async def _decide_later(self, call: str, wait: float) -> None:
        try:
            await asyncio.sleep(wait)
            self._trailing.pop(call, None)
            await self.decide(call, self.calls.version(call))
        except (CallClosed, DraftClosed):
            pass
        except Exception:
            log.exception("decision after a pause failed")

    def questions(self) -> list[Question]:
        catalog = self.catalog.options()
        out = []
        for f in self.fields:
            opts = f.options or tuple((o["value"], o["hint"]) for o in catalog[f.key])
            out.append(Question(f.key, f.prompt, tuple(Option(v, h) for v, h in opts)))
        return out

    # DecideOnFinalSegment / DecideOnPartialSegment -> SuggestConfidentAnswer / RetractUnsureAnswer
    async def decide(self, call: str, version: int) -> None:
        transcript = self.calls.transcript(call)
        if _words(transcript) == self._decided.get(call) or self._confirmed(call):
            return  # nothing new was said since the last answer, or the person already confirmed
        seq = next(self._seq)
        self._started[call] = self._clock()
        try:
            answers = await self.decider.decide(transcript, self.questions())
        except DeciderError as e:  # ReportAdapterProblem: the draft keeps what it has, the call goes on
            log.warning("decider %s failed for %s: %s", self.decider.name, call, e)
            self._problems.setdefault(call, {})["decider"] = str(e)
            return
        self.clear_problem(call, "decider")
        if self.calls.version(call) != version or seq < self._applied.get(call, 0) or self._confirmed(call):
            return  # a newer final arrived, a newer answer was already used, or the person confirmed
        self._applied[call] = seq
        self._decided[call] = _words(transcript)
        unsure: dict[str, Answer] = {}
        for f in self.fields:
            a = answers.get(f.key)
            if a is not None and a.confidence >= f.threshold:
                self.drafts.suggest(call, f.key, a.value, a.confidence, self.decider.name)
            else:
                self.drafts.retract(call, f.key)
                if a is not None:
                    unsure[f.key] = a
        self._unsure[call] = unsure

    def _confirmed(self, call: str) -> bool:
        return self.drafts.view(call)["confirmed"]

    # ReportAdapterProblem
    def report_problem(self, call: str, source: str, message: str) -> None:
        self._problems.setdefault(call, {})[source] = message

    def clear_problem(self, call: str, source: str) -> None:
        self._problems.get(call, {}).pop(source, None)

    # WarmDeciderOnCallStart
    async def warm(self) -> None:
        warm = getattr(self.decider, "warm", None)
        if warm is None:
            return
        try:
            await warm()
        except Exception:
            log.debug("decider warm-up failed", exc_info=True)

    # ListOpenQuestions (computed on every view, nothing stored)
    def open_questions(self, call: str, values: dict[str, str], confirmed: bool) -> list[dict]:
        if confirmed or values.get("intent") == settings.NO_QUOTE_INTENT:
            return []
        unsure = self._unsure.get(call, {})
        out = []
        for f in sorted(self.fields, key=lambda f: f.key not in self.required):
            if f.key in values or not f.ask:
                continue
            maybe = unsure.get(f.key)
            out.append({"key": f.key, "label": f.label, "question": f.ask,
                        "maybe": maybe.value if maybe else None,
                        "confidence": maybe.confidence if maybe else None})
        return out

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
            "ask": self.open_questions(call, values, draft["confirmed"]),
            "problems": dict(self._problems.get(call, {})),
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
