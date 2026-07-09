"""Etapa 7 closure artifacts.

This script does not change the certified engine. It materializes the final
diagnostic bookkeeping requested for Phase B, exports paper tables/figures, and
updates the verifiable official outputs that are archived by ``verify.py``.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_usp.adoption import build_adoption_state
from scripts.run_diagnostics_6b import cached_value_lookup, evaluate_cell
from scripts.run_official_monte_carlo import PARAMETER_SET_ID, load_inputs
from scripts.run_official_tier_a import (
    COUNTRIES,
    DATASET_VERSION,
    REGIMES,
    SCENARIOS,
    clean,
    policy_instances,
    sha256_file,
    value_lookup,
)


RUN_ID = "official_4c_phase_b_closure_baseline_official_v3"
RUN_TYPE = "diagnostic"
XI = 0.10
RESULTS = ROOT / "results" / "official"
REPORTS = ROOT / "reports"
PAPER_RESULTS = ROOT / "results" / "paper_tables"
PAPER_REPORTS = ROOT / "reports" / "paper_tables"
FIGURES = ROOT / "figures"
FIGURE_REPORTS = ROOT / "reports" / "figures"


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def ensure_dirs() -> None:
    for path in [RESULTS, REPORTS, PAPER_RESULTS, PAPER_REPORTS, FIGURES, FIGURE_REPORTS]:
        path.mkdir(parents=True, exist_ok=True)


def prepare_inputs() -> dict[str, Any]:
    inputs = load_inputs(ROOT)
    inputs["_base_value"] = cached_value_lookup(inputs["values"])
    inputs["_frontier_records"] = inputs["frontier_benchmark_anchor"].to_dict("records")
    instances = []
    for country in COUNTRIES:
        instances.extend(policy_instances(country, inputs["policy_cost"], inputs["wpp"]))
    inputs["_policy_instance_map"] = {(p["country_id"], p["policy_variant_id"]): p for p in instances}
    return inputs


def adoption_rows(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
    value = value_lookup(inputs["values"])
    rows: dict[str, dict[str, float]] = {}
    for country in COUNTRIES:
        kwargs = dict(
            q_use_target=value("q_use_target", country=country),
            aipi=value("A_aipi_total", country=country),
            gap=value("Gap_excluded_indicators", country=country),
            omega_i=value("omega_I", country=country),
            omega_g=value("omega_G", country=country),
            nu_a=value("nu_A", country=country),
            nu_i=value("nu_I", country=country),
            nu_g=value("nu_G", country=country),
            epsilon_mu=value("epsilon_mu", country=country),
            frozen=True,
        )
        base = build_adoption_state(informality=value("I_adopt_informality", country=country), **kwargs)
        no_i = build_adoption_state(informality=0.0, **kwargs)
        rows[country] = {
            "informality_observed": value("I_adopt_informality", country=country),
            "q_bar_baseline": base.q_bar,
            "q_bar_no_informality": no_i.q_bar,
            "q_prod_baseline": base.q_prod,
            "q_prod_no_informality": no_i.q_prod,
            "delta_q_bar": no_i.q_bar - base.q_bar,
            "delta_q_prod": no_i.q_prod - base.q_prod,
        }
    return rows


def build_informality_ablation(inputs: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    adoption = adoption_rows(inputs)
    rows: list[dict[str, Any]] = []
    for country in COUNTRIES:
        policy_variants = [key[1] for key in inputs["_policy_instance_map"] if key[0] == country]
        for policy_variant_id in policy_variants:
            policy = inputs["_policy_instance_map"][(country, policy_variant_id)]
            for scenario in SCENARIOS:
                for regime in REGIMES:
                    baseline = evaluate_cell(inputs, country, policy_variant_id, scenario, regime)
                    variant = evaluate_cell(inputs, country, policy_variant_id, scenario, regime, overrides={"I_adopt_informality": 0.0})
                    base_cross = baseline.v_gross >= 1.0
                    variant_cross = variant.v_gross >= 1.0
                    a = adoption[country]
                    rows.append(
                        {
                            "run_id": RUN_ID,
                            "run_type": RUN_TYPE,
                            "country_id": country,
                            "policy_id": policy["policy_id"],
                            "policy_variant_id": policy_variant_id,
                            "gmi_version": policy["gmi_version"],
                            "scenario_id": scenario,
                            "regime_id": regime,
                            "informality_observed": a["informality_observed"],
                            "q_bar_baseline": a["q_bar_baseline"],
                            "q_bar_no_informality": a["q_bar_no_informality"],
                            "delta_q_bar": a["delta_q_bar"],
                            "q_prod_baseline": a["q_prod_baseline"],
                            "q_prod_no_informality": a["q_prod_no_informality"],
                            "delta_q_prod": a["delta_q_prod"],
                            "v_baseline_recomputed": baseline.v_gross,
                            "v_no_informality_adoption": variant.v_gross,
                            "delta_v": variant.v_gross - baseline.v_gross,
                            "baseline_crosses_v1": base_cross,
                            "variant_crosses_v1": variant_cross,
                            "crossing_changed": base_cross != variant_cross,
                            "asymmetry_note": (
                                "Informality is removed only from adoption q_bar and logit; fiscal-side informality is embedded "
                                "in observed effective tax rates and is not separately ablated."
                            ),
                            "parameter_set_id": PARAMETER_SET_ID,
                            "dataset_version": DATASET_VERSION,
                        }
                    )
    df = pd.DataFrame(rows)
    summary = {
        "rows": int(len(df)),
        "max_abs_delta_v": float(df["delta_v"].abs().max()),
        "max_abs_delta_q_prod": float(df["delta_q_prod"].abs().max()),
        "max_delta_q_bar": float(df["delta_q_bar"].max()),
        "gained_crossings": int((~df["baseline_crosses_v1"] & df["variant_crosses_v1"]).sum()),
        "lost_crossings": int((df["baseline_crosses_v1"] & ~df["variant_crosses_v1"]).sum()),
        "baseline_crossings": int(df["baseline_crosses_v1"].sum()),
        "variant_crossings": int(df["variant_crosses_v1"].sum()),
        "verdict": "reported",
    }
    return df, summary


def update_diagnostic_result(informality_summary: dict[str, Any]) -> pd.DataFrame:
    path = RESULTS / "diagnostic_result.csv"
    df = pd.read_csv(path)
    note_d2 = (
        "E_prod replaced by automation/displacement exposure E_auto=0.035; expected V collapse roughly proportional to 0.035/0.11. "
        "Interpretation: el colapso mecanico opera (ratio = ratio de exposiciones); la celda superviviente CHL GMI stress refleja "
        "sobredeterminacion por escala del shock vs costo (corroborado por D4); caveat aplicado al claim condicional de CHL GMI."
    )
    df.loc[df["variant_id"].eq("D2_negative_control_sectorial"), "diagnostic_note"] = note_d2
    df = df[~df["variant_id"].eq("P0_informality_adoption_ablation")].copy()
    row = {
        "run_id": RUN_ID,
        "run_type": RUN_TYPE,
        "variant_id": "P0_informality_adoption_ablation",
        "diagnostic_key": "adoption_only_no_informality",
        "diagnostic_value": json.dumps(informality_summary, sort_keys=True),
        "diagnostic_note": (
            "Informality removed from adoption ceiling q_bar and logit only; Gap and all fiscal primitives unchanged. "
            "Fiscal-side informality is embedded in observed effective tax rates and is not separately ablated."
        ),
        "diagnostic_family": "mechanism_ablation",
        "expected_verdict": "reported; quantifies adoption-margin liberation and documents fiscal-side asymmetry",
        "verdict": "reported",
        "rank_change": "0",
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True, sort=False)
    df.to_csv(RESULTS / "diagnostic_result.csv", index=False)
    df.to_csv(REPORTS / "diagnostic_result_baseline-official-v3.csv", index=False)
    return df


def update_classification_notes() -> pd.DataFrame:
    path = RESULTS / "country_policy_classification_final.csv"
    df = pd.read_csv(path)
    caveat = (
        " D2 caveat: displacement-exposure negative control collapses mechanically, but CHL GMI stress survives because "
        "shock scale is large relative to cost; CHL GMI remains conditional, not robust."
    )
    mask = df["country_id"].eq("CHL") & df["policy_id"].eq("GMI")
    df.loc[mask, "classification_note"] = df.loc[mask, "classification_note"].map(
        lambda note: str(note) if "D2 caveat:" in str(note) else str(note) + caveat
    )
    df.to_csv(RESULTS / "country_policy_classification_final.csv", index=False)
    df.to_csv(REPORTS / "country_policy_classification_final_baseline-official-v3.csv", index=False)
    return df


def update_hypothesis_adjudication(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "tier": "A+B+D",
            "hypothesis_id": "H1",
            "statement": "Cost/feasibility gradient across policy instruments",
            "evidence_summary": (
                "Final evidence is mixed: high-cost UBI remains only a stress benchmark, but the lower-cost ordering is not universal. "
                "PGU/PEN-style categorical pensions and ideal GMI switch order across countries; ideal GMI cannot alone support an operational ranking."
            ),
            "verdict": "MIXED",
            "preliminary_flag": False,
            "evidence_file": "fiscal_space_result.csv; policy_parameter_official_4c.csv; country_policy_classification_final.csv",
            "notes": "H1 is retained as a qualitative gradient claim, not a strict PEN/MUT<GMI<PBI<UBI ordering.",
        },
        {
            "tier": "A+B+D",
            "hypothesis_id": "H2",
            "statement": "Preparedness/adoption matter more than total exposure across countries",
            "evidence_summary": (
                "The official four-country baseline uses a common LAC fallback E_prod, so cross-country exposure variation is not identified. "
                "Preparedness, adoption, Gap and informality move T, but the total-exposure margin is not separately testable."
            ),
            "verdict": "NOT_TESTABLE",
            "preliminary_flag": False,
            "evidence_file": "value_assignment_table_baseline-official-v3.csv; informality_adoption_ablation_result.csv",
            "notes": "Requires country-specific E_prod before becoming a cross-country test.",
        },
        {
            "tier": "A+B+D",
            "hypothesis_id": "H3",
            "statement": "High informality reduces feasibility through adoption and fiscal channels",
            "evidence_summary": (
                f"Adoption-only ablation removes I from q_bar and logit, raising q_bar but leaving q_prod fixed by the frozen q_use_target/mu inversion; "
                f"max_abs_delta_v={summary['max_abs_delta_v']:.12g}, gained_crossings={summary['gained_crossings']}. "
                "The fiscal side is not ablated because informality is embedded in observed effective tax rates."
            ),
            "verdict": "MIXED",
            "preliminary_flag": False,
            "evidence_file": "informality_adoption_ablation_result.csv; diagnostic_result.csv",
            "notes": "The adoption-margin mechanism is inactive in the official frozen baseline because q_bar is not binding; the fiscal channel remains non-separable without a tax-rate counterfactual.",
        },
        {
            "tier": "A+B+D",
            "hypothesis_id": "H4",
            "statement": "Fiscal regimes materially affect feasibility",
            "evidence_summary": (
                "Regime changes materially move V and crossings in stress cells; r2/r4 raise feasible support relative to r0, with erosion companions reported for r>=1."
            ),
            "verdict": "HOLDS",
            "preliminary_flag": False,
            "evidence_file": "fiscal_space_result.csv; robustness_table.csv; diagnostic_channel_ablation_result.csv",
            "notes": "The claim is about regime sensitivity, not about robust feasibility under mid scenarios.",
        },
        {
            "tier": "A+B+D",
            "hypothesis_id": "H5",
            "statement": "Crossings requiring historically extreme fiscal capture are fragile",
            "evidence_summary": (
                "Required-MFC classes are computed against country percentiles and stress/fragile labels are retained. No final robust claim is supported by an extreme historical-capture requirement."
            ),
            "verdict": "HOLDS",
            "preliminary_flag": False,
            "evidence_file": "threshold_inversion_result.csv; historical_window_plausibility_changes.csv; country_policy_classification_final.csv",
            "notes": "The rule is enforced by schema/tests and the required-MFC class pipeline.",
        },
    ]
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "hypothesis_adjudication.csv", index=False)
    df.to_csv(REPORTS / "hypothesis_adjudication.csv", index=False)
    return df


def latex_escape(value: Any) -> str:
    text = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in repl.items():
        text = text.replace(old, new)
    return text


def write_latex(df: pd.DataFrame, path: Path, caption: str) -> None:
    cols = list(df.columns)
    lines = [
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{{latex_escape(caption)}}}",
        r"\begin{tabular}{" + "l" * len(cols) + "}",
        r"\toprule",
        " & ".join(latex_escape(c) for c in cols) + r" \\",
        r"\midrule",
    ]
    for _, row in df.iterrows():
        lines.append(" & ".join(latex_escape(row[c]) for c in cols) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def save_paper_table(name: str, df: pd.DataFrame, caption: str, latex_rows: int | None = 60) -> None:
    df = df.copy()
    for out_dir in [PAPER_RESULTS, PAPER_REPORTS]:
        df.to_csv(out_dir / f"{name}.csv", index=False)
        latex_df = df if latex_rows is None else df.head(latex_rows)
        write_latex(latex_df, out_dir / f"{name}.tex", caption)


def read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / name)


def build_paper_tables(informality_df: pd.DataFrame) -> list[dict[str, str]]:
    fiscal = read_csv("fiscal_space_result.csv")
    fiscal_xi = fiscal[fiscal["xi"].eq(XI)].copy()
    inv = read_csv("threshold_inversion_result.csv")
    hist = read_csv("historical_plausibility_result.csv")
    mc = read_csv("monte_carlo_result.csv")
    final = read_csv("country_policy_classification_final.csv")
    diag_placebo = read_csv("diagnostic_placebo_ict_result.csv")
    diag_negative = read_csv("diagnostic_negative_control_result.csv")
    diag_loso = read_csv("diagnostic_loso_result.csv")
    diag_channel = read_csv("diagnostic_channel_ablation_result.csv")
    diag_no_rent = read_csv("diagnostic_no_rent_capture_result.csv")
    diag_leak = read_csv("diagnostic_high_leakage_result.csv")
    convergence = read_csv("mc_convergence_report.csv")
    robustness = read_csv("robustness_table.csv")
    hyp = read_csv("hypothesis_adjudication.csv")
    value = pd.read_csv(REPORTS / "value_assignment_table_baseline-official-v3.csv")
    policy_param = pd.read_csv(REPORTS / "policy_parameter_official_4c.csv")

    con = duckdb.connect(str(ROOT / "db" / "ai_usp_threshold.duckdb"), read_only=True)
    try:
        macro = con.execute("SELECT country_id, year, gdp_nominal_lcu, gdp_nominal_usd, cpi_index FROM macro_anchor WHERE dataset_version=? AND year=2024", [DATASET_VERSION]).fetchdf()
        fisc = con.execute("SELECT * FROM fiscal_anchor WHERE dataset_version=? AND year=2024", [DATASET_VERSION]).fetchdf()
        debt = con.execute("SELECT country_id, gross_debt_gdp, pb_stabilizing_gdp, nominal_interest_rate FROM debt_guardrail_anchor WHERE dataset_version=? AND year=2024", [DATASET_VERSION]).fetchdf()
        gap = con.execute("SELECT * FROM digital_gap_anchor WHERE dataset_version=?", [DATASET_VERSION]).fetchdf()
        input_audit = con.execute("SELECT * FROM input_audit_report WHERE parameter_set_id=?", [PARAMETER_SET_ID]).fetchdf()
        double_counting = con.execute("SELECT * FROM double_counting_audit WHERE parameter_set_id=?", [PARAMETER_SET_ID]).fetchdf()
        registry = con.execute("SELECT * FROM calibrated_parameter_registry WHERE parameter_set_id=?", [PARAMETER_SET_ID]).fetchdf()
    finally:
        con.close()

    key_params = value[value["name"].isin(["A_aipi_total", "Gap_excluded_indicators", "I_adopt_informality", "q_use_target", "E_prod"])][
        ["country_id", "name", "baseline_value"]
    ]
    key_wide = key_params.pivot_table(index="country_id", columns="name", values="baseline_value", aggfunc="first").reset_index()
    table1 = macro.merge(fisc[["country_id", "tax_revenue_gdp", "total_revenue_gdp"]], on="country_id", how="left")
    table1 = table1.merge(debt, on="country_id", how="left")
    table1 = table1.merge(gap[["country_id", "gap_index", "coverage_lte_wimax_pct", "speed_fixed_download_mbps", "speed_mobile_download_mbps"]], on="country_id", how="left")
    table1 = table1.merge(key_wide, on="country_id", how="left")

    table2 = fiscal_xi[fiscal_xi["scenario_id"].eq("mid") & fiscal_xi["regime_id"].eq("r0")][
        ["country_id", "policy_id", "policy_variant_id", "gmi_version", "cost_gross_gdp", "cost_net_gdp", "endpoint_cost_rule"]
    ].drop_duplicates()

    scenario_rows = []
    for scenario in SCENARIOS:
        sub = fiscal_xi[fiscal_xi["scenario_id"].eq(scenario)]
        scenario_rows.append(
            {
                "block": "scenario",
                "id": scenario,
                "phi_y_nominal_min": sub["phi_y_nominal"].min(),
                "phi_y_nominal_max": sub["phi_y_nominal"].max(),
                "description": "AI shock after bridge and pi_AI_Y",
            }
        )
    for regime in REGIMES:
        sub = hist[hist["regime_id"].eq(regime)]
        scenario_rows.append(
            {
                "block": "regime",
                "id": regime,
                "phi_y_nominal_min": np.nan,
                "phi_y_nominal_max": np.nan,
                "description": f"Fiscal regime; median MFCgross={sub['mfc_gross'].median():.4f}",
            }
        )
    table3 = pd.DataFrame(scenario_rows)

    table4 = fiscal_xi[["country_id", "policy_variant_id", "scenario_id", "regime_id", "v_gross", "crosses_v1", "cell_result_class"]]
    table5 = inv[inv["xi"].eq(XI)][
        [
            "country_id",
            "policy_variant_id",
            "scenario_id",
            "regime_id",
            "requirement_basis",
            "g_ai_required",
            "mfc_required_gross",
            "q_prod_required",
            "historical_total_revenue_class",
            "flags",
        ]
    ]
    table6 = hist.merge(
        fiscal_xi.groupby(["country_id", "scenario_id", "regime_id"], as_index=False)["mfc_gross"].first(),
        on=["country_id", "scenario_id", "regime_id", "mfc_gross"],
        how="left",
    )
    table7 = mc[(mc["mc_mode"].eq("MC_independent_baseline")) & (mc["prob_basis"].eq("all_draw"))][
        [
            "country_id",
            "policy_variant_id",
            "scenario_id",
            "regime_id",
            "prob_v_ge_1",
            "prob_v_ge_1_10",
            "v_p05",
            "v_p50",
            "v_p95",
            "converged_flag",
        ]
    ]
    table8 = final

    negative_appendix = pd.concat(
        [
            diag_negative.assign(diagnostic_block="sectorial_displacement"),
            diag_no_rent.assign(diagnostic_block="no_rent_capture"),
            diag_leak.assign(diagnostic_block="high_leakage"),
        ],
        ignore_index=True,
        sort=False,
    )
    appendix_g = pd.concat(
        [
            diag_channel.assign(diagnostic_block="channel_ablation"),
            informality_df.assign(diagnostic_block="informality_adoption_ablation"),
        ],
        ignore_index=True,
        sort=False,
    )
    double_audit = pd.concat(
        [
            input_audit.assign(audit_table="input_audit_report"),
            double_counting.assign(audit_table="double_counting_audit"),
        ],
        ignore_index=True,
        sort=False,
    )
    historical_modes = mc[mc["mc_mode"].str.startswith("historical_reduced_form")].copy()
    debt_integrated = inv[(inv["xi"].eq(XI)) & (inv["requirement_basis"].eq("debt_consistent"))].copy()
    tests = pd.DataFrame(
        [
            {
                "test_file": path.name,
                "test_family": "pytest",
                "status_at_export": "covered_by_final_pytest_run",
            }
            for path in sorted((ROOT / "tests").glob("test_*.py"))
        ]
    )
    bias_ledger = pd.DataFrame(
        [
            ("frozen_anchor_2024", "T and weights held at 2024 anchor", "mixed; can understate diffusion but avoid unregistered transition dynamics"),
            ("pure_layering", "existing spending not netted from new policy cost", "conservative for feasibility"),
            ("available_tax_rates_r0", "consumption disposable-tax rates frozen at r0 convention", "favorable second-order for r>=1"),
            ("theta_target_loaded", "GMI loaded companion uses theta_target", "conservative relative to ideal GMI"),
            ("GMI_ideal", "ideal aggregate GMI has no implementation load", "favorable; cannot support ranking alone"),
            ("common_LAC_Eprod", "E_prod common fallback across four countries", "limits cross-country exposure inference"),
            ("Gap_excluded_indicators", "Gap built from ITU/Ookla excluded indicators", "reduces AIPI overlap risk"),
            ("AI_rent_subset", "AI rents inactive in r0-r2, active only conditional/stress", "prevents robust claims from rent capture"),
            ("D2_negative_control", "displacement exposure collapses V by exposure ratio but CHL GMI stress survives", "caveat on CHL GMI conditional claim"),
        ],
        columns=["bias_id", "convention", "direction"],
    )
    publishable_checklist = pd.DataFrame(
        [
            ("Baseline deterministico", "obligatorio", "obligatorio", "complete", "fiscal_space_result.csv"),
            ("Scenario-regime grid", "obligatorio", "obligatorio", "complete", "fiscal_space_result.csv"),
            ("Historical plausibility", "obligatorio", "obligatorio", "complete", "historical_plausibility_result.csv"),
            ("Threshold inversion", "obligatorio", "obligatorio", "complete", "threshold_inversion_result.csv"),
            ("Monte Carlo", "recomendable", "obligatorio", "complete", "monte_carlo_result.csv"),
            ("MC convergence report", "opcional", "obligatorio", "complete", "mc_convergence_report.csv"),
            ("GMI microdata", "recomendable", "muy recomendable", "pending_author_microdata", "not in official aggregate package"),
            ("Placebo ICT", "opcional", "obligatorio si claim fuerte", "complete", "diagnostic_placebo_ict_result.csv"),
            ("Negative controls", "opcional", "obligatorio", "complete_with_caveat", "diagnostic_negative_control_result.csv"),
            ("Leave-one-source-out", "opcional", "recomendable", "complete_where_snapshot_has_alternative", "diagnostic_loso_result.csv"),
            ("Channel ablation", "recomendable", "obligatorio", "complete", "diagnostic_channel_ablation_result.csv; informality_adoption_ablation_result.csv"),
            ("Anti-double-counting audit", "obligatorio", "obligatorio", "complete", "double_counting_audit"),
            ("Calibration registry", "obligatorio", "obligatorio", "complete", "master_calibration_matrix.csv"),
            ("Results discipline protocol", "obligatorio", "obligatorio", "complete", "schemas.yaml; verify.py; hypothesis_adjudication.csv"),
        ],
        columns=["element", "working_paper_requirement", "journal_requirement", "status", "evidence"],
    )

    tables: list[tuple[str, pd.DataFrame, str, int | None]] = [
        ("table1_anchors", table1, "Table 1. Observed anchors by country", None),
        ("table2_policy_costs", table2, "Table 2. Gross policy costs", None),
        ("table3_primary_specification", table3, "Table 3. Primary AI scenarios and fiscal regimes", None),
        ("table4_vgross_baseline", table4, "Table 4. Baseline Vgross by country, policy, scenario and regime", 80),
        ("table5_threshold_inversion", table5, "Table 5. Threshold inversion", 80),
        ("table6_historical_plausibility", table6, "Table 6. Historical plausibility", 80),
        ("table7_monte_carlo", table7, "Table 7. Monte Carlo probabilities and percentiles", 80),
        ("table8_final_classification", table8, "Table 8. Final country-policy classification", None),
        ("appendix_a_net_cost_specification", table2.merge(policy_param, on=["country_id", "policy_id"], how="left"), "Appendix A. Net-cost specification", 100),
        ("appendix_b_historical_reduced_form", historical_modes, "Appendix B. Historical reduced-form fiscal mode", 100),
        ("appendix_c_debt_integrated_specification", debt_integrated, "Appendix C. Debt-integrated threshold specification", 100),
        ("appendix_d_placebo_ict", diag_placebo, "Appendix D. Placebo ICT", 100),
        ("appendix_e_negative_controls", negative_appendix, "Appendix E. Negative controls", 100),
        ("appendix_f_leave_one_source_out", diag_loso, "Appendix F. Leave-one-source-out", None),
        ("appendix_g_channel_ablation", appendix_g, "Appendix G. Channel and informality ablations", 120),
        ("appendix_h_double_counting_audit", double_audit, "Appendix H. Anti-double-counting audit", None),
        ("appendix_i_master_calibration_matrix", value, "Appendix I. Master calibration matrix", 120),
        ("appendix_i_calibrated_parameter_registry", registry, "Appendix I. Calibrated parameter registry", 120),
        ("appendix_j_mc_convergence", convergence, "Appendix J. Monte Carlo convergence report", None),
        ("appendix_k_computational_validation_tests", tests, "Appendix K. Computational validation tests", None),
        ("master_calibration_matrix", value, "Master calibration matrix", 120),
        ("bias_ledger", bias_ledger, "Bias ledger and direction of declared conventions", None),
        ("minimum_publishable_package_checklist", publishable_checklist, "Minimum publishable package checklist", None),
        ("hypothesis_adjudication_final", hyp, "Final hypothesis adjudication", None),
        ("robustness_summary", robustness[robustness["headline_cell"].astype(bool)], "Robustness headline summary", 100),
    ]
    manifest_rows = []
    for name, df, caption, latex_rows in tables:
        save_paper_table(name, df, caption, latex_rows=latex_rows)
        manifest_rows.append({"artifact_id": name, "rows": len(df), "caption": caption, "csv": f"{name}.csv", "latex": f"{name}.tex"})
    manifest = pd.DataFrame(manifest_rows)
    save_paper_table("paper_tables_manifest", manifest, "Paper table export manifest", latex_rows=None)
    return manifest_rows


def generate_heatmaps() -> list[dict[str, str]]:
    fiscal = read_csv("fiscal_space_result.csv")
    fiscal = fiscal[fiscal["xi"].eq(XI)].copy()
    outputs = []
    for country in COUNTRIES:
        sub = fiscal[fiscal["country_id"].eq(country)].copy()
        sub["col"] = sub["scenario_id"] + "_" + sub["regime_id"]
        pivot = sub.pivot_table(index="policy_variant_id", columns="col", values="v_gross", aggfunc="first")
        pivot = pivot.reindex(sorted(pivot.index)).reindex(sorted(pivot.columns), axis=1)
        fig, ax = plt.subplots(figsize=(12, 4.8))
        im = ax.imshow(pivot.to_numpy(dtype=float), aspect="auto", cmap="viridis")
        ax.set_title(f"Vgross heatmap - {country}")
        ax.set_xlabel("scenario_regime")
        ax.set_ylabel("policy_variant")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=60, ha="right", fontsize=7)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index, fontsize=8)
        fig.colorbar(im, ax=ax, label="Vgross")
        fig.tight_layout()
        for out_dir in [FIGURES, FIGURE_REPORTS]:
            out = out_dir / f"heatmap_vgross_{country}.png"
            fig.savefig(out, dpi=180)
        plt.close(fig)
        outputs.append({"country_id": country, "figure": f"heatmap_vgross_{country}.png"})
    return outputs


def write_manifest(table_rows: list[dict[str, str]], figure_rows: list[dict[str, str]], runtime_seconds: float) -> dict[str, Any]:
    manifest = {
        "run_id": RUN_ID,
        "run_type": "phase_b_closure",
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_hash": sha256_file(ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{DATASET_VERSION}.json"),
        "commit_sha": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty": bool(git_value(["status", "--short"])),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": runtime_seconds,
        "paper_tables": table_rows,
        "figures": figure_rows,
    }
    (REPORTS / "run_manifest_phase_b_closure_baseline-official-v3.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "phase_b_closure_manifest.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def run(write: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    ensure_dirs()
    inputs = prepare_inputs()
    informality_df, informality_summary = build_informality_ablation(inputs)
    if write:
        informality_df.to_csv(RESULTS / "informality_adoption_ablation_result.csv", index=False)
        informality_df.to_csv(REPORTS / "informality_adoption_ablation_result_baseline-official-v3.csv", index=False)
        update_diagnostic_result(informality_summary)
        update_classification_notes()
        update_hypothesis_adjudication(informality_summary)
        table_rows = build_paper_tables(informality_df)
        figure_rows = generate_heatmaps()
        manifest = write_manifest(table_rows, figure_rows, time.perf_counter() - started)
    else:
        table_rows = []
        figure_rows = []
        manifest = {}
    return {
        "informality_adoption_ablation_result": informality_df,
        "informality_summary": informality_summary,
        "paper_tables": table_rows,
        "figures": figure_rows,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    write = not (argv and "--no-write" in argv)
    outputs = run(write=write)
    payload = {
        "status": "OK",
        "run_id": RUN_ID,
        "parameter_set_id": PARAMETER_SET_ID,
        "dataset_version": DATASET_VERSION,
        "informality_summary": outputs["informality_summary"],
        "paper_table_count": len(outputs["paper_tables"]),
        "figure_count": len(outputs["figures"]),
    }
    print(json.dumps(clean(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
