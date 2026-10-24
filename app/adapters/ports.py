"""Contracts for the two outside services. Concepts never see these; only app/syncs does.

Audio format for SpeechToText: raw PCM, signed 16-bit little-endian, mono, 16 kHz,
sent by the browser in chunks of about 100 ms.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol, Sequence

AUDIO_SAMPLE_RATE = 16_000


class SpeechError(RuntimeError):
    """A SpeechToText adapter lost its service (network, auth, server error). The call itself goes on."""


class DeciderError(RuntimeError):
    """A Decider adapter could not answer (network, auth, rate limit). The draft keeps its values."""


@dataclass(frozen=True)
class Segment:
    text: str
    final: bool


class SpeechToText(Protocol):
    name: str

    def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Segment]:
        """Consume audio chunks until the iterator ends; yield partial and final segments.

        A partial replaces the previous partial; a final closes the current utterance.
        """
        ...


@dataclass(frozen=True)
class Option:
    value: str
    hint: str = ""  # other words people use for this value, comma separated


@dataclass(frozen=True)
class Question:
    key: str
    prompt: str
    options: Sequence[Option]


@dataclass(frozen=True)
class Answer:
    value: str  # always one of the question's option values
    confidence: float  # 0..1


class Decider(Protocol):
    name: str

    async def decide(self, transcript: str, questions: Sequence[Question]) -> dict[str, Answer]:
        """Answer every question it can. A missing key means "no answer"."""
        ...
