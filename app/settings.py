"""Policy values and service selection. One place, so tuning never touches a concept."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    prompt: str
    threshold: float
    options: tuple[tuple[str, str], ...] = ()  # (value, hint); empty = take from the catalog


FIELDS: tuple[Field, ...] = (
    Field(
        "intent",
        "Intent",
        "Is the caller asking for a parts quote?",
        0.6,
        (
            ("parts quote", "quote, price, how much, order, need, send me, do you have"),
            ("other", "delivery, shipping, return, refund, payment, invoice, when will"),
        ),
    ),
    Field("car", "Car model", "Which car model is the caller talking about?", 0.6),
    Field("zone", "Body zone", "Which part of the car is damaged?", 0.6),
    Field("side", "Side", "Which side of the car?", 0.6),
    Field("severity", "Damage", "How bad is the damage?", 0.6),
)

REQUIRED: tuple[str, ...] = ("car", "zone", "severity")

# Companion zones from past accident cases (built by `python -m analysis`); CTQ_COMPANIONS=0 turns them off.
ZONES_TABLE = ROOT / "app" / "data" / "zones.json"
COMPANIONS = os.environ.get("CTQ_COMPANIONS", "1") == "1"

STT = os.environ.get("CTQ_STT", "fake")
DECIDER = os.environ.get("CTQ_DECIDER", "fake")
DEMO_SPEED = float(os.environ.get("CTQ_DEMO_SPEED", "1.0"))  # 0 = replay demo calls instantly
