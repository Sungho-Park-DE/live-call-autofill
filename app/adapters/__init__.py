"""The one place where a real or a fake outside service is chosen (settings CTQ_STT, CTQ_DECIDER)."""
from __future__ import annotations

from .fakes import KeywordDecider, ScriptedSpeech
from .ports import Decider, SpeechToText


def make_speech(name: str) -> SpeechToText:
    if name == "fake":
        return ScriptedSpeech()
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsSpeech

        return ElevenLabsSpeech.from_env()
    raise ValueError(f"unknown CTQ_STT={name!r}")


def make_decider(name: str) -> Decider:
    if name == "fake":
        return KeywordDecider()
    if name == "jev":
        from .jev import JevDecider

        return JevDecider.from_env()
    raise ValueError(f"unknown CTQ_DECIDER={name!r}")
