# call-to-quote

**While a customer is still on the phone, the quote form fills itself in — and the person on the call has the last word.**

A live phone call is turned into text (speech-to-text), a fast *decision model* picks the car, body zone, side and damage level from fixed lists, and the parts quote is pre-filled as **suggestions**. Nothing is sent until the person confirms. Anything the person types is never overwritten by the machine.

![Demo: a caller corrects "left" to "right" and the draft follows](docs/img/demo-correction.png)

> Status: the pipeline, the human-in-the-loop form and the keyless demo work and are tested. The real speech-to-text (ElevenLabs Scribe v2 Realtime) and decision-model (Jev) adapters are being built and measured; see [Roadmap](#roadmap).

## Why

This grew out of automating an auto-parts dealership in Korea. About 95% of orders arrive by phone: a repair shop calls, says something like *"a fender for the Vera — no, not left, the right one"*, and the dealer types it into a parts catalog and then into the dealer's ERP while still talking.

The dealership already runs a version-1 system I built (not in this repository, because it contains customer data and talks to systems I cannot publish):
- a browser quote tool used every day: pick car and damage, get the parts list from a VIN lookup in the parts catalog;
- a desktop bot that types the confirmed quote into the dealer ERP through its scripting interface, restricted to an allowlist of screens and functions, refusing anything that looks like delete, print or invoice;
- caller-ID and recording watchers on the office PC, and a self-healing server that restarts what stops answering.

This repository is the next step, rebuilt from scratch with invented data: **take the typing out of the call itself.**

## How it works

```mermaid
flowchart LR
  mic[Phone / mic audio] -->|PCM 16 kHz| stt[SpeechToText adapter<br/>ElevenLabs · fake]
  typed[Typed line / demo call] --> call
  stt -->|partial + final segments| call[Call<br/>transcript]
  call -->|each final segment| dec[Decider adapter<br/>Jev · fake]
  cat[Catalog<br/>options + parts] -->|choices| dec
  dec -->|answer + confidence| sync{confidence ≥ threshold?}
  sync -->|yes| draft[Draft<br/>suggested value]
  sync -->|no| retract[Draft<br/>retract suggestion]
  person[Person on the call] -->|edits win, always| draft
  person -->|Confirm| quote[Quote<br/>lines from Catalog]
```

**Why a decision model, not a chat LLM.** The form only ever needs answers from fixed lists (which car, which zone, which side, how bad). A decision model such as [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) returns one probability per allowed option instead of generating text: it cannot invent a part, it is fast enough to re-decide after every sentence, and its confidence becomes a simple threshold — below it the field stays empty and the person decides. Exact part numbers never come from the model; they come from the catalog.

**Design rules that come from the real shop:**
- *The person has the last word.* Machine values are shown as suggestions with their confidence; a value the person set is never overwritten; nothing is created without **Confirm**.
- *Empty beats wrong.* A low-confidence answer retracts an earlier suggestion instead of leaving a stale guess.
- *Last mention wins.* Callers correct themselves ("left — no, right"); every final sentence triggers a fresh decision over the whole transcript, and answers to older transcripts are dropped.
- *When unsure, include.* If the side is unknown, both sides go on the quote — removing a line is easier than adding one.

## Architecture

The code is split into small, independent concepts, each a replaceable module:

| Concept | Purpose | Code |
|---|---|---|
| [Call](docs/concepts/Call.md) | the transcript of a live call, partials replaced by finals | `app/modules/call_v1` |
| [Draft](docs/concepts/Draft.md) | a form a machine may pre-fill; the person always wins | `app/modules/draft_v1` |
| [Catalog](docs/concepts/Catalog.md) | choices and the parts for car × zone × side × damage | `app/modules/catalog_v1` |
| [Quote](docs/concepts/Quote.md) | confirmed quotes | `app/modules/quote_v1` |

- Concepts never import each other; they meet only in [syncs](docs/concepts/syncs.md) (`app/syncs/flow.py`).
- Outside services sit behind two ports in `app/adapters/` (`SpeechToText`, `Decider`), each with a fake. Real and fake are chosen in one place by settings — the whole app and every test run without keys or network.
- Things known to change are listed in [volatile.md](docs/concepts/volatile.md): vendors, thresholds, the field list, the parts data.
- A material change can ship as a new module version (`draft_v2`) behind a feature flag (`CTQ_FLAG_<NAME>=1`, see `app/flags.py`), so it can be switched off without touching anything else.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"        # Windows: .venv\Scripts\pip
cp .env.example .env                       # fake engines by default, no keys needed
.venv/bin/python -m uvicorn app.main:app --port 8800
```

Open http://127.0.0.1:8800, press **Start call**, then **Play demo call** — or type what a caller would say. Three scripted calls are included: a simple one, a mid-call correction, and one where the damage is unknown so the person has to pick it.

Tests (about a second, no network): `.venv/bin/python -m pytest -q`

With real engines: set `CTQ_STT=elevenlabs`, `CTQ_DECIDER=jev` and the keys in `.env`; the **Mic** button then streams your microphone.

## Roadmap

- [ ] ElevenLabs Scribe v2 Realtime adapter (8 kHz phone audio)
- [ ] Jev adapter, and an evaluation on recorded test calls: accuracy per field, latency, and the threshold that keeps wrong suggestions rare
- [ ] Words that phone speech-to-text gets wrong (model names, part words, numbers) — keyword boosting with the catalog's own words
- [ ] Phone audio into the PC (handset tap or line adapter) instead of a microphone
- [ ] Several zones per call (one draft per zone)

## Data and privacy

All car names, part numbers and calls in this repository are invented. No real customer audio or transcripts are stored here. In production, sending call audio to outside services is a data-protection decision that has to be made with the business owner, and customers have to be told.
