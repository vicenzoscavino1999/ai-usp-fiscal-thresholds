from pathlib import Path

import pandas as pd

from ai_usp.historical import HistoricalPercentiles, classify_historical_plausibility
from scripts.run_official_tier_a import ROOT, COUNTRIES, historical_percentiles, load_inputs


def test_required_mfc_class_pipeline():
    pct = HistoricalPercentiles(
        revenue_concept="tax",
        percentile_sample="test",
        p50=0.20,
        p75=0.30,
        p90=0.40,
        p50_ci_low=0.18,
        p50_ci_high=0.22,
        p75_ci_low=0.28,
        p75_ci_high=0.32,
        p90_ci_low=0.38,
        p90_ci_high=0.42,
    )

    assert (
        classify_historical_plausibility(0.41, pct).historical_plausibility_class
        == "extreme_or_outside_historical_support"
    )
    assert classify_historical_plausibility(0.19, pct).historical_plausibility_class == "fiscally_ordinary"
    assert classify_historical_plausibility(0.39, pct).borderline_plausibility_flag

    generated = ROOT / "results" / "official" / "threshold_inversion_result.csv"
    threshold = pd.read_csv(
        generated if generated.is_file() else ROOT / "reproducibility" / "reference" / "threshold_inversion_result.csv"
    )
    db_path = ROOT / "db" / "ai_usp_threshold.duckdb"
    inputs = load_inputs(ROOT) if db_path.is_file() else None
    tracked_percentiles = None
    if inputs is None:
        tracked_percentiles = pd.read_csv(
            ROOT / "reports" / "historical_capture_percentiles_baseline-official-v3.csv"
        )

    def p90(country: str, concept: str) -> float:
        if inputs is not None:
            return historical_percentiles(inputs, country, concept).p90
        assert tracked_percentiles is not None
        row = tracked_percentiles[
            tracked_percentiles["country_id"].eq(country)
            & tracked_percentiles["revenue_concept"].eq(concept)
            & tracked_percentiles["percentile_sample"].eq("2000plus")
        ]
        assert len(row) == 1
        return float(row.iloc[0]["p90_mfc_hist_positive"])

    for country in COUNTRIES:
        p90_tax = p90(country, "tax")
        p90_total = p90(country, "total_revenue")
        country_rows = threshold[threshold["country_id"].eq(country)].copy()
        above_tax = country_rows[pd.to_numeric(country_rows["mfc_required_gross"], errors="coerce") > p90_tax]
        above_total = country_rows[pd.to_numeric(country_rows["mfc_required_gross"], errors="coerce") > p90_total]
        assert not above_tax["historical_tax_class"].eq("fiscally_ordinary").any()
        assert not above_total["historical_total_revenue_class"].eq("fiscally_ordinary").any()
