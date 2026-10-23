# Concept: Call [Call]

**Purpose:** Keep what was said on a live phone call, as it is being said, so other parts can react while the call is still going.

**Operational principle:** If a call is started and the speech-to-text engine reports "Atto front bum..." (partial) and then "Atto front bumper" (final),
then the transcript shows "Atto front bumper" once, and the call's version goes from 0 to 1.

**State:**
- calls: Call -> { caller: str, started_at, ended_at?, finals: list str, partial: str }

**Actions:**
- start(caller: str) -> Call
  - effects: new call, version 0, empty transcript
- hear(call: Call, text: str, final: bool) -> version: int
  - requires: call exists and has not ended
  - effects: a partial replaces the previous partial; a final is appended to finals and clears the partial
- end(call: Call)
  - requires: call exists
  - effects: ended_at is set; further `hear` is refused

**Queries:**
- transcript(call) -> str        finals joined, plus the current partial
- version(call) -> int           number of finals so far (used to drop stale decisions)
- get(call) -> dict

**Not this concept's job:** turning audio into text (the speech-to-text adapter), deciding what the caller wants (the decider adapter, via a sync), any quote fields (Draft).
