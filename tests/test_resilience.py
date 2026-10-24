import asyncio

from fastapi.testclient import TestClient

from app import main
from app.adapters.fakes import KeywordDecider
from app.adapters.ports import Answer, DeciderError, Segment, SpeechError
from app.syncs.flow import Flow


def run(coro):
    return asyncio.run(coro)


def values(flow, call):
    return {k: e["value"] for k, e in flow.drafts.view(call)["fields"].items()}


class Counting:
    """Wraps another decider and records the transcripts it was asked about."""

    def __init__(self, inner=None):
        self.inner = inner or KeywordDecider()
        self.name = self.inner.name
        self.asked = []

    async def decide(self, transcript, questions):
        self.asked.append(transcript)
        return await self.inner.decide(transcript, questions)


class Flaky:
    name = "flaky"

    def __init__(self, fail_on):
        self.fail_on = set(fail_on)
        self.n = 0
        self.inner = KeywordDecider()

    async def decide(self, transcript, questions):
        self.n += 1
        if self.n in self.fail_on:
            raise DeciderError("service unavailable")
        return await self.inner.decide(transcript, questions)


class Scripted:
    name = "scripted"

    def __init__(self, answers):
        self.answers = list(answers)

    async def decide(self, transcript, questions):
        return self.answers.pop(0)


def test_decider_error_keeps_the_draft_and_clears_on_the_next_success():
    flow = Flow(Flaky(fail_on=[2]))
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("It's an Atto SUV.", final=True)))
    run(flow.hear(call, Segment("The front bumper is scratched.", final=True)))  # decider fails here
    assert values(flow, call)["car"] == "Atto"
    assert "zone" not in {k for k, v in values(flow, call).items() if v}
    assert flow.view(call)["problems"] == {"decider": "service unavailable"}
    run(flow.hear(call, Segment("A little.", final=True)))
    v = flow.view(call)
    assert v["problems"] == {}
    assert values(flow, call)["zone"] == "front bumper"


def test_say_route_survives_a_decider_error():
    c = TestClient(main.create_app(Flow(Flaky(fail_on=[1])), stt_name="fake"))
    call = c.post("/api/calls", json={}).json()["id"]
    r = c.post(f"/api/calls/{call}/say", json={"text": "Ridge headlight please"})
    assert r.status_code == 200
    assert r.json()["problems"] == {"decider": "service unavailable"}
    r = c.post(f"/api/calls/{call}/say", json={"text": "Ridge headlight please, it is smashed"})
    assert r.json()["problems"] == {} and r.json()["draft"]["fields"]["car"]["value"] == "Ridge"


def test_speech_error_is_reported_and_the_call_stays_open(monkeypatch):
    class Failing:
        name = "failing"

        async def stream(self, audio):
            raise SpeechError("connection lost")
            yield  # pragma: no cover

    monkeypatch.setattr(main, "make_speech", lambda name: Failing())
    with TestClient(main.create_app(Flow(KeywordDecider()), stt_name="fake")) as c:
        call = c.post("/api/calls", json={}).json()["id"]
        with c.websocket_connect(f"/ws/calls/{call}/audio") as ws:
            ws.send_bytes(b"\x00\x00" * 1600)
            msg = ws.receive_json()
        assert msg == {"type": "error", "source": "speech", "message": "connection lost"}
        v = c.get(f"/api/calls/{call}").json()
        assert v["problems"] == {"speech": "connection lost"} and not v["call"]["ended"]
        v = c.post(f"/api/calls/{call}/say", json={"text": "Atto bumper"}).json()
        assert v["draft"]["fields"]["car"]["value"] == "Atto"


def test_partial_decisions_are_throttled_and_the_last_partial_is_decided_after_a_pause():
    async def scenario():
        dec = Counting()
        flow = Flow(dec, partial_secs=0.05)
        call = flow.start_call("demo")
        words = "I need a fender for a Vera".split()
        for i in range(1, len(words) + 1):
            await flow.hear(call, Segment(" ".join(words[:i]), final=False))
        assert len(dec.asked) == 1  # the first partial decided at once, the rest wait
        await asyncio.sleep(0.2)
        return dec, flow, call

    dec, flow, call = run(scenario())
    assert len(dec.asked) == 2 and dec.asked[-1] == "I need a fender for a Vera"
    assert values(flow, call)["car"] == "Vera"


def test_final_after_the_same_words_does_not_decide_again():
    async def scenario():
        dec = Counting()
        flow = Flow(dec, partial_secs=0.05)
        call = flow.start_call("demo")
        await flow.hear(call, Segment("Atto front", final=False))
        await flow.hear(call, Segment("Atto front bumper", final=False))  # waits for the pause
        await flow.hear(call, Segment("Atto front bumper.", final=True))
        asked_after_final = len(dec.asked)
        await asyncio.sleep(0.2)
        return dec, asked_after_final

    dec, asked_after_final = run(scenario())
    assert asked_after_final == 2 and len(dec.asked) == 2


