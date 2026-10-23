"""Feature flags: CTQ_FLAG_<NAME>=1 turns a flag on. Everything is off by default."""
import os


def is_enabled(name: str) -> bool:
    return os.environ.get(f"CTQ_FLAG_{name.upper()}", "") == "1"
