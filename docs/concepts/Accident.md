# Concept: Accident [Target]

**Purpose:** From past accident cases, know which other body zones usually go with a reported damage, so a quote covers the whole repair and not only the zone the caller named.

**Operational principle:** If past front, no-side, moderate cases on the Vera replaced the grille in 44% of 57 cases and the hood in 12%,
then a call about a moderate front bumper on a Vera is offered the grille (44%, n = 57) but not the hood, included by default;
if the person unticks the grille, it stays out for that call however often the suggestion is recomputed.

**State:**
- table: (model | "*", position, side, severity) -> { n, scope: "model" | "all", zones: list { zone, share } }
  - read-only, produced offline by `analysis/` (zones with share ≥ threshold only; scope "all" = the model had fewer than min n cases and all models are used)
- declined: Target -> set zone

**Actions:**
- decline(target, zone)     the person unticks a suggested zone
- accept(target, zone)      the person ticks it again
  - effects: removes the zone from declined

**Queries:**
- companions(target, model, position, side?, severity, exclude: set zone) -> list { zone, share, n, scope, included }
  - looks up the model's cell, then the all-models cell; an unknown side tries "none", then "both"
  - leaves out the excluded zones (the ones already on the draft); included = not declined
  - empty when the table has no matching cell

**Not this concept's job:** which zone sits at which position and which parts a zone has (Catalog), what the caller said (Draft), turning ticked zones into quote lines (a sync).
