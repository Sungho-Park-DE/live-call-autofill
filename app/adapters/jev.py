"""Decider backed by Jev (TypeSafe AI System One API).

Each Question becomes one Choice question in a single request. Every Choice also gets a
"not said yet" option, so a field the caller has not talked about comes back as no answer
instead of a guess. The confidence passed on is the probability of the chosen option
(`confidence="probability"`) or Jev's own spread-based confidence (`confidence="jev"`);
eval/ measures both.

Request and response shape: https://docs.typesafe.ai/primitives/choice.md
Environment: JEV_API_KEY (or TYPESAFE_API_KEY), optional JEV_MODEL, JEV_URL, JEV_CONFIDENCE.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Sequence

import httpx

from .ports import Answer, DeciderError, Question

log = logging.getLogger(__name__)

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
NOT_SAID = "not said yet"
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class JevError(DeciderError):
    pass


class JevDecider:
    name = "jev"

    def __init__(self, api_key: str, *, model: str = MODEL, url: str = URL, confidence: str = "probability",
                 abstain: bool = True, timeout: float = 5.0, retries: int = 2,
                 client: httpx.AsyncClient | None = None) -> None:
        if confidence not in ("probability", "jev"):
            raise ValueError(f"confidence must be 'probability' or 'jev', not {confidence!r}")
        self.api_key = api_key
        self.model = model
        self.url = url
        self.confidence = confidence
        self.abstain = abstain
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self.last: dict[str, Any] = {}  # model, usage and seconds of the last call (no transcript)

    @classmethod
    def from_env(cls) -> "JevDecider":
        key = os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise RuntimeError("CTQ_DECIDER=jev needs JEV_API_KEY in .env (key from https://console.typesafe.ai/keys)")
        return cls(key, model=os.environ.get("JEV_MODEL", MODEL), url=os.environ.get("JEV_URL", URL),
                   confidence=os.environ.get("JEV_CONFIDENCE", "probability"))

    def request(self, transcript: str, questions: Sequence[Question]) -> dict:
        return {
            "model": self.model,
            "state": {"call_transcript": transcript},
            "questions": {q.key: self._choice(q) for q in questions},
        }

    def _choice(self, q: Question) -> dict:
        criteria: dict[str, str | None] = {
            o.value: (f"Callers may also say: {o.hint}" if o.hint else None) for o in q.options}
        if self.abstain and NOT_SAID not in criteria:
            criteria[NOT_SAID] = "The caller has not said this so far, or it cannot be told from the call."
        return {
            "type": "choice",
            "instructions": (f"{q.prompt} Judge only from what the caller says in `call_transcript`. "
                             "If the caller corrects themselves, the later statement counts."),
            "criteria": criteria,
        }

    async def warm(self) -> None:
        """Opens the HTTPS connection before the first question, so the first answer does not pay for it."""
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        self._client = client
        try:
            await client.head(self.url, timeout=self.timeout)
        except httpx.HTTPError:
            log.info("Jev warm-up failed; the first question opens the connection")

    async def ask(self, transcript: str, questions: Sequence[Question]) -> dict:
        """One raw API call; returns the parsed JSON response."""
        body = self.request(transcript, questions)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        self._client = client
        delay = 0.2
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                r = await client.post(self.url, json=body, headers=headers, timeout=self.timeout)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt == self.retries:
                    raise JevError(f"Jev request failed: {type(e).__name__}") from None
            else:
                if r.status_code == 200:
                    data = r.json()
                    self.last = {"model": data.get("model"), "usage": data.get("usage"),
                                 "seconds": time.perf_counter() - started, "attempts": attempt + 1}
                    return data
                if r.status_code == 401:
                    raise JevError("Jev rejected the API key (401); check JEV_API_KEY")
                if r.status_code not in RETRY_STATUS or attempt == self.retries:
                    raise JevError(f"Jev returned {r.status_code}: {r.text[:300]}")
            log.warning("Jev attempt %d failed, retrying", attempt + 1)
            await asyncio.sleep(delay)
            delay *= 2.5
        raise AssertionError("unreachable")

    def answers(self, response: dict, questions: Sequence[Question]) -> dict[str, Answer]:
        out: dict[str, Answer] = {}
        got = response.get("answers") or {}
        for q in questions:
            a = got.get(q.key)
            offered = {o.value for o in q.options}
            if not a or a.get("type") != "choice" or a.get("choice") not in offered:
                continue
            if self.confidence == "jev":
                c = a.get("confidence")
            else:
                c = (a.get("probabilities") or {}).get(a["choice"])
            if c is None:
                continue
            out[q.key] = Answer(a["choice"], min(1.0, max(0.0, float(c))))
        return out

    async def decide(self, transcript: str, questions: Sequence[Question]) -> dict[str, Answer]:
        if not transcript.strip() or not questions:
            return {}
        return self.answers(await self.ask(transcript, questions), questions)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
