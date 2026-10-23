import random
import re
from datetime import date

from app.modules.catalog_v1 import Catalog
from datagen import generate as g

CATALOG_NUMBERS = {
    ln["number"]
    for car in ("Atto", "Vera", "Ridge")
    for z in Catalog().zones()
    for ln in Catalog().lines(car, z["zone"], None, "severe")
}


def small(seed=7):
    return g.generate(n_accidents=150, seed=seed, n_vehicles=60)


def test_seeded_and_repeatable():
    a, b = small(), small()
    assert [(c.claim_no, c.lines) for c in a] == [(c.claim_no, c.lines) for c in b]
    assert [c.lines for c in small(8)] != [c.lines for c in a]


def test_ids_are_invented_formats():
    for c in small():
        assert re.fullmatch(r"CAR-\d{5}", c.vehicle)  # not a 17-character VIN
        assert re.fullmatch(r"CLM-\d{6}", c.claim_no)
        assert re.fullmatch(r"S\d\d", c.shop)
        assert g.START <= c.day <= date(2026, 1, 31)


def test_every_number_is_a_catalog_part_or_a_consumable():
    numbers = {n for c in small() for n, *_ in c.lines}
    consumables = numbers - CATALOG_NUMBERS
    assert consumables and numbers & CATALOG_NUMBERS
    assert all(n.startswith("CS-") or n.endswith("-CK01") for n in consumables)


def test_supplements_follow_within_the_window_with_hidden_parts_only():
    claims = small()
    by_accident = {}
    for c in claims:
        by_accident.setdefault(c.accident, []).append(c)
    supplements = [cs for cs in by_accident.values() if len(cs) > 1]
    assert supplements
    for first, later in supplements:
        assert first.vehicle == later.vehicle
        assert 3 <= (later.day - first.day).days <= 25
        parts = [name for n, name, _, _ in later.lines if n in CATALOG_NUMBERS]
        assert parts and all(g.base_name(p) in g.HIDDEN_PARTS for p in parts)


def test_damage_fades_with_distance_and_layer():
    rng = random.Random(0)
    g.NOISE, noise = 0.0, g.NOISE
    try:
        impact = ((-0.2, 0.0), (0.2, 0.0))
        near = g.local_depth(impact, 1.0, ((-0.1, 0.0), (0.1, 0.0)), 0.0, rng)
        far = g.local_depth(impact, 1.0, ((-1.0, 1.3), (-1.0, 2.4)), 0.0, rng)
        deep = g.local_depth(impact, 1.0, ((-0.1, 0.0), (0.1, 0.0)), 0.5, rng)
    finally:
        g.NOISE = noise
    assert near == 1.0 and far < near and deep == 0.5
    assert g.band(0.1) is None and g.band(0.3) == "minor" and g.band(1.0) == "moderate" and g.band(2.0) == "severe"


def test_deeper_impacts_replace_more_parts():
    catalog = Catalog()

    def parts(depth):
        rng = random.Random(3)
        total = 0
        for i in range(40):
            acc = g.Accident(i, "CAR-00001", "Vera", g.START, "front", ((-0.5, 0.0), (0.5, 0.0)), depth)
            total += len(g.damage(catalog, acc, rng).replaced)
        return total

    assert parts(0.4) < parts(1.0) < parts(2.0)


def test_rows_have_the_csv_fields():
    row = next(g.rows(small()))
    assert tuple(row) == g.CSV_FIELDS
