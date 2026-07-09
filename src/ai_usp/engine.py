"""Deterministic Tier A runner for the pilot PER baseline."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml

from .adoption import build_adoption_state
from .audit import AuditItem, assert_no_result_without_audit, run_hard_gates
from .classify import (
    classify_cell,
    classify_country_policy_preliminary,
    mark_stress_r4_only,
)
from .fiscal_channels import (
    RegimeSettings,
    apply_base_broadening_to_structure,
    compute_mfc,
)
from .fiscal_space import compute_fiscal_space
from .historical import HistoricalPercentiles, classify_historical_plausibility
from .labor_share import compute_labor_capital_weights
from .policy_cost import endpoint_cost_scale, fixed_policy_costs
from .shock import convert_phi_raw
from .thresholds import XI_GRID, debt_guardrail_pass, invert_threshold
from .translation import translate_to_growth


PARAMETER_SET_ID = "baseline-pilot-v3"
DATASET_VERSION = "v0.1.2-pilot-per"
RUN_ID = "pilot_per_tierA_baseline_pilot_v3"
RUN_LABEL = "pilot"
MODEL_VERSION = "deterministic-engine-v1"
COUNTRY_ID = "PER"
SCENARIOS = ("low", "mid", "high", "stress")
REGIMES = ("r0", "r1", "r2", "r3", "r4")
POLICIES = ("PEN", "GMI", "MUT", "PBI", "UBI")
HORIZON_YEARS = 10
ENDPOINT_YEAR = 2034
ANCHOR_YEAR = 2024


class EngineFailure(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _clean(value: Any) -> Any:
    if is_dataclass(value):
        return _clean(asdict(value))
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if pd.isna(value) if isinstance(value, (float, pd.Timestamp)) else False:
        return None
    if hasattr(value, "item"):
        return _clean(value.item())
    return value


def _value_lookup(values_df: pd.DataFrame):
    def value(name: str, *, scenario: str | None = None, regime: str | None = None, policy: str | None = None) -> float:
        mask = values_df["name"].eq(name)
        if scenario is not None:
            mask &= values_df["scenario_id"].eq(scenario)
        if regime is not None:
            mask &= values_df["regime_code"].eq(regime)
        if policy is not None:
            mask &= values_df["policy_id"].eq(policy)
        rows = values_df.loc[mask, "baseline_value"]
        if rows.empty:
            raise EngineFailure(f"Missing calibrated value: {name}")
        return float(rows.iloc[0])

    return value


def _scenario_value(values_df: pd.DataFrame, scenario: str, prefix: str) -> float:
    rows = values_df[
        (values_df["scenario_id"] == scenario)
        & (values_df["module"].eq("ai_shock") | values_df["module"].str.contains("ai_rent|capital", na=False))
        & values_df["name"].str.startswith(prefix)
    ]
    if rows.empty:
        raise EngineFailure(f"Missing scenario value prefix={prefix}, scenario={scenario}")
    return float(rows.iloc[0]["baseline_value"])


def _load_inputs(root: Path) -> dict[str, Any]:
    db_path = root / "db" / "ai_usp_threshold.duckdb"
    con = duckdb.connect(str(db_path))
    values_df = con.execute(
        """
        SELECT * FROM value_assignment_table
        WHERE parameter_set_id = ?
        """,
        [PARAMETER_SET_ID],
    ).fetchdf()
    if values_df.empty:
        raise EngineFailure(f"No value_assignment_table rows for {PARAMETER_SET_ID}.")

    policy_cost_df = con.execute(
        """
        SELECT * FROM policy_cost
        WHERE dataset_version = ? AND country_id = ?
        """,
        [DATASET_VERSION, COUNTRY_ID],
    ).fetchdf()
    admin_df = con.execute(
        """
        SELECT * FROM policy_admin_transition_cost
        WHERE dataset_version = ? AND country_id = ?
        """,
        [DATASET_VERSION, COUNTRY_ID],
    ).fetchdf()
    hist_df = con.execute(
        """
        SELECT * FROM historical_capture_percentiles
        WHERE dataset_version = ? AND country_id = ? AND percentile_sample = '2000plus'
        """,
        [DATASET_VERSION, COUNTRY_ID],
    ).fetchdf()
    frontier_df = con.execute(
        """
        SELECT * FROM frontier_benchmark_anchor
        WHERE dataset_version = ?
          AND benchmark_set_id = 'baseline_oecd_eurostat_ge10_2024'
          AND scenario_id = ?
        ORDER BY benchmark_country_id
        """,
        [DATASET_VERSION, PARAMETER_SET_ID],
    ).fetchdf()
    if frontier_df.empty:
        raise EngineFailure("Selected frontier benchmark set is empty.")
    con.close()

    conventions = yaml.safe_load((root / "metadata" / "data_conventions.yml").read_text(encoding="utf-8"))
    wpp_path = root / "data" / "raw_snapshots" / DATASET_VERSION / "wpp" / "wpp_projections.parquet"
    wpp_df = pd.read_parquet(wpp_path)

    return {
        "values": values_df,
        "policy_cost": policy_cost_df,
        "admin": admin_df,
        "historical": hist_df,
        "frontier": frontier_df,
        "conventions": conventions,
        "wpp": wpp_df,
    }


def _eligible_shares(wpp_df: pd.DataFrame) -> dict[str, dict[int, float]]:
    per = wpp_df[wpp_df["ISO3_code"].eq(COUNTRY_ID)].copy()
    if per.empty:
        raise EngineFailure("WPP projection does not contain PER.")
    shares: dict[str, dict[int, float]] = {policy: {} for policy in POLICIES}
    for year in (ANCHOR_YEAR, ENDPOINT_YEAR):
        yr = per[per["Time"].eq(year)]
        total = float(yr["PopTotal"].sum())
        if total <= 0.0:
            raise EngineFailure(f"WPP population total is not positive for {year}.")
        shares["PEN"][year] = float(yr.loc[yr["AgeGrpStart"] >= 65, "PopTotal"].sum()) / total
        shares["PBI"][year] = float(yr.loc[yr["AgeGrpStart"] >= 18, "PopTotal"].sum()) / total
        shares["UBI"][year] = 1.0
        shares["MUT"][year] = 1.0
        shares["GMI"][year] = 1.0
    return shares


def _policy_costs(value, policy_cost_df: pd.DataFrame, wpp_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    shares = _eligible_shares(wpp_df)
    result: dict[str, dict[str, float]] = {}
    for policy in POLICIES:
        if policy == "GMI":
            cost_2024 = value("policy_cost_gross_gdp_GMI_loaded_aggregate", policy="GMI")
            net_2024 = cost_2024
            source = "GMI_loaded_aggregate"
        else:
            cost_2024 = value(f"policy_cost_gross_gdp_{policy}", policy=policy)
            rows = policy_cost_df[policy_cost_df["policy_id"].eq(policy)]
            net_2024 = float(rows.iloc[0]["policy_cost_net_gdp"]) if not rows.empty else cost_2024
            source = str(rows.iloc[0].get("gmi_version")) if not rows.empty else None
        fixed = policy == "GMI"
        cost_endpoint = endpoint_cost_scale(
            cost_2024,
            shares[policy][ANCHOR_YEAR],
            shares[policy][ENDPOINT_YEAR],
            fixed_policy=fixed,
        )
        net_endpoint = endpoint_cost_scale(
            net_2024,
            shares[policy][ANCHOR_YEAR],
            shares[policy][ENDPOINT_YEAR],
            fixed_policy=fixed,
        )
        result[policy] = {
            "cost_gross_gdp": cost_endpoint,
            "cost_net_gdp": net_endpoint,
            "cost_2024_gdp": cost_2024,
            "eligible_share_2024": shares[policy][ANCHOR_YEAR],
            "eligible_share_endpoint": shares[policy][ENDPOINT_YEAR],
            "cost_source": source,
        }
    return result


def _admin_costs(value, policy: str, leakage_multiplier: float) -> Any:
    return fixed_policy_costs(
        admin_cost_new_gdp=value(f"{policy}_admin_cost_new_gdp", policy=policy),
        admin_savings_existing_gdp=0.0,
        transition_oneoff_gdp=value(f"{policy}_transition_oneoff_gdp", policy=policy),
        transition_recurring_gdp=value(f"{policy}_transition_recurring_gdp", policy=policy),
        transition_horizon_years=int(value(f"{policy}_transition_horizon_years", policy=policy)),
        transition_discount_rate=value(f"{policy}_transition_discount_rate", policy=policy),
        leakage_fixed_gdp=value(f"{policy}_leakage_fixed_gdp", policy=policy),
        leakage_multiplier=leakage_multiplier,
    )


def _historical_percentiles(hist_df: pd.DataFrame, concept: str) -> HistoricalPercentiles:
    rows = hist_df[hist_df["revenue_concept"].eq(concept)]
    if rows.empty:
        raise EngineFailure(f"Missing historical percentiles for {concept}.")
    row = rows.iloc[0]
    return HistoricalPercentiles(
        revenue_concept=concept,
        percentile_sample=str(row["percentile_sample"]),
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


def _regime_settings(value, regime: str) -> RegimeSettings:
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


def _floor_report(values_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "name",
        "baseline_value",
        "low_value",
        "high_value",
        "unit",
        "support_type",
        "source_id",
        "formula_id",
        "notes",
    ]
    return values_df[values_df["name"].isin(["epsilon", "epsilon_mu"])][cols].copy()


def _floor_trace(values_df: pd.DataFrame) -> dict[str, Any]:
    rows = _floor_report(values_df).to_dict("records")
    return {
        row["name"]: {
            "value": row["baseline_value"],
            "low": row["low_value"],
            "high": row["high_value"],
            "unit": row["unit"],
            "justification": row["notes"],
            "formula_id": row["formula_id"],
        }
        for row in rows
    }


def _threshold_trace_detail(
    *,
    requirement_basis: str,
    xi: float,
    threshold: Any,
    cost_gross_gdp: float,
    fixed_cost_gdp: float,
    spb_plus_gdp: float,
    g_ai_level: float,
    mfc_tilde_gross: float,
    mfc_base_without_ai_rent: float,
    me_addback: float,
    translation_s_frontier: float,
    exposure_productive: float,
    q_prod: float,
    beta: float,
    gamma: float,
    epsilon: float,
    lambda_ai: float,
) -> dict[str, Any]:
    s_required = None
    tilde_q_required = None
    q_prod_required = threshold.q_prod_required
    if threshold.t_required_h is not None and threshold.t_required_h <= 1.0:
        s_required = threshold.t_required_h * translation_s_frontier
        tilde_e = epsilon + (1.0 - epsilon) * exposure_productive
        tilde_q_required = (s_required / (tilde_e**beta)) ** (1.0 / gamma)

    return {
        "requirement_basis": requirement_basis,
        "xi": xi,
        "R_req": threshold.required_revenue_gdp,
        "R_req_formula": "(1+xi)*c_gross + fixed_costs + sPB_plus_if_debt_consistent",
        "R_req_components": {
            "buffered_policy_cost": (1.0 + xi) * cost_gross_gdp,
            "fixed_costs": fixed_cost_gdp,
            "sPB_plus": spb_plus_gdp if requirement_basis == "debt_consistent" else 0.0,
        },
        "g_ai_required": threshold.g_ai_required,
        "g_ai_required_formula": "R_req / MFCtilde",
        "mfc_tilde_gross_input": mfc_tilde_gross,
        "mfc_required_gross": threshold.mfc_required_gross,
        "mfc_required_gross_formula": "R_req / g_ai_level + ME_addback",
        "ME_addback": me_addback,
        "g_ai_level_input": g_ai_level,
        "T_req_H": threshold.t_required_h,
        "S_required": s_required,
        "tilde_q_required": tilde_q_required,
        "q_prod_required": q_prod_required,
        "des_flooring_formula": "q=(tilde_q-epsilon)/(1-epsilon)",
        "tau_AI_required": threshold.tau_ai_required,
        "tau_AI_required_statutory_formula": "tau_AI_required=max(0,(R_req/g_ai_level - MFC_base_without_AI_rent)/lambda_AI)",
        "tau_AI_required_inputs": {
            "R_req": threshold.required_revenue_gdp,
            "g_ai_level": g_ai_level,
            "MFC_base_without_AI_rent": mfc_base_without_ai_rent,
            "lambda_AI": lambda_ai,
        },
        "chi_AI_used": lambda_ai,
        "chi_AI_used_source_note": (
            "No separate chi_AI capturability parameter is registered in baseline-pilot-v3; "
            "the trace field echoes lambda_AI, the scenario AI-rent subset share used as "
            "the denominator in the 7.7.6bis tau_AI_required inversion."
        ),
        "flags": list(threshold.flags),
        "existence_condition_pass": threshold.existence_condition_pass,
    }


def _omega_c_trace_components(
    *,
    weights: Any,
    regime_code: str,
    g_ai_level: float,
    lambda_ai: float,
    tau_l_disp: float,
    tau_k_disp: float,
    tau_r_disp: float,
    mpc_w: float,
    mpc_pi: float,
    mpc_r: float,
    m_m: float,
    theta_r_dom: float,
    exempt_c: float,
) -> dict[str, Any]:
    delta_w = weights.delta_w_gdp0
    delta_pi_dom = weights.delta_capital_domestic_gdp0
    delta_residual_rent = max(0.0, weights.delta_nls_gdp0 - weights.delta_capital_base_gdp0)
    labor_available = (1.0 - tau_l_disp) * delta_w
    capital_available = (1.0 - tau_k_disp) * delta_pi_dom
    rent_available = theta_r_dom * (1.0 - tau_r_disp) * delta_residual_rent
    labor_product = mpc_w * labor_available
    capital_product = mpc_pi * capital_available
    rent_product = mpc_r * rent_available
    flow_sum = labor_product + capital_product + rent_product
    import_factor = 1.0 - m_m
    exemption_factor = 1.0 - exempt_c
    total = exemption_factor * import_factor * max(0.0, flow_sum)
    return {
        "reference": "Plan 02 sec. 7.4.1 / consumption-channel endpoint weights",
        "formula": (
            "Delta_C_taxable=(1-exempt_C_r)*(1-m_M)*max(0, "
            "mpc_W*(1-tau_L_disp)*Delta_W + "
            "mpc_Pi*(1-tau_K_disp)*Delta_Pi_dom + "
            "mpc_R*theta_R_dom*(1-tau_R_disp)*Delta_R)"
        ),
        "disposal_tax_convention": {
            "used": "frozen 2024 observed r0 disposal rates",
            "reason": (
                "Regime-indexed tau_j affects MFC capture. The disposable-income chain uses "
                "the frozen 2024 observed effective disposal rates to avoid feeding reform "
                "rates twice into endpoint weights."
            ),
            "regime_code": regime_code,
        },
        "labor_flow": {
            "Delta_W": delta_w,
            "tau_L_disp_used": tau_l_disp,
            "tau_L_disp_is_regime_indexed": False,
            "available_after_tax": labor_available,
            "mpc_W": mpc_w,
            "product": labor_product,
        },
        "capital_flow": {
            "Delta_Pi_dom": delta_pi_dom,
            "tau_K_disp_used": tau_k_disp,
            "tau_K_disp_is_regime_indexed": False,
            "available_after_tax": capital_available,
            "mpc_Pi": mpc_pi,
            "product": capital_product,
        },
        "rent_flow": {
            "enters_consumption_chain": delta_residual_rent > 0.0,
            "actual_base_formula": "Delta_R=max(0, Delta_NLS - Delta_Kbase)",
            "Delta_R": delta_residual_rent,
            "lambda_times_g_diagnostic_not_used": lambda_ai * g_ai_level,
            "lambda_times_g_note": (
                "lambda_AI*g is reported only as a diagnostic for AI-rent scale; the "
                "consumption chain uses residual non-corporate NLS to avoid double-counting "
                "the AI-rent fiscal channel."
            ),
            "tau_R_disp_used": tau_r_disp,
            "tau_R_disp_is_regime_indexed": False,
            "theta_R_dom": theta_r_dom,
            "available_after_tax_and_domestic_routing": rent_available,
            "mpc_R": mpc_r,
            "product": rent_product,
        },
        "flow_sum_before_import_and_exemption": flow_sum,
        "m_M_used": m_m,
        "exempt_C_used": exempt_c,
        "exempt_C_is_regime_indexed": regime_code != "r0",
        "import_factor_1_minus_m_M": import_factor,
        "exemption_factor_1_minus_exempt_C": exemption_factor,
        "delta_consumption_taxable_total": total,
        "omega_c_check": weights.omega_c,
        "omega_c_formula": "omega_C=Delta_C_taxable/g_ai_level",
        "omega_c_recomputed": total / g_ai_level if g_ai_level > 0.0 else None,
    }


def _write_table(con: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame) -> None:
    con.register("_write_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _write_df")
    con.unregister("_write_df")


def _write_outputs(root: Path, outputs: dict[str, Any]) -> None:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    suffix = PARAMETER_SET_ID
    outputs["fiscal_space_result"].to_csv(reports / f"fiscal_space_result_{suffix}.csv", index=False)
    outputs["fiscal_space_result"].to_parquet(reports / f"fiscal_space_result_{suffix}.parquet", index=False)
    outputs["threshold_inversion_result"].to_csv(reports / f"threshold_inversion_result_{suffix}.csv", index=False)
    outputs["threshold_inversion_result"].to_parquet(
        reports / f"threshold_inversion_result_{suffix}.parquet", index=False
    )
    outputs["historical_plausibility_result"].to_csv(
        reports / f"historical_plausibility_result_{suffix}.csv", index=False
    )
    outputs["grid_summary"].to_csv(reports / f"grid_summary_{suffix}.csv", index=False)
    outputs["grid_crossings_by_scenario_regime"].to_csv(
        reports / f"grid_crossings_by_scenario_regime_{suffix}.csv", index=False
    )
    outputs["inversion_summary_pen_gmi"].to_csv(
        reports / f"inversion_summary_PEN_GMI_mid_r0_r2_{suffix}.csv", index=False
    )
    outputs["floor_report"].to_csv(reports / f"frozen_floor_values_{suffix}.csv", index=False)
    outputs["audit_report"].to_csv(reports / f"run_audit_report_{suffix}.csv", index=False)
    (reports / f"run_manifest_{suffix}.json").write_text(
        json.dumps(_clean(outputs["run_manifest"]), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (reports / "toy_example_trace_PER_PEN_mid_r0.json").write_text(
        json.dumps(_clean(outputs["toy_trace_pen"]), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (reports / "toy_example_trace_PER_GMI_high_r4.json").write_text(
        json.dumps(_clean(outputs["toy_trace_gmi"]), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    _write_table(con, "run_manifest", pd.DataFrame([outputs["run_manifest"]]))
    _write_table(con, "fiscal_space_result", outputs["fiscal_space_result"])
    _write_table(con, "threshold_inversion_result", outputs["threshold_inversion_result"])
    _write_table(con, "historical_plausibility_result", outputs["historical_plausibility_result"])
    _write_table(con, "run_audit_report", outputs["audit_report"])
    con.close()


def run_tier_a(root: Path | None = None, write: bool = True) -> dict[str, Any]:
    root = root or _repo_root()
    inputs = _load_inputs(root)
    values_df = inputs["values"]
    value = _value_lookup(values_df)
    audit_items = run_hard_gates(
        uses_phi_raw_directly=False,
        mfc_mode_mixing=False,
        double_counting_failures=[],
        parameter_set_id=PARAMETER_SET_ID,
        expected_parameter_set_id=PARAMETER_SET_ID,
    )
    assert_no_result_without_audit(audit_items)
    if inputs["frontier"]["exposure_productive"].isna().any():
        raise EngineFailure("baseline-pilot-v3 requires declared E_prod_frontier materialized in frontier_benchmark_anchor.")
    audit_items.append(
        AuditItem(
            "frontier_exposure_parameter",
            "pass",
            "hard",
            "E_prod_frontier is registered and materialized in frontier_benchmark_anchor; no exposure fallback is used.",
        )
    )

    adoption = build_adoption_state(
        q_use_target=value("q_use_target", policy=None),
        aipi=value("A_aipi_total", policy=None),
        informality=value("I_adopt_informality", policy=None),
        gap=value("Gap_excluded_indicators_neutral", policy=None),
        omega_i=value("omega_I", policy=None),
        omega_g=value("omega_G", policy=None),
        nu_a=value("nu_A", policy=None),
        nu_i=value("nu_I", policy=None),
        nu_g=value("nu_G", policy=None),
        epsilon_mu=value("epsilon_mu", policy=None),
        frozen=True,
    )
    beta = value("beta_translation")
    gamma = value("gamma_translation")
    epsilon = value("epsilon")
    lambda_q = value("lambda_q_baseline_mid")
    e_prod = value("E_prod")
    e_prod_frontier = value("E_prod_frontier")
    e_auto = value("E_auto")
    e_aug = value("E_aug")
    policy_costs = _policy_costs(value, inputs["policy_cost"], inputs["wpp"])
    hist_total = _historical_percentiles(inputs["historical"], "total_revenue")
    hist_tax = _historical_percentiles(inputs["historical"], "tax")
    frontier_rows = inputs["frontier"].to_dict("records")
    floor_report = _floor_report(values_df)
    floors = _floor_trace(values_df)

    fiscal_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    hist_rows: list[dict[str, Any]] = []
    toy_trace_pen: dict[str, Any] | None = None
    toy_trace_gmi: dict[str, Any] | None = None

    base_cell_elapsed: list[float] = []
    for scenario in SCENARIOS:
        phi_raw = _scenario_value(values_df, scenario, "phi_raw")
        kappa = _scenario_value(values_df, scenario, "kappa")
        pi_ai_y = _scenario_value(values_df, scenario, "pi_AI_Y")
        shock = convert_phi_raw(scenario, phi_raw, kappa, pi_ai_y)
        lambda_ai = value(f"lambda_AI_{scenario}", scenario=scenario)
        lambda_ai_kbase = value(f"lambda_AI_Kbase_{scenario}", scenario=scenario)

        translation = translate_to_growth(
            exposure_productive=e_prod,
            q_prod=adoption.q_prod,
            phi_y_nom=shock.phi_y_nom,
            beta=beta,
            gamma=gamma,
            epsilon=epsilon,
            horizon_years=HORIZON_YEARS,
            benchmark_rows=frontier_rows,
            missing_frontier_exposure_fallback=e_prod_frontier,
        )

        for regime_code in REGIMES:
            regime = _regime_settings(value, regime_code)
            psi_shift_r, exempt_c_r = apply_base_broadening_to_structure(
                value("psi_shift"),
                value("exempt_C"),
                regime.base_broadening_delta,
            )
            weights = compute_labor_capital_weights(
                labor_share=value("LS_labor_share"),
                g_ai_level=translation.g_ai_level,
                q_prod=adoption.q_prod,
                e_auto=e_auto,
                e_aug=e_aug,
                delta_s=value("delta_s"),
                psi_s=value("psi_s"),
                zeta_s=value("zeta_s"),
                rst=value("RST"),
                lambda_ls=value("lambda_LS"),
                chi_kbase=value("chi_Kbase"),
                chi_dom=value("chi_dom"),
                psi_shift=psi_shift_r,
                tau_l_disp=value("tau_L_disp"),
                tau_k_disp=value("tau_K_disp"),
                tau_r_disp=value("tau_R_disp"),
                mpc_w=value("mpc_W"),
                mpc_pi=value("mpc_Pi"),
                mpc_r=value("mpc_R"),
                m_m=value("m_M"),
                theta_r_dom=value("theta_R_dom"),
                exempt_c=exempt_c_r,
            )
            channel = compute_mfc(
                weights=weights,
                regime=regime,
                tau_l_eff=value("tau_L_eff"),
                tau_k_eff=value("tau_K_eff"),
                tau_c_eff=value("tau_C_eff"),
                lambda_ai=lambda_ai,
                lambda_ai_kbase=lambda_ai_kbase,
                use_erosion_companion=True,
            )
            hist_total_class = classify_historical_plausibility(channel.mfc_gross, hist_total)
            hist_tax_class = classify_historical_plausibility(channel.mfc_gross, hist_tax)
            hist_rows.append(
                {
                    "run_id": RUN_ID,
                    "country_id": COUNTRY_ID,
                    "scenario_id": scenario,
                    "regime_id": regime_code,
                    "mfc_gross": channel.mfc_gross,
                    "total_revenue_class": hist_total_class.historical_plausibility_class,
                    "total_revenue_borderline": hist_total_class.borderline_plausibility_flag,
                    "tax_class": hist_tax_class.historical_plausibility_class,
                    "tax_borderline": hist_tax_class.borderline_plausibility_flag,
                }
            )

            for policy in POLICIES:
                cell_started = time.perf_counter()
                fixed = _admin_costs(value, policy, regime.leakage_multiplier)
                fspace = compute_fiscal_space(
                    mfc_gross=channel.mfc_gross,
                    mfc_tilde_gross=channel.mfc_tilde_gross,
                    g_ai_level=translation.g_ai_level,
                    ac_net_fix=fixed.ac_net_fix,
                    tr_ann=fixed.tr_ann,
                    leak_fix=fixed.leak_fix,
                    cost_gross_gdp=policy_costs[policy]["cost_gross_gdp"],
                    cost_net_gdp=policy_costs[policy]["cost_net_gdp"],
                )
                elapsed = time.perf_counter() - cell_started
                base_cell_elapsed.append(elapsed)
                if elapsed > 1.0:
                    raise EngineFailure(
                        f"Cell runtime exceeded 1s: {COUNTRY_ID}/{policy}/{scenario}/{regime_code} {elapsed:.3f}s"
                    )

                cell_inversions: dict[str, Any] = {}
                for xi in XI_GRID:
                    crosses_v1 = fspace.v_gross >= 1.0
                    crosses_buffer = fspace.v_gross >= 1.0 + xi
                    debt_ok = debt_guardrail_pass(
                        fs_eff=fspace.fs_eff,
                        cost_gross_gdp=policy_costs[policy]["cost_gross_gdp"],
                        xi=xi,
                        spb_plus_gdp=value("sPB_plus_gdp_ratio"),
                    )
                    fiscal_rows.append(
                        {
                            "run_id": RUN_ID,
                            "country_id": COUNTRY_ID,
                            "policy_id": policy,
                            "scenario_id": scenario,
                            "regime_id": regime_code,
                            "endpoint_year": ENDPOINT_YEAR,
                            "phi_y_nominal": shock.phi_y_nom,
                            "translation_factor": translation.translation_factor,
                            "g_ai_level": translation.g_ai_level,
                            "mfc_gross": channel.mfc_gross,
                            "mfc_tilde_gross": channel.mfc_tilde_gross,
                            "fs_gross": fspace.fs_gross,
                            "fs_eff": fspace.fs_eff,
                            "cost_gross_gdp": policy_costs[policy]["cost_gross_gdp"],
                            "cost_net_gdp": policy_costs[policy]["cost_net_gdp"],
                            "v_gross": fspace.v_gross,
                            "v_net": fspace.v_net,
                            "xi": xi,
                            "crosses_v1": crosses_v1,
                            "crosses_buffer": crosses_buffer,
                            "debt_guardrail_pass": debt_ok,
                            "historical_plausibility_class": hist_total_class.historical_plausibility_class,
                            "cell_result_class": None,
                            "country_policy_result_class": None,
                        }
                    )

                    for basis in ("baseline", "debt_consistent"):
                        currently_covers = crosses_buffer if basis == "baseline" else debt_ok
                        me_addback = channel.ac_me + channel.tr_me + channel.leak_me
                        threshold = invert_threshold(
                            requirement_basis=basis,
                            xi=xi,
                            cost_gross_gdp=policy_costs[policy]["cost_gross_gdp"],
                            fixed_cost_gdp=fixed.f_fix,
                            spb_plus_gdp=value("sPB_plus_gdp_ratio"),
                            mfc_tilde_gross=channel.mfc_tilde_gross,
                            mfc_gross=channel.mfc_gross,
                            mfc_base_without_ai_rent=channel.mfc_gross - lambda_ai * channel.tau_ai,
                            g_ai_level=translation.g_ai_level,
                            phi_y_nom=shock.phi_y_nom,
                            horizon_years=HORIZON_YEARS,
                            s_frontier=translation.s_frontier,
                            exposure_productive=e_prod,
                            q_prod=adoption.q_prod,
                            q_prod_t0=adoption.q_prod_t0,
                            q_bar=adoption.q_bar,
                            lambda_q=lambda_q,
                            lambda_ai=lambda_ai,
                            tau_ai_cap=1.0,
                            beta=beta,
                            gamma=gamma,
                            epsilon=epsilon,
                            currently_covers_buffer=currently_covers,
                            me_addback=me_addback,
                        )
                        threshold_rows.append(
                            {
                                "run_id": RUN_ID,
                                "model_version": MODEL_VERSION,
                                "parameter_set_id": PARAMETER_SET_ID,
                                "dataset_version": DATASET_VERSION,
                                "country_id": COUNTRY_ID,
                                "policy_id": policy,
                                "requirement_basis": basis,
                                "xi": xi,
                                "scenario_id": scenario,
                                "regime_id": regime_code,
                                "endpoint_year": ENDPOINT_YEAR,
                                "required_revenue_gdp": threshold.required_revenue_gdp,
                                "g_ai_required": threshold.g_ai_required,
                                "mfc_required_gross": threshold.mfc_required_gross,
                                "t_required_H": threshold.t_required_h,
                                "tau_ai_required": threshold.tau_ai_required,
                                "q_prod_required": threshold.q_prod_required,
                                "q_use_required": threshold.q_use_required,
                                "aipi_required": threshold.aipi_required,
                                "exposure_required": threshold.exposure_required,
                                "existence_condition_pass": threshold.existence_condition_pass,
                                "impossibility_reason": threshold.impossibility_reason,
                                "floor_driven_flag": threshold.floor_driven_flag,
                                "epsilon_used": threshold.epsilon_used,
                            }
                        )
                        if math.isclose(float(xi), 0.10):
                            cell_inversions[basis] = _threshold_trace_detail(
                                requirement_basis=basis,
                                xi=xi,
                                threshold=threshold,
                                cost_gross_gdp=policy_costs[policy]["cost_gross_gdp"],
                                fixed_cost_gdp=fixed.f_fix,
                                spb_plus_gdp=value("sPB_plus_gdp_ratio"),
                                g_ai_level=translation.g_ai_level,
                                mfc_tilde_gross=channel.mfc_tilde_gross,
                                mfc_base_without_ai_rent=channel.mfc_gross - lambda_ai * channel.tau_ai,
                                me_addback=me_addback,
                                translation_s_frontier=translation.s_frontier,
                                exposure_productive=e_prod,
                                q_prod=adoption.q_prod,
                                beta=beta,
                                gamma=gamma,
                                epsilon=epsilon,
                                lambda_ai=lambda_ai,
                            )

                if policy == "PEN" and scenario == "mid" and regime_code == "r0":
                    toy_trace_pen = {
                        "run_id": RUN_ID,
                        "country_id": COUNTRY_ID,
                        "policy_id": policy,
                        "scenario_id": scenario,
                        "regime_id": regime_code,
                        "xi": 0.10,
                        "shock": shock,
                        "adoption": adoption,
                        "translation": translation,
                        "weights": weights,
                        "regime": regime,
                        "fiscal_channel": channel,
                        "omega_c_components": _omega_c_trace_components(
                            weights=weights,
                            regime_code=regime_code,
                            g_ai_level=translation.g_ai_level,
                            lambda_ai=lambda_ai,
                            tau_l_disp=value("tau_L_disp"),
                            tau_k_disp=value("tau_K_disp"),
                            tau_r_disp=value("tau_R_disp"),
                            mpc_w=value("mpc_W"),
                            mpc_pi=value("mpc_Pi"),
                            mpc_r=value("mpc_R"),
                            m_m=value("m_M"),
                            theta_r_dom=value("theta_R_dom"),
                            exempt_c=exempt_c_r,
                        ),
                        "fixed_policy_costs": fixed,
                        "policy_cost": policy_costs[policy],
                        "fiscal_space": fspace,
                        "floors": floors,
                        "inversions_xi_0_10": cell_inversions,
                        "historical_total_revenue_class": hist_total_class,
                        "frontier_benchmark": {
                            "benchmark_set_id": "baseline_oecd_eurostat_ge10_2024",
                            "n_members": int(len(frontier_rows)),
                            "E_prod_frontier": e_prod_frontier,
                            "exposure_source": "value_assignment_table:E_prod_frontier",
                            "fallback_used": False,
                        },
                    }
                if policy == "GMI" and scenario == "high" and regime_code == "r4":
                    tau_l_before = value("tau_L_eff")
                    tau_k_before = value("tau_K_eff")
                    tau_c_before = value("tau_C_eff")
                    leak_before = value("GMI_leakage_fixed_gdp", policy="GMI")
                    tau_ai_mechanical_term = lambda_ai * channel.tau_ai
                    tau_ai_eroded_term = (
                        lambda_ai
                        * max(0.0, 1.0 - regime.epsilon_ero_ai * channel.tau_ai)
                        * channel.tau_ai
                    )
                    toy_trace_gmi = {
                        "run_id": RUN_ID,
                        "country_id": COUNTRY_ID,
                        "policy_id": policy,
                        "scenario_id": scenario,
                        "regime_id": regime_code,
                        "xi": 0.10,
                        "shock": shock,
                        "lp_bridge": {
                            "phi_raw_high": phi_raw,
                            "raw_unit": "LP_equivalent_annual_rate_before_bridge",
                            "kappa_LP_to_Y": kappa,
                            "phi_high_Y": shock.phi_y_nom,
                            "formula": "phi_Y_nom=(1+kappa_LP_to_Y*phi_raw_high)*(1+pi_AI_Y)-1",
                        },
                        "adoption": adoption,
                        "translation": translation,
                        "floors": floors,
                        "weights": weights,
                        "regime": regime,
                        "regime_transformations": {
                            "tax_rates": {
                                "formula": "tau_j_eff_r4 = tau_j_eff * (1 + delta_relative_r4)",
                                "L": {"before": tau_l_before, "delta": regime.tau_l_delta, "after": channel.tau_l},
                                "K": {"before": tau_k_before, "delta": regime.tau_k_delta, "after": channel.tau_k},
                                "C": {"before": tau_c_before, "delta": regime.tau_c_delta, "after": channel.tau_c},
                            },
                            "base_broadening": {
                                "base_side_objects": ["psi_shift", "exempt_C"],
                                "rate_side_objects": ["tau_L", "tau_K", "tau_C"],
                                "same_margin_mixing": False,
                                "delta": regime.base_broadening_delta,
                                "psi_shift": {
                                    "before": value("psi_shift"),
                                    "formula": "psi_shift_r = psi_shift * (1 - base_broadening_delta)",
                                    "after": psi_shift_r,
                                },
                                "exempt_C": {
                                    "before": value("exempt_C"),
                                    "formula": "exempt_C_r = exempt_C * (1 - base_broadening_delta)",
                                    "after": exempt_c_r,
                                },
                            },
                            "leakage": {
                                "before": leak_before,
                                "leakage_multiplier": regime.leakage_multiplier,
                                "formula": "leak_fix_r = leak_fix * leakage_multiplier",
                                "after": fixed.leak_fix,
                            },
                        },
                        "ai_rent_channel": {
                            "lambda_AI_high": lambda_ai,
                            "tau_AI_eff_r4": channel.tau_ai,
                            "lambda_times_tau_mechanical": tau_ai_mechanical_term,
                            "lambda_times_tau_eroded": tau_ai_eroded_term,
                            "lambda_AI_Kbase_high": lambda_ai_kbase,
                            "omega_K_before_netting": weights.omega_k,
                            "omega_K_net_formula": "omega_K_net = omega_K - lambda_AI_Kbase",
                            "omega_K_net": channel.omega_k_net,
                        },
                        "erosion_companion": {
                            "epsilon_ero": {
                                "L": regime.epsilon_ero_l,
                                "K": regime.epsilon_ero_k,
                                "C": regime.epsilon_ero_c,
                                "AI": regime.epsilon_ero_ai,
                            },
                            "epsilon_times_tau_lt_1": {
                                "L": regime.epsilon_ero_l * channel.tau_l < 1.0,
                                "K": regime.epsilon_ero_k * channel.tau_k < 1.0,
                                "C": regime.epsilon_ero_c * channel.tau_c < 1.0,
                                "AI": regime.epsilon_ero_ai * channel.tau_ai < 1.0,
                            },
                            "epsilon_times_tau_values": {
                                "L": regime.epsilon_ero_l * channel.tau_l,
                                "K": regime.epsilon_ero_k * channel.tau_k,
                                "C": regime.epsilon_ero_c * channel.tau_c,
                                "AI": regime.epsilon_ero_ai * channel.tau_ai,
                            },
                            "MFC_gross_mechanical": channel.mfc_gross_mechanical,
                            "MFC_gross_eroded": channel.mfc_gross,
                        },
                        "fiscal_channel": channel,
                        "omega_c_components": _omega_c_trace_components(
                            weights=weights,
                            regime_code=regime_code,
                            g_ai_level=translation.g_ai_level,
                            lambda_ai=lambda_ai,
                            tau_l_disp=value("tau_L_disp"),
                            tau_k_disp=value("tau_K_disp"),
                            tau_r_disp=value("tau_R_disp"),
                            mpc_w=value("mpc_W"),
                            mpc_pi=value("mpc_Pi"),
                            mpc_r=value("mpc_R"),
                            m_m=value("m_M"),
                            theta_r_dom=value("theta_R_dom"),
                            exempt_c=exempt_c_r,
                        ),
                        "fixed_policy_costs": fixed,
                        "policy_cost": policy_costs[policy],
                        "gmi_endpoint_cost_rule": {
                            "formula": "c_2034 = c_2024; GMI is fixed aggregate gap cost, no demographic ratio",
                            "grid_mapping_note": {
                                "fiscal_space_result_100_cells_uses": "GMI_loaded_aggregate",
                                "not_changed_in_3B2": True,
                                "plan_rule_for_author_decision": (
                                    "Ideal GMI is the minimum baseline with warning; loaded GMI is the "
                                    "mandatory companion for rankings. The current grid remained loaded "
                                    "and is reported for author decision."
                                ),
                            },
                            "ideal": {
                                "theta_target": 1.0,
                                "c_2024": value("policy_cost_gross_gdp_GMI_ideal_aggregate", policy="GMI"),
                                "c_2034": value("policy_cost_gross_gdp_GMI_ideal_aggregate", policy="GMI"),
                            },
                            "loaded": {
                                "theta_target": value("theta_target_GMI_loaded", policy="GMI"),
                                "c_2024": value("policy_cost_gross_gdp_GMI_loaded_aggregate", policy="GMI"),
                                "c_2034": policy_costs[policy]["cost_gross_gdp"],
                            },
                        },
                        "fiscal_space": fspace,
                        "inversions_xi_0_10": cell_inversions,
                        "historical_total_revenue_class": hist_total_class,
                        "frontier_benchmark": {
                            "benchmark_set_id": "baseline_oecd_eurostat_ge10_2024",
                            "n_members": int(len(frontier_rows)),
                            "E_prod_frontier": e_prod_frontier,
                            "exposure_source": "value_assignment_table:E_prod_frontier",
                            "fallback_used": False,
                        },
                    }

    fiscal_base_rows = fiscal_rows
    mark_stress_r4_only(fiscal_base_rows)
    for row in fiscal_base_rows:
        row["cell_result_class"] = classify_cell(
            existence_condition_pass=True,
            v_gross=float(row["v_gross"]),
            crosses_v1=bool(row["crosses_v1"]),
            debt_guardrail_pass=bool(row["debt_guardrail_pass"]),
            stress_r4_only_crossing=bool(row.get("stress_r4_only_crossing")),
        )

    policy_classes = classify_country_policy_preliminary(
        [row for row in fiscal_base_rows if math.isclose(float(row["xi"]), 0.10)]
    )
    for row in fiscal_base_rows:
        row["country_policy_result_class"] = policy_classes[(row["country_id"], row["policy_id"])]
        row.pop("stress_r4_only_crossing", None)

    fiscal_df = pd.DataFrame(fiscal_base_rows)
    threshold_df = pd.DataFrame(threshold_rows)
    for col in (
        "xi",
        "required_revenue_gdp",
        "g_ai_required",
        "mfc_required_gross",
        "t_required_H",
        "tau_ai_required",
        "q_prod_required",
        "q_use_required",
        "aipi_required",
        "exposure_required",
        "epsilon_used",
    ):
        threshold_df[col] = pd.to_numeric(threshold_df[col], errors="coerce").astype("float64")
    hist_df = pd.DataFrame(hist_rows).drop_duplicates()
    audit_df = pd.DataFrame([asdict(item) for item in audit_items])
    grid_summary = (
        fiscal_df[fiscal_df["xi"].eq(0.10)]
        .groupby(["policy_id", "scenario_id", "regime_id", "cell_result_class"], dropna=False)
        .size()
        .reset_index(name="n_cells")
    )
    grid_crossings = (
        fiscal_df[fiscal_df["xi"].eq(0.10)]
        .groupby(["scenario_id", "regime_id"], dropna=False)
        .agg(
            n_cells=("policy_id", "size"),
            crosses_v1=("crosses_v1", "sum"),
            crosses_buffer=("crosses_buffer", "sum"),
            debt_guardrail_pass=("debt_guardrail_pass", "sum"),
        )
        .reset_index()
    )
    inversion_summary = threshold_df[
        threshold_df["policy_id"].isin(["PEN", "GMI"])
        & threshold_df["scenario_id"].eq("mid")
        & threshold_df["regime_id"].isin(["r0", "r2"])
        & threshold_df["xi"].eq(0.10)
    ].copy()

    run_manifest = {
        "run_id": RUN_ID,
        "run_label": RUN_LABEL,
        "model_version": MODEL_VERSION,
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
        "tier": "A",
        "country_scope": [COUNTRY_ID],
        "policies": list(POLICIES),
        "scenarios": list(SCENARIOS),
        "regimes": list(REGIMES),
        "xi_grid": list(XI_GRID),
        "trajectory_convention": "frozen_anchor_2024",
        "q_prod_initial_condition": "q_prod_t0 = q_use_target_adj",
        "gmi_version": "GMI_loaded_aggregate",
        "frontier_benchmark_set_id": "baseline_oecd_eurostat_ge10_2024",
        "frontier_exposure_parameter": "E_prod_frontier",
        "frontier_E_prod": e_prod_frontier,
        "frontier_missing_exposure_fallback": None,
        "floors": _clean(floors),
        "probabilistic_leg": "not_evaluated",
        "base_grid_cells": len(POLICIES) * len(SCENARIOS) * len(REGIMES),
        "fiscal_space_rows": int(len(fiscal_df)),
        "threshold_inversion_rows": int(len(threshold_df)),
        "max_base_cell_runtime_seconds": max(base_cell_elapsed) if base_cell_elapsed else 0.0,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if toy_trace_pen is None:
        raise EngineFailure("Toy trace cell PER/PEN/mid/r0 was not produced.")
    if toy_trace_gmi is None:
        raise EngineFailure("Toy trace cell PER/GMI/high/r4 was not produced.")

    outputs = {
        "run_manifest": run_manifest,
        "audit_report": audit_df,
        "fiscal_space_result": fiscal_df,
        "threshold_inversion_result": threshold_df,
        "historical_plausibility_result": hist_df,
        "grid_summary": grid_summary,
        "grid_crossings_by_scenario_regime": grid_crossings,
        "inversion_summary_pen_gmi": inversion_summary,
        "floor_report": floor_report,
        "toy_trace_pen": toy_trace_pen,
        "toy_trace_gmi": toy_trace_gmi,
    }
    if write:
        _write_outputs(root, outputs)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic AI-USP Tier A pilot.")
    parser.add_argument("--tier", default="A", choices=["A"], help="Only deterministic Tier A is implemented.")
    parser.add_argument("--no-write", action="store_true", help="Compute without writing outputs.")
    args = parser.parse_args(argv)
    outputs = run_tier_a(write=not args.no_write)
    manifest = outputs["run_manifest"]
    print(
        json.dumps(
            {
                "status": "OK",
                "run_id": manifest["run_id"],
                "parameter_set_id": manifest["parameter_set_id"],
                "base_grid_cells": manifest["base_grid_cells"],
                "fiscal_space_rows": manifest["fiscal_space_rows"],
                "threshold_inversion_rows": manifest["threshold_inversion_rows"],
                "max_base_cell_runtime_seconds": manifest["max_base_cell_runtime_seconds"],
            },
            indent=2,
        )
    )
    return 0
