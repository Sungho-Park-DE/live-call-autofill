"""Speech to text with ElevenLabs Scribe v2 Realtime over its WebSocket API.

The server cuts utterances itself (commit_strategy=vad): a partial_transcript becomes a
partial Segment, a committed_transcript a final one. When the audio ends we send one manual
commit for the last words and wait until the server has been quiet for `end_quiet` seconds.

Protocol: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
Environment: ELEVENLABS_API_KEY; optional ELEVENLABS_LANGUAGE (default en), ELEVENLABS_KEYTERMS
(comma separated words to bias towards, e.g. the car model names), ELEVENLABS_VAD_SILENCE_SECS,
ELEVENLABS_URL (e.g. wss://api.eu.residency.elevenlabs.io for EU data residency).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, AsyncIterator, Callable, Sequence
from urllib.parse import urlencode

from .ports import AUDIO_SAMPLE_RATE, Segment, SpeechError

log = logging.getLogger(__name__)

URL = "wss://api.elevenlabs.io"
PATH = "/v1/speech-to-text/realtime"
MODEL = "scribe_v2_realtime"
# Server messages that do not end the session.
HARMLESS = {"warning", "commit_throttled", "insufficient_audio_activity"}
FINAL_TYPES = {"committed_transcript", "committed_transcript_with_timestamps"}


class ElevenLabsError(SpeechError):
    pass


def _ws_connect(url: str, headers: dict[str, str]):
    from websockets.asyncio.client import connect

    return connect(url, additional_headers=headers, max_size=2**22)


class ElevenLabsSpeech:
    name = "elevenlabs"

    def __init__(self, api_key: str, *, language: str = "en", keyterms: Sequence[str] = (),
                 vad_silence_secs: float | None = None, url: str = URL, end_quiet: float = 1.5,
                 end_wait: float = 8.0, connect: Callable[[str, dict[str, str]], Any] = _ws_connect) -> None:
        self.api_key = api_key
        self.language = language
        self.keyterms = tuple(k for k in keyterms if k)
        self.vad_silence_secs = vad_silence_secs
        self.base_url = url.rstrip("/")
        self.end_quiet = end_quiet
        self.end_wait = end_wait
        self._connect = connect
        self.session_config: dict = {}  # echoed by the server in session_started

    @classmethod
    def from_env(cls) -> "ElevenLabsSpeech":
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("CTQ_STT=elevenlabs needs ELEVENLABS_API_KEY in .env")
        vad = os.environ.get("ELEVENLABS_VAD_SILENCE_SECS")
        return cls(key, language=os.environ.get("ELEVENLABS_LANGUAGE", "en"),
                   keyterms=[k.strip() for k in os.environ.get("ELEVENLABS_KEYTERMS", "").split(",")],
                   vad_silence_secs=float(vad) if vad else None,
                   url=os.environ.get("ELEVENLABS_URL", URL))

    def url(self) -> str:
        query: list[tuple[str, str]] = [
            ("model_id", MODEL),
            ("language_code", self.language),
            ("audio_format", f"pcm_{AUDIO_SAMPLE_RATE}"),
            ("commit_strategy", "vad"),
        ]
        if self.vad_silence_secs is not None:
            query.append(("vad_silence_threshold_secs", str(self.vad_silence_secs)))
        query += [("keyterms", k) for k in self.keyterms]
        return f"{self.base_url}{PATH}?{urlencode(query)}"

    @staticmethod
    def chunk(pcm: bytes, commit: bool = False) -> str:
        return json.dumps({
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(pcm).decode("ascii"),
            "commit": commit,
            "sample_rate": AUDIO_SAMPLE_RATE,
        })

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Segment]:
        async with self._connect(self.url(), {"xi-api-key": self.api_key}) as ws:
            out: asyncio.Queue[Segment | Exception | None] = asyncio.Queue()
            ended = asyncio.Event()

            async def send() -> None:
                try:
                    async for pcm in audio:
                        if pcm:
                            await ws.send(self.chunk(pcm))
                    await ws.send(self.chunk(b"", commit=True))
                except Exception as e:  # connection gone: receive() reports why
                    if not _closed(e):
                        await out.put(e)
                finally:
                    ended.set()

            async def receive() -> None:
                try:
                    async for raw in ws:
                        msg = json.loads(raw)
                        kind = msg.get("message_type")
                        text = (msg.get("text") or "").strip()
                        if kind == "session_started":
                            self.session_config = msg.get("config") or {}
                        elif kind == "partial_transcript":
                            if text:
                                await out.put(Segment(text, final=False))
                        elif kind in FINAL_TYPES:
                            if text:
                                await out.put(Segment(text, final=True))
                        elif kind in HARMLESS:
                            log.info("ElevenLabs %s", kind)
                        elif "error" in msg:
                            await out.put(ElevenLabsError(f"ElevenLabs {kind}: {msg['error']}"))
                            return
                except Exception as e:
                    if not (_closed(e) and ended.is_set()):
                        await out.put(ElevenLabsError(f"ElevenLabs connection lost: {type(e).__name__}"))
                        return
                await out.put(None)

            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            loop = asyncio.get_running_loop()
            deadline = None
            try:
                while True:
                    after_end = ended.is_set()
                    if after_end and deadline is None:
                        deadline = loop.time() + self.end_wait
                    try:
                        # while audio flows, poll so the end of audio is noticed; afterwards stop
                        # once the server has been quiet for end_quiet (or end_wait has passed)
                        item = await asyncio.wait_for(out.get(), self.end_quiet if after_end else 0.5)
                    except asyncio.TimeoutError:
                        if after_end:
                            break
                        continue
                    if deadline is not None and loop.time() > deadline:
                        if isinstance(item, Segment):
                            yield item
                        break
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield item
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


def _closed(e: BaseException) -> bool:
    try:
        from websockets.exceptions import ConnectionClosed
    except ImportError:  # pragma: no cover
        return False
    return isinstance(e, ConnectionClosed)
