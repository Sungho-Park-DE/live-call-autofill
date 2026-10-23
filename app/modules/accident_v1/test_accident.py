from app.modules.accident_v1 import Companions


def cell(model, side, n, scope, zones, position="front", severity="moderate"):
    return {"model": model, "position": position, "side": side, "severity": severity, "n": n,
            "scope": scope, "zones": [{"zone": z, "share": s} for z, s in zones]}


TABLE = {
    "threshold": 0.3,
    "cells": [
        cell("Vera", "none", 57, "model", [("front bumper", 0.93), ("grille", 0.44)]),
        cell("*", "none", 140, "all", [("front bumper", 0.9), ("grille", 0.4), ("hood", 0.31)]),
        cell("*", "both", 80, "all", [("front bumper", 0.8), ("headlamp", 0.5)]),
        cell("*", "left", 30, "all", [("front fender", 0.7)]),
    ],
}


def zones(rows):
    return [(r["zone"], r["share"], r["included"]) for r in rows]


def test_operational_principle_suggest_then_decline_sticks():
    c = Companions(TABLE)
    rows = c.companions("call", "Vera", "front", None, "moderate", exclude={"front bumper"})
    assert zones(rows) == [("grille", 0.44, True)]
    assert rows[0]["n"] == 57 and rows[0]["scope"] == "model"
    c.decline("call", "grille")
    assert zones(c.companions("call", "Vera", "front", None, "moderate", {"front bumper"})) == [
        ("grille", 0.44, False)]
    assert zones(c.companions("other", "Vera", "front", None, "moderate", {"front bumper"})) == [
        ("grille", 0.44, True)]
    c.accept("call", "grille")
    assert c.companions("call", "Vera", "front", None, "moderate")[1]["included"] is True


def test_falls_back_to_all_models_then_to_both_sides():
    c = Companions(TABLE)
    assert [r["zone"] for r in c.companions("x", "Ridge", "front", None, "moderate")] == [
        "front bumper", "grille", "hood"]
    assert [r["zone"] for r in c.companions("x", "Ridge", "front", "left", "moderate")] == ["front fender"]


def test_no_cell_or_no_table_means_no_suggestions():
    assert Companions(TABLE).companions("x", "Vera", "rear", None, "minor") == []
    assert Companions().companions("x", "Vera", "front", None, "moderate") == []
