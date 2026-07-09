"""Etapa 6B diagnostics and falsification runner.

All rows are labelled run_type=diagnostic and compare against the frozen
baseline-official-v3 outputs. The certified mechanics in src/ai_usp are reused
for cell evaluation; the official baseline outputs are never modified.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_usp.adoption import build_adoption_state
from ai_usp.fiscal_channels import compute_mfc
from ai_usp.fiscal_space import compute_fiscal_space
from ai_usp.labor_share import compute_labor_capital_weights
from ai_usp.shock import convert_phi_raw
from ai_usp.translation import translate_to_growth
from scripts.run_official_monte_carlo import PARAMETER_SET_ID, load_inputs
from scripts.run_official_tier_a import (
    COUNTRIES,
    DATASET_VERSION,
    REGIMES,
    SCENARIOS,
    admin_costs,
    clean,
    git_value,
    policy_instances,
    regime_settings,
    scenario_parameters,
    sha256_file,
    value_lookup,
)


RUN_ID = "official_4c_diagnostics_6b_baseline_official_v3"
RUN_TYPE = "diagnostic"
XI = 0.10
SOBOL_N = 1024
SOBOL_SEED = 62024
HEADLINE_CELLS = {
    ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
    ("PER", "PEN", "stress", "r4"),
}
PLACEBO_ENDPOINT_YEAR = 2018
PLACEBO_ANCHOR_YEAR = 2010


@dataclass(frozen=True)
class CellEvaluation:
    v_gross: float
    fs_eff: float
    g_ai_level: float
    mfc_gross: float
    cost_gross_gdp: float
    channel_contrib: dict[str, float]
    fixed_costs: dict[str, float]


def _norm_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return str(value)


def official_baseline() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "results" / "official" / "fiscal_space_result.csv")
    return df[df["xi"].eq(XI)].copy()


def headline_baseline() -> pd.DataFrame:
    b = official_baseline()
    return b[b.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)].copy()


def extra_tables(root: Path) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"), read_only=True)
    try:
        tables = {
            "macro_anchor": con.execute("SELECT * FROM macro_anchor WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "fiscal_anchor": con.execute("SELECT * FROM fiscal_anchor WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "historical_capture_distribution": con.execute("SELECT * FROM historical_capture_distribution WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "grd_revenue_contrast": con.execute("SELECT * FROM grd_revenue_contrast WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
        }
    finally:
        con.close()
    tables["itu"] = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "itu" / "itu_digital.parquet")
    tables["pip"] = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "pip" / "pip_poverty.parquet")
    tables["imf"] = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "imf" / "imf_fiscal_macro.parquet")
    return tables


def make_value(values: pd.DataFrame, overrides: dict[str, float] | None = None):
    base_value = value_lookup(values)
    overrides = overrides or {}

    def value(
        name: str,
        *,
        country: str | None = None,
        scenario: str | None = None,
        policy: str | None = None,
        regime: str | None = None,
    ) -> float:
        if name in overrides:
            return float(overrides[name])
        return base_value(name, country=country, scenario=scenario, policy=policy, regime=regime)

    return value


def cached_value_lookup(values: pd.DataFrame):
    base_value = value_lookup(values)

    @lru_cache(maxsize=None)
    def cached(
        name: str,
        country: str | None = None,
        scenario: str | None = None,
        policy: str | None = None,
        regime: str | None = None,
    ) -> float:
        return base_value(name, country=country, scenario=scenario, policy=policy, regime=regime)

    return cached


def make_fast_value(inputs: dict[str, Any], overrides: dict[str, float] | None = None):
    base_value = inputs["_base_value"]
    overrides = overrides or {}

    def value(
        name: str,
        *,
        country: str | None = None,
        scenario: str | None = None,
        policy: str | None = None,
        regime: str | None = None,
    ) -> float:
        if name in overrides:
            return float(overrides[name])
        return float(base_value(name, country, scenario, policy, regime))

    return value


def evaluate_cell(
    inputs: dict[str, Any],
    country: str,
    policy_variant_id: str,
    scenario: str,
    regime_code: str,
    overrides: dict[str, float] | None = None,
) -> CellEvaluation:
    value = make_fast_value(inputs, overrides)
    policy = inputs["_policy_instance_map"][(country, policy_variant_id)]
    adoption = build_adoption_state(
        q_use_target=value("q_use_target", country=country),
        aipi=value("A_aipi_total", country=country),
        informality=value("I_adopt_informality", country=country),
        gap=value("Gap_excluded_indicators", country=country),
        omega_i=value("omega_I", country=country),
        omega_g=value("omega_G", country=country),
        nu_a=value("nu_A", country=country),
        nu_i=value("nu_I", country=country),
        nu_g=value("nu_G", country=country),
        epsilon_mu=value("epsilon_mu", country=country),
        frozen=True,
    )
    phi_raw, kappa, pi_ai_y, lambda_ai, lambda_ai_kbase = scenario_parameters(value, country, scenario)
    shock = convert_phi_raw(scenario, phi_raw, kappa, pi_ai_y)
    eprod_frontier = value("E_prod_frontier")
    frontier = [
        {**row, "exposure_productive": eprod_frontier}
        for row in inputs["_frontier_records"]
    ]
    tr = translate_to_growth(
        exposure_productive=value("E_prod", country=country),
        q_prod=adoption.q_prod,
        phi_y_nom=shock.phi_y_nom,
        beta=value("beta_translation", country=country),
        gamma=value("gamma_translation", country=country),
        epsilon=value("epsilon", country=country),
        horizon_years=10,
        benchmark_rows=frontier,
        missing_frontier_exposure_fallback=eprod_frontier,
    )
    regime = regime_settings(value, regime_code)
    weights = compute_labor_capital_weights(
        labor_share=value("LS_labor_share", country=country),
        g_ai_level=tr.g_ai_level,
        q_prod=adoption.q_prod,
        e_auto=value("E_auto", country=country),
        e_aug=value("E_aug", country=country),
        delta_s=value("delta_s", country=country),
        psi_s=value("psi_s", country=country),
        zeta_s=value("zeta_s", country=country),
        rst=value("RST", country=country),
        lambda_ls=value("lambda_LS", country=country),
        chi_kbase=value("chi_Kbase", country=country),
        chi_dom=value("chi_dom", country=country),
        psi_shift=value("psi_shift", country=country),
        tau_l_disp=value("tau_L_disp", country=country),
        tau_k_disp=value("tau_K_disp", country=country),
        tau_r_disp=value("tau_R_disp", country=country),
        mpc_w=value("mpc_W", country=country),
        mpc_pi=value("mpc_Pi", country=country),
        mpc_r=value("mpc_R", country=country),
        m_m=value("m_M", country=country),
        theta_r_dom=value("theta_R_dom", country=country),
        exempt_c=value("exempt_C", country=country),
    )
    channel = compute_mfc(
        weights=weights,
        regime=regime,
        tau_l_eff=value("tau_L_eff", country=country),
        tau_k_eff=value("tau_K_eff", country=country),
        tau_c_eff=value("tau_C_eff", country=country),
        lambda_ai=lambda_ai,
        lambda_ai_kbase=lambda_ai_kbase,
        use_erosion_companion=True,
    )
    fixed = admin_costs(inputs["policy_admin_transition_cost"], country, policy["policy_id"], regime.leakage_multiplier)
    fspace = compute_fiscal_space(
        mfc_gross=channel.mfc_gross,
        mfc_tilde_gross=channel.mfc_tilde_gross,
        g_ai_level=tr.g_ai_level,
        ac_net_fix=fixed.ac_net_fix,
        tr_ann=fixed.tr_ann,
        leak_fix=fixed.leak_fix,
        cost_gross_gdp=policy["cost_gross_gdp"],
        cost_net_gdp=policy["cost_net_gdp"],
    )
    def erode(contrib: float, epsilon: float, tau: float) -> float:
        if regime.regime_code == "r0":
            return contrib
        return contrib * max(0.0, 1.0 - epsilon * tau)

    channel_contrib = {
        "labor": erode(channel.omega_l * channel.tau_l, regime.epsilon_ero_l, channel.tau_l),
        "capital": erode(channel.omega_k_net * channel.tau_k, regime.epsilon_ero_k, channel.tau_k),
        "consumption": erode(channel.omega_c * channel.tau_c, regime.epsilon_ero_c, channel.tau_c),
        "ai_rent": erode(lambda_ai * channel.tau_ai, regime.epsilon_ero_ai, channel.tau_ai),
    }
    return CellEvaluation(
        v_gross=fspace.v_gross,
        fs_eff=fspace.fs_eff,
        g_ai_level=tr.g_ai_level,
        mfc_gross=channel.mfc_gross,
        cost_gross_gdp=policy["cost_gross_gdp"],
        channel_contrib=channel_contrib,
        fixed_costs={"ac_net_fix": fixed.ac_net_fix, "tr_ann": fixed.tr_ann, "leak_fix": fixed.leak_fix},
    )


def indicator_value(itu: pd.DataFrame, country: str, indicator: str, year: int) -> float | None:
    sub = itu[(itu["country_id"].eq(country)) & (itu["indicator_code"].eq(indicator)) & (itu["year"].le(year))].sort_values("year")
    if sub.empty:
        return None
    return float(sub.iloc[-1]["value"])


def placebo_ict(inputs: dict[str, Any], tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    macro = tables["macro_anchor"]
    hist = tables["historical_capture_distribution"]
    itu = tables["itu"]
    pip = tables["pip"]
    policies = inputs["policy_cost"]
    admin = inputs["policy_admin_transition_cost"]
    frontier_countries = sorted(inputs["frontier_benchmark_anchor"]["benchmark_country_id"].dropna().unique().tolist())
    indicators = ["IT.NET.USER.ZS", "IT.CEL.SETS.P2", "IT.NET.BBND.P2"]
    bench_means = {}
    for ind in indicators:
        vals = [indicator_value(itu, c, ind, PLACEBO_ANCHOR_YEAR) for c in frontier_countries]
        vals = [v for v in vals if v is not None and not math.isnan(v)]
        bench_means[ind] = float(np.mean(vals)) if vals else 1.0
    mfc_pre2009 = (
        hist[(hist["year"].le(2009)) & (hist["revenue_concept"].eq("tax")) & (hist["delta_gdp_positive"].eq(True))]
        .groupby("country_id")["mfc_hist_gross"]
        .apply(lambda s: float(np.nanpercentile(s.dropna().clip(lower=0), 50)) if len(s.dropna()) else np.nan)
        .to_dict()
    )
    rows = []
    for country in COUNTRIES:
        m2010 = macro[(macro["country_id"].eq(country)) & (macro["year"].eq(PLACEBO_ANCHOR_YEAR))].iloc[0]
        m2024 = macro[(macro["country_id"].eq(country)) & (macro["year"].eq(2024))].iloc[0]
        pip_country = pip[(pip["country_id"].eq(country)) & (pip["year"].le(2012))].sort_values("year")
        p = pip_country.iloc[-1] if not pip_country.empty else None
        proxy_parts = []
        proxy_detail = {}
        for ind in indicators:
            raw = indicator_value(itu, country, ind, PLACEBO_ANCHOR_YEAR)
            norm = None if raw is None else min(1.0, raw / bench_means[ind])
            if norm is not None:
                proxy_parts.append(norm)
            proxy_detail[ind] = raw
        ict_proxy = float(np.mean(proxy_parts)) if proxy_parts else 0.0
        phi_annual = 0.0045
        g_placebo = (1.0 + phi_annual * ict_proxy) ** (PLACEBO_ENDPOINT_YEAR - PLACEBO_ANCHOR_YEAR) - 1.0
        mfc = float(mfc_pre2009.get(country, np.nan))
        for _, pc in policies[policies["country_id"].eq(country)].iterrows():
            policy_id = str(pc["policy_id"])
            policy_variant = policy_id if pd.isna(pc["gmi_version"]) else f"{policy_id}:{pc['gmi_version']}"
            if policy_id == "PEN":
                pop65_ratio = float(m2010["population_65_plus_pct"]) / float(m2024["population_65_plus_pct"])
                cost_gdp = float(pc["policy_cost_gross_gdp"]) * pop65_ratio
                cost_note = "PEN 2010 proxy: official 2024 benefit cost scaled by WDI 65+ share ratio."
            else:
                line_lcu = float(p["poverty_line"]) * float(m2010["ppp_conversion_private_consumption"]) * 365.0 if p is not None else np.nan
                pop = float(m2010["population_total"])
                gdp = float(m2010["gdp_nominal_lcu"])
                gap = float(p["poverty_gap"]) if p is not None else np.nan
                if policy_id == "GMI":
                    theta = 1.5 if str(pc["gmi_version"]) == "GMI_loaded_aggregate" else 1.0
                    cost_gdp = theta * gap * line_lcu * pop / gdp
                    cost_note = "GMI 2010 proxy: PIP nearest <=2012 poverty gap times PPP line and theta."
                else:
                    eta = {"MUT": 0.25, "PBI": 0.50, "UBI": 1.00}[policy_id]
                    eligible = pop * (0.75 if policy_id == "PBI" else 1.0)
                    cost_gdp = eta * line_lcu * eligible / gdp
                    cost_note = f"{policy_id} 2010 proxy: eta_policy times PIP PPP line and WDI population."
            fixed = admin[admin["country_id"].eq(country) & admin["policy_id"].eq(policy_id)].iloc[0]
            fixed_cost = float(fixed["admin_cost_new_gdp"]) + float(fixed["transition_recurring_gdp"]) + float(fixed["leakage_fixed_gdp"])
            v = (mfc * g_placebo - fixed_cost) / cost_gdp if cost_gdp and cost_gdp > 0 and not math.isnan(mfc) else np.nan
            klass = "not_feasible"
            if pd.notna(v) and v >= 1.10:
                klass = "broad_feasible_fail_condition"
            elif pd.notna(v) and v >= 1.0:
                klass = "fragile_or_extreme_crossing"
            for regime in REGIMES:
                rows.append(
                    {
                        "run_id": RUN_ID,
                        "run_type": RUN_TYPE,
                        "country_id": country,
                        "policy_id": policy_id,
                        "policy_variant_id": policy_variant,
                        "gmi_version": None if pd.isna(pc["gmi_version"]) else pc["gmi_version"],
                        "scenario_id": "placebo_ict_mid",
                        "regime_id": regime,
                        "anchor_year": PLACEBO_ANCHOR_YEAR,
                        "endpoint_year": PLACEBO_ENDPOINT_YEAR,
                        "phi_ict_annual": phi_annual,
                        "phi_ict_range_low": 0.003,
                        "phi_ict_range_high": 0.006,
                        "ict_proxy_2010": ict_proxy,
                        "ict_proxy_components_json": json.dumps(proxy_detail, sort_keys=True),
                        "g_placebo": g_placebo,
                        "mfc_pre2009_p50": mfc,
                        "policy_cost_gdp_2010_proxy": cost_gdp,
                        "v_placebo": v,
                        "placebo_cell_class": klass,
                        "assumptions_note": cost_note + " AIPI unavailable; proxy is normalized 2010 ITU digital indicator composite.",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": DATASET_VERSION,
                    }
                )
    df = pd.DataFrame(rows)
    broad = int(df["placebo_cell_class"].eq("broad_feasible_fail_condition").sum())
    fragile = int(df["placebo_cell_class"].eq("fragile_or_extreme_crossing").sum())
    verdict = "PASS" if broad == 0 else "FAIL"
    return df, {"broad_feasible_cells": broad, "fragile_or_extreme_crossings": fragile, "verdict": verdict}


def negative_control(inputs: dict[str, Any], baseline: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    values = inputs["values"]
    value = value_lookup(values)
    rows = []
    for _, r in baseline.iterrows():
        country = r["country_id"]
        ratio = value("E_auto", country=country) / value("E_prod", country=country)
        v_nc = float(r["v_gross"]) * ratio
        rows.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "country_id": country,
                "policy_variant_id": r["policy_variant_id"],
                "scenario_id": r["scenario_id"],
                "regime_id": r["regime_id"],
                "v_baseline": float(r["v_gross"]),
                "v_negative_control": v_nc,
                "collapse_ratio": ratio,
                "baseline_crosses_v1": bool(r["v_gross"] >= 1.0),
                "negative_control_crosses_v1": bool(v_nc >= 1.0),
                "verdict": "PASS" if ratio <= 0.40 else "FAIL",
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    df = pd.DataFrame(rows)
    headline = df[df.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)]
    return df, {"median_collapse_ratio_headline": float(headline["collapse_ratio"].median()), "surviving_headline_crosses": int(headline["negative_control_crosses_v1"].sum()), "verdict": "PASS" if headline["negative_control_crosses_v1"].sum() == 0 else "FAIL"}


def loso(inputs: dict[str, Any], tables: dict[str, pd.DataFrame], baseline: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    headline = baseline[baseline.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)]
    grd = tables["grd_revenue_contrast"]

    def plausible_gdp_share(value: Any) -> bool:
        if pd.isna(value):
            return False
        value = float(value)
        return 0.01 <= value <= 0.60

    for _, r in headline.iterrows():
        country = r["country_id"]
        candidate = grd[
            (grd["country_id"].eq(country))
            & (grd["government_level"].eq("general_government"))
            & (grd["grd_tax_including_sc_gdp"].map(plausible_gdp_share))
            & (grd["oecd_tax_including_sc_gdp"].map(plausible_gdp_share))
        ]
        latest = candidate.sort_values("year").tail(1)
        if latest.empty or pd.isna(latest.iloc[0]["grd_tax_including_sc_gdp"]) or pd.isna(latest.iloc[0]["oecd_tax_including_sc_gdp"]):
            factor = np.nan
            alt_class = "not_available"
            status = "not_available"
            rank_change = None
        else:
            factor = float(latest.iloc[0]["grd_tax_including_sc_gdp"] / latest.iloc[0]["oecd_tax_including_sc_gdp"])
            v_alt = float(r["v_gross"]) * factor
            alt_class = "crosses" if v_alt >= 1.0 else "not_feasible"
            status = "PASS" if (float(r["v_gross"]) >= 1.0) == (v_alt >= 1.0) else "FAIL"
            rank_change = 0 if status == "PASS" else 1
        rows.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "diagnostic_id": "D3_no_oecd_revstats",
                "country_id": country,
                "policy_variant_id": r["policy_variant_id"],
                "scenario_id": r["scenario_id"],
                "regime_id": r["regime_id"],
                "alternative_source": "GRD tax including social contributions vs OECD tax including social contributions",
                "status": status,
                "baseline_v": float(r["v_gross"]),
                "alternative_v": None if pd.isna(factor) else float(r["v_gross"]) * factor,
                "baseline_class": "crosses" if float(r["v_gross"]) >= 1.0 else "not_feasible",
                "alternative_class": alt_class,
                "rank_change": rank_change,
                "notes": "Like-for-like GRD/OECD tax comparison when general-government contrast exists; duplicate GRD rows outside plausible GDP-share bounds are excluded.",
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    for diagnostic_id, note in [
        ("D3_no_wdi_macro", "IMF snapshot has NGDPD and growth but no complete nominal LCU + population/demography path; full WDI-free rebuild is not available in frozen inputs."),
        ("D3_no_pip", "National poverty-line alternatives for all four countries are not present as clean frozen manual sources; no-PIP rebuild is not available."),
        ("D3_no_aipi", "AIPI has no comparable official alternative in the frozen snapshot; source-unique limitation declared."),
    ]:
        rows.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "diagnostic_id": diagnostic_id,
                "country_id": "ALL",
                "policy_variant_id": "ALL",
                "scenario_id": "ALL",
                "regime_id": "ALL",
                "alternative_source": "not_available_in_snapshot",
                "status": "not_available",
                "baseline_v": np.nan,
                "alternative_v": np.nan,
                "baseline_class": "not_evaluated",
                "alternative_class": "not_available",
                "rank_change": np.nan,
                "notes": note,
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    df = pd.DataFrame(rows)
    evaluated = df[df["status"].isin(["PASS", "FAIL"])]
    verdict = "PASS" if evaluated["status"].eq("FAIL").sum() == 0 else "FAIL"
    return df, {"evaluated_rows": int(len(evaluated)), "failed_rows": int(evaluated["status"].eq("FAIL").sum()), "verdict": verdict}


def channel_ablation(inputs: dict[str, Any], baseline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rows = []
    rent_rows = []
    for key in HEADLINE_CELLS:
        country, policy_variant, scenario, regime = key
        ev = evaluate_cell(inputs, country, policy_variant, scenario, regime)
        fixed_total = sum(ev.fixed_costs.values())
        mfc = ev.mfc_gross
        for channel_name, contrib in ev.channel_contrib.items():
            share = contrib / mfc if mfc else np.nan
            v_without = ((mfc - contrib) * ev.g_ai_level - fixed_total) / ev.cost_gross_gdp if ev.cost_gross_gdp > 0 else np.nan
            rows.append(
                {
                    "run_id": RUN_ID,
                    "run_type": RUN_TYPE,
                    "country_id": country,
                    "policy_variant_id": policy_variant,
                    "scenario_id": scenario,
                    "regime_id": regime,
                    "channel": channel_name,
                    "channel_contribution_mfc": contrib,
                    "channel_share_mfc": share,
                    "v_baseline_recomputed": ev.v_gross,
                    "v_without_channel": v_without,
                    "delta_v": v_without - ev.v_gross,
                    "crossing_survives_without_channel": bool(v_without >= 1.0),
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
        if regime in {"r3", "r4"}:
            no_rent_v = ((mfc - ev.channel_contrib["ai_rent"]) * ev.g_ai_level - fixed_total) / ev.cost_gross_gdp
            rent_rows.append(
                {
                    "run_id": RUN_ID,
                    "run_type": RUN_TYPE,
                    "country_id": country,
                    "policy_variant_id": policy_variant,
                    "scenario_id": scenario,
                    "regime_id": regime,
                    "v_baseline_recomputed": ev.v_gross,
                    "v_no_rent_capture": no_rent_v,
                    "delta_v": no_rent_v - ev.v_gross,
                    "r4_crossing_depends_on_rents": bool(ev.v_gross >= 1.0 and no_rent_v < 1.0),
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
    ablation = pd.DataFrame(rows)
    no_rent = pd.DataFrame(rent_rows)
    return ablation, no_rent, {"dominant_channels": ablation.sort_values("channel_share_mfc", ascending=False).groupby(["country_id", "policy_variant_id", "scenario_id", "regime_id"]).head(1)["channel"].tolist(), "verdict": "reported"}


def high_leakage(inputs: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    for key in HEADLINE_CELLS:
        country, policy_variant, scenario, regime = key
        base = evaluate_cell(inputs, country, policy_variant, scenario, regime)
        overrides = {f"leakage_multiplier_{regime}": 1.0}
        stressed = evaluate_cell(inputs, country, policy_variant, scenario, regime, overrides=overrides)
        rows.append(
            {
                "run_id": RUN_ID,
                "run_type": RUN_TYPE,
                "country_id": country,
                "policy_variant_id": policy_variant,
                "scenario_id": scenario,
                "regime_id": regime,
                "v_baseline_recomputed": base.v_gross,
                "v_high_leakage": stressed.v_gross,
                "delta_v": stressed.v_gross - base.v_gross,
                "crossing_survives_high_leakage": bool(stressed.v_gross >= 1.0),
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    df = pd.DataFrame(rows)
    return df, {"surviving_crosses": int(df["crossing_survives_high_leakage"].sum()), "verdict": "reported"}


def sobol(inputs: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    drivers = pd.read_csv(ROOT / "results" / "official" / "driver_ranking.csv")
    rows = []
    max_rank_change = 0
    for country, policy_variant, scenario, regime in [
        ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
        ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
        ("PER", "PEN", "stress", "r4"),
    ]:
        d = drivers[
            drivers["country_id"].eq(country)
            & drivers["policy_variant_id"].eq(policy_variant)
            & drivers["scenario_id"].eq(scenario)
            & drivers["regime_id"].eq(regime)
        ].sort_values("rank_within_cell").head(10)
        names = d["parameter_name"].tolist()
        p10 = d["parameter_p10"].to_numpy(dtype=float)
        p90 = d["parameter_p90"].to_numpy(dtype=float)
        k = len(names)
        sampler = qmc.Sobol(d=2 * k, scramble=True, seed=SOBOL_SEED)
        sample = sampler.random_base2(m=int(math.log2(SOBOL_N)))
        a = p10 + sample[:, :k] * (p90 - p10)
        b = p10 + sample[:, k:] * (p90 - p10)

        def eval_matrix(mat: np.ndarray) -> np.ndarray:
            out = np.empty(len(mat), dtype=float)
            for idx, row in enumerate(mat):
                out[idx] = evaluate_cell(inputs, country, policy_variant, scenario, regime, dict(zip(names, row, strict=False))).v_gross
            return out

        ya = eval_matrix(a)
        yb = eval_matrix(b)
        variance = float(np.var(np.concatenate([ya, yb]), ddof=1))
        for j, name in enumerate(names):
            ab = a.copy()
            ab[:, j] = b[:, j]
            yab = eval_matrix(ab)
            if variance <= 0:
                s1 = 0.0
                st = 0.0
            else:
                s1 = float(np.mean(yb * (yab - ya)) / variance)
                st = float(0.5 * np.mean((ya - yab) ** 2) / variance)
            rows.append(
                {
                    "run_id": RUN_ID,
                    "run_type": RUN_TYPE,
                    "country_id": country,
                    "policy_variant_id": policy_variant,
                    "scenario_id": scenario,
                    "regime_id": regime,
                    "parameter_name": name,
                    "saltelli_n": SOBOL_N,
                    "s1": s1,
                    "st": st,
                    "spearman_rank": int(d.iloc[j]["rank_within_cell"]),
                    "spearman_rho": float(d.iloc[j]["spearman_rho_with_v_gross"]),
                    "parameter_p10": float(p10[j]),
                    "parameter_p90": float(p90[j]),
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
        cell_rows = [r for r in rows if r["country_id"] == country and r["policy_variant_id"] == policy_variant and r["scenario_id"] == scenario and r["regime_id"] == regime]
        ranked = sorted(cell_rows, key=lambda r: abs(r["st"]), reverse=True)
        for rank, row in enumerate(ranked, start=1):
            row["sobol_st_rank"] = rank
            change = abs(rank - row["spearman_rank"])
            row["rank_change_abs"] = int(change)
            max_rank_change = max(max_rank_change, int(change))
    df = pd.DataFrame(rows)
    return df, {"max_rank_change_abs": max_rank_change, "verdict": "PASS" if len(df) == 30 else "FAIL"}


def diagnostic_rows(
    placebo_summary: dict[str, Any],
    negative_summary: dict[str, Any],
    loso_summary: dict[str, Any],
    ablation_summary: dict[str, Any],
    no_rent: pd.DataFrame,
    leakage_summary: dict[str, Any],
    sobol_summary: dict[str, Any],
) -> pd.DataFrame:
    rows = [
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D1_placebo_ict",
            "diagnostic_key": "expected_verdict",
            "diagnostic_value": json.dumps(placebo_summary, sort_keys=True),
            "diagnostic_note": "Pass criterion declared before run: no mid-analog placebo ICT cell may be conditionally/robustly feasible; crossings must remain fragile/extreme.",
            "diagnostic_family": "placebo_falsification",
            "expected_verdict": "PASS if broad_feasible_cells == 0",
            "verdict": placebo_summary["verdict"],
            "rank_change": "not_applicable",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D2_negative_control_sectorial",
            "diagnostic_key": "exposure_displacement_control",
            "diagnostic_value": json.dumps(negative_summary, sort_keys=True),
            "diagnostic_note": (
                "E_prod replaced by automation/displacement exposure E_auto=0.035; expected V collapse roughly proportional to 0.035/0.11. "
                "Interpretation: el colapso mecanico opera (ratio = ratio de exposiciones); la celda superviviente CHL GMI stress refleja "
                "sobredeterminacion por escala del shock vs costo (corroborado por D4); caveat aplicado al claim condicional de CHL GMI."
            ),
            "diagnostic_family": "negative_control",
            "expected_verdict": "PASS if no headline crossing survives the non-productive exposure control",
            "verdict": negative_summary["verdict"],
            "rank_change": "not_applicable",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D3_leave_one_source_out",
            "diagnostic_key": "classification_stability",
            "diagnostic_value": json.dumps(loso_summary, sort_keys=True),
            "diagnostic_note": "LOSO uses available frozen alternatives; unavailable alternatives are documented rather than imputed.",
            "diagnostic_family": "source_falsification",
            "expected_verdict": "PASS if evaluated headline classifications are stable; not_available rows are limitations",
            "verdict": loso_summary["verdict"],
            "rank_change": str(loso_summary.get("failed_rows", 0)),
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D4_channel_ablation",
            "diagnostic_key": "channel_shares",
            "diagnostic_value": json.dumps(ablation_summary, sort_keys=True),
            "diagnostic_note": "One channel is removed at a time; table reports contribution shares and whether crossings survive.",
            "diagnostic_family": "mechanism_ablation",
            "expected_verdict": "reported",
            "verdict": "reported",
            "rank_change": "reported",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D5_no_rent_capture",
            "diagnostic_key": "r4_rent_dependency",
            "diagnostic_value": json.dumps({"rows": int(len(no_rent)), "rent_dependent_crossings": int(no_rent["r4_crossing_depends_on_rents"].sum()) if not no_rent.empty else 0}, sort_keys=True),
            "diagnostic_note": "tau_AI set to zero conceptually by removing AI-rent contribution in r3/r4 cells.",
            "diagnostic_family": "mechanism_ablation",
            "expected_verdict": "reported",
            "verdict": "reported",
            "rank_change": "reported",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D6_high_leakage_stress",
            "diagnostic_key": "high_leakage",
            "diagnostic_value": json.dumps(leakage_summary, sort_keys=True),
            "diagnostic_note": "Leakage multiplier set to 1.0 for the evaluated headline regimes.",
            "diagnostic_family": "stress_falsification",
            "expected_verdict": "reported",
            "verdict": "reported",
            "rank_change": "reported",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D7_informalization_mirror",
            "diagnostic_key": "not_applicable_by_construction",
            "diagnostic_value": "not_applicable",
            "diagnostic_note": "Baseline does not activate endogenous formalization in r1/r4; informalization mirror is not applicable by construction.",
            "diagnostic_family": "scope_check",
            "expected_verdict": "not_applicable",
            "verdict": "not_applicable",
            "rank_change": "not_applicable",
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
        {
            "run_id": RUN_ID,
            "run_type": RUN_TYPE,
            "variant_id": "D8_sobol_saltelli",
            "diagnostic_key": "sobol_vs_spearman",
            "diagnostic_value": json.dumps(sobol_summary, sort_keys=True),
            "diagnostic_note": "Saltelli/Sobol N=1024 over the top-10 Spearman drivers in three headline cells; rank_change compares ST rank to Spearman rank.",
            "diagnostic_family": "sensitivity_decomposition",
            "expected_verdict": "PASS if 30 Sobol rows are produced",
            "verdict": sobol_summary["verdict"],
            "rank_change": str(sobol_summary["max_rank_change_abs"]),
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        },
    ]
    return pd.DataFrame(rows)


def merge_diagnostic_result(new_rows: pd.DataFrame) -> pd.DataFrame:
    current = ROOT / "results" / "official" / "diagnostic_result.csv"
    if current.exists():
        old = pd.read_csv(current)
        old = old[old["run_type"].ne(RUN_TYPE)].copy()
    else:
        old = pd.DataFrame()
    all_cols = [
        "run_id",
        "run_type",
        "variant_id",
        "diagnostic_key",
        "diagnostic_value",
        "diagnostic_note",
        "diagnostic_family",
        "expected_verdict",
        "verdict",
        "rank_change",
        "parameter_set_id",
        "dataset_version",
    ]
    for df in [old, new_rows]:
        for col in all_cols:
            if col not in df.columns:
                df[col] = None
    return pd.concat([old[all_cols], new_rows[all_cols]], ignore_index=True)


def build_outputs(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    inputs = load_inputs(root)
    inputs["_base_value"] = cached_value_lookup(inputs["values"])
    policy_map: dict[tuple[str, str], dict[str, Any]] = {}
    for country in COUNTRIES:
        for row in policy_instances(country, inputs["policy_cost"], inputs["wpp"]):
            policy_map[(country, row["policy_variant_id"])] = row
    inputs["_policy_instance_map"] = policy_map
    inputs["_frontier_records"] = inputs["frontier_benchmark_anchor"].to_dict("records")
    tables = extra_tables(root)
    baseline = official_baseline()
    placebo, placebo_summary = placebo_ict(inputs, tables)
    negative, negative_summary = negative_control(inputs, baseline)
    loso_df, loso_summary = loso(inputs, tables, baseline)
    ablation, no_rent, ablation_summary = channel_ablation(inputs, baseline)
    leakage, leakage_summary = high_leakage(inputs)
    sobol_df, sobol_summary = sobol(inputs)
    diag = merge_diagnostic_result(diagnostic_rows(placebo_summary, negative_summary, loso_summary, ablation_summary, no_rent, leakage_summary, sobol_summary))
    manifest = {
        "run_id": RUN_ID,
        "run_type": RUN_TYPE,
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_hash": sha256_file(root / "reproducibility" / "snapshot" / f"dataset_manifest_{DATASET_VERSION}.json"),
        "runtime_seconds": time.perf_counter() - started,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit_sha": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty": bool(git_value(["status", "--short"])),
        "tables": {
            "diagnostic_placebo_ict_result": len(placebo),
            "diagnostic_negative_control_result": len(negative),
            "diagnostic_loso_result": len(loso_df),
            "diagnostic_channel_ablation_result": len(ablation),
            "diagnostic_no_rent_capture_result": len(no_rent),
            "diagnostic_high_leakage_result": len(leakage),
            "diagnostic_sobol_result": len(sobol_df),
        },
    }
    return {
        "diagnostic_result": diag,
        "diagnostic_placebo_ict_result": placebo,
        "diagnostic_negative_control_result": negative,
        "diagnostic_loso_result": loso_df,
        "diagnostic_channel_ablation_result": ablation,
        "diagnostic_no_rent_capture_result": no_rent,
        "diagnostic_high_leakage_result": leakage,
        "diagnostic_sobol_result": sobol_df,
        "manifest": manifest,
    }


def write_outputs(root: Path, outputs: dict[str, Any]) -> None:
    result_dir = root / "results" / "official"
    reports = root / "reports"
    result_dir.mkdir(parents=True, exist_ok=True)
    reports.mkdir(exist_ok=True)
    table_names = [name for name in outputs if name != "manifest"]
    for name in table_names:
        outputs[name].to_csv(result_dir / f"{name}.csv", index=False)
        outputs[name].to_csv(reports / f"{name}_baseline-official-v3.csv", index=False)
    (reports / "run_manifest_diagnostics_6b_baseline-official-v3.json").write_text(json.dumps(clean(outputs["manifest"]), indent=2, sort_keys=True), encoding="utf-8")
    (result_dir / "diagnostics_manifest.json").write_text(json.dumps(clean(outputs["manifest"]), indent=2, sort_keys=True), encoding="utf-8")
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        for name in table_names:
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
