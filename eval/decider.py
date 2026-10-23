"""Decider evaluation: replays labelled calls the way the app does (one decision per final
line, on the transcript so far) and scores every field at every threshold.

    python -m eval decider                 # Jev (needs JEV_API_KEY)
    python -m eval decider --decider fake  # keyword baseline, offline
    python -m eval decider --order         # also re-ask Jev with options reversed

Scoring per field and checkpoint, at threshold t:
  right  = suggested (confidence >= t) and equals the expected value
  wrong  = suggested and differs, or suggested although nothing should be
  held   = nothing suggested (expected value missed, or correctly left empty)
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from app import settings
from app.adapters.fakes import KeywordDecider
from app.adapters.ports import Answer, Question
from app.syncs.flow import Flow

HERE = Path(__file__).parent
CASES = HERE / "cases.json"
RESULTS = HERE / "results"
THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def questions() -> list[Question]:
    return Flow(KeywordDecider(), zones_table={}).questions()


def load_cases(path: Path = CASES) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    offered = {q.key: {o.value for o in q.options} for q in questions()}
    for c in cases:
        if "demo" in c:
            demo = json.loads((settings.ROOT / "demo" / "calls" / f"{c['demo']}.json").read_text(encoding="utf-8"))
            c["lines"] = [l["text"] for l in demo["lines"]]
        checks = {len(c["lines"]): c["expect"]} | {int(k): v for k, v in c.get("after", {}).items()}
        for n, exp in checks.items():
            if not 1 <= n <= len(c["lines"]):
                raise ValueError(f"{c['id']}: checkpoint after line {n} out of range")
            for k, v in exp.items():
                if k not in offered or (v is not None and v not in offered[k]):
                    raise ValueError(f"{c['id']}: {k}={v!r} is not an offered option")
        c["checks"] = dict(sorted(checks.items()))
    return cases


@dataclass
class Run:
    decider: str
    model: str | None = None
    seconds: list[float] = field(default_factory=list)
    # (case id, after line, field) -> expected; and per confidence mode -> Answer | None
    expected: dict[tuple[str, int, str], str | None] = field(default_factory=dict)
    got: dict[str, dict[tuple[str, int, str], Answer | None]] = field(default_factory=dict)
    order_flips: list[tuple[str, str]] = field(default_factory=list)


def reversed_options(qs: Sequence[Question]) -> list[Question]:
    return [Question(q.key, q.prompt, tuple(reversed(q.options))) for q in qs]


async def run(decider, cases: list[dict], *, order: bool = False) -> Run:
    qs = questions()
    r = Run(decider=getattr(decider, "name", "?"))
    raw = hasattr(decider, "ask") and hasattr(decider, "answers")
    modes = ("probability", "jev") if raw else ("decider",)
    for m in modes:
        r.got[m] = {}
    for c in cases:
        for n in range(1, len(c["lines"]) + 1):
            transcript = " ".join(c["lines"][:n])
            t0 = time.perf_counter()
            if raw:
                resp = await decider.ask(transcript, qs)
                r.model = resp.get("model") or r.model
                per_mode = {}
                for m in modes:
                    decider.confidence = m
                    per_mode[m] = decider.answers(resp, qs)
            else:
                per_mode = {"decider": await decider.decide(transcript, qs)}
            r.seconds.append(time.perf_counter() - t0)
            if n not in c["checks"]:
                continue
            for k, exp in c["checks"][n].items():
                r.expected[(c["id"], n, k)] = exp
                for m, answers in per_mode.items():
                    r.got[m][(c["id"], n, k)] = answers.get(k)
            if order and raw and n == len(c["lines"]):
                flipped = decider.answers(await decider.ask(transcript, reversed_options(qs)), qs)
                for k in per_mode[modes[0]].keys() | flipped.keys():
                    a, b = per_mode[modes[0]].get(k), flipped.get(k)
                    if (a and a.value) != (b and b.value):
                        r.order_flips.append((c["id"], k))
    if raw:
        decider.confidence = "probability"
    return r


def score(r: Run, mode: str, t: float, key: str | None = None) -> dict[str, int]:
    s = {"right": 0, "wrong": 0, "held": 0, "held_ok": 0}
    for (cid, n, k), exp in r.expected.items():
        if key is not None and k != key:
            continue
        a = r.got[mode].get((cid, n, k))
        suggested = a is not None and a.confidence >= t
        if not suggested:
            s["held"] += 1
            s["held_ok"] += exp is None
        elif a.value == exp:
            s["right"] += 1
        else:
            s["wrong"] += 1
    return s


def mistakes(r: Run, mode: str, thresholds: dict[str, float]) -> list[str]:
    out = []
    for (cid, n, k), exp in r.expected.items():
        a = r.got[mode].get((cid, n, k))
        suggested = a is not None and a.confidence >= thresholds[k]
        if suggested and a.value != exp:
            out.append(f"  WRONG  {cid} @{n} {k}: got {a.value!r} ({a.confidence:.2f}), want {exp!r}")
        elif not suggested and exp is not None:
            got = f"{a.value!r} ({a.confidence:.2f})" if a else "nothing"
            out.append(f"  missed {cid} @{n} {k}: got {got}, want {exp!r}")
    return out


def report(r: Run) -> str:
    fields = [f.key for f in settings.FIELDS]
    thresholds = {f.key: f.threshold for f in settings.FIELDS}
    lines = [f"decider={r.decider} model={r.model} checks={len(r.expected)} calls={len(r.seconds)}"]
    if r.seconds:
        sec = sorted(r.seconds)
        lines.append(f"latency p50={statistics.median(sec)*1000:.0f}ms "
                     f"p90={sec[int(0.9 * (len(sec) - 1))]*1000:.0f}ms max={sec[-1]*1000:.0f}ms")
    for mode in r.got:
        lines.append(f"\n[{mode}] per field at settings threshold")
        lines.append(f"{'field':10} {'t':>4} {'right':>5} {'wrong':>5} {'held':>5} {'(ok)':>5}")
        for k in fields:
            s = score(r, mode, thresholds[k], k)
            lines.append(f"{k:10} {thresholds[k]:4.2f} {s['right']:5} {s['wrong']:5} {s['held']:5} {s['held_ok']:5}")
        lines.append(f"\n[{mode}] all fields by threshold (wrong share = wrong / suggested)")
        lines.append(f"{'t':>4} {'right':>5} {'wrong':>5} {'held':>5} {'wrong share':>11}")
        for t in THRESHOLDS:
            s = score(r, mode, t)
            n = s["right"] + s["wrong"]
            lines.append(f"{t:4.2f} {s['right']:5} {s['wrong']:5} {s['held']:5} {(s['wrong'] / n if n else 0):11.2f}")
        lines.append(f"\n[{mode}] mistakes at settings thresholds")
        lines += mistakes(r, mode, thresholds) or ["  none"]
    if r.order_flips:
        lines.append(f"\noption order changed the answer {len(r.order_flips)}x: {r.order_flips}")
    return "\n".join(lines)


def save(r: Run) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"decider-{r.decider}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rows = [{"case": cid, "after": n, "field": k, "expected": exp,
             **{m: (lambda a: a and {"value": a.value, "confidence": a.confidence})(r.got[m].get((cid, n, k)))
                for m in r.got}}
            for (cid, n, k), exp in r.expected.items()]
    path.write_text(json.dumps({"decider": r.decider, "model": r.model, "seconds": r.seconds,
                                "order_flips": r.order_flips, "rows": rows}, indent=1), encoding="utf-8")
    return path


def make(name: str):
    if name == "fake":
        return KeywordDecider()
    from app.adapters.jev import JevDecider

    return JevDecider.from_env()
