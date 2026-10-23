"""Claims -> cases -> zone shares per (model, position, side, severity), and a time-split backtest."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.modules.catalog_v1 import Catalog

THRESHOLD = 0.30  # a zone joins a cell's companions when this share of its cases contain it
MIN_N = 20  # model cells with fewer cases fall back to the all-models cell
MERGE_DAYS = 30  # claims of one vehicle within this many days of the case's first claim = one case
TEST_FROM = date(2025, 1, 1)  # backtest: train on the 4 years before, test on the year from here

SEVERITIES = ("minor", "moderate", "severe")
SIDES = ("left", "right", "both", "none")
ALL = "*"


@dataclass
class Claim:
    claim_no: str
    shop: str
    vehicle: str
    model: str
    day: date
    lines: list[tuple[str, str, int, str]] = field(default_factory=list)  # number, name, qty, kind


@dataclass
class Layout:
    zone_of: dict[str, str]  # part number -> zone
    position_of: dict[str, str]  # zone -> front | rear | side
    zones: list[str]  # catalog order
    positions: list[str]
    models: list[str]


@lru_cache(maxsize=1)
def layout() -> Layout:
    catalog = Catalog()
    models = [o["value"] for o in catalog.options()["car"]]
    zones = catalog.zones()
    zone_of = {}
    for model in models:
        for z in zones:
            for ln in catalog.lines(model, z["zone"], None, "severe"):
                zone_of[ln["number"]] = z["zone"]
    positions = list(dict.fromkeys(z["position"] for z in zones))
    return Layout(zone_of, {z["zone"]: z["position"] for z in zones}, [z["zone"] for z in zones], positions, models)


def claims_from_rows(rows: Iterable[dict]) -> list[Claim]:
    claims: dict[str, Claim] = {}
    for r in rows:
        c = claims.get(r["claim_no"])
        if c is None:
            c = claims[r["claim_no"]] = Claim(r["claim_no"], r["shop"], r["vehicle_id"], r["car_model"],
                                              date.fromisoformat(r["date"]))
        c.lines.append((r["part_number"], r["part_name"], int(r["qty"]), r.get("kind", "")))
    return list(claims.values())


def read_claims(path: Path) -> list[Claim]:
    with path.open(newline="", encoding="utf-8") as fh:
        return claims_from_rows(csv.DictReader(fh))


def merge(claims: list[Claim], days: int | None = MERGE_DAYS) -> list[list[Claim]]:
    """Group claims per vehicle; a claim joins the open group when it is at most `days` after the
    group's first claim. days=None: every claim is its own group."""
    if days is None:
        return [[c] for c in sorted(claims, key=lambda c: (c.day, c.claim_no))]
    by_vehicle: dict[str, list[Claim]] = defaultdict(list)
    for c in claims:
        by_vehicle[c.vehicle].append(c)
    groups = []
    for vehicle_claims in by_vehicle.values():
        vehicle_claims.sort(key=lambda c: (c.day, c.claim_no))
        group: list[Claim] = []
        for c in vehicle_claims:
            if group and (c.day - group[0].day).days <= days:
                group.append(c)
            else:
                if group:
                    groups.append(group)
                group = [c]
        groups.append(group)
    groups.sort(key=lambda g: (g[0].day, g[0].claim_no))
    return groups


@dataclass
class Case:
    vehicle: str
    model: str
    start: date
    claim_nos: list[str]
    zones: dict[str, int]  # zone -> replaced lines, catalog order
    count: int  # lines used for severity
    position: str | None
    side: str


def side_of(numbers: Iterable[str]) -> str:
    sides = {n[-1] for n in numbers if n[-1] in "LR"}
    return {frozenset("L"): "left", frozenset("R"): "right", frozenset("LR"): "both"}.get(frozenset(sides), "none")


def make_case(group: list[Claim], drop_consumables: bool = True) -> Case:
    lay = layout()
    numbers = [ln[0] for c in group for ln in c.lines]
    parts = [n for n in numbers if n in lay.zone_of]
    per_zone = Counter(lay.zone_of[n] for n in parts)
    zones = {z: per_zone[z] for z in lay.zones if per_zone[z]}
    per_position = Counter()
    for z, k in zones.items():
        per_position[lay.position_of[z]] += k
    position = None
    if per_position:
        position = max(lay.positions, key=lambda p: (per_position[p], -lay.positions.index(p)))
    return Case(group[0].vehicle, group[0].model, group[0].day, [c.claim_no for c in group], zones,
                len(parts) if drop_consumables else len(numbers), position, side_of(parts))


def build_cases(claims: list[Claim], merge_days: int | None = MERGE_DAYS, drop_consumables: bool = True) -> list[Case]:
    return [make_case(g, drop_consumables) for g in merge(claims, merge_days)]


