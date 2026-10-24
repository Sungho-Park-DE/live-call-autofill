"""Offline tests for the real adapters: fake HTTP and a fake WebSocket, no keys, no network."""
import asyncio
import json

import httpx
import pytest

from app.adapters.elevenlabs import ElevenLabsError, ElevenLabsSpeech
from app.adapters.jev import NOT_SAID, JevDecider, JevError
from app.adapters.ports import Option, Question, Segment

SIDE = Question("side", "Which side of the car?", (Option("left", "driver side"), Option("right", "passenger side")))
CAR = Question("car", "Which car model?", (Option("Atto"), Option("Vera")))


def jev(handler, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JevDecider("test-key", client=client, **kw)


def choice(value, probs, confidence=0.5):
    return {"type": "choice", "choice": value, "confidence": confidence, "probabilities": probs}


def test_jev_request_shape_and_answers():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "jev-x", "answers": {
            "side": choice("right", {"left": 0.1, "right": 0.85, NOT_SAID: 0.05}, 0.7),
            "car": choice(NOT_SAID, {"Atto": 0.2, "Vera": 0.1, NOT_SAID: 0.7}),
        }})

    d = jev(handler)
    got = asyncio.run(d.decide("left... no, the passenger side", [SIDE, CAR]))
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["state"] == {"call_transcript": "left... no, the passenger side"}
    side = body["questions"]["side"]
    assert side["type"] == "choice"
    assert list(side["criteria"]) == ["left", "right", NOT_SAID]
    assert side["criteria"]["left"] == "Callers may also say: driver side"
    assert body["questions"]["car"]["criteria"]["Atto"] is None
    assert got == {"side": got["side"]} and got["side"].value == "right"
    assert got["side"].confidence == pytest.approx(0.85)
    assert d.last["model"] == "jev-x"


def test_jev_confidence_mode_and_unknown_choice_dropped():
    def handler(request):
        return httpx.Response(200, json={"answers": {
            "side": choice("left", {"left": 0.9, "right": 0.1}, 0.8),
            "car": choice("Zeta", {"Zeta": 1.0}),
        }})

    got = asyncio.run(jev(handler, confidence="jev", abstain=False).decide("x", [SIDE, CAR]))
    assert set(got) == {"side"} and got["side"].confidence == pytest.approx(0.8)


def test_jev_retries_overload_then_fails_clearly():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(529, json={"error": "overloaded"})

    d = jev(handler, retries=1)
    with pytest.raises(JevError, match="529"):
        asyncio.run(d.decide("x", [SIDE]))
    assert len(calls) == 2


def test_jev_bad_key_no_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401)

    with pytest.raises(JevError, match="401"):
        asyncio.run(jev(handler).decide("x", [SIDE]))
    assert len(calls) == 1


def test_jev_empty_transcript_makes_no_call():
    def handler(request):
        raise AssertionError("no call expected")

    assert asyncio.run(jev(handler).decide("  ", [SIDE])) == {}


