"""Export the frozen historical-capture percentile registry from DuckDB read-only."""

from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "ai_usp_threshold.duckdb"
OUTPUT_PATH = ROOT / "reports" / "historical_capture_percentiles_baseline-official-v3.csv"
PER_PEN_REQUIRED = 0.30496566450665274

SOURCE_FIELDS = [
    "country_id",
    "government_level",
    "revenue_concept",
    "percentile_sample",
    "p10_mfc_hist_positive",
    "p25_mfc_hist_positive",
    "p50_mfc_hist_positive",
    "p50_ci_low",
    "p50_ci_high",
    "p75_mfc_hist_positive",
    "p75_ci_low",
    "p75_ci_high",
    "p90_mfc_hist_positive",
    "p90_ci_low",
    "p90_ci_high",
    "ci_method",
    "n_years_total",
    "n_years_positive",
    "p_negative_capture",
    "p10_mfc_hist_negative",
    "p50_mfc_hist_negative",
    "p90_mfc_hist_negative",
    "support_warning",
    "dataset_version",
    "build_id",
]
OUTPUT_FIELDS = [*SOURCE_FIELDS, "bootstrap_ci_available_flag", "support_warning_flag"]


def main() -> int:
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        query = f"""
            SELECT {', '.join(SOURCE_FIELDS)}
            FROM historical_capture_percentiles
            ORDER BY country_id, government_level, revenue_concept, percentile_sample
        """
        result = connection.execute(query)
        rows = [dict(zip(SOURCE_FIELDS, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()

    if not rows:
        raise AssertionError("historical_capture_percentiles: no rows exported")
    for row in rows:
        row["bootstrap_ci_available_flag"] = all(
            row[field] is not None
            for field in ("p50_ci_low", "p50_ci_high", "p75_ci_low", "p75_ci_high", "p90_ci_low", "p90_ci_high")
        )
        row["support_warning_flag"] = bool(str(row["support_warning"] or "").strip())

    peru_tax = [
        row
        for row in rows
        if row["country_id"] == "PER"
        and row["government_level"] == "general_government"
        and row["revenue_concept"] == "tax"
        and row["percentile_sample"] == "2000plus"
    ]
    if len(peru_tax) != 1:
        raise AssertionError(f"expected one PER tax 2000plus percentile row, found {len(peru_tax)}")
    row = peru_tax[0]
    p90 = float(row["p90_mfc_hist_positive"])
    if Decimal(str(p90)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) != Decimal("0.297"):
        raise AssertionError(f"PER tax P90 does not round to Results literal 0.297: {p90}")
    if not float(row["p90_ci_low"]) <= PER_PEN_REQUIRED <= float(row["p90_ci_high"]):
        raise AssertionError("PER PEN required capture 0.30497 is outside the exported P90 bootstrap interval")

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest()
    print(f"PASS rows={len(rows)}")
    print(f"PASS per_tax_p90_2000plus={p90}")
    print(f"PASS per_tax_p90_rounds_to_0_297=True")
    print(f"PASS per_pen_required_0_30497_inside_p90_ci=True")
    print(f"PASS per_tax_p90_ci=[{row['p90_ci_low']},{row['p90_ci_high']}]")
    print(f"PASS duckdb_read_only=True")
    print(f"WROTE {OUTPUT_PATH.relative_to(ROOT).as_posix()} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
