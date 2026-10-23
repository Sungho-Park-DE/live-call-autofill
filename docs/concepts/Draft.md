# Concept: Draft [Target]

**Purpose:** A form that a machine may pre-fill while a person works, where the person always has the last word and nothing counts until the person confirms.

**Operational principle:** If the machine suggests `car = Atto` (0.91), then the field shows Atto marked as a suggestion;
if the person then picks Vera, a later suggestion of Atto no longer changes the field;
if the person confirms, the values are frozen and returned, and further suggestions or edits are refused.

**State:**
- drafts: Target -> { fields: field -> Entry, confirmed: bool }
- Entry = { value: str, origin: "suggested" | "human", confidence: float?, source: str? }

**Actions:**
- open(target)
  - effects: empty draft
- suggest(target, field, value, confidence, source) -> "applied" | "kept-human" | "unchanged"
  - requires: draft open and not confirmed
  - effects: if the field is human-set nothing changes ("kept-human"); otherwise the entry becomes this suggestion
- retract(target, field) -> bool
  - requires: draft open and not confirmed
  - effects: removes the field only if its origin is "suggested" (the machine is no longer sure)
- set(target, field, value)            the person types or picks a value
  - requires: draft open and not confirmed
  - effects: entry with origin "human"; an empty value clears the field but keeps it human-owned
- release(target, field)               the person hands the field back to the machine
  - effects: removes a human entry so suggestions apply again
- confirm(target, required: list field) -> dict field -> value
  - requires: not confirmed, every required field has a value
  - effects: confirmed = true

**Queries:**
- view(target) -> { fields, confirmed }

**Not this concept's job:** which fields exist and how sure the machine must be (settings, applied by a sync), what the values mean (Catalog), what happens after confirming (Quote, via a sync).
