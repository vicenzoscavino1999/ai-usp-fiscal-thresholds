"""Historical plausibility classes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalPercentiles:
    revenue_concept: str
    percentile_sample: str
    p50: float
    p75: float
    p90: float
    p50_ci_low: float | None = None
    p50_ci_high: float | None = None
    p75_ci_low: float | None = None
    p75_ci_high: float | None = None
    p90_ci_low: float | None = None
    p90_ci_high: float | None = None


@dataclass(frozen=True)
class HistoricalClassResult:
    historical_plausibility_class: str
    borderline_plausibility_flag: bool


def classify_historical_plausibility(
    mfc_gross: float,
    percentiles: HistoricalPercentiles,
) -> HistoricalClassResult:
    if mfc_gross <= percentiles.p50:
        klass = "fiscally_ordinary"
    elif mfc_gross <= percentiles.p75:
        klass = "fiscally_moderate"
    elif mfc_gross <= percentiles.p90:
        klass = "fiscally_demanding"
    else:
        klass = "extreme_or_outside_historical_support"

    borderline = False
    for low, high in (
        (percentiles.p50_ci_low, percentiles.p50_ci_high),
        (percentiles.p75_ci_low, percentiles.p75_ci_high),
        (percentiles.p90_ci_low, percentiles.p90_ci_high),
    ):
        if low is not None and high is not None and low <= mfc_gross <= high:
            borderline = True
            break
    return HistoricalClassResult(klass, borderline)
