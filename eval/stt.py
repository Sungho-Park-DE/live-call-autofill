"""Speech-to-text evaluation: stream a WAV file through ElevenLabsSpeech at real-time pace,
like the browser microphone does, and optionally run the result through the app's Flow.

    python -m eval tts                                  # demo calls -> recordings/<demo>.wav (ElevenLabs TTS)
    python -m eval stt recordings/2-correction.wav      # segments, latency, word error rate
    python -m eval stt recordings/2-correction.wav --decide   # + Flow with CTQ_DECIDER, checked against cases.json

WAV files must be PCM 16-bit mono 16 kHz. recordings/ is git-ignored; record your own voice
there too (e.g. reading demo/calls/2-correction.json) to test a real microphone.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import wave
from pathlib import Path

from app import settings
from app.adapters.elevenlabs import ElevenLabsSpeech
from app.adapters.ports import AUDIO_SAMPLE_RATE

RECORDINGS = settings.ROOT / "recordings"
DEMO_CALLS = settings.ROOT / "demo" / "calls"
CHUNK = AUDIO_SAMPLE_RATE * 2 // 10  # 100 ms, as the browser sends
TTS_VOICE = "JBFqnCBsd6RMkjVDRZzb"
TTS_MODEL = "eleven_multilingual_v2"


def tts(out_dir: Path = RECORDINGS, gap: float = 1.2) -> list[Path]:
    """Synthesise every demo call line by line, with silence between lines so VAD commits."""
    import httpx

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY missing in .env")
    voice = os.environ.get("ELEVENLABS_TTS_VOICE", TTS_VOICE)
    out_dir.mkdir(exist_ok=True)
    written = []
    with httpx.Client(timeout=60) as client:
        for path in sorted(DEMO_CALLS.glob("*.json")):
            demo = json.loads(path.read_text(encoding="utf-8"))
            pcm = bytearray(_silence(0.5))
            for line in demo["lines"]:
                r = client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                                params={"output_format": f"pcm_{AUDIO_SAMPLE_RATE}"},
                                headers={"xi-api-key": key}, json={"text": line["text"], "model_id": TTS_MODEL})
                if r.status_code != 200:
                    raise SystemExit(f"TTS failed {r.status_code}: {r.text[:300]}")
                pcm += r.content + _silence(gap + line.get("pause", 0.5))
            target = out_dir / f"{path.stem}.wav"
            write_wav(target, bytes(pcm))
            written.append(target)
            print(f"wrote {target.relative_to(settings.ROOT)} ({len(pcm) / 2 / AUDIO_SAMPLE_RATE:.1f}s)")
    return written


def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(seconds * AUDIO_SAMPLE_RATE)


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(AUDIO_SAMPLE_RATE)
        w.writeframes(pcm)


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, AUDIO_SAMPLE_RATE):
            raise SystemExit(f"{path}: need mono 16-bit {AUDIO_SAMPLE_RATE} Hz; convert with "
                             f"ffmpeg -i in.m4a -ac 1 -ar {AUDIO_SAMPLE_RATE} -sample_fmt s16 out.wav")
        return w.readframes(w.getnframes())


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return d[len(h)] / max(1, len(r))


async def stream_file(stt, pcm: bytes, speed: float = 1.0, on_segment=None) -> dict:
    t0 = time.perf_counter()
    audio_end = None
    events = []

    async def audio():
        nonlocal audio_end
        for i in range(0, len(pcm), CHUNK):
            yield pcm[i:i + CHUNK]
            if speed > 0:
                await asyncio.sleep(0.1 / speed)
        audio_end = time.perf_counter() - t0

    async for seg in stt.stream(audio()):
        at = time.perf_counter() - t0
        events.append((at, seg))
        if on_segment:
            await on_segment(seg)
    done = time.perf_counter() - t0
    finals = [s.text for _, s in events if s.final]
    partials = [at for at, s in events if not s.final]
    return {"events": events, "finals": finals, "audio_seconds": len(pcm) / 2 / AUDIO_SAMPLE_RATE,
            "first_partial": partials[0] if partials else None, "audio_end": audio_end,
            "last_final": max((at for at, s in events if s.final), default=None), "done": done}


async def evaluate(path: Path, speed: float = 1.0, decide: bool = False, verbose: bool = False) -> int:
    from eval.decider import load_cases

    pcm = read_wav(path)
    stt = ElevenLabsSpeech.from_env()
    demo_file = DEMO_CALLS / f"{path.stem}.json"
    reference = (" ".join(l["text"] for l in json.loads(demo_file.read_text(encoding="utf-8"))["lines"])
                 if demo_file.exists() else None)

    flow = call = None
    if decide:
        from app.adapters import make_decider
        from app.syncs.flow import Flow

        flow = Flow(make_decider(settings.DECIDER))
        call = flow.start_call("eval")

    started = time.perf_counter()

    async def on_segment(seg):
        if seg.final or verbose:
            print(f"  {time.perf_counter() - started:6.1f}s {'FINAL  ' if seg.final else 'partial'} {seg.text}")
        if flow:
            await flow.hear(call, seg)
            if seg.final:
                f = {k: (e["value"], round(e["confidence"] or 0, 2))
                     for k, e in flow.drafts.view(call)["fields"].items() if e["value"]}
                print(f"          draft: {f}")

    res = await stream_file(stt, pcm, speed, on_segment)
    out = settings.ROOT / "eval" / "results" / f"stt-{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"recording": path.stem, "config": stt.session_config, "finals": res["finals"],
                               "final_at": [round(at, 1) for at, s in res["events"] if s.final]},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved {out.relative_to(settings.ROOT)}")
    print(f"keyterms echoed by server: {stt.session_config.get('keyterms')}")
    print(f"audio {res['audio_seconds']:.1f}s, first partial at {res['first_partial'] or 0:.2f}s, "
          f"audio ended {res['audio_end'] or 0:.2f}s, last final {res['last_final'] or 0:.2f}s, stream closed {res['done']:.2f}s")
    if reference:
        print(f"WER vs {demo_file.name}: {wer(reference, ' '.join(res['finals'])):.2%}")
    if not flow:
        return 0
    problems = flow.view(call)["problems"]
    if problems:
        print(f"adapter problems during the call: {problems}")
        return 1
    got = {k: e["value"] for k, e in flow.drafts.view(call)["fields"].items() if e["value"]}
    case = next((c for c in load_cases() if path.stem in (c.get("demo"), c.get("recording"))), None)
    if not case:
        print(f"draft: {got}")
        return 0
    bad = {k: (got.get(k), v) for k, v in case["expect"].items() if got.get(k) != v}
    print(f"draft: {got}\n{'OK' if not bad else f'MISMATCH (got, want): {bad}'}")
    return 1 if bad else 0
