# Volatile decisions

| Decision | Evidence it will change | Hidden in |
|---|---|---|
| Speech-to-text vendor (ElevenLabs Scribe v2 Realtime) and its audio format | External service; accuracy on phone audio is unmeasured, other vendors such as Whisper are candidates | `app/adapters/` — port `SpeechToText`, chosen by `CTQ_STT` (`fake` replays text) |
| Decision model (Jev by TypeSafe AI) and its request shape | External service released 2026-09; a plain LLM with structured output is the fallback | `app/adapters/` — port `Decider`, chosen by `CTQ_DECIDER` (`fake` = keyword matching) |
| Confidence threshold per field | Has to be tuned against measured accuracy | `app/settings.py` `FIELDS[*].threshold` |
| Which fields the form asks and which are required | The shop decides what a quote needs | `app/settings.py` `FIELDS`, `REQUIRED` |
| Parts data | A real catalog would replace the invented one | `catalog_v1` data; a real lookup would be a new adapter |
