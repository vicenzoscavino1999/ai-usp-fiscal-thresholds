from pathlib import Path

import pandas as pd

from scripts.run_h_star_extension_7_1 import (
    AMENDMENT_CREATED_AT_UTC,
    REPORTING_CAP_YEARS,
    amendment_registry,
    find_h_star,
)


ROOT = Path(__file__).resolve().parents[1]


def flat_ratios():
    return {h: 1.0 for h in range(1, REPORTING_CAP_YEARS + 1)}


def test_h_star_monotone_in_annual_shock():
    common = dict(
        mfc_tilde_gross=0.40,
        fixed_cost_gdp=0.0,
        cost_2024_gdp=0.02,
        ratios_by_h=flat_ratios(),
        xi=0.10,
        requirement_basis="baseline",
    )
    slow = find_h_star(annual_ai_growth=0.01, **common)
    fast = find_h_star(annual_ai_growth=0.03, **common)

    assert fast.h_star is not None
    assert slow.h_star is None or fast.h_star <= slow.h_star


def test_h_star_censoring_respects_cap():
    result = find_h_star(
        mfc_tilde_gross=0.01,
        annual_ai_growth=0.001,
        fixed_cost_gdp=0.0,
        cost_2024_gdp=0.10,
        ratios_by_h=flat_ratios(),
        xi=0.50,
        requirement_basis="baseline",
    )

    assert result.h_star is None
    assert result.status == "censored_beyond_defensible_horizon"
    assert "censored_beyond_defensible_horizon" in result.flags


def test_h_star_minimal_crossing_condition():
    result = find_h_star(
        mfc_tilde_gross=1.0,
        annual_ai_growth=0.03,
        fixed_cost_gdp=0.0,
        cost_2024_gdp=0.02,
        ratios_by_h=flat_ratios(),
        xi=0.10,
        requirement_basis="baseline",
    )

    assert result.h_star is not None
    assert result.v_at_h_star is not None and result.v_at_h_star >= 1.10
    assert result.h_star == 1 or (result.v_at_h_minus_1 is not None and result.v_at_h_minus_1 < 1.10)


def test_h_star_outputs_if_present():
    registry = amendment_registry()
    assert registry.loc[0, "created_at_utc"] == AMENDMENT_CREATED_AT_UTC

    hstar_path = ROOT / "results" / "official" / "h_star_result.csv"
    mc_path = ROOT / "results" / "official" / "monte_carlo_result.csv"
    if not hstar_path.exists() or not mc_path.exists():
        return

    hstar = pd.read_csv(hstar_path)
    assert len(hstar) == 4800
    assert hstar["h_star_reporting_cap"].eq(25).all()
    assert hstar["h_star"].dropna().le(25).all()
    crossed = hstar[hstar["h_star_status"].eq("crosses_within_cap")]
    assert (crossed["v_at_h_star"] >= crossed["threshold_at_h_star"]).all()
    prior = crossed[crossed["h_star"] > 1]
    assert (prior["v_at_h_minus_1"] < prior["threshold_at_h_minus_1"]).all()

    mc = pd.read_csv(mc_path)
    assert {"prob_h_star_le_10", "prob_h_star_le_25"}.issubset(mc.columns)
    primary = mc[mc["mc_mode"].eq("MC_independent_baseline") & mc["prob_basis"].eq("all_draw")]
    if not primary.empty:
        assert (primary["prob_h_star_le_10"].round(12) == primary["prob_v_ge_1_10"].round(12)).all()
