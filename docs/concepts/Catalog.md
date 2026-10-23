# Concept: Catalog

**Purpose:** Know which parts belong to a given car, body zone, side and damage level, and the words people use for each choice.

**Operational principle:** If someone asks for lines for (Atto, front bumper, both, moderate), then they get the bumper cover, absorber and both brackets,
but not the reinforcement beam, which only comes with severe.

**State** (read-only data — all names and part numbers are invented for this demo):
- cars: list Option          Option = { value, hint }   hint = other words for it ("front bumper, bumper at the front")
- zones, sides, severities: list Option
- zone position: zone -> front | rear | side
- parts: (car, zone) -> list Part   Part = { number, name, sided: bool, min_severity }

**Queries:**
- options() -> { car, zone, side, severity: list Option }
- zones() -> list { zone, position, parts: list { name, sided, min_severity } }
  - the layout without a car, for offline use (the invented claims generator and the analysis)
- lines(car, zone, side, severity) -> list { number, name, qty }
  - sided parts follow the side; when the side is unknown or both, both sides are included
    ("when unsure, include it — removing a line is easier than adding one")

**Not this concept's job:** prices, stock, checking that a part really fits a specific vehicle (a real parts catalog lookup would sit behind an adapter).
