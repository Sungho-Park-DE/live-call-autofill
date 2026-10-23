from datetime import date, timedelta

import pytest

from analysis import core

D0 = date(2023, 3, 1)


def claim(no, vehicle, day, numbers, model="Atto", shop="S01"):
    return core.Claim(no, shop, vehicle, model, day, [(n, n, 1, "part") for n in numbers])


def case(zones, model="Atto", position="front", side="none", count=None, start=D0):
    zones = dict(zones)
    return core.Case("CAR-00001", model, start, ["x"], zones, sum(zones.values()) if count is None else count,
                     position, side)


def test_merge_within_window_and_not_beyond():
    claims = [
        claim("C1", "CAR-00001", D0, ["AT-FB01"]),
        claim("C2", "CAR-00001", D0 + timedelta(days=30), ["AT-FB02L"], shop="S02"),
        claim("C3", "CAR-00001", D0 + timedelta(days=31), ["AT-RB01"]),
        claim("C4", "CAR-00002", D0 + timedelta(days=1), ["AT-FB01"]),
    ]
    groups = [[c.claim_no for c in g] for g in core.merge(claims)]
    assert groups == [["C1", "C2"], ["C4"], ["C3"]]
    assert [[c.claim_no for c in g] for g in core.merge(claims, None)] == [["C1"], ["C4"], ["C2"], ["C3"]]


def test_window_counts_from_the_first_claim_not_chained():
    claims = [claim(f"C{i}", "CAR-00001", D0 + timedelta(days=20 * i), ["AT-FB01"]) for i in range(3)]
    assert [len(g) for g in core.merge(claims)] == [2, 1]


def test_consumables_dropped_by_catalog_mapping_not_by_kind():
    c = claim("C1", "CAR-00001", D0, ["AT-FB01", "AT-GR01"])
    c.lines += [("CS-PM40", "Paint", 2, "part"), ("AT-CK01", "Clip kit", 1, "consumable")]
    kept = core.make_case([c])
    assert kept.zones == {"front bumper": 1, "grille": 1} and kept.count == 2
    assert core.make_case([c], drop_consumables=False).count == 4


def test_position_side_and_anchor():
    c = core.make_case([claim("C1", "CAR-00001", D0, ["AT-FB01", "AT-FB02L", "AT-HL01L", "AT-FR02L"])])
    assert c.position == "front" and c.side == "left"
    assert core.anchor(c) == "front bumper"
    assert core.side_of(["AT-FB01"]) == "none"
    assert core.side_of(["AT-FB02L", "AT-FB02R"]) == "both"
    assert core.side_of(["AT-HL01R", "AT-GR01"]) == "right"
    tie = core.make_case([claim("C1", "CAR-00001", D0, ["AT-HL01L", "AT-GR01"])])
    assert core.anchor(tie) == "grille"  # catalog order: grille before headlamp


def test_case_without_catalog_parts_has_no_position():
    c = core.make_case([claim("C1", "CAR-00001", D0, ["CS-FL50"])])
    assert c.position is None and c.zones == {}


def test_tertiles():
    cases = [case({"front bumper": k}) for k in range(1, 10)]
    cuts = core.tertile_cuts(cases)
    assert cuts == {"front": (3, 6)}
    assert [core.severity(c, cuts) for c in cases] == ["minor"] * 3 + ["moderate"] * 3 + ["severe"] * 3


def _cells(n_model, n_other, zones_model, zones_other):
    cases = [case(zones_model, model="Ridge") for _ in range(n_model)]
    cases += [case(zones_other, model="Atto") for _ in range(n_other)]
    cuts = {"front": (100, 200)}  # everything minor
    return core.table(cases, cuts)


def test_fallback_to_all_models_when_model_cell_is_small():
    cells = _cells(5, 30, {"front bumper": 1, "hood": 1}, {"front bumper": 1, "grille": 1})
    doc = core.zones_json(cells)
    by = {(c["model"], c["severity"]): c for c in doc["cells"]}
    ridge = by[("Ridge", "minor")]
    assert ridge["scope"] == "all" and ridge["n"] == 35
    assert ridge["zones"] == by[("*", "minor")]["zones"]
    atto = by[("Atto", "minor")]
    assert atto["scope"] == "model" and atto["n"] == 30
    assert atto["zones"] == [{"zone": "front bumper", "share": 1.0}, {"zone": "grille", "share": 1.0}]


def test_share_threshold_and_rounding():
    cases = [case({"front bumper": 1, "grille": 1}) for _ in range(3)]
    cases += [case({"front bumper": 1}) for _ in range(7)]
    cases += [case({"front bumper": 1, "hood": 1}) for _ in range(2)]
    cells = core.table(cases, {"front": (100, 200)})
    zones = core.zones_json(cells, min_n=1)["cells"][0]["zones"]
    # grille 3/12 = 0.25 is out, hood 2/12 out; lower the threshold and grille comes in
    assert zones == [{"zone": "front bumper", "share": 1.0}]
    zones = core.zones_json(cells, threshold=0.25, min_n=1)["cells"][0]["zones"]
    assert zones == [{"zone": "front bumper", "share": 1.0}, {"zone": "grille", "share": 0.25}]


def test_zones_json_shape():
    doc = core.zones_json(_cells(25, 25, {"front bumper": 1}, {"front bumper": 1}))
    assert {"threshold", "min_n", "merge_days", "source", "cells"} <= set(doc)
    assert [c["model"] for c in doc["cells"]] == ["Atto", "Ridge", "*"]
    assert set(doc["cells"][0]) == {"model", "position", "side", "severity", "n", "scope", "zones"}


def test_backtest_on_a_tiny_dataset():
    # Train: 20 cases bumper+grille+hood, 10 cases bumper+grille -> grille 1.0, hood 0.67, bumper 1.0.
    train = [case({"front bumper": 2, "grille": 1, "hood": 1}) for _ in range(20)]
    train += [case({"front bumper": 2, "grille": 1}) for _ in range(10)]
    test = [
        case({"front bumper": 2, "grille": 1, "hood": 1}),  # anchor bumper; predict grille, hood: 2 tp
        case({"front bumper": 2, "fog lamp": 1}),  # predict grille, hood: 0 tp, misses fog lamp
        case({"front bumper": 2}),  # predict grille, hood: 0 tp, nothing to find
    ]
    for c in train + test:
        c.count = 1  # all in one severity
    s = core.backtest(train, test, threshold=0.30, min_n=20)
    assert (s.cases, s.tp, s.predicted, s.actual) == (3, 2, 6, 3)
    assert s.precision == pytest.approx(2 / 6) and s.recall == pytest.approx(2 / 3)
    s = core.backtest(train, test, threshold=0.70, min_n=20)  # hood 0.67 drops out
    assert (s.tp, s.predicted, s.actual) == (1, 3, 3)
    s = core.backtest(train, test, threshold=0.30, min_n=40)  # model cell too small -> "*" cell, same data
    assert s.fallback == 3 and s.tp == 2


def test_split_by_case_start():
    old, new = case({"grille": 1}, start=date(2024, 12, 31)), case({"grille": 1}, start=date(2025, 1, 1))
    assert core.split([old, new]) == ([old], [new])
