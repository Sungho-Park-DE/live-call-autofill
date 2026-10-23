# eval — measuring the real adapters

Only this folder calls the live APIs. Keys come from `.env`; results go to `eval/results/` and audio to `recordings/` (both git-ignored).

| Command | Needs | What it measures |
|---|---|---|
| `python -m pytest -q eval` | nothing | adapters against a fake WebSocket / HTTP server; harness runs with the keyword baseline |
| `python -m eval decider --decider fake` | nothing | keyword baseline on `cases.json` |
| `python -m eval decider [--order]` | `JEV_API_KEY` | Jev: right / wrong / held per field, threshold sweep for both confidence measures, latency; `--order` re-asks with options reversed |
| `python -m eval tts` | `ELEVENLABS_API_KEY` | writes `recordings/<demo>.wav` from `demo/calls/` (synthetic voice) |
| `python -m eval stt recordings/2-correction.wav [--decide]` | `ELEVENLABS_API_KEY` (+ `JEV_API_KEY` with `--decide` and `CTQ_DECIDER=jev`) | segments, latency, WER against the demo text; with `--decide` the whole Flow, checked against `cases.json` |

`cases.json`: invented calls. `expect` is the field value after the whole call (`null` = nothing should be suggested); `after` adds checkpoints after line N, e.g. the correction call must say `left` after line 2 and `right` after line 3. The app decides after every final line, and so does the eval.

Confidence measures for Jev (`JEV_CONFIDENCE`):
- `probability` (default): probability of the chosen option. Every question also offers "not said yet", so this reads as "how likely the caller said this value".
- `jev`: Jev's own confidence, `(p_max - 1/n) / (1 - 1/n)`; depends on the number of options (n = 3 for Atto/Vera/Ridge + not said, 15 for zones).

Optional settings for the STT adapter: `ELEVENLABS_KEYTERMS=Atto,Vera,Ridge` biases recognition towards the invented model names; `eval stt` prints whether the server echoed them. `ELEVENLABS_VAD_SILENCE_SECS` (0.192–3.0) sets how long a pause ends an utterance.
