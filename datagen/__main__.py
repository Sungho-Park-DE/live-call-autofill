"""python -m datagen: write build/claims.csv (and build/claims_truth.csv, the accident behind each claim)."""
from __future__ import annotations

import csv
import time
from pathlib import Path

from .generate import CSV_FIELDS, N_ACCIDENTS, SEED, generate, rows

BUILD = Path(__file__).resolve().parents[1] / "build"


def main() -> None:
    started = time.perf_counter()
    claims = generate(N_ACCIDENTS, SEED)
    BUILD.mkdir(exist_ok=True)
    with (BUILD / "claims.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        n_lines = 0
        for row in rows(claims):
            writer.writerow(row)
            n_lines += 1
    with (BUILD / "claims_truth.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(("claim_no", "accident_id"))
        writer.writerows((c.claim_no, c.accident) for c in claims)
    print(f"datagen: {len(claims)} claims, {n_lines} lines -> {BUILD / 'claims.csv'} "
          f"({time.perf_counter() - started:.1f} s)")


if __name__ == "__main__":
    main()
