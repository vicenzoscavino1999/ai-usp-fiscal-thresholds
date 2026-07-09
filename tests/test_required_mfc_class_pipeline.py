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

    threshold = pd.read_csv(ROOT / "results" / "official" / "threshold_inversion_result.csv")
    inputs = load_inputs(ROOT)
    for country in COUNTRIES:
        p90_tax = historical_percentiles(inputs, country, "tax").p90
        p90_total = historical_percentiles(inputs, country, "total_revenue").p90
        country_rows = threshold[threshold["country_id"].eq(country)].copy()
        above_tax = country_rows[pd.to_numeric(country_rows["mfc_required_gross"], errors="coerce") > p90_tax]
        above_total = country_rows[pd.to_numeric(country_rows["mfc_required_gross"], errors="coerce") > p90_total]
        assert not above_tax["historical_tax_class"].eq("fiscally_ordinary").any()
        assert not above_total["historical_total_revenue_class"].eq("fiscally_ordinary").any()
