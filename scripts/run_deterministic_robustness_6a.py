"""Etapa 6A deterministic robustness runner.

All outputs are labelled run_type=robustness and compare against the official
baseline calibration baseline-official-v3. The certified mechanics in
src/ai_usp are reused but not modified.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_usp.adoption import build_adoption_state
from ai_usp.classify import classify_cell
from ai_usp.fiscal_channels import RegimeSettings, apply_base_broadening_to_structure, compute_mfc
from ai_usp.fiscal_space import compute_fiscal_space
from ai_usp.historical import HistoricalPercentiles, classify_historical_plausibility
from ai_usp.labor_share import compute_labor_capital_weights
from ai_usp.policy_cost import endpoint_cost_scale, fixed_policy_costs
from ai_usp.shock import convert_phi_raw
from ai_usp.translation import s_ndc_score, tilde, translate_to_growth
from scripts.materialize_official_v3_measurement_uncertainty import materialize as materialize_v3
from scripts.run_official_monte_carlo import PARAMETER_SET_ID, load_inputs
from scripts.run_official_tier_a import (
    ANCHOR_YEAR,
    COUNTRIES,
    DATASET_VERSION,
    MODEL_VERSION,
    POLICIES,
    REGIMES,
    SCENARIOS,
    OfficialRunError,
    admin_costs,
    clean,
    eligible_metric,
    git_value,
    historical_percentiles,
    mark_and_classify_cells,
    regime_settings,
    scenario_parameters,
    sha256_file,
    value_lookup,
)


RUN_ID = "official_4c_deterministic_robustness_6a_baseline_official_v3"
RUN_TYPE = "robustness"
BASELINE_RESULTS_PARAMETER_SET = "baseline-official-v2"
BASELINE_COMPARISON_PARAMETER_SET = PARAMETER_SET_ID
DEFAULT_ENDPOINT_YEAR = 2034
DEFAULT_HORIZON_YEARS = 10
XI = 0.10
HEADLINE_CELLS = {
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
    ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
    ("PER", "PEN", "stress", "r2"),
    ("PER", "PEN", "stress", "r4"),
}


@dataclass(frozen=True)
class Variant:
    variant_id: str
    family: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)
    full_grid: bool = True


def variants() -> list[Variant]:
    return [
        Variant("R1_horizon_H5", "R1_horizon", "H=5 endpoint 2029", {"horizon": 5, "endpoint_year": 2029}),
        Variant("R1_horizon_H15", "R1_horizon", "H=15 endpoint 2039; WPP clipped to 2035 if unavailable", {"horizon": 15, "endpoint_year": 2039}),
        Variant("R2_trajectory_lambda_015", "R2_trajectory_sensitivity", "explicit q trajectory lambda_q=0.15", {"trajectory_lambda": 0.15}),
        Variant("R2_trajectory_lambda_030", "R2_trajectory_sensitivity", "explicit q trajectory lambda_q=0.30", {"trajectory_lambda": 0.30}),
        Variant("R2_trajectory_lambda_050", "R2_trajectory_sensitivity", "explicit q trajectory lambda_q=0.50", {"trajectory_lambda": 0.50}),
        Variant("R3_frontier_best_country", "R3_S_frontier", "frontier=max individual benchmark score", {"frontier": "best_individual"}),
        Variant("R3_frontier_alt_year", "R3_S_frontier", "alternate benchmark year; frozen snapshot only has 2024", {"frontier": "alt_year_noop"}),
        Variant("R3_full_score_alpha1", "R3_S_frontier", "full score robustness alpha=1 with AIPI in both domestic/frontier score", {"frontier": "full_score_alpha1"}),
        Variant("R4_cost_net", "R4_cost_net", "V_net with documented C_exist, no contributive subtraction", {"cost_metric": "net"}),
        Variant("R5_demography_constant_2024", "R5_demography_constant", "endpoint costs fixed at 2024 demographic shares", {"constant_demography": True}),
        Variant("R6_gap_residualized", "R6_gap_residualized", "Gap residualized on international ITU LTE coverage vs AIPI", {"gap": "residualized"}),
        Variant("R7_kappa_tfp_075", "R7_shock_bridge", "kappa_TFP_to_Y=0.75 for low/mid TFP scenarios", {"kappa_tfp": 0.75}),
        Variant("R7_high_no_LP_bridge", "R7_shock_bridge", "high scenario without LP bridge: kappa=1 as raw-unit upper cota", {"high_kappa": 1.0}),
        Variant("R8_ai_rents_additional", "R8_ai_rents", "omega_K not netted plus AI-rent channel separately", {"lambda_ai_kbase": 0.0}),
        Variant("R9_vat_rate_side", "R9_tax_base_conventions", "VAT base broadening as rate-side tau_C change, exempt_C=0", {"vat_rate_side": True}),
        Variant("R9_profit_shift_rate_side", "R9_tax_base_conventions", "profit shifting handled via chi_dom rate-side, not base-side psi", {"profit_shift_rate_side": True}),
        Variant("R10_margin_equivalent_costs", "R10_margin_equivalent_costs", "admin/transition/leakage as MFCtilde ME terms", {"fixed_costs_as_me": True}),
        Variant("R11_hist_window_2010plus", "R11_historical_windows", "required-MFC plausibility with 2010plus window", {"historical_window": "2010plus"}),
        Variant("R11_hist_window_2015plus", "R11_historical_windows", "required-MFC plausibility with 2015plus window", {"historical_window": "2015plus"}),
        Variant("R11_hist_window_excl_pandemic", "R11_historical_windows", "required-MFC plausibility excluding 2020-2021", {"historical_window": "excl_pandemic_2020_2021"}),
        Variant("R12_non_resource_plausibility", "R12_non_resource", "non-resource plausibility unavailable in frozen canonical percentiles", {"diagnostic_only": "non_resource_unavailable"}),
        Variant("R13_recycling_mpc_ben", "R13_recycling", "first-round benefit recycling c_recyc with mpc_ben proxy", {"recycling": True}),
        Variant("R14_hist_tax_p10", "R14_historical_reduced_form", "r0 V with tax historical MFC P10", {"historical_mfc": ("tax", "p10")}),
        Variant("R14_hist_tax_p50", "R14_historical_reduced_form", "r0 V with tax historical MFC P50", {"historical_mfc": ("tax", "p50")}),
        Variant("R14_hist_tax_p90", "R14_historical_reduced_form", "r0 V with tax historical MFC P90", {"historical_mfc": ("tax", "p90")}),
        Variant("R14_hist_total_p10", "R14_historical_reduced_form", "r0 V with total-revenue historical MFC P10", {"historical_mfc": ("total_revenue", "p10")}),
        Variant("R14_hist_total_p50", "R14_historical_reduced_form", "r0 V with total-revenue historical MFC P50", {"historical_mfc": ("total_revenue", "p50")}),
        Variant("R14_hist_total_p90", "R14_historical_reduced_form", "r0 V with total-revenue historical MFC P90", {"historical_mfc": ("total_revenue", "p90")}),
    ]


def endpoint_available_year(wpp: pd.DataFrame, country: str, requested: int) -> int:
    years = sorted(int(x) for x in wpp.loc[wpp["ISO3_code"].eq(country), "Time"].dropna().unique())
    if requested in years:
        return requested
    prior = [year for year in years if year <= requested]
    return max(prior) if prior else min(years)


def policy_instances_variant(country: str, policy_cost: pd.DataFrame, wpp: pd.DataFrame, variant: Variant) -> list[dict[str, Any]]:
    endpoint_year = int(variant.params.get("endpoint_year", DEFAULT_ENDPOINT_YEAR))
    constant = bool(variant.params.get("constant_demography", False))
    effective_year = ANCHOR_YEAR if constant else endpoint_available_year(wpp, country, endpoint_year)
    rows = []
    pc = policy_cost[policy_cost["country_id"].eq(country)]
    for policy in POLICIES:
        versions = ("GMI_ideal_aggregate", "GMI_loaded_aggregate") if policy == "GMI" else (None,)
        for version in versions:
            cost_row = pc[(pc["policy_id"].eq(policy)) & (pc["gmi_version"].isna() if version is None else pc["gmi_version"].eq(version))]
            if cost_row.empty:
                raise OfficialRunError(f"Missing policy_cost for {country}/{policy}/{version}")
            r = cost_row.iloc[0]
            cost_2024 = float(r["policy_cost_gross_gdp"])
            net_2024 = float(r["policy_cost_net_gdp"])
            fixed = policy == "GMI"
            if policy == "PEN" and country == "COL":
                scale = eligible_metric(wpp, country, effective_year, policy) / eligible_metric(wpp, country, ANCHOR_YEAR, policy)
            else:
                anchor = eligible_metric(wpp, country, ANCHOR_YEAR, policy)
                endpoint = eligible_metric(wpp, country, effective_year, policy)
                scale = 1.0 if fixed else endpoint / anchor
            rows.append(
                {
                    "country_id": country,
                    "policy_id": policy,
                    "gmi_version": version,
                    "policy_variant_id": policy if version is None else f"{policy}:{version}",
                    "cost_gross_gdp": cost_2024 * scale,
                    "cost_net_gdp": net_2024 * scale,
                    "cost_2024_gdp": cost_2024,
                    "endpoint_year_requested": endpoint_year,
                    "endpoint_year_effective": effective_year,
                    "endpoint_cost_rule": (
                        "2024 demographic shares held constant."
                        if constant
                        else f"Endpoint costs use WPP year {effective_year}; requested {endpoint_year}."
                    ),
                }
            )
    return rows


def historical_percentiles_sample(inputs: dict[str, Any], country: str, concept: str, sample: str) -> HistoricalPercentiles:
    pct = inputs["historical_capture_percentiles"]
    rows = pct[pct["country_id"].eq(country) & pct["revenue_concept"].eq(concept) & pct["percentile_sample"].eq(sample)]
    if rows.empty:
        raise OfficialRunError(f"Missing historical percentiles {country}/{concept}/{sample}")
    r = rows.iloc[0]
    return HistoricalPercentiles(
        revenue_concept=concept,
        percentile_sample=sample,
        p50=float(r["p50_mfc_hist_positive"]),
        p75=float(r["p75_mfc_hist_positive"]),
        p90=float(r["p90_mfc_hist_positive"]),
        p50_ci_low=float(r["p50_ci_low"]),
        p50_ci_high=float(r["p50_ci_high"]),
        p75_ci_low=float(r["p75_ci_low"]),
        p75_ci_high=float(r["p75_ci_high"]),
        p90_ci_low=float(r["p90_ci_low"]),
        p90_ci_high=float(r["p90_ci_high"]),
    )


def residualized_gap_map(root: Path) -> dict[str, float]:
    aipi = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "imf_aipi" / "aipi.parquet")
    itu = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "itu" / "itu_digital.parquet")
    lte = itu[itu["indicator_code"].eq("ITU_COVERAGE_LTE_WIMAX")].copy()
    lte = lte.sort_values("year").groupby("country_id").tail(1)
    df = lte[["country_id", "value"]].merge(aipi[["country_id", "aipi_total"]], on="country_id", how="inner").dropna()
    if len(df) < 10:
        raise OfficialRunError("Residualized Gap requires international ITU/AIPI sample.")
    y = (df["value"].astype(float) / 100.0).clip(0.0, 1.0).to_numpy()
    x = df["aipi_total"].astype(float).to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    df = df.copy()
    df["coverage_residual"] = y - (slope * x + intercept)
    # Low residual = worse connectivity than AIPI predicts = higher gap.
    df["gap_residualized"] = 1.0 - df["coverage_residual"].rank(method="average", pct=True)
    return {country: float(df.loc[df["country_id"].eq(country), "gap_residualized"].iloc[0]) for country in COUNTRIES}


def frontier_rows_for_variant(inputs: dict[str, Any], value, country: str, variant: Variant) -> tuple[list[dict[str, Any]], str]:
    frontier = inputs["frontier_benchmark_anchor"].copy()
    eprod_frontier = value("E_prod_frontier")
    frontier["exposure_productive"] = eprod_frontier
    note = "baseline frontier mean OECD-Eurostat."
    mode = variant.params.get("frontier")
    if mode == "alt_year_noop":
        years = sorted(frontier["year"].dropna().unique().tolist())
        note = f"alternate reference year requested; available benchmark years={years}; no-op robustness."
    return frontier.to_dict("records"), note


def translate_variant(
    *,
    inputs: dict[str, Any],
    value,
    country: str,
    variant: Variant,
    adoption,
    shock,
    horizon: int,
    frontier_rows: list[dict[str, Any]],
) -> dict[str, float | bool | str]:
    beta = value("beta_translation", country=country)
    gamma = value("gamma_translation", country=country)
    epsilon = value("epsilon", country=country)
    eprod = value("E_prod", country=country)
    frontier_mode = variant.params.get("frontier")
    if frontier_mode == "best_individual":
        s_domestic = s_ndc_score(eprod, adoption.q_prod, beta, gamma, epsilon)
        scores = [s_ndc_score(float(r["exposure_productive"]), float(r["adoption_proxy"]), beta, gamma, epsilon) for r in frontier_rows]
        s_frontier = max(scores)
        t = 0.0 if s_frontier <= 0.0 else min(1.0, s_domestic / s_frontier)
        g = (1.0 + shock.phi_y_nom * t) ** horizon - 1.0
        return {"s_frontier": s_frontier, "translation_factor": t, "g_ai_level": g, "fallback": False, "note": "s_frontier=max individual benchmark score."}
    if frontier_mode == "full_score_alpha1":
        s_domestic = s_ndc_score(eprod, adoption.q_prod, beta, gamma, epsilon) * tilde(value("A_aipi_total", country=country), epsilon)
        scores = [
            s_ndc_score(float(r["exposure_productive"]), float(r["adoption_proxy"]), beta, gamma, epsilon)
            * tilde(float(r["aipi_total"]), epsilon)
            for r in frontier_rows
        ]
        s_frontier = sum(scores) / len(scores)
        t = 0.0 if s_frontier <= 0.0 else min(1.0, s_domestic / s_frontier)
        g = (1.0 + shock.phi_y_nom * t) ** horizon - 1.0
        return {"s_frontier": s_frontier, "translation_factor": t, "g_ai_level": g, "fallback": False, "note": "full_score alpha=1 applied symmetrically."}
    if "trajectory_lambda" in variant.params:
        lam = float(variant.params["trajectory_lambda"])
        q = adoption.q_prod_t0
        factors = []
        s_frontier = None
        t_last = None
        for _ in range(horizon):
            q = q + lam * (adoption.q_use_target_adj - q)
            tr = translate_to_growth(
                exposure_productive=eprod,
                q_prod=q,
                phi_y_nom=shock.phi_y_nom,
                beta=beta,
                gamma=gamma,
                epsilon=epsilon,
                horizon_years=1,
                benchmark_rows=frontier_rows,
                missing_frontier_exposure_fallback=value("E_prod_frontier"),
            )
            s_frontier = tr.s_frontier
            t_last = tr.translation_factor
            factors.append(1.0 + shock.phi_y_nom * tr.translation_factor)
        return {
            "s_frontier": float(s_frontier or 0.0),
            "translation_factor": float(t_last or 0.0),
            "g_ai_level": math.prod(factors) - 1.0,
            "fallback": False,
            "note": f"explicit q path lambda={lam}; q_use_target equals q_prod_t0 in frozen convention.",
        }
    tr = translate_to_growth(
        exposure_productive=eprod,
        q_prod=adoption.q_prod,
        phi_y_nom=shock.phi_y_nom,
        beta=beta,
        gamma=gamma,
        epsilon=epsilon,
        horizon_years=horizon,
        benchmark_rows=frontier_rows,
        missing_frontier_exposure_fallback=value("E_prod_frontier"),
    )
    return {"s_frontier": tr.s_frontier, "translation_factor": tr.translation_factor, "g_ai_level": tr.g_ai_level, "fallback": tr.frontier_exposure_fallback_used, "note": "baseline translation mechanics."}


def classify_country_policy_variant(rows: list[dict[str, Any]]) -> pd.DataFrame:
    out = []
    df = pd.DataFrame(rows)
    for (country, policy, gmi), grp in df.groupby(["country_id", "policy_id", "gmi_version"], dropna=False):
        crossings = grp[grp["crosses_buffer"]]
        if policy == "UBI":
            klass = "stress_benchmark_only"
        elif crossings.empty:
            klass = "not_feasible"
        elif (~crossings["debt_guardrail_pass"]).any() or crossings["historical_total_revenue_class"].eq("extreme_or_outside_historical_support").any():
            klass = "fragile_feasibility"
        else:
            klass = "conditional_feasibility_probabilistic_leg_not_evaluated"
        out.append({"country_id": country, "policy_id": policy, "gmi_version": None if pd.isna(gmi) else gmi, "variant_country_policy_result_class": klass})
    return pd.DataFrame(out)


def run_variant(root: Path, inputs: dict[str, Any], variant: Variant, baseline: pd.DataFrame, baseline_classes: pd.DataFrame, gap_resid: dict[str, float]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    values = inputs["values"]
    value = value_lookup(values)
    horizon = int(variant.params.get("horizon", DEFAULT_HORIZON_YEARS))
    fiscal_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    if variant.params.get("diagnostic_only") == "non_resource_unavailable":
        diagnostic_rows.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "variant_id": variant.variant_id,
                "diagnostic_key": "non_resource_percentiles",
                "diagnostic_value": "not_available",
                "diagnostic_note": "Frozen historical_capture_percentiles has tax and total_revenue only; non-resource concept deferred.",
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
        # no-op grid to keep the variant visible in robustness_table
        b = baseline.copy()
        b["variant_id"] = variant.variant_id
        b["variant_family"] = variant.family
        b["variant_label"] = variant.label
        b["v_variant"] = b["v_gross"]
        b["variant_cell_result_class"] = b["cell_result_class"]
        b["variant_country_policy_result_class"] = b["country_policy_result_class"]
        b["variant_note"] = "diagnostic-only: non-resource percentiles unavailable."
        return b, diagnostic_rows

    for country in COUNTRIES:
        gap = gap_resid[country] if variant.params.get("gap") == "residualized" else value("Gap_excluded_indicators", country=country)
        hist_tax = historical_percentiles(inputs, country, "tax")
        hist_total = historical_percentiles(inputs, country, "total_revenue")
        adoption = build_adoption_state(
            q_use_target=value("q_use_target", country=country),
            aipi=value("A_aipi_total", country=country),
            informality=value("I_adopt_informality", country=country),
            gap=gap,
            omega_i=value("omega_I", country=country),
            omega_g=value("omega_G", country=country),
            nu_a=value("nu_A", country=country),
            nu_i=value("nu_I", country=country),
            nu_g=value("nu_G", country=country),
            epsilon_mu=value("epsilon_mu", country=country),
            frozen=True,
        )
        policy_rows = policy_instances_variant(country, inputs["policy_cost"], inputs["wpp"], variant)
        frontier_rows, frontier_note = frontier_rows_for_variant(inputs, value, country, variant)
        for scenario in SCENARIOS:
            phi_raw, kappa, pi_ai_y, lambda_ai, lambda_ai_kbase = scenario_parameters(value, country, scenario)
            if scenario in {"low", "mid"} and "kappa_tfp" in variant.params:
                kappa = float(variant.params["kappa_tfp"])
            if scenario == "high" and "high_kappa" in variant.params:
                kappa = float(variant.params["high_kappa"])
            shock = convert_phi_raw(scenario, phi_raw, kappa, pi_ai_y)
            tr = translate_variant(
                inputs=inputs,
                value=value,
                country=country,
                variant=variant,
                adoption=adoption,
                shock=shock,
                horizon=horizon,
                frontier_rows=frontier_rows,
            )
            for regime_code in REGIMES:
                regime = regime_settings(value, regime_code)
                psi_shift = value("psi_shift", country=country)
                exempt_c = value("exempt_C", country=country)
                if variant.params.get("vat_rate_side"):
                    psi_shift_r, exempt_c_r = psi_shift, 0.0
                    tau_c_eff = value("tau_C_eff", country=country) * max(0.0, 1.0 - regime.base_broadening_delta)
                elif variant.params.get("profit_shift_rate_side"):
                    psi_shift_r, exempt_c_r = psi_shift, exempt_c
                    tau_c_eff = value("tau_C_eff", country=country)
                else:
                    psi_shift_r, exempt_c_r = apply_base_broadening_to_structure(psi_shift, exempt_c, regime.base_broadening_delta)
                    tau_c_eff = value("tau_C_eff", country=country)
                chi_dom = value("chi_dom", country=country)
                if variant.params.get("profit_shift_rate_side"):
                    chi_dom = min(1.0, chi_dom + regime.base_broadening_delta * (1.0 - chi_dom))
                weights = compute_labor_capital_weights(
                    labor_share=value("LS_labor_share", country=country),
                    g_ai_level=float(tr["g_ai_level"]),
                    q_prod=adoption.q_prod,
                    e_auto=value("E_auto", country=country),
                    e_aug=value("E_aug", country=country),
                    delta_s=value("delta_s", country=country),
                    psi_s=value("psi_s", country=country),
                    zeta_s=value("zeta_s", country=country),
                    rst=value("RST", country=country),
                    lambda_ls=value("lambda_LS", country=country),
                    chi_kbase=value("chi_Kbase", country=country),
                    chi_dom=chi_dom,
                    psi_shift=psi_shift_r,
                    tau_l_disp=value("tau_L_disp", country=country),
                    tau_k_disp=value("tau_K_disp", country=country),
                    tau_r_disp=value("tau_R_disp", country=country),
                    mpc_w=value("mpc_W", country=country),
                    mpc_pi=value("mpc_Pi", country=country),
                    mpc_r=value("mpc_R", country=country),
                    m_m=value("m_M", country=country),
                    theta_r_dom=value("theta_R_dom", country=country),
                    exempt_c=exempt_c_r,
                )
                channel_base = compute_mfc(
                    weights=weights,
                    regime=regime,
                    tau_l_eff=value("tau_L_eff", country=country),
                    tau_k_eff=value("tau_K_eff", country=country),
                    tau_c_eff=tau_c_eff,
                    lambda_ai=lambda_ai,
                    lambda_ai_kbase=float(variant.params.get("lambda_ai_kbase", lambda_ai_kbase)),
                    use_erosion_companion=True,
                )
                hist_tax_class = classify_historical_plausibility(channel_base.mfc_gross, hist_tax)
                hist_total_class = classify_historical_plausibility(channel_base.mfc_gross, hist_total)
                for policy in policy_rows:
                    fixed = admin_costs(inputs["policy_admin_transition_cost"], country, policy["policy_id"], regime.leakage_multiplier)
                    channel = channel_base
                    fixed_for_fspace = fixed
                    if variant.params.get("fixed_costs_as_me"):
                        channel = compute_mfc(
                            weights=weights,
                            regime=regime,
                            tau_l_eff=value("tau_L_eff", country=country),
                            tau_k_eff=value("tau_K_eff", country=country),
                            tau_c_eff=tau_c_eff,
                            lambda_ai=lambda_ai,
                            lambda_ai_kbase=float(variant.params.get("lambda_ai_kbase", lambda_ai_kbase)),
                            ac_me=fixed.ac_net_fix,
                            tr_me=fixed.tr_ann,
                            leak_me=fixed.leak_fix,
                            use_erosion_companion=True,
                        )
                        fixed_for_fspace = fixed_policy_costs(
                            admin_cost_new_gdp=0.0,
                            admin_savings_existing_gdp=0.0,
                            transition_oneoff_gdp=0.0,
                            transition_recurring_gdp=0.0,
                            transition_horizon_years=1,
                            transition_discount_rate=0.0,
                            leakage_fixed_gdp=0.0,
                        )
                    mfc_override = variant.params.get("historical_mfc")
                    if mfc_override and regime_code == "r0":
                        concept, pct = mfc_override
                        pct_row = inputs["historical_capture_percentiles"][
                            inputs["historical_capture_percentiles"]["country_id"].eq(country)
                            & inputs["historical_capture_percentiles"]["revenue_concept"].eq(concept)
                            & inputs["historical_capture_percentiles"]["percentile_sample"].eq("2000plus")
                        ].iloc[0]
                        column = f"{pct}_mfc_hist_positive"
                        mfc_value = float(pct_row[column])
                        channel = compute_mfc(
                            weights=weights,
                            regime=regime,
                            tau_l_eff=value("tau_L_eff", country=country),
                            tau_k_eff=value("tau_K_eff", country=country),
                            tau_c_eff=tau_c_eff,
                            lambda_ai=lambda_ai,
                            lambda_ai_kbase=float(variant.params.get("lambda_ai_kbase", lambda_ai_kbase)),
                            use_erosion_companion=False,
                        )
                        channel = channel.__class__(**{**channel.__dict__, "mfc_gross_mechanical": mfc_value, "mfc_gross": mfc_value, "mfc_tilde_gross": mfc_value})
                    fspace = compute_fiscal_space(
                        mfc_gross=channel.mfc_gross,
                        mfc_tilde_gross=channel.mfc_tilde_gross,
                        g_ai_level=float(tr["g_ai_level"]),
                        ac_net_fix=fixed_for_fspace.ac_net_fix,
                        tr_ann=fixed_for_fspace.tr_ann,
                        leak_fix=fixed_for_fspace.leak_fix,
                        cost_gross_gdp=policy["cost_gross_gdp"],
                        cost_net_gdp=policy["cost_net_gdp"],
                    )
                    fs_eff = fspace.fs_eff
                    if variant.params.get("recycling"):
                        tau_c = min(1.0, max(0.0, value("tau_C_eff", country=country) * (1.0 + regime.tau_c_delta)))
                        c_recyc = policy["cost_gross_gdp"] * value("mpc_W", country=country) * (1.0 - value("m_M", country=country)) * tau_c
                        fs_eff += c_recyc
                    if variant.params.get("cost_metric") == "net":
                        v_eval = fs_eff / policy["cost_net_gdp"] if policy["cost_net_gdp"] > 0 else float("nan")
                        cost_eval = policy["cost_net_gdp"]
                    else:
                        v_eval = fs_eff / policy["cost_gross_gdp"] if policy["cost_gross_gdp"] > 0 else float("nan")
                        cost_eval = policy["cost_gross_gdp"]
                    if mfc_override and regime_code != "r0":
                        # Historical reduced-form diagnostic is r0-only; retain baseline grid elsewhere.
                        b = baseline[
                            baseline["country_id"].eq(country)
                            & baseline["policy_variant_id"].eq(policy["policy_variant_id"])
                            & baseline["scenario_id"].eq(scenario)
                            & baseline["regime_id"].eq(regime_code)
                        ].iloc[0]
                        v_eval = float(b["v_gross"])
                        fs_eff = float(b["fs_eff"])
                    debt_ok = fs_eff >= (1.0 + XI) * cost_eval + value("sPB_plus_gdp_ratio", country=country)
                    fiscal_rows.append(
                        {
                            "country_id": country,
                            "policy_id": policy["policy_id"],
                            "policy_variant_id": policy["policy_variant_id"],
                            "gmi_version": policy["gmi_version"],
                            "scenario_id": scenario,
                            "regime_id": regime_code,
                            "xi": XI,
                            "endpoint_year": int(variant.params.get("endpoint_year", DEFAULT_ENDPOINT_YEAR)),
                            "endpoint_year_effective": policy["endpoint_year_effective"],
                            "v_gross": v_eval,
                            "fs_eff": fs_eff,
                            "mfc_gross": channel.mfc_gross,
                            "mfc_tilde_gross": channel.mfc_tilde_gross,
                            "g_ai_level": float(tr["g_ai_level"]),
                            "translation_factor": float(tr["translation_factor"]),
                            "cost_gross_gdp": policy["cost_gross_gdp"],
                            "cost_net_gdp": policy["cost_net_gdp"],
                            "crosses_v1": v_eval >= 1.0,
                            "crosses_v1_10": v_eval >= 1.10,
                            "crosses_buffer": v_eval >= 1.10,
                            "debt_guardrail_pass": bool(debt_ok),
                            "existence_condition_pass": bool(channel.mfc_tilde_gross > 0 and float(tr["g_ai_level"]) > 0),
                            "historical_tax_class": hist_tax_class.historical_plausibility_class,
                            "historical_tax_borderline": hist_tax_class.borderline_plausibility_flag,
                            "historical_total_revenue_class": hist_total_class.historical_plausibility_class,
                            "historical_total_revenue_borderline": hist_total_class.borderline_plausibility_flag,
                            "cell_result_class": None,
                            "variant_note": f"{variant.label}; {tr['note']} {frontier_note}",
                        }
                    )
    mark_and_classify_cells(fiscal_rows)
    grid = pd.DataFrame(fiscal_rows)
    class_df = classify_country_policy_variant(grid)
    grid = grid.merge(class_df, on=["country_id", "policy_id", "gmi_version"], how="left")
    grid["variant_id"] = variant.variant_id
    grid["variant_family"] = variant.family
    grid["variant_label"] = variant.label
    grid["v_variant"] = grid["v_gross"]
    grid["variant_cell_result_class"] = grid["cell_result_class"]
    return grid, diagnostic_rows


def classify_required_windows(inputs: dict[str, Any]) -> pd.DataFrame:
    threshold = pd.read_csv(ROOT / "results" / "official" / "threshold_inversion_result.csv")
    cells = threshold[
        threshold["xi"].eq(0.10)
        & threshold["requirement_basis"].eq("baseline")
        & threshold.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)
    ].copy()
    rows = []
    for sample in ["2010plus", "2015plus", "excl_pandemic_2020_2021"]:
        for _, r in cells.iterrows():
            for concept in ["tax", "total_revenue"]:
                if pd.isna(r["mfc_required_gross"]):
                    klass = None
                    border = False
                else:
                    pct = historical_percentiles_sample(inputs, r["country_id"], concept, sample)
                    res = classify_historical_plausibility(float(r["mfc_required_gross"]), pct)
                    klass = res.historical_plausibility_class
                    border = res.borderline_plausibility_flag
                rows.append(
                    {
                        "run_id": RUN_ID,
                        "run_type": RUN_TYPE,
                        "variant_id": f"R11_hist_window_{sample}",
                        "diagnostic_key": f"{r['country_id']}|{r['policy_variant_id']}|{r['scenario_id']}|{r['regime_id']}|{concept}",
                        "diagnostic_value": klass,
                        "diagnostic_note": f"required MFC plausibility with sample={sample}; borderline={border}",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": DATASET_VERSION,
                    }
                )
    return pd.DataFrame(rows)


def ensure_v3_materialized(root: Path) -> None:
    db_path = root / "db" / "ai_usp_threshold.duckdb"
    if db_path.exists():
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            table_exists = con.execute(
                """
                SELECT COUNT(*) > 0
                FROM information_schema.tables
                WHERE table_name = 'value_assignment_table'
                """
            ).fetchone()[0]
            if table_exists:
                count = con.execute(
                    "SELECT COUNT(*) FROM value_assignment_table WHERE parameter_set_id = ?",
                    [BASELINE_COMPARISON_PARAMETER_SET],
                ).fetchone()[0]
                if count:
                    return
        finally:
            con.close()
    materialize_v3(root)


def build_outputs(root: Path) -> dict[str, pd.DataFrame | dict[str, Any]]:
    started = time.perf_counter()
    ensure_v3_materialized(root)
    inputs = load_inputs(root)
    baseline = pd.read_csv(root / "results" / "official" / "fiscal_space_result.csv")
    baseline = baseline[baseline["xi"].eq(XI)].copy()
    baseline_classes = baseline[["country_id", "policy_id", "gmi_version", "country_policy_result_class"]].drop_duplicates()
    gap_resid = residualized_gap_map(root)

    grids = []
    diagnostic_rows: list[dict[str, Any]] = []
    for variant in variants():
        grid, diag = run_variant(root, inputs, variant, baseline, baseline_classes, gap_resid)
        grids.append(grid)
        diagnostic_rows.extend(diag)
    robust_grid = pd.concat(grids, ignore_index=True, sort=False)
    merge_cols = ["country_id", "policy_variant_id", "scenario_id", "regime_id"]
    base_cols = merge_cols + [
        "policy_id",
        "gmi_version",
        "v_gross",
        "cell_result_class",
        "country_policy_result_class",
        "fs_eff",
    ]
    merged = robust_grid.merge(
        baseline[base_cols].rename(
            columns={
                "v_gross": "v_baseline",
                "cell_result_class": "baseline_cell_result_class",
                "country_policy_result_class": "baseline_country_policy_result_class",
                "fs_eff": "fs_eff_baseline",
            }
        ),
        on=merge_cols,
        how="left",
        suffixes=("", "_baseline_key"),
    )
    merged["delta_v"] = merged["v_variant"] - merged["v_baseline"]
    merged["abs_delta_v"] = merged["delta_v"].abs()
    merged["cambia_clase_celda"] = merged["variant_cell_result_class"] != merged["baseline_cell_result_class"]
    merged["cambia_clasificacion_pais_politica"] = merged["variant_country_policy_result_class"] != merged["baseline_country_policy_result_class"]
    merged["baseline_crosses_v1"] = merged["v_baseline"] >= 1.0
    merged["variant_crosses_v1"] = merged["v_variant"] >= 1.0
    merged["baseline_reversed_flag"] = merged["baseline_crosses_v1"] & ~merged["variant_crosses_v1"]
    merged["headline_cell"] = merged.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)
    merged["run_id"] = RUN_ID
    merged["run_type"] = RUN_TYPE
    merged["parameter_set_id"] = PARAMETER_SET_ID
    merged["baseline_parameter_set_id"] = BASELINE_COMPARISON_PARAMETER_SET
    merged["dataset_version"] = DATASET_VERSION

    robustness_table = merged[
        [
            "run_id",
            "run_type",
            "variant_id",
            "variant_family",
            "variant_label",
            "country_id",
            "policy_id",
            "policy_variant_id",
            "gmi_version",
            "scenario_id",
            "regime_id",
            "headline_cell",
            "v_baseline",
            "v_variant",
            "delta_v",
            "abs_delta_v",
            "baseline_cell_result_class",
            "variant_cell_result_class",
            "cambia_clase_celda",
            "baseline_country_policy_result_class",
            "variant_country_policy_result_class",
            "cambia_clasificacion_pais_politica",
            "baseline_reversed_flag",
            "variant_note",
            "parameter_set_id",
            "baseline_parameter_set_id",
            "dataset_version",
        ]
    ].sort_values(["variant_id", "country_id", "policy_variant_id", "scenario_id", "regime_id"])

    summaries = []
    for variant_id, grp in robustness_table.groupby("variant_id"):
        summaries.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "variant_id": variant_id,
                "diagnostic_key": "summary",
                "diagnostic_value": json.dumps(
                    {
                        "max_abs_delta_v_headline": float(grp.loc[grp["headline_cell"], "abs_delta_v"].max() or 0.0),
                        "cell_class_changes": int(grp["cambia_clase_celda"].sum()),
                        "country_policy_class_changes": int(grp["cambia_clasificacion_pais_politica"].sum()),
                        "baseline_reversed_cells": int(grp["baseline_reversed_flag"].sum()),
                    },
                    sort_keys=True,
                ),
                "diagnostic_note": "Deterministic robustness summary; does not modify official classification.",
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    diagnostic = pd.concat([pd.DataFrame(diagnostic_rows), classify_required_windows(inputs), pd.DataFrame(summaries)], ignore_index=True, sort=False)
    manifest = {
        "run_id": RUN_ID,
        "run_type": RUN_TYPE,
        "parameter_set_id": PARAMETER_SET_ID,
        "baseline_parameter_set_id": BASELINE_COMPARISON_PARAMETER_SET,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_hash": sha256_file(root / "reproducibility" / "snapshot" / f"dataset_manifest_{DATASET_VERSION}.json"),
        "variant_count": len(variants()),
        "robustness_rows": int(len(robustness_table)),
        "headline_rows": int(robustness_table["headline_cell"].sum()),
        "runtime_seconds": time.perf_counter() - started,
        "commit_sha": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty": bool(git_value(["status", "--short"])),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": "GMI microdata-strong deferred pending ENAHO, Phase B optional.",
    }
    return {"robustness_table": robustness_table, "diagnostic_result": diagnostic, "manifest": manifest}


def write_outputs(root: Path, outputs: dict[str, Any]) -> None:
    reports = root / "reports"
    result_dir = root / "results" / "official"
    reports.mkdir(exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    for name in ["robustness_table", "diagnostic_result"]:
        df = outputs[name]
        df.to_csv(result_dir / f"{name}.csv", index=False)
        df.to_csv(reports / f"{name}_baseline-official-v3.csv", index=False)
    (reports / "run_manifest_robustness_6a_baseline-official-v3.json").write_text(json.dumps(clean(outputs["manifest"]), indent=2, sort_keys=True), encoding="utf-8")
    (result_dir / "robustness_manifest.json").write_text(json.dumps(clean(outputs["manifest"]), indent=2, sort_keys=True), encoding="utf-8")
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        for name in ["robustness_table", "diagnostic_result"]:
            con.register("_df", outputs[name])
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    outputs = build_outputs(ROOT)
    if not args.no_write:
        write_outputs(ROOT, outputs)
    print(json.dumps(clean({"status": "OK", **outputs["manifest"]}), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
