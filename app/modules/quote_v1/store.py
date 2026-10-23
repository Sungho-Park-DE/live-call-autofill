from __future__ import annotations

import itertools
import time


class DuplicateQuote(RuntimeError):
    pass


class EmptyQuote(ValueError):
    pass


class Quotes:
    def __init__(self) -> None:
        self._quotes: dict[str, dict] = {}
        self._by_call: dict[str, str] = {}
        self._ids = itertools.count(1)

    def create(self, call: str, header: dict, lines: list[dict]) -> str:
        if call in self._by_call:
            raise DuplicateQuote(call)
        if not lines:
            raise EmptyQuote(call)
        quote = f"Q-{next(self._ids):04d}"
        self._quotes[quote] = {
            "id": quote,
            "call": call,
            "header": dict(header),
            "lines": [dict(l) for l in lines],
            "created_at": time.time(),
        }
        self._by_call[call] = quote
        return quote

    def get(self, quote: str) -> dict:
        return self._quotes[quote]

    def for_call(self, call: str) -> dict | None:
        q = self._by_call.get(call)
        return self._quotes[q] if q else None

    def list(self) -> list[dict]:
        return list(self._quotes.values())
