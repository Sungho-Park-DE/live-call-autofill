# Results — real adapters, measured (2026-10-24)

What the live services did on our test calls, and what we decided from it. Every number below
comes from a command in [README.md](README.md); raw outputs are in `eval/results/` (git-ignored,
re-create them with the commands at the end).

## Goal and what the data says

Can Jev take routine work off the person on the phone, during the call, for parts orders and
customer questions? Measured here: how much of the form is filled correctly while the caller is
still talking. Not measured: the agent's time saved (that needs a study with real agents).

- **Filled before hang-up:** of 78 field values the caller gave, Jev filled 74–75 (95 %), **0 wrong**;
  all 24 fields that should stay empty stayed empty.
- **Why during the call and not after it:** a general LLM after hang-up also saves typing, and only
  ~2 s later. What it cannot do is show *during* the call what is still missing, so the agent asks
  now instead of calling back. Jev's held fields are exactly that list.
- **Why Jev for that:** it returns a probability, so the app fills only what is certain and leaves
  the rest for the agent; Sonnet answers every field as certain. And at 0.43 s (p90 0.44 s) it can
  re-decide every few seconds on partial transcripts; Sonnet takes 1.5–2.2 s per call.
- **What still limits it:** the speech service cuts utterances late on calls without pauses
  (section 3), so the draft trails the conversation by up to ~30 s until the app also decides on
  partial transcripts.

**Setup.** 22 labelled calls in [`cases.json`](cases.json): 18 invented (3 scripted demos + 15 short
ones) and 4 recorded test calls (`audio_samples/`: staged calls read by two people in English, one mono
track, 57–70 s each; no customer audio).
102 checks in total (field value after the whole call, plus checkpoints mid-call, e.g. the side
must be `left` before the caller corrects it and `right` after). 58 decider calls per run.

## 1. Who fills the form: keywords vs Jev vs a general LLM

Same questions, same options ("not said yet" included), same order, threshold 0.6.

| Decider | Right | **Wrong** | Held (of which correctly empty) | Latency p50 / p90 |
|---|---|---|---|---|
| Keyword baseline (74 invented checks) | 57 | **3** | 14 | ~1 ms |
| Jev `jev-1.14.0` (102 checks, 3 runs) | 74–75 | **0** | 27–28 (24) | **427 / 439 ms** |
| Claude Sonnet 5.5 (102 checks, 3 runs) | 77 | **0** | 25 (24) | 1528 / 2224 ms |

- The keyword baseline gets corrections wrong ("Atto… no, a Vera" → Atto) and reads
  "driver's side back door" as tailgate. Jev and Sonnet get all of these right.
- Neither LLM suggested a wrong value in 6 runs. The difference is 3–4 checks where Jev chose the
  right value but below 0.6 (e.g. "both front doors" → `both`; a hood mentioned in a return call).
- Jev latency is flat (run p50s 427/427/427 ms). Its slowest call, ~1.9 s, was the first call of
  every run (connection setup); without it the maximum was 742 ms. Sonnet's tail reaches 4–5 s.
- Sonnet returns no probability, so every answer is "certain"; it cannot hold back an unsure value
  the way a threshold on Jev does. We measured speed and accuracy, not that risk.

**Decision:** Jev for the live draft (it runs on every final transcript; 0.4 s vs 1.5–2.2 s is
visible on screen). A general LLM fits offline work where latency does not matter, e.g. a nightly
second opinion that flags calls where the two disagree.

## 2. Jev settings

| Question | Result | Decision |
|---|---|---|
| Threshold | No wrong suggestions at any threshold 0.3–0.95; above 0.6 only right answers get dropped (0.95: 64 right instead of 74) | keep **0.6** (one borderline intent sits at 0.46–0.58) |
| Confidence measure | Probability of the chosen option is consistently higher on right answers than Jev's own spread-based confidence (0.56 vs 0.34 on the same answer) and misses fewer | keep **probability** |
| "not said yet" option | All 13 + 11 checks that should stay empty stayed empty | **keep** |
| Option order bias | Options reversed on all 18 invented calls: 0 answers changed | no measurable first-option bias |

## 3. Speech to text on the recorded test calls (ElevenLabs Scribe v2 Realtime)

