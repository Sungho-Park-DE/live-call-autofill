"""Comparison decider for eval only: a general LLM (Claude Sonnet) answering the same questions
as Jev, so speed and accuracy can be put side by side. Not wired into the app.

Same content as the Jev request: per question the prompt, the options with their hints and a
"not said yet" option, answered in one call with a JSON schema output (output_config.format;
Sonnet 5.5 rejects a forced tool_choice). Claude returns no probabilities, so
every answer gets confidence 1.0 and the threshold table is flat for this decider.

Environment: ANTHROPIC_API_KEY; optional CLAUDE_MODEL (default claude-sonnet-5-5).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Sequence

import httpx

from app.adapters.jev import NOT_SAID, RETRY_STATUS
from app.adapters.ports import Answer, Question

URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"
SYSTEM = ("You fill in a parts-quote form from a phone call transcript between a parts shop and a caller. "
          "Judge only from what the caller says. If the caller corrects themselves, the later statement "
          f"counts. If something has not been said or cannot be told, answer {NOT_SAID!r}.")


class SonnetError(RuntimeError):
    pass


class SonnetDecider:
    name = "sonnet"

    def __init__(self, api_key: str, *, model: str = MODEL, url: str = URL, timeout: float = 30.0,
                 retries: int = 2, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self.last: dict[str, Any] = {}

    @classmethod
    def from_env(cls) -> "SonnetDecider":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("--decider sonnet needs ANTHROPIC_API_KEY in .env")
        return cls(key, model=os.environ.get("CLAUDE_MODEL", MODEL))

    def request(self, transcript: str, questions: Sequence[Question]) -> dict:
        props = {}
        for q in questions:
            hints = "; ".join(f"{o.value}: callers may also say {o.hint}" for o in q.options if o.hint)
            props[q.key] = {"type": "string", "enum": [o.value for o in q.options] + [NOT_SAID],
                            "description": q.prompt + (f" ({hints})" if hints else "")}
        return {
            "model": self.model,
            "max_tokens": 400,
            "system": SYSTEM,
            "output_config": {"format": {"type": "json_schema", "schema": {
                "type": "object", "properties": props, "required": list(props), "additionalProperties": False}}},
            "messages": [{"role": "user", "content": f"<call_transcript>\n{transcript}\n</call_transcript>"}],
        }

    async def ask(self, transcript: str, questions: Sequence[Question]) -> dict:
        body = self.request(transcript, questions)
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        self._client = client = self._client or httpx.AsyncClient(timeout=self.timeout)
        delay = 0.5
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                r = await client.post(self.url, json=body, headers=headers, timeout=self.timeout)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt == self.retries:
                    raise SonnetError(f"Claude request failed: {type(e).__name__}") from None
            else:
                if r.status_code == 200:
                    data = r.json()
                    self.last = {"model": data.get("model"), "usage": data.get("usage"),
                                 "seconds": time.perf_counter() - started, "attempts": attempt + 1}
                    return data
                if r.status_code == 401:
                    raise SonnetError("Claude rejected the API key (401); check ANTHROPIC_API_KEY")
                if r.status_code not in RETRY_STATUS or attempt == self.retries:
                    raise SonnetError(f"Claude returned {r.status_code}: {r.text[:300]}")
            await asyncio.sleep(delay)
            delay *= 2.5
        raise AssertionError("unreachable")

    @staticmethod
    def answers(response: dict, questions: Sequence[Question]) -> dict[str, Answer]:
        text = next((b.get("text") or "" for b in response.get("content") or [] if b.get("type") == "text"), "")
        try:
            given = json.loads(text) if text else {}
        except json.JSONDecodeError:
            given = {}
        out = {}
        for q in questions:
            v = given.get(q.key)
            if v in {o.value for o in q.options}:
                out[q.key] = Answer(v, 1.0)
        return out

    async def decide(self, transcript: str, questions: Sequence[Question]) -> dict[str, Answer]:
        if not transcript.strip() or not questions:
            return {}
        return self.answers(await self.ask(transcript, questions), questions)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
