# eval/runs — raw outputs cited in RESULTS.md

Copies of the measurement JSONs behind the tables in [../RESULTS.md](../RESULTS.md) (written and synthetic test calls only, no customer data).

| File | Backs |
|---|---|
| `decider-keywords-20261024-082926.json` | section 1, keyword baseline (74 invented checks) |
| `decider-jev-20261024-170213.json`, `-170420`, `-170626` | section 1, Jev, 3 runs of 102 checks (75 / 74 / 74 right, 0 wrong), sections 2 and 5 |
| `decider-sonnet-20261024-170146.json`, `-170353`, `-170559` | section 1, Claude Sonnet 5.5, 3 runs of 102 checks (77 right, 0 wrong) |
| `decider-jev-20261025-033619-order.json` | section 2, option order: `python -m eval decider --order`, reversed options on all 22 calls (`order_cases: 22`, `order_flips: []`); also a fourth full Jev run (75 right, 0 wrong at 0.6) |
| `decider-jev-20261024-164438.json` | section 4, Jev on the 4 recorded calls (28 checks: 16 right, 12 held) |
| `stt-demo1-…164343.json` … `stt-demo4-…164335.json` | section 3 and 4, speech-to-text finals of the recordings (`ELEVENLABS_VAD_SILENCE_SECS=0.4`, keyterms on) |

| `partial/partial-demoN-finals-only.json`, `partial/partial-demoN-2.5s.json` | section 4b, draft changes over time with and without partial decisions (written by a throwaway script that streams the recording through the same Flow; `python -m eval stt recordings/demoN.wav --decide` prints the same changes) |

Commands (see RESULTS.md "Reproduce"): `python -m eval decider --decider fake`, `python -m eval decider`, `python -m eval decider --decider sonnet`, `python -m eval stt recordings/demoN.wav --decide`.
New runs are written to the git-ignored `eval/results/`, not here.