def test_older_answer_that_returns_late_is_dropped():
    async def scenario():
        gate = asyncio.Event()

        class Slow:
            name = "slow"

            def __init__(self):
                self.n = 0

            async def decide(self, transcript, questions):
                self.n += 1
                if self.n == 1:
                    await gate.wait()
                    return {"car": Answer("Atto", 0.95)}
                return {"car": Answer("Vera", 0.95)}

        flow = Flow(Slow(), partial_secs=0.05)
        call = flow.start_call("demo")
        first = asyncio.create_task(flow.hear(call, Segment("Atto", final=False)))
        await asyncio.sleep(0.01)
        await flow.hear(call, Segment("No, a Vera.", final=True))
        gate.set()
        await first
        return values(flow, call)

    assert run(scenario())["car"] == "Vera"


def test_older_partial_answer_that_returns_after_a_newer_one_is_dropped():
    async def scenario():
        gate = asyncio.Event()

        class Slow:
            name = "slow"

            def __init__(self):
                self.n = 0

            async def decide(self, transcript, questions):
                self.n += 1
                if self.n == 1:
                    await gate.wait()
                    return {"car": Answer("Atto", 0.95)}
                return {"car": Answer("Vera", 0.95)}

        flow = Flow(Slow(), partial_secs=0.05)
        call = flow.start_call("demo")
        first = asyncio.create_task(flow.hear(call, Segment("Atto", final=False)))
        await asyncio.sleep(0.01)
        await flow.hear(call, Segment("No, a Vera", final=False))  # waits for the pause, then decides
        await asyncio.sleep(0.2)
        assert values(flow, call)["car"] == "Vera"
        gate.set()
        await first
        return values(flow, call)

    assert run(scenario())["car"] == "Vera"


def test_zero_seconds_means_finals_only():
    async def scenario():
        dec = Counting()
        flow = Flow(dec, partial_secs=0)
        call = flow.start_call("demo")
        await flow.hear(call, Segment("Atto front bum", final=False))
        await asyncio.sleep(0.05)
        return dec

    assert run(scenario()).asked == []


def test_open_questions_list_what_is_still_empty_required_first():
    flow = Flow(KeywordDecider())
    call = flow.start_call("demo")
    assert [q["key"] for q in flow.view(call)["ask"]] == ["car", "zone", "severity", "intent", "side"]
    run(flow.hear(call, Segment("A quote for the Atto front bumper please", final=True)))
    ask = {q["key"]: q for q in flow.view(call)["ask"]}
    assert set(ask) == {"severity", "side"} and ask["side"]["question"] == "Which side?"
    flow.set_field(call, "side", "left")
    assert [q["key"] for q in flow.view(call)["ask"]] == ["severity"]


def test_open_question_shows_what_was_heard_below_the_threshold():
    flow = Flow(Scripted([{"zone": Answer("headlamp", 0.51)}]))
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("something with the light", final=True)))
    zone = next(q for q in flow.view(call)["ask"] if q["key"] == "zone")
    assert zone["maybe"] == "headlamp" and zone["confidence"] == 0.51


def test_nothing_is_asked_for_a_call_without_a_quote_or_after_confirm():
    flow = Flow(Scripted([{"intent": Answer("other", 0.9)}]))
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("Where is my order?", final=True)))
    assert flow.view(call)["ask"] == []

    flow = Flow(KeywordDecider(), zones_table={})
    call = flow.start_call("demo")
    run(flow.hear(call, Segment("Atto front bumper, a little scratched", final=True)))
    flow.confirm(call)
    assert flow.view(call)["ask"] == []


def test_warm_calls_the_decider_when_it_can_and_never_raises():
    async def scenario():
        class Warmable:
            name = "w"
            warmed = 0

            async def warm(self):
                self.warmed += 1

            async def decide(self, transcript, questions):
                return {}

        class Broken(Warmable):
            async def warm(self):
                raise RuntimeError("network down")

        ok = Warmable()
        await Flow(ok).warm()
        await Flow(Broken()).warm()
        await Flow(KeywordDecider()).warm()
        return ok.warmed

    assert run(scenario()) == 1


def test_start_route_warms_the_decider():
    seen = []

    class Warmable(KeywordDecider):
        async def warm(self):
            seen.append(1)

    with TestClient(main.create_app(Flow(Warmable()), stt_name="fake")) as c:
        c.post("/api/calls", json={})
    assert seen == [1]
