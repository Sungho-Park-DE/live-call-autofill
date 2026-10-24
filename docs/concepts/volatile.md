# Volatile decisions

| Decision | Evidence it will change | Hidden in |
|---|---|---|
| Speech-to-text vendor (ElevenLabs Scribe v2 Realtime) and its audio format | External service; measured on English test calls only (eval/RESULTS.md); other vendors such as Whisper are candidates | `app/adapters/` — port `SpeechToText`, chosen by `CTQ_STT` (`fake` replays text) |
| Decision model (Jev by TypeSafe AI) and its request shape | External service released 2026-09; measured on English test calls only; a plain LLM with structured output is the fallback | `app/adapters/` — port `Decider`, chosen by `CTQ_DECIDER` (`fake` = keyword matching) |
| Confidence threshold per field | Has to be tuned against measured accuracy | `app/settings.py` `FIELDS[*].threshold` |
| How often the draft is re-decided while the caller is still talking | Depends on the decision model's latency and cost and on how late the speech service closes an utterance (eval/RESULTS.md, section 3) | `app/settings.py` `PARTIAL_DECIDE_SECS` (`CTQ_PARTIAL_DECIDE_SECS`, 0 = final segments only) |
| Which fields the form asks and which are required | The shop decides what a quote needs | `app/settings.py` `FIELDS` (including the question to ask the caller), `REQUIRED` |
| Companion-zone table and its rules (30% share, n ≥ 20, 30-day merge) | Rebuilt whenever sales data grows; the threshold is a business rule ("removing is easier than adding") | `app/data/zones.json` built by `analysis/` (constants at its top); read by `accident_v1`; off with `CTQ_COMPANIONS=0` |
| Parts data | A real catalog would replace the invented one | `catalog_v1` data; a real lookup would be a new adapter |