| Finding | Detail |
|---|---|
| Transcripts are good | Corrections ("driver's side… no, sorry… passenger side"), VIN digits ("731842"), order numbers ("SH4529") come through cleanly |
| Invented model names need keyterms | Without them "Atto" became "auto" / "ATO"; with `ELEVENLABS_KEYTERMS=Atto,Vera,Ridge` it is "Atto" (server echoes the terms) |
| Utterances are cut late | The recordings have almost no pauses (longest 0.95 s, most 0.3–0.6 s). With default VAD: 2 finals per call, the first after ~40 s. With `ELEVENLABS_VAD_SILENCE_SECS=0.4`: 3–8 finals, but gaps of up to 30 s remain, and the same cuts on every run |
| Consequence | The form updates only on final transcripts, so a car named at ~35 s appeared in the draft at ~60 s. Fix belongs in the app: also decide on partial transcripts, debounced |

Recommended settings: `ELEVENLABS_KEYTERMS=Atto,Vera,Ridge`, `ELEVENLABS_VAD_SILENCE_SECS=0.4`.

## 4. The 4 recorded test calls end to end (STT → Jev)

Labels written by the owner for each call (what the quote should contain), mapped to the form fields (extra facts such as
VIN, order number and photo promised are kept under `truth` in `cases.json`, not scored).

| Call | What happens | Jev |
|---|---|---|
| demo1 | Vera, "front fender… actually the back one… rear quarter panel", damage unknown | quarter panel ✅, severity held ✅ |
| demo2 | Delivery question about a headlamp order, no quote | intent `other` ✅, headlamp at 0.51–0.59 (held) |
| demo3 | Ridge, side mirror, "driver's side… no, passenger side" | `left` mid-call, `right` at the end ✅ |
| demo4 | Atto, rear bumper cracked, dented, scratched | all fields ✅ |

28 checks: 16 right, **0 wrong**, 12 held (11 of them correctly empty).

## 5. Limits

- 102 checks, mostly written by us. "0 wrong" bounds the error rate only loosely (≈3 % at 95 %
  confidence, rule of three).
- 4 recorded test calls, one speaker pair, **English only**, mono, 16 kHz. Other languages, accents
  and narrowband phone audio (8 kHz) are **not measured**; results may not carry over.
- Latency measured from the developer's PC only; cost not measured.
- The recording cases freeze one STT run as their lines; a different VAD setting changes the line
  numbers used by mid-call checkpoints.

## 6. How this would be used in a real shop (not built here)

The parts trade identifies the exact part through the VIN: the part name comes from the call, but
which part number fits this model and year is fixed by the VIN. The pieces measured above fit that
flow:

```
speech partials ──► VIN caught by a pattern (not by the LLM) ──► staff confirms with one click
                                                                    │
                                                                    ▼
                                                parts catalogue lookup by VIN → model, year
                                                                    │
Jev: part (zone) + side + severity ─────────────────────────────────┴──► fitting part numbers (left/right)
```

- **VIN from partials, by pattern.** The digits are in the partial transcript seconds after they
  are spoken, long before the late final, so VIN capture does not wait for the VAD.
  A choice model is the wrong tool for free digits; a pattern next to "VIN" / "last six digits" is
  free and instant.
- **Confirm, don't auto-submit.** A wrong VIN means a wrong part, and the last digits carry no check
  digit. Cross-check: the model decoded from the VIN against the model Jev heard.
- **Side matters.** Left and right parts have different numbers; the correction handling above is
  what makes that field usable.
- **Daily recordings + the quotes written afterwards** give labelled data for free: score "wrong"
  (suggested value differs from the quote) as the hard metric, and "held" only as a soft one, since
  some quote values come from photos or VIN lookups after the call.

## Reproduce

```
python -m pytest -q eval                                   # offline, no keys
python -m eval decider --decider fake                      # keyword baseline
python -m eval decider --order                             # Jev (JEV_API_KEY)
python -m eval decider --decider sonnet                    # Sonnet (ANTHROPIC_API_KEY)
python -m eval stt recordings/demo3.wav --decide           # STT + Jev on a recording (ELEVENLABS_API_KEY)
```

Recordings: convert `audio_samples/*.mp3` to 16 kHz mono 16-bit WAV in `recordings/demo1.wav` … `demo4.wav`.
