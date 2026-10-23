import time

from fastapi.testclient import TestClient

from app import main, settings
from app.adapters.fakes import KeywordDecider
from app.syncs.flow import Flow


def client():
    return TestClient(main.create_app(Flow(KeywordDecider()), stt_name="fake"))


def test_meta_lists_fields_and_demos():
    m = client().get("/api/meta").json()
    assert [f["key"] for f in m["fields"]] == ["intent", "car", "zone", "side", "severity"]
    assert len(m["demos"]) == 3
    assert m["stt"] == "fake" and m["decider"] == "keywords"


def test_typed_lines_human_edit_confirm():
    c = client()
    call = c.post("/api/calls", json={"caller": "test"}).json()["id"]
    v = c.post(f"/api/calls/{call}/say", json={"text": "Ridge headlight quote please"}).json()
    assert v["draft"]["fields"]["car"]["value"] == "Ridge"
    assert c.post(f"/api/calls/{call}/confirm").status_code == 422  # severity missing
    c.put(f"/api/calls/{call}/fields/severity", json={"value": "minor"})
    v = c.post(f"/api/calls/{call}/confirm").json()
    assert v["quote"]["lines"][0]["number"] == "RG-HL01L"
    assert c.post(f"/api/calls/{call}/say", json={"text": "x"}).status_code == 409


def test_demo_call_replays(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_SPEED", 0.0)
    with client() as c:
        call = c.post("/api/calls", json={}).json()["id"]
        assert c.post(f"/api/calls/{call}/demo/2-correction").status_code == 200
        deadline = time.time() + 5
        while time.time() < deadline:
            v = c.get(f"/api/calls/{call}").json()
            if len(v["call"]["finals"]) == 4:
                break
            time.sleep(0.05)
        f = v["draft"]["fields"]
        assert (f["car"]["value"], f["zone"]["value"], f["side"]["value"], f["severity"]["value"]) == (
            "Vera", "front fender", "right", "moderate")


def test_audio_socket_feeds_speech_into_call():
    from app.adapters.fakes import ScriptedSpeech
    from app.adapters.ports import Segment

    app = main.create_app(Flow(KeywordDecider()), stt_name="fake")
    with TestClient(app) as c:
        call = c.post("/api/calls", json={}).json()["id"]
        import app.main as m

        original = m.make_speech
        m.make_speech = lambda name: ScriptedSpeech([Segment("Vera hood, it got smashed badly", True)])
        try:
            with c.websocket_connect(f"/ws/calls/{call}/audio") as ws:
                ws.send_bytes(b"\x00\x00" * 1600)
                ws.send_text("end")
        finally:
            m.make_speech = original
        f = c.get(f"/api/calls/{call}").json()["draft"]["fields"]
        assert f["zone"]["value"] == "hood" and f["severity"]["value"] == "severe"


def test_companion_toggle_route():
    from tests.test_flow import TABLE

    c = TestClient(main.create_app(Flow(KeywordDecider(), zones_table=TABLE), stt_name="fake"))
    call = c.post("/api/calls", json={}).json()["id"]
    c.post(f"/api/calls/{call}/say", json={"text": "Atto front bumper, it got a dent"})
    v = c.put(f"/api/calls/{call}/companions/grille", json={"included": False}).json()
    assert [(x["zone"], x["included"]) for x in v["companions"]] == [("grille", False), ("fog lamp", True)]
    assert c.put("/api/calls/nope/companions/grille", json={"included": True}).status_code == 404
