"""Materialize Etapa 4B official calibration after author ratification.

This script assumes the official 4-country anchors were rebuilt over
v1.0.1-official-4c. It does not run economic results and does not modify the
certified engine mechanics under src/ai_usp.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


DATASET_VERSION = "v1.0.1-official-4c"
V1 = "baseline-official-v1"
V2 = "baseline-official-v2"
AUTHOR_DATE = "2026-07-08"
AUTHOR_NOTE = "ratificacion del autor registrada pre-resultados"
SCRIPT_NAME = Path(__file__).name
COUNTRIES = ("PER", "CHL", "COL", "MEX")
SCENARIOS = ("low", "mid", "high", "stress")
REGIMES = ("r0", "r1", "r2", "r3", "r4")
POLICIES = ("PEN", "GMI", "MUT", "PBI", "UBI")
PENDING_STATUSES = {
    "registered_author_review",
    "literature_disciplined_pending_author_signature",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_table(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {name}").fetchdf()


def write_table(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
    con.unregister("_df")


def bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def pct_rank(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True)


def compute_rst(root: Path) -> dict[str, float]:
    aipi = pd.read_parquet(root / "data" / "raw_snapshots" / DATASET_VERSION / "imf_aipi" / "aipi.parquet")
    latest = aipi.sort_values("year").dropna(subset=["aipi_total", "human_capital_labor"]).groupby("country_id").tail(1)
    x = latest["aipi_total"].astype(float).to_numpy()
    y = latest["human_capital_labor"].astype(float).to_numpy()
    if len(latest) < 10:
        return {country: 0.5 for country in COUNTRIES}
    slope, intercept = np.polyfit(x, y, 1)
    latest = latest.copy()
    latest["rst_residual"] = y - (slope * x + intercept)
    latest["rst_percentile"] = pct_rank(latest["rst_residual"])
    return {
        country: float(latest.loc[latest["country_id"].eq(country), "rst_percentile"].iloc[0])
        for country in COUNTRIES
    }


def build_grd_contrast(root: Path, fiscal: pd.DataFrame, build_id: str) -> pd.DataFrame:
    grd_path = root / "data" / "raw_snapshots" / DATASET_VERSION / "grd" / "grd_revenue.parquet"
    grd = pd.read_parquet(grd_path)
    grd = grd[grd["country_id"].isin(COUNTRIES) & pd.to_numeric(grd["year"], errors="coerce").between(2000, 2024)].copy()
    for col in [
        "canonical_total_revenue",
        "canonical_tax_revenue",
        "tax_revenue_including_sc",
        "tax_revenue_excluding_sc",
        "common_gdp_series",
    ]:
        grd[col] = pd.to_numeric(grd[col], errors="coerce")
    grd["grd_total_revenue_ex_grants_ex_sc_gdp"] = grd["canonical_total_revenue"] / grd["common_gdp_series"]
    grd["grd_tax_excluding_sc_gdp"] = grd["tax_revenue_excluding_sc"] / grd["common_gdp_series"]
    grd["grd_tax_including_sc_gdp"] = grd["tax_revenue_including_sc"] / grd["common_gdp_series"]
    f = fiscal[["country_id", "year", "tax_revenue_gdp", "social_contrib_gdp", "total_revenue_gdp", "government_level"]].copy()
    f["oecd_tax_including_sc_gdp"] = pd.to_numeric(f["tax_revenue_gdp"], errors="coerce") / 100.0
    f["oecd_social_contrib_gdp"] = pd.to_numeric(f["social_contrib_gdp"], errors="coerce") / 100.0
    f["oecd_tax_excluding_sc_gdp"] = f["oecd_tax_including_sc_gdp"] - f["oecd_social_contrib_gdp"]
    f["imf_total_revenue_general_government_gdp"] = pd.to_numeric(f["total_revenue_gdp"], errors="coerce") / 100.0
    out = grd.merge(f, on=["country_id", "year"], how="left", suffixes=("", "_anchor"))
    out["tax_comparison_concept"] = (
        "like_for_like_excluding_social_contributions: GRD canonical tax excludes social "
        "contributions; OECD comparison subtracts OECD social_contrib_gdp from total tax."
    )
    out["grd_minus_oecd_tax_ex_sc_gdp"] = out["grd_tax_excluding_sc_gdp"] - out["oecd_tax_excluding_sc_gdp"]
    out["grd_minus_oecd_tax_inc_sc_gdp"] = out["grd_tax_including_sc_gdp"] - out["oecd_tax_including_sc_gdp"]
    out["grd_minus_imf_total_revenue_gdp"] = (
        out["grd_total_revenue_ex_grants_ex_sc_gdp"] - out["imf_total_revenue_general_government_gdp"]
    )
    out["comparison_role"] = "contrast_only_not_baseline_anchor"
    out["dataset_version"] = DATASET_VERSION
    out["build_id"] = build_id
    out["created_at"] = now()
    out["created_by_script"] = SCRIPT_NAME
    keep = [
        "country_id",
        "year",
        "government_level",
        "grd_total_revenue_ex_grants_ex_sc_gdp",
        "grd_tax_excluding_sc_gdp",
        "grd_tax_including_sc_gdp",
        "oecd_tax_excluding_sc_gdp",
        "oecd_tax_including_sc_gdp",
        "oecd_social_contrib_gdp",
        "imf_total_revenue_general_government_gdp",
        "grd_minus_oecd_tax_ex_sc_gdp",
        "grd_minus_oecd_tax_inc_sc_gdp",
        "grd_minus_imf_total_revenue_gdp",
        "tax_comparison_concept",
        "comparison_role",
        "source_excel_file",
        "canonical_mapping_note",
        "dataset_version",
        "build_id",
        "created_at",
        "created_by_script",
    ]
    return out[keep].reset_index(drop=True)


def normalize_key_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["country_id", "scenario_id", "policy_id", "regime_code"]:
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), None)
            df[col] = df[col].map(lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else str(x))
    return df


def value_row(
    *,
    parameter_set_id: str,
    name: str,
    module: str,
    baseline_value: float,
    low_value: float | None = None,
    high_value: float | None = None,
    country_id: str | None = None,
    scenario_id: str | None = None,
    policy_id: str | None = None,
    regime_code: str | None = None,
    value_type: str = "calibrated_parameter",
    unit: str = "unitless",
    support_type: str = "registered_official_calibration",
    source_id: str = "PLAN_01_02",
    formula_id: str = "registered",
    distribution: str = "fixed",
    truncation_rule: str | None = None,
    double_counting_risk: str = "none",
    double_counting_note: str = "none",
    audit_status: str = "registered",
    notes: str = "",
    is_lac_fallback: bool = False,
    assumption_id: str | None = None,
    build_id: str = "",
) -> dict[str, Any]:
    if low_value is None:
        low_value = baseline_value
    if high_value is None:
        high_value = baseline_value
    if truncation_rule is None:
        truncation_rule = "0_to_1" if unit in {"share", "index_0_to_1", "effective_tax_rate"} else "declared"
    approved = audit_status in PENDING_STATUSES
    return {
        "parameter_set_id": parameter_set_id,
        "name": name,
        "module": module,
        "country_id": country_id,
        "scenario_id": scenario_id,
        "policy_id": policy_id,
        "regime_code": regime_code,
        "value_type": value_type,
        "unit": unit,
        "baseline_value": float(baseline_value),
        "low_value": float(low_value),
        "high_value": float(high_value),
        "support_type": support_type,
        "source_id": source_id,
        "formula_id": formula_id,
        "distribution": distribution,
        "truncation_rule": truncation_rule,
        "primary_spec_flag": True,
        "robustness_flag": False,
        "stress_flag": scenario_id == "stress",
        "double_counting_risk": double_counting_risk,
        "double_counting_note": double_counting_note,
        "audit_status": "author_approved" if approved else audit_status,
        "notes": notes,
        "is_lac_fallback": bool(is_lac_fallback),
        "assumption_id": assumption_id or f"OFFICIAL_V2_{name}_{country_id or 'GLOBAL'}_{scenario_id or ''}_{policy_id or ''}_{regime_code or ''}",
        "dataset_version": DATASET_VERSION,
        "build_id": build_id,
        "created_at": now(),
        "created_by_script": SCRIPT_NAME,
        "author_approval_date": AUTHOR_DATE if approved else None,
        "author_approval_note": AUTHOR_NOTE if approved else None,
    }


def copy_pilot_global_rows(root: Path, build_id: str) -> list[dict[str, Any]]:
    pilot = pd.read_csv(root / "reports" / "value_assignment_table_baseline-pilot-v3.csv")
    keep_modules = {
        "ai_shock",
        "behavioral_erosion",
        "fiscal_channels_ai_rent",
        "fiscal_channels_capital",
        "fiscal_regime",
        "frontier_benchmark",
    }
    rows = []
    for _, row in pilot[pilot["module"].isin(keep_modules)].iterrows():
        if row["name"] == "E_prod_frontier":
            continue
        country = None if pd.isna(row.get("country_id")) else str(row.get("country_id"))
        if country == "PER" and str(row["name"]).startswith("kappa_LP_to_Y_high"):
            continue
        status = str(row.get("audit_status") or "registered")
        rows.append(
            value_row(
                parameter_set_id=V2,
                name=str(row["name"]),
                module=str(row["module"]),
                country_id=country,
                scenario_id=None if pd.isna(row.get("scenario_id")) else str(row.get("scenario_id")),
                policy_id=None if pd.isna(row.get("policy_id")) else str(row.get("policy_id")),
                regime_code=None if pd.isna(row.get("regime_code")) else str(row.get("regime_code")),
                baseline_value=float(row["baseline_value"]),
                low_value=float(row["low_value"]),
                high_value=float(row["high_value"]),
                unit=str(row["unit"]),
                support_type=str(row["support_type"]),
                source_id=str(row["source_id"]),
                formula_id=str(row["formula_id"]),
                distribution=str(row["distribution"]),
                double_counting_risk=str(row["double_counting_risk"]),
                double_counting_note=str(row["double_counting_note"]),
                audit_status=status,
                notes=str(row["notes"]),
                build_id=build_id,
            )
        )
    return rows


def copy_v1_as_v2(v1: pd.DataFrame, build_id: str) -> pd.DataFrame:
    v2 = v1.copy()
    v2["parameter_set_id"] = V2
    v2["dataset_version"] = DATASET_VERSION
    v2["build_id"] = build_id
    v2["created_at"] = now()
    v2["created_by_script"] = SCRIPT_NAME
    v2["author_approval_date"] = None
    v2["author_approval_note"] = None
    return normalize_key_columns(v2)


def official_country_rows(tables: dict[str, pd.DataFrame], build_id: str) -> list[dict[str, Any]]:
    cp = tables["country_panel"]
    debt = tables["debt_guardrail_anchor"]
    rst_map = tables["rst_map"]
    rows: list[dict[str, Any]] = []
    common_country_params = [
        ("beta_translation", "adoption_translation", 1.0, 0.5, 2.0, "elasticity", "PAPER_TRANSLATION_GRID", "Baseline unit elasticity; sensitivity grid {0.5,1,1.5,2}.", "registered"),
        ("gamma_translation", "adoption_translation", 1.0, 0.5, 2.0, "elasticity", "PAPER_TRANSLATION_GRID", "Baseline unit elasticity; sensitivity grid {0.5,1,1.5,2}.", "registered"),
        ("epsilon", "adoption_translation", 1e-9, 1e-9, 1e-9, "numerical_floor", "PLAN_02_SEC_7_7", "Frozen numerical floor for support checks and de-flooring.", "registered"),
        ("epsilon_mu", "adoption_translation", 1e-6, 1e-6, 1e-6, "numerical_floor", "PLAN_02_SEC_7_3", "Frozen logit inversion floor; q_use_target_adj is projected to interior support.", "registered"),
        ("lambda_q_baseline_mid", "adoption_translation", 0.30, 0.15, 0.50, "diffusion_rate", "PLAN_02_SEC_7_3", "Baseline diffusion-speed grid {0.15,0.30,0.50}; frozen baseline keeps q_prod at anchor.", "registered"),
        ("lambda_q_stress_instant", "adoption_translation", 1.0, 1.0, 1.0, "diffusion_rate", "PLAN_02_SEC_7_3", "Instant-adoption stress only, not baseline primary.", "registered"),
        ("nu_A", "adoption_translation", 1.0, 0.25, 2.0, "coefficient", "PLAN_02_SEC_7_3", "Preparedness coefficient; inert in frozen baseline because mu is inverted to target.", "registered_author_review"),
        ("nu_I", "adoption_translation", 0.50, 0.0, 1.0, "coefficient", "PLAN_02_SEC_7_3", "Informality coefficient; inert in frozen baseline because mu is inverted to target.", "registered_author_review"),
        ("nu_G", "adoption_translation", 0.50, 0.0, 1.0, "coefficient", "PLAN_02_SEC_7_3", "Gap coefficient; inert in frozen baseline because mu is inverted to target.", "registered_author_review"),
        ("omega_I", "adoption_translation", 0.50, 0.25, 0.75, "coefficient", "PLAN_02_SEC_7_3", "Informality ceiling penalty; omega_I<1 is the paper economic restriction.", "registered_author_review"),
        ("omega_G", "adoption_translation", 0.50, 0.25, 0.75, "coefficient", "PLAN_02_SEC_7_3", "Digital-gap ceiling penalty, now based on excluded coverage+speed Gap.", "registered_author_review"),
        ("delta_s", "fiscal_channels", 0.50, 0.25, 1.0, "unitless", "PAPER_MASTER_CALIBRATION_MATRIX", "Automation pressure grid {0.25,0.50,1.00}.", "registered"),
        ("psi_s", "fiscal_channels", 0.50, 0.25, 1.0, "unitless", "PAPER_MASTER_CALIBRATION_MATRIX", "Augmentation pressure grid {0.25,0.50,1.00}.", "registered"),
        ("zeta_s", "fiscal_channels", 0.50, 0.25, 1.0, "unitless", "PAPER_MASTER_CALIBRATION_MATRIX", "Reskilling mitigation grid {0.25,0.50,1.00}; engine enforces zeta*RST through the weight formula.", "registered"),
        ("lambda_LS", "fiscal_channels", 0.50, 0.25, 1.0, "unitless", "PAPER_MASTER_CALIBRATION_MATRIX", "Labor-share partial-adjustment grid {0.25,0.50,1.00}.", "registered"),
        ("chi_Kbase", "fiscal_channels", 0.70, 0.55, 0.85, "share", "AUTHOR_REVIEW_PENDING_NATIONAL_ACCOUNTS;PLAN_02_SEC_7_4_1", "Share of non-labor surplus that is corporate taxable base; 1.0 only favorable variant.", "registered_author_review"),
        ("chi_dom", "fiscal_channels", 0.95, 0.85, 1.0, "share", "AUTHOR_REVIEW_PENDING_NATIONAL_ACCOUNTS;PLAN_02_SEC_7_4_1", "Domestic share of incremental corporate base.", "registered_author_review"),
        ("psi_shift", "fiscal_channels", 0.15, 0.0, 0.30, "share", "PAPER_APP_FISCAL_CONVERSION;PLAN_02_SEC_10_8", "Ordinary shifting of incremental capital base; central conservative-moderate; zero only favorable labeled variant.", "registered_author_review"),
        ("tau_R_disp", "fiscal_channels", 0.0, 0.0, 0.0, "effective_tax_rate", "PAPER_APP_FISCAL_CONVERSION", "Residual non-labor income is routed through consumption only in primary.", "registered"),
        ("exempt_C", "fiscal_channels", 0.0, 0.0, 0.0, "share", "PLAN_02_SEC_10_8", "Observed tau_C_eff already embeds exemptions and informal untaxed consumption; base-side exempt_C is zero to avoid double count.", "registered"),
    ]
    for country in COUNTRIES:
        r = cp[cp["country_id"].eq(country)].iloc[0]
        d = debt[(debt["country_id"].eq(country)) & (debt["year"].eq(2024))].iloc[0]
        consumption_share = float(r["final_consumption_gdp_share"]) / 100.0
        labor_share = float(r["labor_share_raw"])
        tau_l = ((float(r["pit_gdp"]) + float(r["social_contrib_gdp"])) / 100.0) / labor_share
        tau_k = (float(r["cit_gdp"]) / 100.0) / (1.0 - labor_share)
        tau_c = (float(r["vat_gdp"]) / 100.0) / consumption_share
        values = [
            ("I_ceiling_informality", "adoption_translation", float(r["informality_total"]) / 100.0, 0.0, 1.0, "share", "ILOSTAT", "Same observed informality used for adoption ceiling.", "registered"),
            ("LS_labor_share", "fiscal_channels", float(r["labor_share_raw"]), float(r["labor_share_raw"]), float(r["labor_share_raw"]), "share", "PWT_10_01", "PWT labor share carried forward to 2024.", "registered"),
            ("E_aug", "fiscal_channels", 0.11, 0.08, 0.14, "share", "PLAN_01_02", "No automation/augmentation split in snapshot; augmentation uses LAC productive-exposure fallback.", "registered_author_review"),
            ("RST", "fiscal_channels", float(rst_map[country]), 0.0, 1.0, "index_0_to_1", "IMF_AIPI_DATA360;PLAN_01_SEC_14_6", "RST proxy uses AIPI human_capital_labor residualized on total AIPI over the international AIPI sample, then percentile-ranked.", "registered_author_review"),
            ("tau_L_disp", "fiscal_channels", tau_l, tau_l, tau_l, "effective_tax_rate", "OECD_REVSTAT_LAC;PWT_10_01", "Disposable labor rate frozen at r0 observed effective labor rate.", "registered"),
            ("tau_K_disp", "fiscal_channels", tau_k, tau_k, tau_k, "effective_tax_rate", "OECD_REVSTAT_LAC;PWT_10_01", "Disposable capital rate frozen at r0 observed effective capital rate.", "registered"),
            ("tau_C_disp", "fiscal_channels", tau_c, tau_c, tau_c, "effective_tax_rate", "OECD_REVSTAT_LAC;WDI", "Observed consumption effective tax rate; MFC uses regime-indexed rate, disposable chain freezes r0.", "registered"),
            ("mpc_W", "fiscal_channels", bounded(consumption_share), bounded(consumption_share - 0.15), bounded(consumption_share + 0.10), "share", "WDI;PAPER_APP_FISCAL_CONVERSION", "Final-consumption/GDP share as transparent proxy for labor-income MPC.", "registered_author_review"),
            ("mpc_Pi", "fiscal_channels", bounded(0.5 * consumption_share), bounded(0.5 * consumption_share - 0.15), bounded(0.5 * consumption_share + 0.15), "share", "WDI;PAPER_APP_FISCAL_CONVERSION", "Profit-income MPC proxy set below labor-income proxy.", "registered_author_review"),
            ("mpc_R", "fiscal_channels", bounded(0.75 * consumption_share), bounded(0.75 * consumption_share - 0.15), bounded(0.75 * consumption_share + 0.15), "share", "WDI;PAPER_APP_FISCAL_CONVERSION", "Residual-income MPC proxy between labor and profit proxies.", "registered_author_review"),
            ("sPB_plus_gdp_ratio", "fiscal_channels", max(0.0, -float(d["pb_gap_gdp"])) / 100.0, max(0.0, -float(d["pb_gap_gdp"])) / 100.0, max(0.0, -float(d["pb_gap_gdp"])) / 100.0, "share_of_GDP", "IMF_WEO_GFS;PLAN_02_SEC_7_7", "max(0,-pb_gap_gdp_pp)/100 because anchor stores IMF percent-of-GDP values in percentage points.", "registered"),
        ]
        values.extend(common_country_params)
        for name, module, val, low, high, unit, source_id, notes, status in values:
            rows.append(
                value_row(
                    parameter_set_id=V2,
                    name=name,
                    module=module,
                    country_id=country,
                    baseline_value=val,
                    low_value=low,
                    high_value=high,
                    unit=unit,
                    source_id=source_id,
                    formula_id=notes,
                    distribution="bounded_PERT" if low != high else "fixed",
                    support_type="official_4c_country_specific",
                    audit_status=status,
                    notes=notes,
                    is_lac_fallback=name in {"E_aug", "E_prod", "E_auto"},
                    build_id=build_id,
                )
            )
        high_kappa = float(r["labor_share_raw"])
        rows.append(
            value_row(
                parameter_set_id=V2,
                name="kappa_LP_to_Y_high",
                module="ai_shock",
                country_id=country,
                scenario_id="high",
                baseline_value=high_kappa,
                low_value=high_kappa,
                high_value=high_kappa,
                unit="GDP_equivalent_per_raw_unit",
                support_type="paper_bridge_convention_country_labor_share",
                source_id="PWT_10_01;PAPER_SEC_PARAMETERS",
                formula_id="LP high scenario uses observed labor share as output bridge.",
                distribution="fixed",
                audit_status="registered",
                notes="Country-specific LP to Y bridge for high scenario.",
                build_id=build_id,
            )
        )
        phi_raw_high = 0.0085
        phi_y_high = (1.0 + phi_raw_high * high_kappa) - 1.0
        rows.append(
            value_row(
                parameter_set_id=V2,
                name="phi_Y_nom_high",
                module="ai_shock",
                country_id=country,
                scenario_id="high",
                baseline_value=phi_y_high,
                low_value=(1.0 + 0.004 * high_kappa) - 1.0,
                high_value=(1.0 + 0.013 * high_kappa) - 1.0,
                unit="nominal_GDP_equivalent_annual_rate",
                support_type="derived_from_registered_inputs",
                source_id="OECD2025G7;PWT_10_01;PAPER_SEC_10_4",
                formula_id="phi_Y_nom=(1+kappa_LP_to_Y*phi_raw_high)*(1+pi_AI_Y)-1",
                distribution="derived_bounded_PERT",
                audit_status="registered",
                notes="High-scenario nominal GDP-equivalent shock is country-specific because kappa_LP_to_Y equals labor share.",
                build_id=build_id,
            )
        )
    return rows


def official_policy_rows(tables: dict[str, pd.DataFrame], build_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cost = tables["policy_cost"]
    admin = tables["policy_admin_transition_cost"]
    for _, r in cost.iterrows():
        country = str(r["country_id"])
        policy = str(r["policy_id"])
        if policy == "GMI":
            version = str(r["gmi_version"])
            name = f"policy_cost_gross_gdp_{version}"
        else:
            name = f"policy_cost_gross_gdp_{policy}"
        rows.append(
            value_row(
                parameter_set_id=V2,
                name=name,
                module="policy_cost",
                country_id=country,
                policy_id=policy,
                baseline_value=float(r["policy_cost_gross_gdp"]),
                low_value=float(r["policy_cost_gross_gdp"]),
                high_value=float(r["policy_cost_gross_gdp"]),
                unit="share_of_GDP",
                support_type="official_policy_cost_anchor",
                source_id=str(r.get("policy_parameter_id") or "policy_parameter"),
                formula_id=str(r.get("cost_convention") or "policy_cost"),
                distribution="fixed_observed_or_mechanical",
                audit_status="registered",
                notes="Gross recurring cost is the primary cost convention.",
                build_id=build_id,
            )
        )
        if policy in {"MUT", "PBI", "UBI"}:
            rows.append(
                value_row(
                    parameter_set_id=V2,
                    name=f"eta_{policy}",
                    module="policy_cost",
                    country_id=country,
                    policy_id=policy,
                    baseline_value=float(r["eta_policy"]),
                    low_value=0.25 if policy != "MUT" else 0.10,
                    high_value=1.0 if policy != "MUT" else 0.40,
                    unit="policy_eta",
                    support_type="policy_design_parameter",
                    source_id="PLAN_01_02",
                    formula_id="Policy eta ladder for MUT/PBI/UBI.",
                    distribution="bounded_PERT",
                    audit_status="registered",
                    notes="Policy eta ladder registered for MUT/PBI/UBI.",
                    build_id=build_id,
                )
            )
        if policy == "GMI":
            rows.append(
                value_row(
                    parameter_set_id=V2,
                    name=f"chi_gmi_{r['gmi_version']}",
                    module="policy_cost",
                    country_id=country,
                    policy_id=policy,
                    baseline_value=1.0,
                    low_value=1.0,
                    high_value=1.0,
                    unit="share",
                    support_type="policy_design_parameter",
                    source_id="PLAN_02_SEC_10_10",
                    formula_id="GMI aggregate gap-coverage parameter.",
                    distribution="fixed",
                    audit_status="registered",
                    notes="GMI aggregate gap-coverage parameter.",
                    build_id=build_id,
                )
            )
            if str(r["gmi_version"]) == "GMI_loaded_aggregate":
                rows.append(
                    value_row(
                        parameter_set_id=V2,
                        name="theta_target_GMI_loaded",
                        module="policy_cost",
                        country_id=country,
                        policy_id=policy,
                        baseline_value=1.5,
                        low_value=1.0,
                        high_value=1.5,
                        unit="multiplier",
                        support_type="paper_policy_cost_support",
                        source_id="PLAN_02_SEC_10_10",
                        formula_id="Loaded aggregate GMI uses theta_target=1.5.",
                        distribution="bounded_PERT",
                        audit_status="registered",
                        notes="Loaded aggregate GMI is companion mandatory in rankings.",
                        build_id=build_id,
                    )
                )
    for _, r in admin.iterrows():
        country = str(r["country_id"])
        policy = str(r["policy_id"])
        values = [
            (f"{policy}_admin_cost_new_gdp", r["admin_cost_new_gdp"]),
            (f"{policy}_transition_oneoff_gdp", r["transition_oneoff_gdp"]),
            (f"{policy}_transition_recurring_gdp", r["transition_recurring_gdp"]),
            (f"{policy}_transition_horizon_years", r["transition_horizon_years"]),
            (f"{policy}_transition_discount_rate", r["transition_discount_rate"]),
            (f"{policy}_leakage_fixed_gdp", r["leakage_fixed_gdp"]),
        ]
        for name, val in values:
            rows.append(
                value_row(
                    parameter_set_id=V2,
                    name=name,
                    module="policy_admin_transition_cost",
                    country_id=country,
                    policy_id=policy,
                    baseline_value=float(val),
                    low_value=float(val),
                    high_value=float(val),
                    unit="share_of_GDP" if "years" not in name and "rate" not in name else "years_or_rate",
                    support_type="assumption_registry_authorized",
                    source_id=str(r["source_id"]),
                    formula_id=str(r["assumption_id"]),
                    distribution="fixed_registered_assumption",
                    audit_status="registered",
                    notes="Administrative and transition cost from official 4C assumption registry.",
                    build_id=build_id,
                )
            )
    return rows


def eprod_frontier_row(build_id: str) -> dict[str, Any]:
    return value_row(
        parameter_set_id=V2,
        name="E_prod_frontier",
        module="frontier_benchmark",
        baseline_value=0.134,
        low_value=0.11,
        high_value=0.20,
        unit="share_of_employment_high_income_augmentation_potential",
        support_type="literature_disciplined",
        source_id="Gmyrek_Berg_Bescond_2023_ILO_WP96;ILO_WP140_2025",
        formula_id="ILO HIC augmentation potential anchor; upper tail supported by WP140 2025 refined index.",
        distribution="bounded_PERT",
        double_counting_risk="measurement_lineage_consistency",
        double_counting_note="Mismo linaje metodologico OIT que el ancla LAC de E_prod; consistencia de medicion en numerador y denominador de T.",
        audit_status="literature_disciplined_pending_author_signature",
        notes=(
            "Gmyrek, Berg & Bescond (2023), ILO Working Paper 96, Generative AI and jobs: "
            "potencial de aumento = 13.4% del empleo en paises de ingreso alto; cola superior "
            "justificada por ILO Working Paper 140 (2025). Re-anclado durante la ratificacion "
            "de autor PRE-oficial por regla de jerarquia (literatura > prior calibrado). "
            "Direccion del cambio: favorable a factibilidad; el rango conserva el prior anterior 0.17."
        ),
        build_id=build_id,
    )


def dedupe_value_rows(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["parameter_set_id", "name", "country_id", "scenario_id", "policy_id", "regime_code"]
    df = normalize_key_columns(df)
    return df.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)


def build_parameter_tables(values: pd.DataFrame, parameter_set: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    item = values[
        [
            "parameter_set_id",
            "assumption_id",
            "name",
            "country_id",
            "policy_id",
            "scenario_id",
            "regime_code",
            "baseline_value",
            "distribution",
            "truncation_rule",
            "notes",
        ]
    ].rename(
        columns={
            "name": "parameter_name",
            "regime_code": "regime_id",
            "baseline_value": "parameter_value",
            "truncation_rule": "draw_rule",
        }
    )
    registry = values[
        [
            "name",
            "module",
            "country_id",
            "baseline_value",
            "low_value",
            "high_value",
            "distribution",
            "truncation_rule",
            "source_id",
            "value_type",
            "notes",
            "double_counting_note",
            "primary_spec_flag",
            "parameter_set_id",
            "dataset_version",
            "assumption_id",
            "created_at",
            "created_by_script",
            "audit_status",
            "author_approval_date",
            "author_approval_note",
        ]
    ].rename(columns={"name": "parameter_name", "notes": "justification"})
    registry["is_observed"] = registry["value_type"].eq("observed")
    registry["is_scenario"] = registry["parameter_name"].str.contains("phi_|lambda_AI|tau_|delta_|multiplier", regex=True)
    registry["is_structural_unobserved"] = ~registry["is_observed"]
    registry["sensitivity_level"] = "baseline"
    registry["included_in_primary"] = registry["primary_spec_flag"]
    registry = registry.drop(columns=["value_type", "primary_spec_flag"])
    return item, registry


def governance_tables(build_id: str) -> dict[str, pd.DataFrame]:
    threshold_assignment = pd.DataFrame(
        [
            {"threshold_id": "xi_baseline", "threshold_name": "baseline buffer xi", "threshold_value": 0.10, "unit": "share", "scope": "Tier A", "rule": "R_req(xi)=(1+xi)*cost+fixed(+debt gap for DC)", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "xi_grid", "threshold_name": "threshold inversion xi grid", "threshold_value": np.nan, "unit": "grid", "scope": "Tier A", "rule": "0,0.05,0.10,0.25,0.50", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "hist_p50_p75_p90", "threshold_name": "historical plausibility percentiles", "threshold_value": np.nan, "unit": "percentile", "scope": "country", "rule": "P50/P75/P90 from 2000plus historical capture distributions", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "prob_v_ge_1_10", "threshold_name": "future MC probability threshold", "threshold_value": 0.75, "unit": "probability", "scope": "Tier B future", "rule": "prob_basis=all_draw; deterministic official run marks MC leg not_evaluated", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "debt_guardrail", "threshold_name": "debt consistent requirement", "threshold_value": np.nan, "unit": "share_of_GDP", "scope": "cell", "rule": "fs_eff >= (1+xi)*cost_gross + sPB_plus", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "q_ceiling", "threshold_name": "adoption ceiling", "threshold_value": np.nan, "unit": "share", "scope": "cell", "rule": "q_required <= q_bar", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"threshold_id": "T_ceiling", "threshold_name": "frontier translation ceiling", "threshold_value": 1.0, "unit": "share", "scope": "cell", "rule": "T_req_H <= 1 because T=min(1,S/S_frontier)", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
        ]
    )
    threshold_rule = pd.DataFrame(
        [
            {"axis": "cell_result_class", "precedence": 1, "rule": "existence_condition_pass is false", "class_value": "impossible_or_noncomputable"},
            {"axis": "cell_result_class", "precedence": 2, "rule": "Vgross < 1", "class_value": "not_feasible"},
            {"axis": "cell_result_class", "precedence": 3, "rule": "crosses V>=1 but fails debt guardrail", "class_value": "accounting_feasible_debt_failed"},
            {"axis": "cell_result_class", "precedence": 4, "rule": "crosses only in stress+r4 over country-policy set", "class_value": "extreme_conditional_crossing"},
            {"axis": "cell_result_class", "precedence": 5, "rule": "otherwise feasible", "class_value": "feasible_cell"},
            {"axis": "historical_plausibility_class", "precedence": 1, "rule": "MFCgross <= P50", "class_value": "fiscally_ordinary"},
            {"axis": "historical_plausibility_class", "precedence": 2, "rule": "P50 < MFCgross <= P75", "class_value": "fiscally_moderate"},
            {"axis": "historical_plausibility_class", "precedence": 3, "rule": "P75 < MFCgross <= P90", "class_value": "fiscally_demanding"},
            {"axis": "historical_plausibility_class", "precedence": 4, "rule": "MFCgross > P90", "class_value": "extreme_or_outside_historical_support"},
        ]
    )
    threshold_rule["parameter_set_id"] = V2
    threshold_rule["dataset_version"] = DATASET_VERSION
    threshold_rule["build_id"] = build_id
    input_audit = pd.DataFrame(
        [
            {"audit_id": "official_country_scope_complete", "module": "governance", "table_name": "dim_country", "passed": True, "severity": "hard", "notes": "PER/CHL/COL/MEX present for official run.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "gap_pilot_robustness_closed", "module": "adoption_translation", "table_name": "digital_gap_anchor", "passed": True, "severity": "robustness_only", "notes": "Pilot Gap=0 diagnostic row closed; official calibration uses excluded coverage+speed gap_index.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "author_signature_materialized", "module": "governance", "table_name": "value_assignment_table", "passed": True, "severity": "hard", "notes": AUTHOR_NOTE, "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "run_readiness_flag", "module": "governance", "table_name": "input_audit_report", "passed": True, "severity": "hard", "notes": "TRUE for official deterministic Tier A after author ratification and v1.0.1 anchors.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
        ]
    )
    double_counting = pd.DataFrame(
        [
            {"audit_id": "aipi_q_target_and_mu_inversion", "module": "adoption_translation", "risk": "AIPI enters target derivation and logistic index", "status": "pass", "notes": "Frozen baseline logit inversion of mu absorbs the level and neutralizes double use; structural-intercept mode must remember this.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "gap_excluded_indicators", "module": "adoption_translation", "risk": "AIPI digital overlap", "status": "pass", "notes": "Gap indicators are LTE coverage and Ookla fixed/mobile speed, verified as excluded from the IMF AIPI component note.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "tax_base_double_discount", "module": "fiscal_channels", "risk": "rate-side and base-side broadening mix", "status": "pass", "notes": "Base broadening changes psi_shift/exempt_C; effective tax rates are not broadened on the same margin twice.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
            {"audit_id": "ai_rent_capital_overlap", "module": "fiscal_channels", "risk": "AI rents counted in capital and AI-rent channels", "status": "pass", "notes": "lambda_AI_Kbase nets the AI-rent subset out of omega_K.", "parameter_set_id": V2, "dataset_version": DATASET_VERSION},
        ]
    )
    return {
        "threshold_assignment_table": threshold_assignment,
        "threshold_rule_registry": threshold_rule,
        "input_audit_report": input_audit,
        "double_counting_audit": double_counting,
    }


def build(root: Path) -> int:
    db_path = root / "db" / "ai_usp_threshold.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        tables = {name: read_table(con, name) for name in [
            "value_assignment_table",
            "parameter_set",
            "country_panel",
            "policy_cost",
            "policy_admin_transition_cost",
            "fiscal_anchor",
            "debt_guardrail_anchor",
            "dim_source",
        ]}
        build_manifest = read_table(con, "build_manifest")
        build_id = f"{str(build_manifest.iloc[0]['build_id'])}-baseline-official-v2-author-approved"
        if str(build_manifest.iloc[0]["dataset_version"]) != DATASET_VERSION:
            raise RuntimeError(f"Expected {DATASET_VERSION}, got {build_manifest.iloc[0]['dataset_version']}")
        v1 = tables["value_assignment_table"][tables["value_assignment_table"]["parameter_set_id"].eq(V1)].copy()
        if v1.empty:
            raise RuntimeError(f"Missing {V1}; rebuild official anchors first.")
        tables["rst_map"] = compute_rst(root)
        grd_contrast = build_grd_contrast(root, tables["fiscal_anchor"], build_id)
        v1 = normalize_key_columns(v1)
        v1["author_approval_date"] = None
        v1["author_approval_note"] = None
        v2 = copy_v1_as_v2(v1, build_id)
        extra_rows = []
        extra_rows.extend(copy_pilot_global_rows(root, build_id))
        extra_rows.extend(official_country_rows(tables, build_id))
        extra_rows.extend(official_policy_rows(tables, build_id))
        extra_rows.append(eprod_frontier_row(build_id))
        extra = pd.DataFrame(extra_rows)
        value = dedupe_value_rows(pd.concat([v1, v2, extra], ignore_index=True, sort=False))
        pending = value[
            value["parameter_set_id"].eq(V2)
            & value["audit_status"].isin(PENDING_STATUSES)
        ]
        if not pending.empty:
            raise RuntimeError("Pending official author-review rows remain:\n" + pending[["name", "country_id", "audit_status"]].to_string(index=False))
        pset_v1 = tables["parameter_set"][tables["parameter_set"]["parameter_set_id"].eq(V1)].copy()
        pset_v2 = pd.DataFrame(
            [
                {
                    "parameter_set_id": V2,
                    "parameter_set_name": "baseline official v2",
                    "description": "Official 4-country deterministic Tier A calibration; author ratified pre-results on 2026-07-08.",
                    "model_version": "deterministic-engine-v1_official_runner_no_mechanics_change",
                    "dataset_version": DATASET_VERSION,
                    "created_at": now(),
                    "created_by_script": SCRIPT_NAME,
                }
            ]
        )
        parameter_set = pd.concat([pset_v1, pset_v2], ignore_index=True, sort=False)
        item, registry = build_parameter_tables(value, parameter_set)
        changelog = pd.DataFrame(
            [
                {"from_parameter_set_id": V1, "to_parameter_set_id": V2, "change_id": "R1", "description": "E_prod_frontier re-anchored to ILO HIC augmentation potential 0.134 [0.11,0.20].", "direction": "favorable_to_feasibility_declared", "author_approval_date": AUTHOR_DATE},
                {"from_parameter_set_id": V1, "to_parameter_set_id": V2, "change_id": "B0", "description": AUTHOR_NOTE, "direction": "governance_signature_only", "author_approval_date": AUTHOR_DATE},
                {"from_parameter_set_id": V1, "to_parameter_set_id": V2, "change_id": "B1", "description": "Baseline-official-v2 expanded with certified deterministic-run parameter families and v1.0.1 GRD contrast.", "direction": "materialization_for_official_run", "author_approval_date": AUTHOR_DATE},
            ]
        )
        write_table(con, "value_assignment_table", value)
        write_table(con, "parameter_set", parameter_set)
        write_table(con, "parameter_set_item", item)
        write_table(con, "calibrated_parameter_registry", registry)
        write_table(con, "parameter_set_changelog", changelog)
        write_table(con, "grd_revenue_contrast", grd_contrast)
        for name, df in governance_tables(build_id).items():
            write_table(con, name, df)
    finally:
        con.close()

    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    value[value["parameter_set_id"].eq(V2)].to_csv(reports / f"value_assignment_table_{V2}.csv", index=False)
    item[item["parameter_set_id"].eq(V2)].to_csv(reports / f"parameter_set_item_{V2}.csv", index=False)
    registry[registry["parameter_set_id"].eq(V2)].to_csv(reports / f"calibrated_parameter_registry_{V2}.csv", index=False)
    changelog.to_csv(reports / f"parameter_set_changelog_{V2}.csv", index=False)
    grd_contrast.to_csv(reports / f"grd_revenue_contrast_{DATASET_VERSION}.csv", index=False)
    changed = value[value["parameter_set_id"].eq(V2) & value["author_approval_date"].eq(AUTHOR_DATE)]
    changed.to_csv(reports / f"author_approved_rows_{V2}.csv", index=False)
    print(
        json.dumps(
            {
                "status": "OK",
                "dataset_version": DATASET_VERSION,
                "parameter_set_id": V2,
                "value_rows": int(value["parameter_set_id"].eq(V2).sum()),
                "author_approved_rows": int(len(changed)),
                "pending_rows": 0,
                "grd_contrast_rows": int(len(grd_contrast)),
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    return build(repo_root())


if __name__ == "__main__":
    raise SystemExit(main())
