from __future__ import annotations


class DraftClosed(RuntimeError):
    pass


class MissingFields(ValueError):
    def __init__(self, fields: list[str]):
        super().__init__(", ".join(fields))
        self.fields = fields


class Drafts:
    def __init__(self) -> None:
        self._drafts: dict[str, dict] = {}

    def open(self, target: str) -> None:
        self._drafts[target] = {"fields": {}, "confirmed": False}

    def _open(self, target: str) -> dict:
        d = self._drafts[target]
        if d["confirmed"]:
            raise DraftClosed(target)
        return d

    def suggest(self, target: str, field: str, value: str, confidence: float, source: str) -> str:
        fields = self._open(target)["fields"]
        current = fields.get(field)
        if current and current["origin"] == "human":
            return "kept-human"
        new = {"value": value, "origin": "suggested", "confidence": confidence, "source": source}
        if current == new:
            return "unchanged"
        fields[field] = new
        return "applied"

    def retract(self, target: str, field: str) -> bool:
        fields = self._open(target)["fields"]
        if fields.get(field, {}).get("origin") == "suggested":
            del fields[field]
            return True
        return False

    def set(self, target: str, field: str, value: str) -> None:
        self._open(target)["fields"][field] = {
            "value": value.strip(),
            "origin": "human",
            "confidence": None,
            "source": None,
        }

    def release(self, target: str, field: str) -> None:
        fields = self._open(target)["fields"]
        if fields.get(field, {}).get("origin") == "human":
            del fields[field]

    def confirm(self, target: str, required: list[str] | tuple[str, ...]) -> dict[str, str]:
        d = self._open(target)
        values = {k: e["value"] for k, e in d["fields"].items() if e["value"]}
        missing = [f for f in required if f not in values]
        if missing:
            raise MissingFields(missing)
        d["confirmed"] = True
        return values

    def view(self, target: str) -> dict:
        d = self._drafts[target]
        return {"fields": {k: dict(v) for k, v in d["fields"].items()}, "confirmed": d["confirmed"]}
