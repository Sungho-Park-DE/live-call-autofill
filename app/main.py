"""HTTP app. Wiring only: requests go to the syncs, outside services come from app.adapters."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import settings
from app.adapters import make_decider, make_speech
from app.adapters.ports import Segment
from app.modules.call_v1 import CallClosed, UnknownCall
from app.modules.catalog_v1 import UnknownChoice
from app.modules.draft_v1 import DraftClosed, MissingFields
from app.modules.quote_v1 import DuplicateQuote, EmptyQuote
from app.syncs.flow import Flow

STATIC = Path(__file__).parent / "static"
DEMO_CALLS = settings.ROOT / "demo" / "calls"


class StartBody(BaseModel):
    caller: str = "Unknown caller"


class SayBody(BaseModel):
    text: str
    final: bool = True


class FieldBody(BaseModel):
    value: str


class CompanionBody(BaseModel):
    included: bool


def load_demo_calls() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DEMO_CALLS.glob("*.json"))}


def create_app(flow: Flow | None = None, stt_name: str | None = None) -> FastAPI:
    app = FastAPI(title="call-to-quote")
    app.state.flow = flow or Flow(make_decider(settings.DECIDER))
    app.state.stt_name = stt_name or settings.STT
    app.state.tasks = set()
    demos = load_demo_calls()

    def flow_() -> Flow:
        return app.state.flow

    def guard(fn, *args):
        try:
            return fn(*args)
        except (UnknownCall, KeyError):
            raise HTTPException(404, "unknown call")
        except (CallClosed, DraftClosed, DuplicateQuote):
            raise HTTPException(409, "call already confirmed")
        except MissingFields as e:
            raise HTTPException(422, {"missing": e.fields})
        except (UnknownChoice, EmptyQuote) as e:
            raise HTTPException(422, str(e))

    @app.get("/api/meta")
    def meta():
        f = flow_()
        options = {q.key: [o.value for o in q.options] for q in f.questions()}
        return {
            "stt": app.state.stt_name,
            "decider": f.decider.name,
            "fields": [{"key": x.key, "label": x.label, "threshold": x.threshold,
                        "options": options[x.key], "required": x.key in f.required} for x in f.fields],
            "demos": [{"id": k, "title": v["title"]} for k, v in demos.items()],
        }

    @app.post("/api/calls")
    def start(body: StartBody):
        return {"id": flow_().start_call(body.caller)}

    @app.get("/api/calls/{call}")
    def view(call: str):
        return guard(flow_().view, call)

    @app.post("/api/calls/{call}/say")
    async def say(call: str, body: SayBody):
        try:
            await flow_().hear(call, Segment(body.text, body.final))
        except UnknownCall:
            raise HTTPException(404, "unknown call")
        except (CallClosed, DraftClosed):
            raise HTTPException(409, "call already confirmed")
        return flow_().view(call)

    @app.post("/api/calls/{call}/demo/{demo}")
    async def play_demo(call: str, demo: str):
        if demo not in demos:
            raise HTTPException(404, "unknown demo call")
        guard(flow_().view, call)
        task = asyncio.create_task(replay(flow_(), call, demos[demo], settings.DEMO_SPEED))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)
        return {"playing": demo}

    @app.put("/api/calls/{call}/fields/{field}")
    def set_field(call: str, field: str, body: FieldBody):
        guard(flow_().set_field, call, field, body.value)
        return flow_().view(call)

    @app.delete("/api/calls/{call}/fields/{field}")
    def release_field(call: str, field: str):
        guard(flow_().release_field, call, field)
        return flow_().view(call)

    @app.put("/api/calls/{call}/companions/{zone}")
    def toggle_companion(call: str, zone: str, body: CompanionBody):
        guard(flow_().toggle_companion, call, zone, body.included)
        return flow_().view(call)

    @app.post("/api/calls/{call}/confirm")
    def confirm(call: str):
        guard(flow_().confirm, call)
        return flow_().view(call)

    @app.get("/api/quotes")
    def quotes():
        return flow_().quotes.list()

    @app.websocket("/ws/calls/{call}/audio")
    async def audio(ws: WebSocket, call: str):
        await ws.accept()
        stt = make_speech(app.state.stt_name)
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def audio_iter() -> AsyncIterator[bytes]:
            while (chunk := await chunks.get()) is not None:
                yield chunk

        async def pump():
            async for seg in stt.stream(audio_iter()):
                try:
                    await flow_().hear(call, seg)
                except (CallClosed, DraftClosed):
                    break

        consumer = asyncio.create_task(pump())
        try:
            while True:
                msg = await ws.receive()
                if msg.get("bytes"):
                    await chunks.put(msg["bytes"])
                elif msg.get("text") == "end" or msg["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await chunks.put(None)
            await consumer

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


async def replay(flow: Flow, call: str, demo: dict, speed: float) -> None:
    """Plays a scripted call as a speech engine would: growing partials, then a final."""
    for line in demo["lines"]:
        words = line["text"].split()
        try:
            for i in range(1, len(words)):
                await flow.hear(call, Segment(" ".join(words[:i]), final=False))
                await asyncio.sleep(0.15 * speed)
            await flow.hear(call, Segment(line["text"], final=True))
        except (CallClosed, DraftClosed):
            return
        await asyncio.sleep(line.get("pause", 0.5) * speed)


app = create_app()
