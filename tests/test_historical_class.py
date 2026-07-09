from ai_usp.historical import HistoricalPercentiles, classify_historical_plausibility


def test_historical_plausibility_classes():
    pct = HistoricalPercentiles("total_revenue", "2000plus", 0.2, 0.3, 0.4)
    assert classify_historical_plausibility(0.1, pct).historical_plausibility_class == "fiscally_ordinary"
    assert classify_historical_plausibility(0.25, pct).historical_plausibility_class == "fiscally_moderate"
    assert classify_historical_plausibility(0.35, pct).historical_plausibility_class == "fiscally_demanding"
    assert (
        classify_historical_plausibility(0.45, pct).historical_plausibility_class
        == "extreme_or_outside_historical_support"
    )
