"""Numbers for docs/data-report.md and the Markdown itself."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from . import core


def _backtests(claims: list[core.Claim]) -> tuple[list[dict], int, int]:
    merged = core.build_cases(claims)
    unmerged = core.build_cases(claims, merge_days=None)
    kept = core.build_cases(claims, drop_consumables=False)
    train_m, test_m = core.split(merged)
    train_u, test_u = core.split(unmerged)
    train_k, test_k = core.split(kept)
    rows = []
    for key, label, train, test, note in (
        ("ship", "merge 30 d + drop consumables (shipped)", train_m, test_m, "merged cases"),
        ("nomerge", "no merge (every claim its own case)", train_u, test_m, "merged cases"),
        ("own", "no merge, judged on its own claims", train_u, test_u, "single claims"),
        ("kept", "merge, consumables counted as lines", train_k, test_k, "merged cases"),
    ):
        for threshold in (core.THRESHOLD, 0.50):
            s = core.backtest(train, test, threshold)
            rows.append({"key": key, "variant": label, "threshold": threshold, "eval": note, "cases": s.cases,
                         "precision": s.precision, "recall": s.recall, "predicted": s.predicted,
                         "tp": s.tp, "actual": s.actual, "fallback": s.fallback, "no_cell": s.no_cell})
    s = core.backtest(train_m, test_m, baseline=True)
    rows.append({"key": "baseline", "variant": "baseline: every zone of the case's position", "threshold": None, "eval": "merged cases",
                 "cases": s.cases, "precision": s.precision, "recall": s.recall, "predicted": s.predicted,
                 "tp": s.tp, "actual": s.actual, "fallback": 0, "no_cell": 0})
    return rows, len(train_m), len(test_m)


def _truth(path: Path, cases: list[core.Case]) -> dict:
    with path.open(newline="", encoding="utf-8") as fh:
        accident = {r["claim_no"]: r["accident_id"] for r in csv.DictReader(fh)}
    wrong = sum(1 for c in cases if len({accident[n] for n in c.claim_nos}) > 1)
    seen: dict[str, set[int]] = {}
    for i, c in enumerate(cases):
        for n in c.claim_nos:
            seen.setdefault(accident[n], set()).add(i)
    split = sum(1 for ids in seen.values() if len(ids) > 1)
    return {"accidents": len(set(accident.values())), "wrong_merges": wrong, "split_accidents": split,
            "multi_claim_accidents": sum(1 for k in Counter(accident.values()).values() if k > 1)}


def summarize(claims, cases, cuts, cells, doc, truth_path) -> dict:
    lay = core.layout()
    lines = [ln for c in claims for ln in c.lines]
    unmapped = [ln for ln in lines if ln[0] not in lay.zone_of]
    multi = [c for c in cases if len(c.claim_nos) > 1]
    by_no = {c.claim_no: c for c in claims}
    cross_shop = sum(1 for c in multi if len({by_no[n].shop for n in c.claim_nos}) > 1)
    usable = [c for c in cases if c.position]
    new_zone = sum(1 for c in multi
                   if set(c.zones) - {lay.zone_of[ln[0]] for ln in by_no[c.claim_nos[0]].lines if ln[0] in lay.zone_of})
    backtests, n_train, n_test = _backtests(claims)
    model_cells = [c for c in doc["cells"] if c["model"] != core.ALL]
    return {
        "n_claims": len(claims), "n_vehicles": len({c.vehicle for c in claims}),
        "n_shops": len({c.shop for c in claims}), "first": min(c.day for c in claims),
        "last": max(c.day for c in claims),
        "n_lines": len(lines), "n_part_lines": len(lines) - len(unmapped), "n_unmapped": len(unmapped),
        "unmapped_marked_part": sum(1 for ln in unmapped if ln[3] == "part"),
        "unmapped_numbers": Counter(ln[0] for ln in unmapped).most_common(),
        "n_cases": len(cases), "n_multi": len(multi), "cross_shop": cross_shop, "new_zone": new_zone,
        "n_no_parts": len(cases) - len(usable),
        "positions": Counter(c.position for c in usable), "sides": Counter(c.side for c in usable),
        "models": Counter(c.model for c in usable),
        "severities": Counter((c.position, core.severity(c, cuts)) for c in usable),
        "cuts": cuts,
        "n_cells": len(doc["cells"]), "n_model_cells": len(model_cells),
        "n_fallback": sum(1 for c in model_cells if c["scope"] == "all"),
        "fallback_by_model": Counter(c["model"] for c in model_cells if c["scope"] == "all"),
        "model_cells_by_model": Counter(c["model"] for c in model_cells),
        "n_all_cells": len(doc["cells"]) - len(model_cells),
        "small_all_cells": [c for c in doc["cells"] if c["model"] == core.ALL and c["n"] < core.MIN_N],
        "empty_cells": sum(1 for c in doc["cells"] if not c["zones"]),
        "doc": doc, "backtests": backtests, "n_train": n_train, "n_test": n_test,
        "truth": _truth(truth_path, cases) if truth_path else None,
    }


def _pct(x: float) -> str:
    return f"{x:.2f}"


def _cell_table(doc: dict, model: str, position: str) -> list[str]:
    out = ["| side | severity | n | scope | companion zones (share) |", "|---|---|---:|---|---|"]
    for c in doc["cells"]:
        if c["model"] == model and c["position"] == position:
            zs = ", ".join(f"{z['zone']} {z['share']:.2f}" for z in c["zones"]) or "-"
            out.append(f"| {c['side']} | {c['severity']} | {c['n']} | {c['scope']} | {zs} |")
    return out


def render(f: dict) -> str:
    t = f["truth"]
    cuts = f["cuts"]
    lay = core.layout()
    md = [
        "# Data report: companion zones from invented claims",
        "",
        "Generated by `python -m analysis` from `build/claims.csv` (written by `python -m datagen`). "
        "Every car, shop, vehicle, claim and part number here is invented.",
        "",
        "## What this re-tells",
        "",
        "A parts dealer turned five years of accident-repair sales into quote logic: when a caller says "
        "\"front bumper\", which other zones usually come with it? This repo re-tells that with invented data. "
        "The generator (`datagen/generate.py`) encodes only mechanisms - impact face, point, width and depth; "
        "zones at invented distances and layers; damage fading with distance and layer; per-part min severity "
        "from the catalog; repair instead of replacement; hidden damage found after disassembly; consumables. "
        "It contains no co-occurrence rates. The shares below fall out of those mechanisms, which is the "
        "point of the exercise *and* its weakest spot (see Caveats).",
        "",
        "## Settings",
        "",
        f"| constant | value |", "|---|---|",
        f"| `THRESHOLD` (zone joins a cell) | {core.THRESHOLD} |",
        f"| `MIN_N` (model cell smaller -> all-models cell) | {core.MIN_N} |",
        f"| `MERGE_DAYS` (same vehicle, after the case's first claim) | {core.MERGE_DAYS} |",
        f"| `TEST_FROM` (backtest split) | {core.TEST_FROM.isoformat()} |",
        "",
        "## From claims to cases",
        "",
        "| step | count |", "|---|---:|",
        f"| claims ({f['first']} .. {f['last']}, {f['n_shops']} shops, {f['n_vehicles']} vehicles) | {f['n_claims']} |",
        f"| claim lines | {f['n_lines']} |",
        f"| lines mapped to a catalog zone (kept) | {f['n_part_lines']} |",
        f"| lines not in the catalog (consumables, dropped) | {f['n_unmapped']} |",
        f"| ...of which the dealer's article group still said `part` | {f['unmapped_marked_part']} |",
        f"| cases after merging claims of one vehicle within {core.MERGE_DAYS} days | {f['n_cases']} |",
        f"| ...cases built from more than one claim (supplements) | {f['n_multi']} |",
        f"| ...of which the claims came from different shops | {f['cross_shop']} |",
        f"| ...where a later claim adds a zone the first claim did not have | {f['new_zone']} |",
        f"| cases without any catalog part (repair only), not used | {f['n_no_parts']} |",
        f"| cases used | {f['n_cases'] - f['n_no_parts']} |",
        "",
        "Consumables are recognised by *not* mapping to a catalog zone (number -> zone map built from "
        "`Catalog.lines(car, zone, None, \"severe\")` for every car and zone), not by the article group, "
        "which is wrong now and then. Dropped numbers: "
        + ", ".join(f"`{n}` ({k})" for n, k in f["unmapped_numbers"]) + ".",
        "",
    ]
    if t:
        md += [
            "Merge check against the generator's ground truth (`build/claims_truth.csv`, never used by the analysis itself):",
            "",
            "| check | count |", "|---|---:|",
            f"| accidents | {t['accidents']} |",
            f"| accidents with a supplement claim | {t['multi_claim_accidents']} |",
            f"| accidents split over more than one case (missed merges) | {t['split_accidents']} |",
            f"| cases that wrongly glue two unrelated accidents together | {t['wrong_merges']} |",
            "",
        ]
    md += [
        "## Case features",
        "",
        "- position = position with the most lines (ties: front, rear, side); side = from the `L`/`R` suffix of "
        "sided parts (`both` when both appear, `none` when no sided part was replaced).",
        "- severity = tertile of the case's line count within its position: "
        + "; ".join(f"{p}: minor <= {lo}, moderate <= {hi}, severe > {hi} lines" for p, (lo, hi) in sorted(cuts.items()))
        + ". Ties make the thirds uneven.",
        "",
        "| position | cases | minor | moderate | severe |", "|---|---:|---:|---:|---:|",
    ]
    for p in lay.positions:
        md.append(f"| {p} | {f['positions'][p]} | " + " | ".join(str(f['severities'][(p, s)]) for s in core.SEVERITIES) + " |")
    md += [
        "",
        "| side | cases |  | model | cases |", "|---|---:|---|---|---:|",
    ]
    models = lay.models
    for i, s in enumerate(core.SIDES):
        m = models[i] if i < len(models) else ""
        md.append(f"| {s} | {f['sides'][s]} |  | {m} | {f['models'][m] if m else ''} |")
    md += [
        "",
        "## The table (`app/data/zones.json`)",
        "",
        f"- {f['n_cells']} cells: {f['n_model_cells']} model cells and {f['n_all_cells']} all-models (`*`) cells.",
        f"- {f['n_fallback']} model cells have fewer than {core.MIN_N} cases and use the all-models cell "
        "(`scope: all`, `n` = all-models n): "
        + ", ".join(f"{m} {f['fallback_by_model'][m]} of {f['model_cells_by_model'][m]}" for m in models) + ".",
        f"- {len(f['small_all_cells'])} all-models cells are themselves below {core.MIN_N} cases and are shipped as they are: "
        + (", ".join(f"{c['position']}/{c['side']}/{c['severity']} (n={c['n']})" for c in f["small_all_cells"]) or "none") + ".",
        f"- {f['empty_cells']} cells have no zone at or above {core.THRESHOLD}.",
        "- A cell exists only where data exists. Some combinations never occur (e.g. front/none/moderate: a moderate "
        "front hit always breaks some sided part), so the app needs its own fallback for those.",
        "",
        "All-models cells, front:",
        "",
        *_cell_table(f["doc"], core.ALL, "front"),
        "",
        "All-models cells, rear:",
        "",
        *_cell_table(f["doc"], core.ALL, "rear"),
        "",
        "All-models cells, side:",
        "",
        *_cell_table(f["doc"], core.ALL, "side"),
        "",
        "## Backtest",
        "",
        f"Time split: train on cases starting before {core.TEST_FROM} ({f['n_train']} cases), test on the rest "
        f"({f['n_test']} cases). For each test case the anchor zone (most lines, ties in catalog order) stands in for "
        "what the caller said; the trained table predicts the companion zones (anchor excluded), compared with the "
        "case's other zones. Micro-averaged over all test cases.",
        "",
        "| variant | threshold | judged on | cases | predicted | correct | actual | precision | recall | fallback cells |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in f["backtests"]:
        th = f"{r['threshold']:.2f}" if r["threshold"] is not None else "-"
        md.append(f"| {r['variant']} | {th} | {r['eval']} | {r['cases']} | {r['predicted']} | {r['tp']} | {r['actual']} "
                  f"| {_pct(r['precision'])} | {_pct(r['recall'])} | {r['fallback']} |")
    bt = {(r["key"], r["threshold"]): r for r in f["backtests"]}
    ship3, ship5 = bt[("ship", core.THRESHOLD)], bt[("ship", 0.50)]
    nom3, own3, kep3 = bt[("nomerge", core.THRESHOLD)], bt[("own", core.THRESHOLD)], bt[("kept", core.THRESHOLD)]

    def pr(r):
        return f"{_pct(r['precision'])} / {_pct(r['recall'])}"

    md += [
        "",
        "Reading it (precision / recall):",
        "",
        f"- **Threshold.** 0.30 gives {pr(ship3)}, 0.50 gives {pr(ship5)}: the lower threshold adds more companions, "
        "catching more of what the shop will need at the cost of lines that get deleted again. The app ships 0.30 "
        "because removing a line is easier than adding one.",
        f"- **Merge.** Training on single claims instead of merged cases gives {pr(nom3)} against the same merged test "
        f"cases ({pr(ship3)} with the merge). Judged on its own single claims it gives {pr(own3)}. The difference is "
        f"small here because a supplement mostly adds hidden parts of zones already on the first claim: only "
        f"{f['new_zone']} of {f['n_multi']} merged cases gain a zone from a later claim.",
        f"- **Consumables.** Counting them as lines gives {pr(kep3)}. They never map to a zone, so they only move "
        "the severity thirds (and with them which cell a case lands in).",
        "",
        "## Caveats",
        "",
        "- **Circular by construction.** We wrote the generator, so the analysis can only find what its mechanisms "
        "imply. The guard is that the generator holds no target shares, only geometry and rules; but the numbers "
        "say nothing about real cars. What the exercise shows is that the pipeline (merge, consumables, cells, "
        "fallback, backtest) works and where it breaks.",
        "- **Severity is optimistic.** Here severity is the tertile of the case's own line count, which already "
        "encodes how many zones were hit - the backtest peeks at the answer through it. In production severity "
        "comes from the caller's words (\"scratch\", \"smashed\"), which is noisier, so expect lower numbers.",
        "- **The anchor is a stand-in.** The caller names the zone they see; we use the zone with the most lines, "
        "which may differ from what a person would say first.",
        "- **Side `both` mostly means a centre hit** (brackets or lamps on both sides), not a caller saying "
        "\"both sides\". A caller who names no side maps to `none`, which only exists for light hits.",
        "- **The 30-day merge cannot tell a supplement from a second accident** within the window. With the "
        "generator's fleet that happens rarely (see the merge check), in real data it depends on the fleet.",
        "- The thirds are computed per position over all models, so a stiffer model (fewer broken parts per "
        "impact) lands in lower severities more often.",
        "",
        "## Regenerate",
        "",
        "```",
        ".venv/Scripts/python -m datagen     # build/claims.csv, build/claims_truth.csv (seeded)",
        ".venv/Scripts/python -m analysis    # app/data/zones.json, docs/data-report.md",
        "```",
        "",
    ]
    return "\n".join(md)