def test_from_env_needs_keys(monkeypatch):
    for k in ("JEV_API_KEY", "TYPESAFE_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="JEV_API_KEY"):
        JevDecider.from_env()
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        ElevenLabsSpeech.from_env()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setenv("ELEVENLABS_KEYTERMS", "Atto, Vera,")
    s = ElevenLabsSpeech.from_env()
    assert s.keyterms == ("Atto", "Vera") and s.language == "en"


class FakeWS:
    """Replies to audio with scripted server messages; the script is keyed by audio chunk count."""

    def __init__(self, script, close_after_commit=True):
        self.script = script  # {n_chunks_seen: [messages]}, "commit": [messages]
        self.sent = []
        self.inbox = asyncio.Queue()
        self.close_after_commit = close_after_commit
        self.url = self.headers = None

    async def __aenter__(self):
        await self.inbox.put({"message_type": "session_started", "session_id": "s", "config": {"language_code": "en"}})
        return self

    async def __aexit__(self, *exc):
        await self.inbox.put(None)

    async def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        key = "commit" if msg["commit"] else len(self.sent)
        for m in self.script.get(key, []):
            await self.inbox.put(m)
        if msg["commit"] and self.close_after_commit:
            await self.inbox.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        m = await self.inbox.get()
        if m is None:
            raise StopAsyncIteration
        return json.dumps(m)


def speech(ws, **kw):
    def connect(url, headers):
        ws.url, ws.headers = url, headers
        return ws

    return ElevenLabsSpeech("el-key", connect=connect, end_quiet=0.2, **kw)


async def collect(s, chunks):
    async def audio():
        for c in chunks:
            yield c
            await asyncio.sleep(0.01)

    return [seg async for seg in s.stream(audio())]


def test_elevenlabs_partials_finals_and_final_commit():
    ws = FakeWS({
        1: [{"message_type": "partial_transcript", "text": "Left"}],
        2: [{"message_type": "partial_transcript", "text": ""},  # keepalive / nothing yet: skipped
            {"message_type": "committed_transcript", "text": "Left side."}],
        "commit": [{"message_type": "committed_transcript", "text": "No, the right one."}],
    })
    s = speech(ws, keyterms=["Atto", "Vera"])
    segs = asyncio.run(collect(s, [b"\x00\x01" * 1600, b"\x00\x00" * 1600]))
    assert segs == [Segment("Left", False), Segment("Left side.", True), Segment("No, the right one.", True)]
    assert ws.headers == {"xi-api-key": "el-key"}
    assert "model_id=scribe_v2_realtime" in ws.url and "language_code=en" in ws.url
    assert "audio_format=pcm_16000" in ws.url and "commit_strategy=vad" in ws.url
    assert "keyterms=Atto&keyterms=Vera" in ws.url
    first = ws.sent[0]
    assert first["message_type"] == "input_audio_chunk" and first["sample_rate"] == 16000
    assert first["commit"] is False and first["audio_base_64"]
    assert ws.sent[-1]["commit"] is True and ws.sent[-1]["audio_base_64"] == ""
    assert s.session_config == {"language_code": "en"}


def test_elevenlabs_stops_after_quiet_when_server_stays_open():
    ws = FakeWS({"commit": [{"message_type": "committed_transcript", "text": "Bye."}]}, close_after_commit=False)
    segs = asyncio.run(asyncio.wait_for(collect(speech(ws), [b"\x00\x00" * 160]), 3))
    assert segs == [Segment("Bye.", True)]


def test_eval_harness_runs_offline_with_keyword_baseline():
    from eval import decider as ev
    from eval.stt import wer

    cases = ev.load_cases()  # also validates that every expected value is an offered option
    r = asyncio.run(ev.run(ev.make("fake"), [c for c in cases if c["id"] == "demo-2-correction"]))
    assert ev.score(r, "decider", 0.6, "side") == {"right": 3, "wrong": 0, "held": 0, "held_ok": 0}
    assert "latency" in ev.report(r)
    assert wer("Left side, no right.", "left side no light") == 0.25


def test_sonnet_comparison_decider_request_and_answers():
    from eval.sonnet import SonnetDecider

    seen = {}

    def handler(request):
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "claude-x", "content": [
            {"type": "text", "text": json.dumps({"side": "right", "car": NOT_SAID})}]})

    d = SonnetDecider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    got = asyncio.run(d.decide("left... no, the passenger side", [SIDE, CAR]))
    schema = seen["body"]["output_config"]["format"]["schema"]
    assert seen["key"] == "k" and schema["additionalProperties"] is False
    side = schema["properties"]["side"]
    assert side["enum"] == ["left", "right", NOT_SAID] and "driver side" in side["description"]
    assert set(got) == {"side"} and got["side"].value == "right" and d.last["model"] == "claude-x"


def test_elevenlabs_error_message_raises_and_harmless_ones_do_not():
    ws = FakeWS({1: [{"message_type": "insufficient_audio_activity", "error": "quiet"},
                     {"message_type": "auth_error", "error": "invalid key"}]})
    with pytest.raises(ElevenLabsError, match="auth_error"):
        asyncio.run(collect(speech(ws), [b"\x00\x00" * 160]))
