from __future__ import annotations

import itertools
import time


class UnknownCall(KeyError):
    pass


class CallClosed(RuntimeError):
    pass


class CallBook:
    def __init__(self) -> None:
        self._calls: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def start(self, caller: str) -> str:
        call = f"call-{next(self._ids)}"
        self._calls[call] = {
            "caller": caller,
            "started_at": time.time(),
            "ended_at": None,
            "finals": [],
            "partial": "",
        }
        return call

    def _get(self, call: str) -> dict:
        try:
            return self._calls[call]
        except KeyError:
            raise UnknownCall(call) from None

    def hear(self, call: str, text: str, final: bool) -> int:
        c = self._get(call)
        if c["ended_at"] is not None:
            raise CallClosed(call)
        text = text.strip()
        if final:
            if text:
                c["finals"].append(text)
            c["partial"] = ""
        else:
            c["partial"] = text
        return len(c["finals"])

    def end(self, call: str) -> None:
        c = self._get(call)
        if c["ended_at"] is None:
            c["ended_at"] = time.time()

    def transcript(self, call: str) -> str:
        c = self._get(call)
        return " ".join(c["finals"] + ([c["partial"]] if c["partial"] else []))

    def version(self, call: str) -> int:
        return len(self._get(call)["finals"])

    def get(self, call: str) -> dict:
        c = self._get(call)
        return {
            "id": call,
            "caller": c["caller"],
            "started_at": c["started_at"],
            "ended": c["ended_at"] is not None,
            "finals": list(c["finals"]),
            "partial": c["partial"],
        }
