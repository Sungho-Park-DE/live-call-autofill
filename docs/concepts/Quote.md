# Concept: Quote [Call]

**Purpose:** Keep the quotes a person has confirmed, so they can be sent on and looked up later.

**Operational principle:** If a quote is created for a call with header {car: Atto, zone: front bumper} and three lines,
then listing quotes shows it with those three lines, and creating a second quote for the same call is refused.

**State:**
- quotes: Quote -> { call, header: dict, lines: list {number, name, qty}, created_at }

**Actions:**
- create(call, header, lines) -> Quote
  - requires: no quote yet for this call, at least one line
  - effects: stores the quote

**Queries:**
- get(quote), for_call(call), list()

**Not this concept's job:** where the lines come from (Catalog, via a sync), sending it to a dealer system (would be an adapter).
