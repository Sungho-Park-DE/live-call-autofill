# Volatile decisions

| Decision | Evidence it will change | Hidden in |
|---|---|---|
| Speech-to-text vendor (ElevenLabs Scribe v2 Realtime) and its audio format | External service; accuracy on phone audio is unmeasured, other vendors such as Whisper are candidates | `app/adapters/` — port `SpeechToText`, chosen by `CTQ_STT` (`fake` replays text) |
| Decision model (Jev by TypeSafe AI) and its request shape | External service released 2026-09; a plain LLM with structured output is the fallback | `app/adapters/` — port `Decider`, chosen by `CTQ_DECIDER` (`fake` = keyword matching) |
| Confidence threshold per field | Has to be tuned against measured accuracy | `app/settings.py` `FIELDS[*].threshold` |
| Which fields the form asks and which are required | The shop decides what a quote needs | `app/settings.py` `FIELDS`, `REQUIRED` |
| Companion-zone table and its rules (30% share, n ≥ 20, 30-day merge) | Rebuilt whenever sales data grows; the threshold is a business rule ("removing is easier than adding") | `app/data/zones.json` built by `analysis/` (constants at its top); read by `accident_v1`; off with `CTQ_COMPANIONS=0` |
| Parts data | A real catalog would replace the invented one | `catalog_v1` data; a real lookup would be a new adapter |
