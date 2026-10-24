"""python -m eval {decider,tts,stt} — see eval/README.md."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decider", help="score a decider on eval/cases.json")
    d.add_argument("--decider", default="jev", choices=["jev", "fake"])
    d.add_argument("--order", action="store_true", help="also ask with options reversed (Jev only)")
    d.add_argument("--only", help="comma separated case ids")
    sub.add_parser("tts", help="synthesise demo calls into recordings/*.wav")
    s = sub.add_parser("stt", help="stream a WAV through ElevenLabs Scribe")
    s.add_argument("wav", type=Path)
    s.add_argument("--speed", type=float, default=1.0, help="1 = real time, 0 = as fast as possible")
    s.add_argument("--decide", action="store_true", help="feed segments into the Flow (CTQ_DECIDER)")
    s.add_argument("--verbose", action="store_true", help="also print every partial transcript")
    a = p.parse_args(argv)

    if a.cmd == "decider":
        from eval import decider as ev

        cases = ev.load_cases()
        if a.only:
            ids = set(a.only.split(","))
            cases = [c for c in cases if c["id"] in ids]

        async def go():
            dec = ev.make(a.decider)
            try:
                return await ev.run(dec, cases, order=a.order)
            finally:
                if hasattr(dec, "aclose"):
                    await dec.aclose()

        r = asyncio.run(go())
        print(ev.report(r))
        print(f"\nsaved {ev.save(r)}")
        return 0
    if a.cmd == "tts":
        from eval.stt import tts

        tts()
        return 0
    from eval.stt import evaluate

    return asyncio.run(evaluate(a.wav, a.speed, a.decide, a.verbose))


if __name__ == "__main__":
    sys.exit(main())
