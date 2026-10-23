from __future__ import annotations

from . import data

_SIDE_SUFFIX = {"left": ("L",), "right": ("R",)}


class UnknownChoice(ValueError):
    pass


class Catalog:
    def __init__(self) -> None:
        self._severity_rank = {v: i for i, (v, _) in enumerate(data.SEVERITIES)}
        self._cars = {v: code for v, _, code in data.CARS}
        self._zones = {v: (code, position, parts) for v, _, code, position, parts in data.ZONES}

    def options(self) -> dict[str, list[dict[str, str]]]:
        return {
            "car": [{"value": v, "hint": h} for v, h, _ in data.CARS],
            "zone": [{"value": v, "hint": h} for v, h, _, _, _ in data.ZONES],
            "side": [{"value": v, "hint": h} for v, h in data.SIDES],
            "severity": [{"value": v, "hint": h} for v, h in data.SEVERITIES],
        }

    def zones(self) -> list[dict]:
        """Zone layout without a car: position and parts (name, sided, min severity) per zone."""
        return [
            {
                "zone": v,
                "position": position,
                "parts": [{"name": n, "sided": s, "min_severity": m} for n, s, m in parts],
            }
            for v, _, _, position, parts in data.ZONES
        ]

    def lines(self, car: str, zone: str, side: str | None, severity: str) -> list[dict]:
        if car not in self._cars:
            raise UnknownChoice(f"car {car!r}")
        if zone not in self._zones:
            raise UnknownChoice(f"zone {zone!r}")
        if severity not in self._severity_rank:
            raise UnknownChoice(f"severity {severity!r}")
        zone_code, _, parts = self._zones[zone]
        level = self._severity_rank[severity]
        suffixes = _SIDE_SUFFIX.get(side or "", ("L", "R"))  # unknown or both: include both sides
        out = []
        for n, (name, sided, min_sev) in enumerate(parts, start=1):
            if self._severity_rank[min_sev] > level:
                continue
            number = f"{self._cars[car]}-{zone_code}{n:02d}"
            if sided:
                for s in suffixes:
                    out.append({"number": f"{number}{s}", "name": f"{name} {s}", "qty": 1})
            else:
                out.append({"number": number, "name": name, "qty": 1})
        return out
