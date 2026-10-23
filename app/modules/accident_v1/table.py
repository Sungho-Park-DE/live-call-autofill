from __future__ import annotations

from collections import defaultdict


class Companions:
    """Zones that usually go with a reported damage, read from a table built offline by `analysis/`."""

    def __init__(self, table: dict | None = None) -> None:
        table = table or {}
        self.threshold = table.get("threshold")
        self._cells = {
            (c["model"], c["position"], c["side"], c["severity"]): c for c in table.get("cells", ())
        }
        self._declined: dict[str, set[str]] = defaultdict(set)

    def decline(self, target: str, zone: str) -> None:
        self._declined[target].add(zone)

    def accept(self, target: str, zone: str) -> None:
        self._declined[target].discard(zone)

    def _cell(self, model: str, position: str, side: str | None, severity: str) -> dict | None:
        sides = (side,) if side else ("none", "both")
        for m in (model, "*"):
            for s in sides:
                cell = self._cells.get((m, position, s, severity))
                if cell:
                    return cell
        return None

    def companions(self, target: str, model: str, position: str, side: str | None, severity: str,
                   exclude: set[str] | frozenset[str] = frozenset()) -> list[dict]:
        cell = self._cell(model, position, side, severity)
        if cell is None:
            return []
        declined = self._declined.get(target, set())
        return [
            {"zone": z["zone"], "share": z["share"], "n": cell["n"], "scope": cell["scope"],
             "included": z["zone"] not in declined}
            for z in cell["zones"]
            if z["zone"] not in exclude
        ]
