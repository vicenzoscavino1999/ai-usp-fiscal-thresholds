"""Official deterministic Tier A runner for Etapa 4B.

The certified mechanics live in src/ai_usp. This runner only orchestrates the
official 4-country parameter set, provenance, output writing, and reporting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict, is_dataclass
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

from ai_usp.adoption import build_adoption_state
from ai_usp.classify import classify_cell
from ai_usp.fiscal_channels import RegimeSettings, apply_base_broadening_to_structure, compute_mfc
from ai_usp.fiscal_space import compute_fiscal_space
from ai_usp.historical import HistoricalPercentiles, classify_historical_plausibility
from ai_usp.labor_share import compute_labor_capital_weights
from ai_usp.policy_cost import endpoint_cost_scale, fixed_policy_costs
from ai_usp.shock import convert_phi_raw
from ai_usp.thresholds import XI_GRID, debt_guardrail_pass, invert_threshold
from ai_usp.translation import translate_to_growth


DATASET_VERSION = "v1.0.1-official-4c"
PARAMETER_SET_ID = "baseline-official-v2"
RUN_LABEL = "official"
RUN_ID = "official_4c_tierA_baseline_official_v2"
MODEL_VERSION = "deterministic-engine-v1_official-runner"
COUNTRIES = ("PER", "CHL", "COL", "MEX")
POLICIES = ("PEN", "GMI", "MUT", "PBI", "UBI")
SCENARIOS = ("low", "mid", "high", "stress")
REGIMES = ("r0", "r1", "r2", "r3", "r4")
ANCHOR_YEAR = 2024
ENDPOINT_YEAR = 2034
HORIZON_YEARS = 10
PENDING_STATUSES = {
    "registered_author_review",
    "literature_disciplined_pending_author_signature",
}


class OfficialRunError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(value: Any) -> Any:
    if is_dataclass(value):
        return clean(asdict(value))
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return clean(value.item())
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value) if isinstance(value, (pd.Timestamp,)) else False:
        return None
    return value


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["country_id", "scenario_id", "policy_id", "regime_code"]:
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), None)
            df[col] = df[col].map(lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else str(x))
    return df


def load_inputs(root: Path) -> dict[str, Any]:
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        values = normalize_keys(
            con.execute(
                "SELECT * FROM value_assignment_table WHERE parameter_set_id = ?",
                [PARAMETER_SET_ID],
            ).fetchdf()
        )
        if values.empty:
            raise OfficialRunError(f"No rows for {PARAMETER_SET_ID}.")
        pending = values[values["audit_status"].isin(PENDING_STATUSES)]
        if not pending.empty:
            raise OfficialRunError("Pending author-review rows remain:\n" + pending[["name", "country_id", "audit_status"]].to_string(index=False))
        tables = {
            "policy_cost": con.execute("SELECT * FROM policy_cost WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "policy_admin_transition_cost": con.execute("SELECT * FROM policy_admin_transition_cost WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "frontier_benchmark_anchor": con.execute("SELECT * FROM frontier_benchmark_anchor WHERE dataset_version = ? AND benchmark_set_id = 'baseline_oecd_eurostat_ge10_2024'", [DATASET_VERSION]).fetchdf(),
            "historical_capture_percentiles": con.execute("SELECT * FROM historical_capture_percentiles WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "fiscal_anchor": con.execute("SELECT * FROM fiscal_anchor WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "macro_anchor": con.execute("SELECT country_id, year, gdp_nominal_lcu FROM macro_anchor WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "digital_gap_anchor": con.execute("SELECT * FROM digital_gap_anchor WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "grd_revenue_contrast": con.execute("SELECT * FROM grd_revenue_contrast WHERE dataset_version = ?", [DATASET_VERSION]).fetchdf(),
            "input_audit_report": con.execute("SELECT * FROM input_audit_report WHERE parameter_set_id = ?", [PARAMETER_SET_ID]).fetchdf(),
            "double_counting_audit": con.execute("SELECT * FROM double_counting_audit WHERE parameter_set_id = ?", [PARAMETER_SET_ID]).fetchdf(),
        }
    finally:
        con.close()
    wpp = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "wpp" / "wpp_projections.parquet")
    return {"values": values, "wpp": wpp, **tables}


def value_lookup(values: pd.DataFrame):
    def value(
        name: str,
        *,
        country: str | None = None,
        scenario: str | None = None,
        policy: str | None = None,
        regime: str | None = None,
    ) -> float:
        df = values[values["name"].eq(name)].copy()
        for col, arg in [
            ("country_id", country),
            ("scenario_id", scenario),
            ("policy_id", policy),
            ("regime_code", regime),
        ]:
            if arg is None:
                df = df[df[col].isna()]
            else:
                df = df[df[col].isna() | df[col].eq(str(arg))]
        if df.empty:
            raise OfficialRunError(f"Missing calibrated value: {name} country={country} scenario={scenario} policy={policy} regime={regime}")
        df["_score"] = 0
        for col, arg in [
            ("country_id", country),
            ("scenario_id", scenario),
            ("policy_id", policy),
            ("regime_code", regime),
        ]:
            if arg is not None:
                df["_score"] += df[col].eq(str(arg)).astype(int)
        df = df.sort_values("_score", ascending=False)
        return float(df.iloc[0]["baseline_value"])

    return value


def scenario_parameters(value, country: str, scenario: str) -> tuple[float, float, float, float, float]:
    phi_raw = value(f"phi_raw_{scenario}", scenario=scenario)
    if scenario == "high":
        kappa = value("kappa_LP_to_Y_high", country=country, scenario=scenario)
    elif scenario == "stress":
        kappa = value("kappa_Y_to_Y_stress", scenario=scenario)
    else:
        kappa = value(f"kappa_TFP_to_Y_{scenario}", scenario=scenario)
    pi_ai_y = value(f"pi_AI_Y_{scenario}", scenario=scenario)
    lambda_ai = value(f"lambda_AI_{scenario}", scenario=scenario)
    lambda_ai_kbase = value(f"lambda_AI_Kbase_{scenario}", scenario=scenario)
    return phi_raw, kappa, pi_ai_y, lambda_ai, lambda_ai_kbase


def eligible_metric(wpp: pd.DataFrame, country: str, year: int, policy: str) -> float:
    sub = wpp[(wpp["ISO3_code"].eq(country)) & (wpp["Time"].eq(year))].copy()
    if sub.empty:
        raise OfficialRunError(f"WPP missing {country} {year}")
    total = float(sub["PopTotal"].sum())
    if policy == "PEN" and country == "COL":
        male59 = float(sub.loc[sub["AgeGrpStart"] >= 59, "PopMale"].sum())
        female54 = float(sub.loc[sub["AgeGrpStart"] >= 54, "PopFemale"].sum())
        age80 = float(sub.loc[sub["AgeGrpStart"] >= 80, "PopTotal"].sum())
        eligible = male59 + female54
        under80 = max(0.0, eligible - age80)
        return under80 * 80_000.0 * 12.0 + age80 * 225_000.0 * 12.0
    if policy == "PEN":
        return float(sub.loc[sub["AgeGrpStart"] >= 65, "PopTotal"].sum()) / total
    if policy == "PBI":
        return float(sub.loc[sub["AgeGrpStart"] >= 18, "PopTotal"].sum()) / total
    return 1.0


def policy_instances(country: str, policy_cost: pd.DataFrame, wpp: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    pc = policy_cost[policy_cost["country_id"].eq(country)]
    for policy in POLICIES:
        if policy == "GMI":
            versions = ("GMI_ideal_aggregate", "GMI_loaded_aggregate")
        else:
            versions = (None,)
        for version in versions:
            cost_row = pc[(pc["policy_id"].eq(policy)) & (pc["gmi_version"].isna() if version is None else pc["gmi_version"].eq(version))]
            if cost_row.empty:
                raise OfficialRunError(f"Missing policy_cost for {country}/{policy}/{version}")
            r = cost_row.iloc[0]
            cost_2024 = float(r["policy_cost_gross_gdp"])
            net_2024 = float(r["policy_cost_net_gdp"])
            fixed = policy == "GMI"
            if policy == "PEN" and country == "COL":
                scale = eligible_metric(wpp, country, ENDPOINT_YEAR, policy) / eligible_metric(wpp, country, ANCHOR_YEAR, policy)
                cost_endpoint = cost_2024 * scale
                net_endpoint = net_2024 * scale
                rule_note = "Colombia PEN endpoint uses WPP sex/age rule: women>=54, men>=59; COP 80k monthly under 80 and COP 225k monthly age>=80."
            else:
                anchor = eligible_metric(wpp, country, ANCHOR_YEAR, policy)
                endpoint = eligible_metric(wpp, country, ENDPOINT_YEAR, policy)
                cost_endpoint = endpoint_cost_scale(cost_2024, anchor, endpoint, fixed_policy=fixed)
                net_endpoint = endpoint_cost_scale(net_2024, anchor, endpoint, fixed_policy=fixed)
                rule_note = "GMI fixed aggregate endpoint c_2034=c_2024." if fixed else "Endpoint cost scales by WPP eligible-share ratio."
            rows.append(
                {
                    "country_id": country,
                    "policy_id": policy,
                    "gmi_version": version,
                    "policy_variant_id": policy if version is None else f"{policy}:{version}",
                    "cost_gross_gdp": cost_endpoint,
                    "cost_net_gdp": net_endpoint,
                    "cost_2024_gdp": cost_2024,
                    "endpoint_cost_rule": rule_note,
                    "policy_parameter_id": r.get("policy_parameter_id"),
                }
            )
    return rows


def admin_costs(admin: pd.DataFrame, country: str, policy: str, leakage_multiplier: float):
    rows = admin[admin["country_id"].eq(country) & admin["policy_id"].eq(policy)]
    if rows.empty:
        raise OfficialRunError(f"Missing admin costs for {country}/{policy}")
    r = rows.iloc[0]
    return fixed_policy_costs(
        admin_cost_new_gdp=float(r["admin_cost_new_gdp"]),
        admin_savings_existing_gdp=float(r["admin_savings_existing_gdp"]),
        transition_oneoff_gdp=float(r["transition_oneoff_gdp"]),
        transition_recurring_gdp=float(r["transition_recurring_gdp"]),
        transition_horizon_years=int(r["transition_horizon_years"]),
        transition_discount_rate=float(r["transition_discount_rate"]),
        leakage_fixed_gdp=float(r["leakage_fixed_gdp"]),
        leakage_multiplier=leakage_multiplier,
    )


def historical_percentiles(inputs: dict[str, Any], country: str, variable: str) -> HistoricalPercentiles:
    pct_df = inputs["historical_capture_percentiles"]
    rows = pct_df[
        pct_df["country_id"].eq(country)
        & pct_df["revenue_concept"].eq(variable)
        & pct_df["percentile_sample"].eq("2000plus")
    ]
    if rows.empty:
        raise OfficialRunError(f"Missing canonical historical_capture_percentiles row for {country}/{variable}/2000plus")
    row = rows.iloc[0]
    return HistoricalPercentiles(
        revenue_concept=variable,
        percentile_sample="2000plus",
        p50=float(row["p50_mfc_hist_positive"]),
        p75=float(row["p75_mfc_hist_positive"]),
        p90=float(row["p90_mfc_hist_positive"]),
        p50_ci_low=float(row["p50_ci_low"]),
        p50_ci_high=float(row["p50_ci_high"]),
        p75_ci_low=float(row["p75_ci_low"]),
        p75_ci_high=float(row["p75_ci_high"]),
        p90_ci_low=float(row["p90_ci_low"]),
        p90_ci_high=float(row["p90_ci_high"]),
    )


def regime_settings(value, regime: str) -> RegimeSettings:
    return RegimeSettings(
        regime_code=regime,
        tau_l_delta=value(f"tau_L_relative_delta_{regime}", regime=regime),
        tau_k_delta=value(f"tau_K_relative_delta_{regime}", regime=regime),
        tau_c_delta=value(f"tau_C_relative_delta_{regime}", regime=regime),
        tau_ai_eff=value(f"tau_AI_eff_{regime}", regime=regime),
        base_broadening_delta=value(f"base_broadening_delta_{regime}", regime=regime),
        leakage_multiplier=value(f"leakage_multiplier_{regime}", regime=regime),
        epsilon_ero_l=value(f"epsilon_ero_L_{regime}", regime=regime),
        epsilon_ero_k=value(f"epsilon_ero_K_{regime}", regime=regime),
        epsilon_ero_c=value(f"epsilon_ero_C_{regime}", regime=regime),
        epsilon_ero_ai=value(f"epsilon_ero_AI_{regime}", regime=regime),
    )


def classify_country_policy(rows: list[dict[str, Any]]) -> pd.DataFrame:
    result = []
    for (country, policy, gmi_version), grp in pd.DataFrame(rows).groupby(["country_id", "policy_id", "gmi_version"], dropna=False):
        crossings = grp[grp["crosses_buffer"]]
        if policy == "UBI":
            klass = "stress_benchmark_only"
        elif crossings.empty:
            klass = "not_feasible"
        elif (~crossings["debt_guardrail_pass"]).any() or (crossings["historical_total_revenue_class"].eq("extreme_or_outside_historical_support")).any():
            klass = "fragile_feasibility"
        else:
            klass = "conditional_feasibility_probabilistic_leg_not_evaluated"
        result.append(
            {
                "run_id": RUN_ID,
                "country_id": country,
                "policy_id": policy,
                "gmi_version": None if pd.isna(gmi_version) else gmi_version,
                "country_policy_result_class": klass,
                "probabilistic_leg": "not_evaluated",
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    return pd.DataFrame(result)


def mark_and_classify_cells(fiscal_rows: list[dict[str, Any]]) -> None:
    df = pd.DataFrame([r for r in fiscal_rows if math.isclose(float(r["xi"]), 0.10)])
    stress_only: dict[tuple[str, str, str], bool] = {}
    for key, grp in df.groupby(["country_id", "policy_variant_id", "gmi_version"], dropna=False):
        crossing = grp[grp["crosses_v1"]]
        stress_only[key] = (not crossing.empty) and all(
            crossing["scenario_id"].eq("stress") & crossing["regime_id"].eq("r4")
        )
    for row in fiscal_rows:
        key = (row["country_id"], row["policy_variant_id"], row["gmi_version"])
        stress_r4 = stress_only.get(key, False) and row["scenario_id"] == "stress" and row["regime_id"] == "r4" and bool(row["crosses_v1"])
        row["cell_result_class"] = classify_cell(
            existence_condition_pass=bool(row["existence_condition_pass"]),
            v_gross=float(row["v_gross"]),
            crosses_v1=bool(row["crosses_v1"]),
            debt_guardrail_pass=bool(row["debt_guardrail_pass"]),
            stress_r4_only_crossing=stress_r4,
        )


def run_tier_a(root: Path = ROOT, write: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    inputs = load_inputs(root)
    values = inputs["values"]
    value = value_lookup(values)
    eprod_frontier = value("E_prod_frontier")
    frontier = inputs["frontier_benchmark_anchor"].copy()
    frontier["exposure_productive"] = eprod_frontier
    frontier_rows = frontier.to_dict("records")
    if frontier["exposure_productive"].isna().any():
        raise OfficialRunError("E_prod_frontier was not materialized; fallback exposure is forbidden.")

    fiscal_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    hist_rows: list[dict[str, Any]] = []
    base_cell_seconds: list[float] = []

    for country in COUNTRIES:
        hist_tax = historical_percentiles(inputs, country, "tax")
        hist_total = historical_percentiles(inputs, country, "total_revenue")
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
        policy_rows = policy_instances(country, inputs["policy_cost"], inputs["wpp"])
        for scenario in SCENARIOS:
            phi_raw, kappa, pi_ai_y, lambda_ai, lambda_ai_kbase = scenario_parameters(value, country, scenario)
            shock = convert_phi_raw(scenario, phi_raw, kappa, pi_ai_y)
            translation = translate_to_growth(
                exposure_productive=value("E_prod", country=country),
                q_prod=adoption.q_prod,
                phi_y_nom=shock.phi_y_nom,
                beta=value("beta_translation", country=country),
                gamma=value("gamma_translation", country=country),
                epsilon=value("epsilon", country=country),
                horizon_years=HORIZON_YEARS,
                benchmark_rows=frontier_rows,
                missing_frontier_exposure_fallback=eprod_frontier,
            )
            if translation.frontier_exposure_fallback_used:
                raise OfficialRunError("Frontier exposure fallback was used; Etapa 4B forbids fallback exposure.")
            for regime_code in REGIMES:
                regime = regime_settings(value, regime_code)
                psi_shift_r, exempt_c_r = apply_base_broadening_to_structure(
                    value("psi_shift", country=country),
                    value("exempt_C", country=country),
                    regime.base_broadening_delta,
                )
                weights = compute_labor_capital_weights(
                    labor_share=value("LS_labor_share", country=country),
                    g_ai_level=translation.g_ai_level,
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
                hist_tax_class = classify_historical_plausibility(channel.mfc_gross, hist_tax)
                hist_total_class = classify_historical_plausibility(channel.mfc_gross, hist_total)
                hist_rows.append(
                    {
                        "run_id": RUN_ID,
                        "country_id": country,
                        "scenario_id": scenario,
                        "regime_id": regime_code,
                        "mfc_gross": channel.mfc_gross,
                        "tax_class": hist_tax_class.historical_plausibility_class,
                        "tax_borderline": hist_tax_class.borderline_plausibility_flag,
                        "total_revenue_class": hist_total_class.historical_plausibility_class,
                        "total_revenue_borderline": hist_total_class.borderline_plausibility_flag,
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": DATASET_VERSION,
                    }
                )
                for policy in policy_rows:
                    cell_started = time.perf_counter()
                    fixed = admin_costs(inputs["policy_admin_transition_cost"], country, policy["policy_id"], regime.leakage_multiplier)
                    fspace = compute_fiscal_space(
                        mfc_gross=channel.mfc_gross,
                        mfc_tilde_gross=channel.mfc_tilde_gross,
                        g_ai_level=translation.g_ai_level,
                        ac_net_fix=fixed.ac_net_fix,
                        tr_ann=fixed.tr_ann,
                        leak_fix=fixed.leak_fix,
                        cost_gross_gdp=policy["cost_gross_gdp"],
                        cost_net_gdp=policy["cost_net_gdp"],
                    )
                    base_cell_seconds.append(time.perf_counter() - cell_started)
                    existence = channel.mfc_tilde_gross > 0.0 and translation.g_ai_level > 0.0
                    for xi in XI_GRID:
                        crosses_v1 = fspace.v_gross >= 1.0
                        crosses_buffer = fspace.v_gross >= 1.0 + xi
                        debt_ok = debt_guardrail_pass(
                            fs_eff=fspace.fs_eff,
                            cost_gross_gdp=policy["cost_gross_gdp"],
                            xi=xi,
                            spb_plus_gdp=value("sPB_plus_gdp_ratio", country=country),
                        )
                        fiscal_rows.append(
                            {
                                "run_id": RUN_ID,
                                "model_version": MODEL_VERSION,
                                "parameter_set_id": PARAMETER_SET_ID,
                                "dataset_version": DATASET_VERSION,
                                "country_id": country,
                                "policy_id": policy["policy_id"],
                                "policy_variant_id": policy["policy_variant_id"],
                                "gmi_version": policy["gmi_version"],
                                "scenario_id": scenario,
                                "regime_id": regime_code,
                                "endpoint_year": ENDPOINT_YEAR,
                                "xi": float(xi),
                                "phi_y_nominal": shock.phi_y_nom,
                                "translation_factor": translation.translation_factor,
                                "g_ai_level": translation.g_ai_level,
                                "mfc_gross": channel.mfc_gross,
                                "mfc_tilde_gross": channel.mfc_tilde_gross,
                                "fs_gross": fspace.fs_gross,
                                "fs_eff": fspace.fs_eff,
                                "cost_gross_gdp": policy["cost_gross_gdp"],
                                "cost_net_gdp": policy["cost_net_gdp"],
                                "v_gross": fspace.v_gross,
                                "v_net": fspace.v_net,
                                "crosses_v1": crosses_v1,
                                "crosses_v1_10": fspace.v_gross >= 1.10,
                                "crosses_buffer": crosses_buffer,
                                "debt_guardrail_pass": debt_ok,
                                "existence_condition_pass": existence,
                                "historical_tax_class": hist_tax_class.historical_plausibility_class,
                                "historical_tax_borderline": hist_tax_class.borderline_plausibility_flag,
                                "historical_total_revenue_class": hist_total_class.historical_plausibility_class,
                                "historical_total_revenue_borderline": hist_total_class.borderline_plausibility_flag,
                                "cell_result_class": None,
                                "endpoint_cost_rule": policy["endpoint_cost_rule"],
                            }
                        )
                        for basis in ("baseline", "debt_consistent"):
                            currently_covers = crosses_buffer if basis == "baseline" else debt_ok
                            me_addback = channel.ac_me + channel.tr_me + channel.leak_me
                            threshold = invert_threshold(
                                requirement_basis=basis,
                                xi=float(xi),
                                cost_gross_gdp=policy["cost_gross_gdp"],
                                fixed_cost_gdp=fixed.f_fix,
                                spb_plus_gdp=value("sPB_plus_gdp_ratio", country=country),
                                mfc_tilde_gross=channel.mfc_tilde_gross,
                                mfc_gross=channel.mfc_gross,
                                mfc_base_without_ai_rent=channel.mfc_gross - lambda_ai * channel.tau_ai,
                                g_ai_level=translation.g_ai_level,
                                phi_y_nom=shock.phi_y_nom,
                                horizon_years=HORIZON_YEARS,
                                s_frontier=translation.s_frontier,
                                exposure_productive=value("E_prod", country=country),
                                q_prod=adoption.q_prod,
                                q_prod_t0=adoption.q_prod_t0,
                                q_bar=adoption.q_bar,
                                lambda_q=value("lambda_q_baseline_mid", country=country),
                                lambda_ai=lambda_ai,
                                tau_ai_cap=1.0,
                                beta=value("beta_translation", country=country),
                                gamma=value("gamma_translation", country=country),
                                epsilon=value("epsilon", country=country),
                                currently_covers_buffer=currently_covers,
                                me_addback=me_addback,
                            )
                            required_tax_class = (
                                classify_historical_plausibility(threshold.mfc_required_gross, hist_tax)
                                if threshold.mfc_required_gross is not None
                                else None
                            )
                            required_total_class = (
                                classify_historical_plausibility(threshold.mfc_required_gross, hist_total)
                                if threshold.mfc_required_gross is not None
                                else None
                            )
                            threshold_rows.append(
                                {
                                    "run_id": RUN_ID,
                                    "model_version": MODEL_VERSION,
                                    "parameter_set_id": PARAMETER_SET_ID,
                                    "dataset_version": DATASET_VERSION,
                                    "country_id": country,
                                    "policy_id": policy["policy_id"],
                                    "policy_variant_id": policy["policy_variant_id"],
                                    "gmi_version": policy["gmi_version"],
                                    "requirement_basis": basis,
                                    "xi": float(xi),
                                    "scenario_id": scenario,
                                    "regime_id": regime_code,
                                    "endpoint_year": ENDPOINT_YEAR,
                                    "required_revenue_gdp": threshold.required_revenue_gdp,
                                    "g_ai_required": threshold.g_ai_required,
                                    "mfc_required_gross": threshold.mfc_required_gross,
                                    "historical_tax_class": (
                                        required_tax_class.historical_plausibility_class
                                        if required_tax_class is not None
                                        else None
                                    ),
                                    "historical_tax_borderline": (
                                        required_tax_class.borderline_plausibility_flag
                                        if required_tax_class is not None
                                        else None
                                    ),
                                    "historical_total_revenue_class": (
                                        required_total_class.historical_plausibility_class
                                        if required_total_class is not None
                                        else None
                                    ),
                                    "historical_total_revenue_borderline": (
                                        required_total_class.borderline_plausibility_flag
                                        if required_total_class is not None
                                        else None
                                    ),
                                    "realized_mfc_tax_class": hist_tax_class.historical_plausibility_class,
                                    "realized_mfc_tax_borderline": hist_tax_class.borderline_plausibility_flag,
                                    "realized_mfc_total_revenue_class": hist_total_class.historical_plausibility_class,
                                    "realized_mfc_total_revenue_borderline": hist_total_class.borderline_plausibility_flag,
                                    "t_required_H": threshold.t_required_h,
                                    "tau_ai_required": threshold.tau_ai_required,
                                    "q_prod_required": threshold.q_prod_required,
                                    "q_use_required": threshold.q_use_required,
                                    "aipi_required": threshold.aipi_required,
                                    "exposure_required": threshold.exposure_required,
                                    "existence_condition_pass": threshold.existence_condition_pass,
                                    "impossibility_reason": threshold.impossibility_reason,
                                    "flags": ";".join(threshold.flags),
                                    "floor_driven_flag": threshold.floor_driven_flag,
                                    "epsilon_used": threshold.epsilon_used,
                                }
                            )

    mark_and_classify_cells(fiscal_rows)
    fiscal_df = pd.DataFrame(fiscal_rows)
    class_df = classify_country_policy([r for r in fiscal_rows if math.isclose(float(r["xi"]), 0.10)])
    fiscal_df = fiscal_df.merge(
        class_df[["country_id", "policy_id", "gmi_version", "country_policy_result_class"]],
        on=["country_id", "policy_id", "gmi_version"],
        how="left",
    )
    threshold_df = pd.DataFrame(threshold_rows)
    hist_df = pd.DataFrame(hist_rows).drop_duplicates()
    grid_summary = (
        fiscal_df[fiscal_df["xi"].eq(0.10)]
        .groupby(["country_id", "scenario_id", "regime_id"], dropna=False)
        .agg(
            cells=("policy_variant_id", "size"),
            crosses_v1=("crosses_v1", "sum"),
            crosses_v1_10=("crosses_v1_10", "sum"),
            debt_guardrail_pass=("debt_guardrail_pass", "sum"),
        )
        .reset_index()
    )
    class_counts = (
        fiscal_df[fiscal_df["xi"].eq(0.10)]
        .groupby(["country_id", "policy_id", "gmi_version", "cell_result_class"], dropna=False)
        .size()
        .reset_index(name="n_cells")
    )
    headline = threshold_df[
        threshold_df["country_id"].isin(COUNTRIES)
        & threshold_df["policy_id"].isin(["PEN", "GMI"])
        & (
            threshold_df["policy_id"].ne("GMI")
            | threshold_df["gmi_version"].eq("GMI_ideal_aggregate")
        )
        & threshold_df["scenario_id"].eq("mid")
        & threshold_df["regime_id"].isin(["r0", "r2"])
        & threshold_df["xi"].eq(0.10)
    ].copy()
    headline = headline.merge(
        fiscal_df[fiscal_df["xi"].eq(0.10)][
            [
                "country_id",
                "policy_variant_id",
                "scenario_id",
                "regime_id",
                "historical_total_revenue_class",
                "historical_total_revenue_borderline",
                "historical_tax_class",
                "historical_tax_borderline",
                "v_gross",
            ]
        ].rename(
            columns={
                "historical_total_revenue_class": "realized_mfc_total_revenue_class_from_fiscal_space",
                "historical_total_revenue_borderline": "realized_mfc_total_revenue_borderline_from_fiscal_space",
                "historical_tax_class": "realized_mfc_tax_class_from_fiscal_space",
                "historical_tax_borderline": "realized_mfc_tax_borderline_from_fiscal_space",
            }
        ),
        on=["country_id", "policy_variant_id", "scenario_id", "regime_id"],
        how="left",
    )
    runtime = time.perf_counter() - started
    manifest = {
        "run_id": RUN_ID,
        "run_label": RUN_LABEL,
        "tier": "A",
        "model_version": MODEL_VERSION,
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_hash": sha256_file(root / "reproducibility" / "snapshot" / f"dataset_manifest_{DATASET_VERSION}.json"),
        "commit_sha": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty": bool(git_value(["status", "--short"])),
        "run_modes": ["deterministic_tier_A", "erosion_companions_r_ge_1", "threshold_inversion_xi_grid"],
        "seeds": {"historical_bootstrap": "deterministic by country-variable hash"},
        "country_scope": list(COUNTRIES),
        "policy_scope": list(POLICIES),
        "base_grid_cells_declared": len(COUNTRIES) * len(POLICIES) * len(SCENARIOS) * len(REGIMES),
        "gmi_companion_policy_variant_rows_at_xi_0_10": int(len(fiscal_df[fiscal_df["xi"].eq(0.10)])),
        "fiscal_space_rows": int(len(fiscal_df)),
        "threshold_inversion_rows": int(len(threshold_df)),
        "xi_grid": list(XI_GRID),
        "probabilistic_leg": "not_evaluated",
        "changelog": [
            "correccion de clase historica del objeto requerido; V intacto",
            "restaurado esquema canonico de historical_capture_percentiles segun plan 01 seccion 15.5; clases titulares sin cambios",
        ],
        "frontier_E_prod": eprod_frontier,
        "frontier_missing_exposure_fallback": None,
        "colombia_pen_eligibility_rule": "WPP by sex and single age: women>=54, men>=59; COP 80,000 monthly under 80 and COP 225,000 monthly age>=80.",
        "runtime_seconds": runtime,
        "max_base_cell_runtime_seconds": max(base_cell_seconds) if base_cell_seconds else 0.0,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    outputs = {
        "fiscal_space_result": fiscal_df,
        "threshold_inversion_result": threshold_df,
        "historical_plausibility_result": hist_df,
        "country_policy_classification_preliminary": class_df,
        "grid_summary": grid_summary,
        "cell_class_counts": class_counts,
        "headline_inversions": headline,
        "manifest": manifest,
    }
    if write:
        write_outputs(root, outputs)
    return outputs


def write_outputs(root: Path, outputs: dict[str, Any]) -> None:
    reports = root / "reports"
    result_dir = root / "results" / "official"
    reports.mkdir(exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    file_map = {
        "fiscal_space_result": "fiscal_space_result_baseline-official-v2",
        "threshold_inversion_result": "threshold_inversion_result_baseline-official-v2",
        "historical_plausibility_result": "historical_plausibility_result_baseline-official-v2",
        "country_policy_classification_preliminary": "country_policy_classification_preliminary_baseline-official-v2",
        "grid_summary": "grid_summary_baseline-official-v2",
        "cell_class_counts": "cell_class_counts_baseline-official-v2",
        "headline_inversions": "headline_inversions_PEN_GMI_ideal_mid_r0_r2_baseline-official-v2",
    }
    for key, stem in file_map.items():
        df = outputs[key]
        df.to_csv(reports / f"{stem}.csv", index=False)
        df.to_csv(result_dir / f"{key}.csv", index=False)
        if key in {"fiscal_space_result", "threshold_inversion_result"}:
            df.to_parquet(reports / f"{stem}.parquet", index=False)
            df.to_parquet(result_dir / f"{key}.parquet", index=False)
    output_hashes = {}
    for path in result_dir.glob("*"):
        if path.is_file():
            output_hashes[path.name] = sha256_file(path)
    manifest = dict(outputs["manifest"])
    manifest["output_hashes"] = output_hashes
    (reports / "run_manifest_baseline-official-v2.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    (result_dir / "manifest.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        for name in [
            "fiscal_space_result",
            "threshold_inversion_result",
            "historical_plausibility_result",
            "country_policy_classification_preliminary",
        ]:
            con.register("_df", outputs[name])
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
        con.register("_manifest", pd.DataFrame([manifest]))
        con.execute("CREATE OR REPLACE TABLE results_manifest AS SELECT * FROM _manifest")
        con.unregister("_manifest")
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    outputs = run_tier_a(write=not args.no_write)
    manifest = outputs["manifest"]
    print(
        json.dumps(
            {
                "status": "OK",
                "run_id": manifest["run_id"],
                "dataset_version": manifest["dataset_version"],
                "parameter_set_id": manifest["parameter_set_id"],
                "base_grid_cells_declared": manifest["base_grid_cells_declared"],
                "rows_at_xi_0_10_including_gmi_companion": manifest["gmi_companion_policy_variant_rows_at_xi_0_10"],
                "fiscal_space_rows": manifest["fiscal_space_rows"],
                "threshold_inversion_rows": manifest["threshold_inversion_rows"],
                "runtime_seconds": manifest["runtime_seconds"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
