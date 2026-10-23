"""Invented demo data. Model names and part numbers are fictional and match no real maker."""

# value, hint (other words people use), part-number prefix
CARS = (
    ("Atto", "atto suv, compact suv", "AT"),
    ("Vera", "vera suv, midsize suv", "VR"),
    ("Ridge", "ridge pickup, pickup, truck", "RG"),
)

SEVERITIES = (
    ("minor", "scratch, scuff, a little, small, light damage"),
    ("moderate", "dent, crack, pushed in, broken"),
    ("severe", "smashed, totaled, wrecked, badly, airbag, crushed"),
)

SIDES = (
    ("left", "driver side, driver's side"),
    ("right", "passenger side, passenger's side"),
    ("both", "both sides, both of them"),
)

POSITIONS = ("front", "rear", "side")

# zone value, hint, code, position, parts: (name, sided, min severity)
ZONES = (
    ("front bumper", "front bumper, bumper at the front", "FB", "front", (
        ("Front bumper cover", False, "minor"),
        ("Front bumper bracket", True, "moderate"),
        ("Front bumper absorber", False, "moderate"),
        ("Front bumper beam", False, "severe"),
    )),
    ("grille", "grille, grill, radiator grille", "GR", "front", (
        ("Radiator grille", False, "minor"),
        ("Grille emblem", False, "moderate"),
    )),
    ("headlamp", "headlamp, headlight, head light", "HL", "front", (
        ("Headlamp assembly", True, "minor"),
        ("Headlamp bracket", True, "severe"),
    )),
    ("fog lamp", "fog lamp, fog light", "FL", "front", (
        ("Fog lamp", True, "minor"),
        ("Fog lamp cover", True, "minor"),
    )),
    ("hood", "hood, bonnet", "HD", "front", (
        ("Hood panel", False, "minor"),
        ("Hood hinge", True, "moderate"),
        ("Hood latch", False, "severe"),
    )),
    ("front fender", "front fender, fender, wing", "FD", "front", (
        ("Front fender panel", True, "minor"),
        ("Fender liner", True, "moderate"),
    )),
    ("radiator support", "radiator support, core support, radiator", "RS", "front", (
        ("Radiator support panel", False, "moderate"),
        ("Radiator", False, "severe"),
        ("Condenser", False, "severe"),
    )),
    ("rear bumper", "rear bumper, back bumper", "RB", "rear", (
        ("Rear bumper cover", False, "minor"),
        ("Rear bumper bracket", True, "moderate"),
        ("Rear bumper beam", False, "severe"),
    )),
    ("tail lamp", "tail lamp, taillight, tail light, rear light", "TL", "rear", (
        ("Tail lamp assembly", True, "minor"),
    )),
    ("tailgate", "tailgate, trunk, liftgate, back door", "TG", "rear", (
        ("Tailgate panel", False, "moderate"),
        ("Tailgate garnish", False, "minor"),
        ("Tailgate strut", True, "severe"),
    )),
    ("front door", "front door, driver door, passenger door", "FR", "side", (
        ("Front door panel", True, "moderate"),
        ("Front door moulding", True, "minor"),
    )),
    ("rear door", "rear door, back seat door", "RR", "side", (
        ("Rear door panel", True, "moderate"),
        ("Rear door moulding", True, "minor"),
    )),
    ("side mirror", "side mirror, wing mirror, mirror", "SM", "side", (
        ("Side mirror cover", True, "minor"),
        ("Side mirror assembly", True, "moderate"),
    )),
    ("quarter panel", "quarter panel, rear fender, rear quarter", "QP", "side", (
        ("Quarter panel", True, "moderate"),
        ("Rear wheel arch moulding", True, "minor"),
    )),
)