def tertile_cuts(cases: Iterable[Case]) -> dict[str, tuple[int, int]]:
    """Per position: (upper bound of minor, upper bound of moderate) on the line count."""
    counts: dict[str, list[int]] = defaultdict(list)
    for c in cases:
        if c.position:
            counts[c.position].append(c.count)
    cuts = {}
    for position, values in counts.items():
        values.sort()
        n = len(values)
        cuts[position] = (values[math.ceil(n / 3) - 1], values[math.ceil(2 * n / 3) - 1])
    return cuts


def severity(case: Case, cuts: dict[str, tuple[int, int]]) -> str:
    low, high = cuts[case.position]
    return "minor" if case.count <= low else "moderate" if case.count <= high else "severe"


Key = tuple[str, str, str, str]  # model (or "*"), position, side, severity


@dataclass
class Cell:
    n: int = 0
    zones: Counter = field(default_factory=Counter)  # zone -> cases containing it

    def shares(self) -> dict[str, float]:
        return {z: k / self.n for z, k in self.zones.items()}


def table(cases: Iterable[Case], cuts: dict[str, tuple[int, int]]) -> dict[Key, Cell]:
    cells: dict[Key, Cell] = defaultdict(Cell)
    for c in cases:
        if not c.position or c.position not in cuts:
            continue
        sev = severity(c, cuts)
        for model in (c.model, ALL):
            cell = cells[(model, c.position, c.side, sev)]
            cell.n += 1
            cell.zones.update(c.zones.keys())
    return dict(cells)


def lookup(cells: dict[Key, Cell], key: Key, min_n: int = MIN_N) -> tuple[str, Cell] | None:
    """The cell actually used: the model's own when it has min_n cases, else the all-models cell."""
    own = cells.get(key)
    if own is not None and own.n >= min_n and key[0] != ALL:
        return "model", own
    shared = cells.get((ALL, *key[1:]))
    return ("all", shared) if shared is not None else None


def companions(cell: Cell, threshold: float = THRESHOLD) -> list[tuple[str, float]]:
    order = {z: i for i, z in enumerate(layout().zones)}
    picked = [(z, s) for z, s in cell.shares().items() if s >= threshold]
    return sorted(picked, key=lambda zs: (-zs[1], order[zs[0]]))


def zones_json(cells: dict[Key, Cell], threshold: float = THRESHOLD, min_n: int = MIN_N, merge_days: int = MERGE_DAYS) -> dict:
    lay = layout()
    model_rank = {m: i for i, m in enumerate([*lay.models, ALL])}
    out = []
    for key in sorted(cells, key=lambda k: (model_rank.get(k[0], 99), lay.positions.index(k[1]),
                                            SIDES.index(k[2]), SEVERITIES.index(k[3]))):
        scope, cell = lookup(cells, key, min_n)
        out.append({
            "model": key[0], "position": key[1], "side": key[2], "severity": key[3],
            "n": cell.n, "scope": scope,
            "zones": [{"zone": z, "share": round(s, 2)} for z, s in companions(cell, threshold)],
        })
    return {"threshold": threshold, "min_n": min_n, "merge_days": merge_days,
            "source": "invented claims from datagen, see docs/data-report.md", "cells": out}


def anchor(case: Case) -> str:
    """The zone with the most lines; ties go to the earlier zone in catalog order (zones is in that order)."""
    return max(case.zones, key=lambda z: (case.zones[z], -list(case.zones).index(z)))


@dataclass
class Score:
    cases: int = 0
    tp: int = 0
    predicted: int = 0
    actual: int = 0
    no_cell: int = 0
    fallback: int = 0

    @property
    def precision(self) -> float:
        return self.tp / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.tp / self.actual if self.actual else 0.0


def backtest(train: list[Case], test: list[Case], threshold: float = THRESHOLD, min_n: int = MIN_N,
             baseline: bool = False) -> Score:
    """For each test case the anchor zone stands in for what the caller said; predict the other zones
    from the table trained on `train` and compare with the case's other zones (micro averages).
    baseline=True predicts every catalog zone of the case's position instead."""
    lay = layout()
    cuts = tertile_cuts(train)
    cells = table(train, cuts)
    score = Score()
    for c in test:
        if not c.position or not c.zones:
            continue
        a = anchor(c)
        actual = set(c.zones) - {a}
        if baseline:
            predicted = {z for z in lay.zones if lay.position_of[z] == c.position} - {a}
        else:
            hit = lookup(cells, (c.model, c.position, c.side, severity(c, cuts)), min_n) if c.position in cuts else None
            if hit is None:
                score.no_cell += 1
                predicted = set()
            else:
                score.fallback += hit[0] == "all"
                predicted = {z for z, _ in companions(hit[1], threshold)} - {a}
        score.cases += 1
        score.tp += len(predicted & actual)
        score.predicted += len(predicted)
        score.actual += len(actual)
    return score


def split(cases: list[Case], test_from: date = TEST_FROM) -> tuple[list[Case], list[Case]]:
    return [c for c in cases if c.start < test_from], [c for c in cases if c.start >= test_from]
