"""Stand-ins that need no network or keys: tests, CI and the keyless demo use these."""
from __future__ import annotations

import re
from typing import AsyncIterator, Iterable, Sequence

from .ports import Answer, Question, Segment


class ScriptedSpeech:
    """Ignores the audio and yields a fixed list of segments once the audio ends."""

    name = "fake"

    def __init__(self, segments: Iterable[Segment] = ()):
        self._segments = list(segments)

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Segment]:
        async for _ in audio:
            pass
        for seg in self._segments:
            yield seg


def _words(option_value: str, hint: str) -> list[str]:
    words = [option_value] + [w.strip() for w in hint.split(",")]
    return [w for w in words if w]


def _pattern(phrase: str) -> re.Pattern[str]:
    """Word-boundary prefix match: "dent" finds "dented" but not "accident"."""
    words = phrase.lower().split()
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"\w*")


def _last(text: str, phrase: str) -> tuple[int, int] | None:
    """(end, length) of the last match, so a longer phrase ending at the same place wins."""
    last = None
    for m in _pattern(phrase).finditer(text):
        last = (m.end(), m.end() - m.start())
    return last


class KeywordDecider:
    """Picks the option whose value or hint word appears last in the transcript.

    Deliberately simple: it shows the pipeline without a model. Corrections such as
    "left... no, right" work because the last mention wins.
    """

    name = "keywords"

    async def decide(self, transcript: str, questions: Sequence[Question]) -> dict[str, Answer]:
        text = transcript.lower()
        answers: dict[str, Answer] = {}
        for q in questions:
            best: tuple[tuple[int, int], str] | None = None
            hits = 0
            for opt in q.options:
                found = [p for w in _words(opt.value, opt.hint) if (p := _last(text, w))]
                if found:
                    pos = max(found)
                    hits += 1
                    if best is None or pos > best[0]:
                        best = (pos, opt.value)
            if best is not None:
                answers[q.key] = Answer(best[1], 0.9 if hits == 1 else 0.7)
        return answers
