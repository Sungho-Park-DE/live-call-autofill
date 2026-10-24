# Adapters

Everything that talks to an outside service lives here, and nowhere else. Concepts (`app/modules`) never import this folder; only `app/syncs` and `app/main.py` do.

| Port (`ports.py`) | Fake (`fakes.py`) | Real | Chosen by |
|---|---|---|---|
| `SpeechToText.stream(audio) -> Segment…` | `ScriptedSpeech` | `elevenlabs.py` `ElevenLabsSpeech` | `CTQ_STT=fake\|elevenlabs` |
| `Decider.decide(transcript, questions) -> {key: Answer}` | `KeywordDecider` | `jev.py` `JevDecider` | `CTQ_DECIDER=fake\|jev` |

Contract for a real adapter:
- a class with `name: str` and a `@classmethod from_env(cls)` that reads its key from the environment (`.env` is loaded by `app/settings.py`) and fails with a clear message if the key is missing;
- `Decider`: return only option values that were offered; confidence in [0, 1]; omit a key rather than guess;
- `SpeechToText`: audio is PCM s16le mono 16 kHz (`ports.AUDIO_SAMPLE_RATE`); yield partials and finals as they arrive;
- failures: a `Decider` raises `ports.DeciderError` and a `SpeechToText` raises `ports.SpeechError` (subclass them, e.g. `JevError`, `ElevenLabsError`) after its own retries. `Flow` and `app/main.py` catch exactly these, show the problem to the person and keep the call going; any other exception is a bug and is not hidden;
- a `Decider` may offer `async warm()` that opens its connection before the first question; it is optional and must not raise for network problems;
- never log transcripts or audio to files in the repository.
