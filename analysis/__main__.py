"""python -m analysis: build/claims.csv -> app/data/zones.json + docs/data-report.md."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import core
from .report import render, summarize

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "build" / "claims.csv"
TRUTH = ROOT / "build" / "claims_truth.csv"
ZONES_JSON = ROOT / "app" / "data" / "zones.json"
REPORT = ROOT / "docs" / "data-report.md"


def main() -> None:
    started = time.perf_counter()
    if not CLAIMS.exists():
        raise SystemExit(f"{CLAIMS} not found - run `python -m datagen` first")
    claims = core.read_claims(CLAIMS)
    cases = core.build_cases(claims)
    cuts = core.tertile_cuts(cases)
    cells = core.table(cases, cuts)
    doc = core.zones_json(cells)
    ZONES_JSON.parent.mkdir(parents=True, exist_ok=True)
    ZONES_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    facts = summarize(claims, cases, cuts, cells, doc, TRUTH if TRUTH.exists() else None)
    REPORT.write_text(render(facts), encoding="utf-8", newline="\n")
    print(f"analysis: {facts['n_claims']} claims -> {facts['n_cases']} cases, {len(doc['cells'])} cells "
          f"-> {ZONES_JSON.relative_to(ROOT)}, {REPORT.relative_to(ROOT)} ({time.perf_counter() - started:.1f} s)")


if __name__ == "__main__":
    main()
