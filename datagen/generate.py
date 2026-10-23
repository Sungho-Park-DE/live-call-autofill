"""Invented accident-repair claims, generated from mechanisms only.

Everything here is fictional: cars, shops, vehicles, claim and part numbers. The generator
encodes *mechanisms*, never target statistics: there is no table of "zone A comes with zone B
x % of the time" anywhere. Whatever co-occurrence the analysis finds falls out of these rules:

1. Accident. A car (model mix), a date, an impact face (front / rear / side) and an impact
   segment on that face: lateral offset + overlap width for front/rear, a side (left/right),
   a point along the car and a sweep length for side impacts. The impact has a depth drawn
   from a log-normal distribution and scaled by the model's stiffness.
2. Geometry. The car is a plan (x lateral -1 left .. +1 right, y 0 front .. 4.5 rear). Every
   zone instance is a segment on that plan plus a layer (how far under the outer skin it sits).
   Sided parts of a zone live on a left and a right instance; non-sided parts on the zone span.
3. Propagation. Local depth = impact depth - ATTENUATION * distance(impact, instance)
   - layer + noise. Deeper impacts reach farther zones and lower layers.
4. Damage. Local depth maps to a local severity by fixed bands; which parts are replaced is
   decided by the catalog's min severity per part (Catalog.lines with the local severity).
5. Repair. An instance of a repairable zone (sheet metal or plastic skin) is repaired instead
   of replaced with a probability that falls with severity; no part is sold for it.
6. Hidden damage. Some parts sit behind the skin (HIDDEN_PARTS: brackets, absorbers, beams,
   hinges, the radiator support...). Each is found only after the car is taken apart with
   probability P_HIDDEN and then goes onto a supplement claim a few days later, usually from
   the same shop.
7. Consumables. Bolts, clips, sealant, paint material, filler follow the work done, with
   invented numbers that are not in the catalog. The article group ("kind") is sometimes wrong.
8. Fleet. Accidents pick vehicles at random from a fixed fleet, so some cars come back with an
   unrelated accident - now and then within 30 days, indistinguishable from a supplement.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.modules.catalog_v1 import Catalog

SEED = 20211
N_ACCIDENTS = 3200
N_VEHICLES = 6000
START = date(2021, 1, 1)
END = date(2025, 12, 31)

MODELS = {  # mix weight, stiffness (impact depth multiplier), layer overrides
    "Atto": (0.45, 1.15, {}),
    "Vera": (0.35, 1.00, {}),
    "Ridge": (0.20, 0.85, {"tailgate": 0.45, "grille": 0.05, "rear bumper": -0.05}),
}
SHOPS = {"S01": 22, "S02": 18, "S03": 15, "S04": 12, "S05": 11, "S06": 9, "S07": 8, "S08": 5}
P_HOME_SHOP = 0.75
P_SUPPLEMENT_SAME_SHOP = 0.6

FACES = {"front": 0.45, "rear": 0.35, "side": 0.20}
DEPTH_MEDIAN = 0.55
DEPTH_SIGMA = 0.65
ATTENUATION = 0.9
NOISE = 0.15
BANDS = (("severe", 1.4), ("moderate", 0.8), ("minor", 0.25))  # local depth >= value
P_REPAIR = {"minor": 0.5, "moderate": 0.15, "severe": 0.0}
P_HIDDEN = 0.35
P_KIND_MISCODED = 0.05

LENGTH = 4.5

# zone: span for non-sided parts (or None), left instance for sided parts (or None), layer.
# Right instances mirror the left ones (x -> -x).
GEOMETRY = {
    "front bumper": (((-1.0, 0.0), (1.0, 0.0)), ((-0.85, 0.05), (-0.85, 0.05)), 0.0),
    "grille": (((-0.45, 0.15), (0.45, 0.15)), None, 0.15),
    "headlamp": (None, ((-0.85, 0.25), (-0.55, 0.25)), 0.15),  # above and behind the bumper face
    "fog lamp": (None, ((-0.7, 0.1), (-0.6, 0.1)), 0.25),  # recessed behind the bumper cover
    "hood": (((-0.9, 0.3), (0.9, 0.3)), ((-0.85, 1.3), (-0.85, 1.3)), 0.3),
    "front fender": (None, ((-1.0, 0.15), (-1.0, 1.2)), 0.1),
    "radiator support": (((-0.7, 0.35), (0.7, 0.35)), None, 0.55),
    "rear bumper": (((-1.0, LENGTH), (1.0, LENGTH)), ((-0.85, 4.45), (-0.85, 4.45)), 0.0),
    "tail lamp": (None, ((-0.95, 4.3), (-0.7, 4.3)), 0.15),  # above and ahead of the bumper face
    "tailgate": (((-0.8, 4.45), (0.8, 4.45)), ((-0.75, 4.2), (-0.75, 4.2)), 0.25),
    "front door": (None, ((-1.0, 1.3), (-1.0, 2.4)), 0.0),
    "rear door": (None, ((-1.0, 2.4), (-1.0, 3.4)), 0.0),
    "side mirror": (None, ((-1.1, 1.35), (-1.1, 1.35)), -0.1),
    "quarter panel": (None, ((-1.0, 3.4), (-1.0, 4.35)), 0.05),
}
REPAIRABLE = {"front bumper", "hood", "front fender", "rear bumper", "tailgate",
              "front door", "rear door", "quarter panel"}
PAINTED = REPAIRABLE | {"side mirror"}
# Parts nobody sees before the car is taken apart (catalog part names, without the L/R suffix).
HIDDEN_PARTS = {"Front bumper bracket", "Front bumper absorber", "Front bumper beam", "Headlamp bracket",
                "Hood hinge", "Hood latch", "Fender liner", "Radiator support panel", "Radiator", "Condenser",
                "Rear bumper bracket", "Rear bumper beam", "Tailgate strut"}
BUMPERS = {"front bumper", "rear bumper"}

CONSUMABLES = {  # invented, outside the catalog
    "bolts": ("CS-BT10", "Bolt and nut kit"),
    "clips": ("CS-CL20", "Body clip assortment"),
    "sealant": ("CS-SL30", "Seam sealant"),
    "paint": ("CS-PM40", "Paint material, litre"),
    "filler": ("CS-FL50", "Body filler"),
    "tape": ("CS-AT60", "Double-sided trim tape"),
}

Seg = tuple[tuple[float, float], tuple[float, float]]


@dataclass
class Accident:
    id: int
    vehicle: str
    model: str
    day: date
    face: str
    impact: Seg
    depth: float


@dataclass
class Claim:
    claim_no: str
    shop: str
    vehicle: str
    model: str
    day: date
    accident: int
    lines: list[tuple[str, str, int, str]] = field(default_factory=list)  # number, name, qty, kind


def _point_seg(p, seg: Seg) -> float:
    (ax, ay), (bx, by) = seg
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def distance(a: Seg, b: Seg) -> float:
    """Shortest distance between two segments that do not cross (true for the plan's segments)."""
    return min(_point_seg(a[0], b), _point_seg(a[1], b), _point_seg(b[0], a), _point_seg(b[1], a))


def mirror(seg: Seg) -> Seg:
    return ((-seg[0][0], seg[0][1]), (-seg[1][0], seg[1][1]))


def band(local_depth: float) -> str | None:
    for severity, low in BANDS:
        if local_depth >= low:
            return severity
    return None


def local_depth(impact: Seg, depth: float, instance: Seg, layer: float, rng: random.Random) -> float:
    return depth - ATTENUATION * distance(impact, instance) - layer + rng.gauss(0.0, NOISE)


def draw_impact(rng: random.Random) -> tuple[str, Seg]:
    face = rng.choices(list(FACES), weights=list(FACES.values()))[0]
    if face == "side":
        x = rng.choice((-1.0, 1.0))
        y0 = rng.uniform(0.2, 4.3)
        y1 = min(LENGTH - 0.1, y0 + rng.uniform(0.0, 2.0))
        return face, ((x, y0), (x, y1))
    x0 = max(-1.0, min(1.0, rng.gauss(0.0, 0.55)))
    half = rng.uniform(0.1, 0.8)
    y = 0.0 if face == "front" else LENGTH
    return face, ((max(-1.0, x0 - half), y), (min(1.0, x0 + half), y))


def _sided(number: str) -> bool:
    return number[-1] in "LR"


def base_name(name: str) -> str:
    return name[:-2] if name[-2:] in (" L", " R") else name


@dataclass
class Work:
    replaced: list[dict]  # catalog lines with "hidden" flag
    repaired: set[str]  # zones with at least one repaired instance
    touched: set[str]  # zones with replaced or repaired instances


def damage(catalog: Catalog, acc: Accident, rng: random.Random) -> Work:
    overrides = MODELS[acc.model][2]
    work = Work([], set(), set())
    for zone, (span, left, base_layer) in GEOMETRY.items():
        layer = overrides.get(zone, base_layer)
        instances = []
        if span is not None:
            instances.append(("left", span, False))  # "left" only narrows sided parts away
        if left is not None:
            instances.append(("left", left, True))
            instances.append(("right", mirror(left), True))
        for side, seg, sided in instances:
            severity = band(local_depth(acc.impact, acc.depth, seg, layer, rng))
            if severity is None:
                continue
            work.touched.add(zone)
            if zone in REPAIRABLE and rng.random() < P_REPAIR[severity]:
                work.repaired.add(zone)
                continue
            for ln in catalog.lines(acc.model, zone, side, severity):
                if _sided(ln["number"]) != sided:
                    continue
                hidden = base_name(ln["name"]) in HIDDEN_PARTS and rng.random() < P_HIDDEN
                work.replaced.append({**ln, "hidden": hidden})
    return work


def consumables(acc: Accident, work: Work, rng: random.Random, supplement: bool) -> list[tuple[str, int]]:
    """(consumable key or model clip kit marker, qty) following the work done."""
    out: list[tuple[str, int]] = []
    if supplement:
        if rng.random() < 0.7:
            out.append(("bolts", 1))
        return out
    painted = len(work.touched & PAINTED)
    if work.replaced and rng.random() < 0.6:
        out.append(("bolts", 1))
    if work.touched & BUMPERS:
        out.append(("clips", 1))
        if rng.random() < 0.5:
            out.append(("clipkit", 1))
    if work.touched & {"front fender", "quarter panel", "tailgate", "hood", "front door", "rear door"} \
            and rng.random() < 0.5:
        out.append(("sealant", 1))
    if painted:
        out.append(("paint", max(1, round(painted * rng.uniform(0.6, 1.4)))))
    if work.repaired:
        out.append(("filler", 1))
    if work.touched & {"side mirror", "front door", "rear door"} and rng.random() < 0.4:
        out.append(("tape", 1))
    return out


def _consumable_line(key: str, qty: int, model_prefix: str, rng: random.Random) -> tuple[str, str, int, str]:
    if key == "clipkit":
        number, name = f"{model_prefix}-CK01", "Bumper clip kit"
    else:
        number, name = CONSUMABLES[key]
    kind = "part" if rng.random() < P_KIND_MISCODED else "consumable"
    return number, name, qty, kind


def generate(n_accidents: int = N_ACCIDENTS, seed: int = SEED, n_vehicles: int = N_VEHICLES) -> list[Claim]:
    rng = random.Random(seed)
    catalog = Catalog()
    prefixes = {m: catalog.lines(m, "grille", None, "minor")[0]["number"].split("-")[0] for m in MODELS}
    shops = list(SHOPS)
    models = list(MODELS)
    vehicle_model = {}
    vehicle_shop = {}
    for i in range(1, n_vehicles + 1):
        vid = f"CAR-{i:05d}"
        vehicle_model[vid] = rng.choices(models, weights=[MODELS[m][0] for m in models])[0]
        vehicle_shop[vid] = rng.choices(shops, weights=list(SHOPS.values()))[0]
    vehicles = list(vehicle_model)
    span_days = (END - START).days - 30

    claims: list[Claim] = []
    for acc_id in range(1, n_accidents + 1):
        vid = rng.choice(vehicles)
        model = vehicle_model[vid]
        face, impact = draw_impact(rng)
        depth = math.exp(rng.gauss(math.log(DEPTH_MEDIAN), DEPTH_SIGMA)) * MODELS[model][1]
        acc = Accident(acc_id, vid, model, START + timedelta(days=rng.randrange(span_days)), face, impact, depth)
        work = damage(catalog, acc, rng)
        if not work.touched:
            continue  # nothing beyond a polish: no parts, no claim
        shop = vehicle_shop[vid] if rng.random() < P_HOME_SHOP else rng.choice(shops)
        first = Claim("", shop, vid, model, acc.day + timedelta(days=rng.randrange(0, 7)), acc_id)
        later = [ln for ln in work.replaced if ln["hidden"]]
        first.lines = [(ln["number"], ln["name"], ln["qty"], "part") for ln in work.replaced if not ln["hidden"]]
        first.lines += [_consumable_line(k, q, prefixes[model], rng) for k, q in consumables(acc, work, rng, False)]
        if not first.lines:  # everything found only later: the first order is just fixings
            first.lines.append(_consumable_line("bolts", 1, prefixes[model], rng))
        claims.append(first)
        if later:
            sup_shop = shop if rng.random() < P_SUPPLEMENT_SAME_SHOP else rng.choice([s for s in shops if s != shop])
            sup = Claim("", sup_shop, vid, model, first.day + timedelta(days=rng.randint(3, 25)), acc_id)
            sup.lines = [(ln["number"], ln["name"], ln["qty"], "part") for ln in later]
            sup.lines += [_consumable_line(k, q, prefixes[model], rng) for k, q in consumables(acc, work, rng, True)]
            claims.append(sup)

    claims.sort(key=lambda c: (c.day, c.accident))
    for seq, claim in enumerate(claims, start=100001):
        claim.claim_no = f"CLM-{seq:06d}"
    return claims


CSV_FIELDS = ("claim_no", "shop", "vehicle_id", "car_model", "date", "part_number", "part_name", "qty", "kind")


def rows(claims: list[Claim]):
    for c in claims:
        for number, name, qty, kind in c.lines:
            yield {"claim_no": c.claim_no, "shop": c.shop, "vehicle_id": c.vehicle, "car_model": c.model,
                   "date": c.day.isoformat(), "part_number": number, "part_name": name, "qty": qty, "kind": kind}
