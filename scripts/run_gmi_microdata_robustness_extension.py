"""Labelled post-baseline GMI microdata robustness extension for Peru.

The runner validates ENAHO 2024 against official monetary-poverty aggregates,
derives microdata GMI costs, and swaps only those costs in an in-memory copy of
the certified deterministic inputs. Official files and PRIMARY_SPEC_HASH are
protected by before/after hashes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_deterministic_robustness_6a as robustness
from scripts import run_official_monte_carlo as mc


RUN_ID = "official_4c_gmimicro_per_robustness_extension_baseline_official_v3"
EXTENSION_ID = "GMI_MICRODATA_STRONG_PER_EXTENSION_2026_07_10"
EXTENSION_TYPE = "post_baseline_robustness_extension_new_input_series"
PARAMETER_SET_ID = "robustness-gmimicro-per-v1"
BASELINE_PARAMETER_SET_ID = "baseline-official-v3"
BASELINE_DATASET_VERSION = "v1.0.1-official-4c"
INPUT_SNAPSHOT_ID = PARAMETER_SET_ID
EXPECTED_PRIMARY_SPEC_HASH = "0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81"
SNAPSHOT_DIR = ROOT / "data" / "raw_snapshots" / INPUT_SNAPSHOT_ID / "enaho_sumaria"
SNAPSHOT_MANIFEST = ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{INPUT_SNAPSHOT_ID}.json"
VALIDATION_OUTPUT = ROOT / "reports" / "gmimicro_enaho_validation_2024.csv"
COST_OUTPUT = ROOT / "reports" / "gmimicro_cost_comparison_baseline-official-v3.csv"
PARAMETER_OUTPUT = ROOT / "reports" / f"value_assignment_table_{PARAMETER_SET_ID}.csv"
PARAMETER_CHANGES_OUTPUT = ROOT / "reports" / f"value_assignment_changes_{BASELINE_PARAMETER_SET_ID}_to_{PARAMETER_SET_ID}.csv"
COMPARISON_OUTPUT = ROOT / "reports" / "robustness_gmimicro_class_changes_baseline-official-v3.csv"
AMENDMENT_OUTPUT = ROOT / "reports" / "gmimicro_robustness_amendment_registry_baseline-official-v3.csv"
MANIFEST_OUTPUT = ROOT / "reports" / f"run_manifest_{PARAMETER_SET_ID}.json"
PRIMARY_WELFARE_CONCEPT = "income"
PRIMARY_WELFARE_VARIABLE = "INGHOG2D"
SENSITIVITY_WELFARE_CONCEPT = "expenditure"
SENSITIVITY_WELFARE_VARIABLE = "GASHOG2D"
OFFICIAL_FGT0 = 0.276
OFFICIAL_FGT1 = 0.072
EXPECTED_HOUSEHOLDS = 33_691
PROTECTED_FILES = (
    ROOT / "02_ESD_AI_USP_v6.md",
    ROOT / "PRIMARY_SPEC_HASH.txt",
    ROOT / "db" / "ai_usp_threshold.duckdb",
    ROOT / "results" / "official" / "fiscal_space_result.csv",
    ROOT / "results" / "official" / "country_policy_classification_final.csv",
    ROOT / "reports" / "fiscal_space_result_baseline-official-v2.csv",
    ROOT / "reports" / "country_policy_classification_final_baseline-official-v3.csv",
    ROOT / "reports" / "value_assignment_table_baseline-official-v3.csv",
    ROOT / "reports" / "calibrated_parameter_registry_baseline-official-v3.csv",
    ROOT / "reports" / "policy_parameter_official_4c.csv",
    ROOT / "reports" / "paper_tables" / "table2_policy_costs.csv",
    ROOT / "reproducibility" / "reference" / "fiscal_space_result.csv",
    ROOT / "reproducibility" / "reference" / "country_policy_classification_final.csv",
    ROOT / "paper" / "main.tex",
)


class ExtensionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise ExtensionError("Protected files are missing: " + ", ".join(missing))
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}


def primary_spec_hash_status() -> dict[str, str]:
    actual = sha256_file(ROOT / "02_ESD_AI_USP_v6.md")
    declared = None
    for line in (ROOT / "PRIMARY_SPEC_HASH.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("sha256:"):
            declared = line.split(":", 1)[1].strip()
            break
    return {
        "status": "PASS" if actual == declared == EXPECTED_PRIMARY_SPEC_HASH else "FAIL",
        "actual": actual,
        "declared": declared or "missing",
    }


def load_microdata() -> tuple[pd.DataFrame, dict[str, Any]]:
    parquet = SNAPSHOT_DIR / "enaho_sumaria_2024_required_variables.parquet"
    metadata_path = SNAPSHOT_DIR / "metadata.json"
    missing = [str(path) for path in (parquet, metadata_path, SNAPSHOT_MANIFEST) if not path.exists()]
    if missing:
        raise ExtensionError("Run scripts/17_download_enaho_sumaria.py first; missing: " + ", ".join(missing))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if sha256_file(parquet) != metadata["file_hashes"][parquet.name]:
        raise ExtensionError("ENAHO normalized parquet hash mismatch")
    frame = pd.read_parquet(parquet)
    if len(frame) != EXPECTED_HOUSEHOLDS:
        raise ExtensionError(f"Expected {EXPECTED_HOUSEHOLDS} ENAHO households, found {len(frame)}")
    return frame, metadata


def validate_enaho(frame: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = ["GASHOG2D", "INGHOG2D", "MIEPERHO", "FACTOR07", "POBREZA", "LINEA", "LINPE"]
    df = frame.copy()
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    valid = (
        df["GASHOG2D"].notna()
        & df["MIEPERHO"].gt(0)
        & df["FACTOR07"].gt(0)
        & df["LINEA"].gt(0)
        & df["POBREZA"].isin([1, 2, 3])
    )
    if not valid.all():
        raise ExtensionError(f"ENAHO validation fields invalid in {int((~valid).sum())} rows")
    ypc_expenditure = df["GASHOG2D"] / (12.0 * df["MIEPERHO"])
    poor_from_line = ypc_expenditure < df["LINEA"]
    poor_from_code = df["POBREZA"].isin([1, 2])
    matches = poor_from_line.eq(poor_from_code)
    person_weight = df["FACTOR07"] * df["MIEPERHO"]
    relative_gap = ((df["LINEA"] - ypc_expenditure) / df["LINEA"]).clip(lower=0.0)
    fgt0 = float(np.average(poor_from_line.astype(float), weights=person_weight))
    fgt1 = float(np.average(relative_gap, weights=person_weight))
    if int(matches.sum()) != EXPECTED_HOUSEHOLDS:
        raise ExtensionError(
            f"POBREZA/LINEA household classification mismatch: {int(matches.sum())}/{EXPECTED_HOUSEHOLDS}"
        )
    if round(100.0 * fgt0, 1) != round(100.0 * OFFICIAL_FGT0, 1):
        raise ExtensionError(f"FGT0 validation failed: recalculated={100*fgt0:.9f}%")
    if round(100.0 * fgt1, 1) != round(100.0 * OFFICIAL_FGT1, 1):
        raise ExtensionError(f"FGT1 validation failed: recalculated={100*fgt1:.9f}%")
    return pd.DataFrame(
        [
            {
                "country_id": "PER",
                "survey_year": 2024,
                "validation_object": "FGT0_headcount",
                "recalculated_exact": fgt0,
                "recalculated_percent": 100.0 * fgt0,
                "official_percent": 100.0 * OFFICIAL_FGT0,
                "rounding_decimals": 1,
                "assert_status": "PASS",
                "formula": "weighted mean[GASHOG2D/(12*MIEPERHO) < LINEA], weight=FACTOR07*MIEPERHO",
            },
            {
                "country_id": "PER",
                "survey_year": 2024,
                "validation_object": "FGT1_poverty_gap",
                "recalculated_exact": fgt1,
                "recalculated_percent": 100.0 * fgt1,
                "official_percent": 100.0 * OFFICIAL_FGT1,
                "rounding_decimals": 1,
                "assert_status": "PASS",
                "formula": "weighted mean[max(0,(LINEA-ypc_expenditure)/LINEA)], weight=FACTOR07*MIEPERHO",
            },
            {
                "country_id": "PER",
                "survey_year": 2024,
                "validation_object": "POBREZA_household_classification",
                "recalculated_exact": float(matches.sum()),
                "recalculated_percent": 100.0 * float(matches.mean()),
                "official_percent": 100.0,
                "rounding_decimals": 9,
                "assert_status": "PASS",
                "formula": f"POBREZA in {{1,2}} equals ypc_expenditure < LINEA: {int(matches.sum())}/{len(matches)}",
            },
        ]
    )


def official_inputs(inputs: dict[str, Any]) -> dict[str, float | str]:
    poverty = pd.read_parquet(ROOT / "data" / "model_inputs" / "poverty_distribution_anchor.parquet")
    poverty = poverty[poverty["country_id"].eq("PER") & poverty["year"].eq(2024)]
    macro = inputs["macro_anchor"]
    macro = macro[macro["country_id"].eq("PER") & macro["year"].eq(2024)]
    costs = inputs["policy_cost"]
    costs = costs[costs["country_id"].eq("PER") & costs["policy_id"].eq("GMI")]
    if len(poverty) != 1 or len(macro) != 1 or len(costs) != 2:
        raise ExtensionError("Official PER GMI provenance is not unique")
    p = poverty.iloc[0]
    if str(p["welfare_type"]) != PRIMARY_WELFARE_CONCEPT:
        raise ExtensionError(f"Expected official welfare_type=income, found {p['welfare_type']}")
    ideal = costs[costs["gmi_version"].eq("GMI_ideal_aggregate")].iloc[0]
    loaded = costs[costs["gmi_version"].eq("GMI_loaded_aggregate")].iloc[0]
    return {
        "gdp_nominal_lcu_2024": float(macro.iloc[0]["gdp_nominal_lcu"]),
        "official_welfare_type": str(p["welfare_type"]),
        "official_poverty_line_ppp_daily": float(p["poverty_line_ppp_daily"]),
        "official_poverty_line_lcu_annual": float(p["poverty_line_national_lcu_annual"]),
        "official_poverty_gap": float(p["poverty_gap"]),
        "official_source_year": int(p["source_year"]),
        "official_ideal_cost_gdp": float(ideal["policy_cost_gross_gdp"]),
        "official_loaded_cost_gdp": float(loaded["policy_cost_gross_gdp"]),
        "official_ideal_cost_lcu": float(ideal["policy_cost_gross_lcu"]),
        "official_loaded_cost_lcu": float(loaded["policy_cost_gross_lcu"]),
        "chi_gmi": float(ideal["chi_gmi"]),
        "theta_ideal": 1.0,
        "theta_loaded": float(loaded["policy_cost_gross_lcu"] / ideal["policy_cost_gross_lcu"]),
    }


def aggregate_micro_gap(frame: pd.DataFrame, welfare_variable: str) -> float:
    ypc_monthly = frame[welfare_variable].astype(float) / (12.0 * frame["MIEPERHO"].astype(float))
    monthly_gap = (frame["LINEA"].astype(float) - ypc_monthly).clip(lower=0.0)
    return float(
        (frame["FACTOR07"].astype(float) * frame["MIEPERHO"].astype(float) * 12.0 * monthly_gap).sum()
    )


def build_costs(frame: pd.DataFrame, official: dict[str, float | str]) -> pd.DataFrame:
    gdp = float(official["gdp_nominal_lcu_2024"])
    chi = float(official["chi_gmi"])
    rows: list[dict[str, Any]] = []
    concepts = [
        (PRIMARY_WELFARE_CONCEPT, PRIMARY_WELFARE_VARIABLE, True),
        (SENSITIVITY_WELFARE_CONCEPT, SENSITIVITY_WELFARE_VARIABLE, False),
    ]
    for concept, variable, primary in concepts:
        gap_lcu = aggregate_micro_gap(frame, variable)
        for targeting, theta in [("ideal", float(official["theta_ideal"])), ("loaded", float(official["theta_loaded"]))]:
            cost_lcu = theta * chi * gap_lcu
            official_cost_lcu = float(official[f"official_{targeting}_cost_lcu"])
            official_cost_gdp = float(official[f"official_{targeting}_cost_gdp"])
            rows.append(
                {
                    "parameter_set_id": PARAMETER_SET_ID,
                    "country_id": "PER",
                    "policy_id": "GMI",
                    "micro_gmi_version": f"GMI_{targeting}_microdata_{concept}",
                    "baseline_gmi_version": f"GMI_{targeting}_aggregate",
                    "welfare_concept": concept,
                    "welfare_variable": variable,
                    "primary_variant": primary,
                    "poverty_line_variable": "LINEA",
                    "survey_year": 2024,
                    "carried_forward_to_2024": False,
                    "chi_gmi": chi,
                    "theta_target": theta,
                    "aggregate_gap_lcu_annual": gap_lcu,
                    "cost_micro_lcu": cost_lcu,
                    "cost_micro_gdp": cost_lcu / gdp,
                    "cost_official_aggregate_lcu": official_cost_lcu,
                    "cost_official_aggregate_gdp": official_cost_gdp,
                    "difference_lcu": cost_lcu - official_cost_lcu,
                    "difference_gdp": cost_lcu / gdp - official_cost_gdp,
                    "difference_percent_vs_official": 100.0 * (cost_lcu / official_cost_lcu - 1.0),
                    "gdp_nominal_lcu_2024": gdp,
                    "source_id": "INEI_ENAHO_SUMARIA_2024",
                    "robustness_flag": True,
                }
            )
    return pd.DataFrame(rows)


def build_parameter_set(inputs: dict[str, Any], costs: pd.DataFrame, metadata: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    values = inputs["values"].copy()
    if set(values["parameter_set_id"].dropna().unique()) != {BASELINE_PARAMETER_SET_ID}:
        raise ExtensionError("Input calibration is not exclusively baseline-official-v3")
    values["parameter_set_id"] = PARAMETER_SET_ID
    values["build_id"] = f"{PARAMETER_SET_ID}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    values["created_at"] = datetime.now(timezone.utc).isoformat()
    values["created_by_script"] = Path(__file__).name
    changes: list[dict[str, Any]] = []
    primary = costs[costs["primary_variant"]].set_index("baseline_gmi_version")
    for targeting in ("ideal", "loaded"):
        baseline_version = f"GMI_{targeting}_aggregate"
        name = f"policy_cost_gross_gdp_{baseline_version}"
        mask = values["country_id"].eq("PER") & values["name"].eq(name)
        if int(mask.sum()) != 1:
            raise ExtensionError(f"Expected one official value-assignment row for {name}")
        old = float(values.loc[mask, "baseline_value"].iloc[0])
        new = float(primary.loc[baseline_version, "cost_micro_gdp"])
        values.loc[mask, ["baseline_value", "low_value", "high_value"]] = new
        values.loc[mask, "primary_spec_flag"] = False
        values.loc[mask, "robustness_flag"] = True
        values.loc[mask, "stress_flag"] = False
        values.loc[mask, "value_type"] = "observed_microdata_derived_cost"
        values.loc[mask, "support_type"] = "post_baseline_robustness_new_input_series"
        values.loc[mask, "source_id"] = "INEI_ENAHO_SUMARIA_2024"
        values.loc[mask, "formula_id"] = "theta_target*chi_gmi*sum(FACTOR07*MIEPERHO*12*max(0,LINEA-INGHOG2D/(12*MIEPERHO)))/GDP_2024"
        values.loc[mask, "distribution"] = "fixed"
        values.loc[mask, "audit_status"] = "registered_post_baseline_robustness"
        values.loc[mask, "notes"] = (
            "Labelled post-baseline GMI microdata-strong variant; official PIP aggregate cost remains unchanged. "
            f"ENAHO 2024 t0 exact, no carried-forward; source={metadata['source_url']}."
        )
        changes.append(
            {
                "parameter_set_id": PARAMETER_SET_ID,
                "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
                "country_id": "PER",
                "name": name,
                "baseline_value_official": old,
                "robustness_value": new,
                "delta": new - old,
                "source_year": 2024,
                "target_year": 2024,
                "carried_forward_to_2024": False,
                "source_id": "INEI_ENAHO_SUMARIA_2024",
                "source_endpoint": metadata["source_url"],
                "robustness_flag": True,
            }
        )
    return values, pd.DataFrame(changes)


def in_memory_policy_cost(inputs: dict[str, Any], costs: pd.DataFrame) -> pd.DataFrame:
    policy_cost = inputs["policy_cost"].copy()
    primary = costs[costs["primary_variant"]].set_index("baseline_gmi_version")
    for version, row in primary.iterrows():
        mask = (
            policy_cost["country_id"].eq("PER")
            & policy_cost["policy_id"].eq("GMI")
            & policy_cost["gmi_version"].eq(version)
        )
        if int(mask.sum()) != 1:
            raise ExtensionError(f"Expected one policy-cost row for PER/{version}")
        policy_cost.loc[mask, "policy_cost_gross_lcu"] = float(row["cost_micro_lcu"])
        policy_cost.loc[mask, "policy_cost_net_lcu"] = float(row["cost_micro_lcu"])
        policy_cost.loc[mask, "policy_cost_gross_gdp"] = float(row["cost_micro_gdp"])
        policy_cost.loc[mask, "policy_cost_net_gdp"] = float(row["cost_micro_gdp"])
        policy_cost.loc[mask, "cost_convention"] = f"labelled_{row['micro_gmi_version']}"
        policy_cost.loc[mask, "microdata_used"] = True
        policy_cost.loc[mask, "parameter_set_id"] = PARAMETER_SET_ID
    return policy_cost


def ordinal_rank(frame: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    ranked_parts = []
    for _, group in frame.groupby(["country_id", "scenario_id", "regime_id"], sort=True):
        ranked = group.sort_values([value_col, "policy_variant_id"], ascending=[False, True]).copy()
        ranked[output_col] = np.arange(1, len(ranked) + 1, dtype=int)
        ranked_parts.append(ranked)
    return pd.concat(ranked_parts, ignore_index=True)


def add_primary_five_policy_rank(frame: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    """Rank five instruments using ideal GMI; loaded GMI is a companion, not a sixth policy."""
    keys = ["country_id", "policy_id", "policy_variant_id", "scenario_id", "regime_id"]
    primary = frame[~frame["gmi_version"].eq("GMI_loaded_aggregate")].copy()
    primary = ordinal_rank(primary, value_col, output_col)
    return frame.merge(primary[keys + [output_col]], on=keys, how="left", validate="one_to_one")


def build_comparison(inputs: dict[str, Any], costs: pd.DataFrame) -> pd.DataFrame:
    baseline = pd.read_csv(ROOT / "results" / "official" / "fiscal_space_result.csv")
    baseline = baseline[baseline["xi"].eq(robustness.XI)].copy()
    if len(baseline) != 480:
        raise ExtensionError(f"Expected 480 official baseline cells at xi=0.10, found {len(baseline)}")
    baseline_classes = baseline[
        ["country_id", "policy_id", "gmi_version", "country_policy_result_class"]
    ].drop_duplicates()
    variant = robustness.Variant(
        variant_id="GMI_microdata_strong_PER",
        family="post_baseline_GMI_microdata_strong",
        label="ENAHO 2024 microdata income-gap GMI cost; official aggregate cost retained as comparator",
    )
    variant_grid, diagnostics = robustness.run_variant(
        ROOT, inputs, variant, baseline, baseline_classes, gap_resid={}
    )
    if diagnostics or len(variant_grid) != 480:
        raise ExtensionError(
            f"Unexpected GMI-micro runner output: rows={len(variant_grid)}, diagnostics={diagnostics}"
        )
    baseline = ordinal_rank(baseline, "v_gross", "policy_rank_baseline")
    variant_grid = ordinal_rank(variant_grid, "v_gross", "policy_rank_micro")
    baseline = add_primary_five_policy_rank(
        baseline, "v_gross", "primary_five_policy_rank_baseline"
    )
    variant_grid = add_primary_five_policy_rank(
        variant_grid, "v_gross", "primary_five_policy_rank_micro"
    )
    keys = ["country_id", "policy_id", "policy_variant_id", "scenario_id", "regime_id"]
    base_cols = keys + [
        "gmi_version", "v_gross", "cost_gross_gdp", "crosses_v1", "crosses_v1_10",
        "debt_guardrail_pass", "cell_result_class", "country_policy_result_class",
        "historical_tax_class", "historical_tax_borderline",
        "historical_total_revenue_class", "historical_total_revenue_borderline",
        "policy_rank_baseline", "primary_five_policy_rank_baseline",
    ]
    variant_cols = keys + [
        "v_gross", "cost_gross_gdp", "crosses_v1", "crosses_v1_10",
        "debt_guardrail_pass", "variant_cell_result_class", "variant_country_policy_result_class",
        "historical_tax_class", "historical_tax_borderline",
        "historical_total_revenue_class", "historical_total_revenue_borderline",
        "policy_rank_micro", "primary_five_policy_rank_micro",
    ]
    merged = baseline[base_cols].merge(
        variant_grid[variant_cols], on=keys, how="outer", validate="one_to_one",
        suffixes=("_baseline", "_micro"), indicator=True,
    )
    if len(merged) != 480 or not merged["_merge"].eq("both").all():
        raise ExtensionError("Baseline/GMI-micro full-grid key matching failed")
    merged = merged.drop(columns="_merge")
    result = merged[merged["country_id"].eq("PER") & merged["policy_id"].eq("GMI")].copy()
    if len(result) != 40:
        raise ExtensionError(f"Expected 40 PER GMI comparison cells, found {len(result)}")
    result = result.rename(
        columns={
            "gmi_version": "baseline_gmi_version",
            "v_gross_baseline": "v_baseline",
            "v_gross_micro": "v_micro",
            "cell_result_class": "baseline_cell_result_class",
            "variant_cell_result_class": "micro_cell_result_class",
            "country_policy_result_class": "baseline_country_policy_result_class",
            "variant_country_policy_result_class": "micro_country_policy_result_class",
        }
    )
    micro_version = {
        "GMI_ideal_aggregate": "GMI_ideal_microdata_income",
        "GMI_loaded_aggregate": "GMI_loaded_microdata_income",
    }
    result["micro_gmi_version"] = result["baseline_gmi_version"].map(micro_version)
    result["delta_v"] = result["v_micro"] - result["v_baseline"]
    result["class_changed_flag"] = result["baseline_cell_result_class"] != result["micro_cell_result_class"]
    result["country_policy_class_changed_flag"] = (
        result["baseline_country_policy_result_class"] != result["micro_country_policy_result_class"]
    )
    result["policy_rank_changed_flag"] = result["policy_rank_baseline"] != result["policy_rank_micro"]
    result["primary_five_policy_rank_changed_flag"] = (
        result["primary_five_policy_rank_baseline"].notna()
        & result["primary_five_policy_rank_micro"].notna()
        & (result["primary_five_policy_rank_baseline"] != result["primary_five_policy_rank_micro"])
    )
    result["crosses_v1_changed_flag"] = result["crosses_v1_baseline"] != result["crosses_v1_micro"]
    result["crosses_v1_10_changed_flag"] = result["crosses_v1_10_baseline"] != result["crosses_v1_10_micro"]
    result["debt_guardrail_changed_flag"] = (
        result["debt_guardrail_pass_baseline"] != result["debt_guardrail_pass_micro"]
    )
    result.insert(0, "extension_id", EXTENSION_ID)
    result.insert(0, "run_id", RUN_ID)
    result["run_type"] = "robustness"
    result["extension_type"] = EXTENSION_TYPE
    result["parameter_set_id"] = PARAMETER_SET_ID
    result["baseline_parameter_set_id"] = BASELINE_PARAMETER_SET_ID
    result["baseline_dataset_version"] = BASELINE_DATASET_VERSION
    result["extension_input_snapshot_id"] = INPUT_SNAPSHOT_ID
    return result.sort_values(["scenario_id", "regime_id", "baseline_gmi_version"]).reset_index(drop=True)


def git_value(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_outputs() -> dict[str, Any]:
    started = time.perf_counter()
    spec = primary_spec_hash_status()
    if spec["status"] != "PASS":
        raise ExtensionError(f"PRIMARY_SPEC_HASH gate failed: {spec}")
    protected_before = file_hashes(PROTECTED_FILES)
    frame, metadata = load_microdata()
    validation = validate_enaho(frame)
    inputs = mc.load_inputs(ROOT)
    official = official_inputs(inputs)
    costs = build_costs(frame, official)
    parameter_set, parameter_changes = build_parameter_set(inputs, costs, metadata)
    variant_inputs = {
        **inputs,
        "values": parameter_set,
        "policy_cost": in_memory_policy_cost(inputs, costs),
    }
    comparison = build_comparison(variant_inputs, costs)

    ROOT.joinpath("reports").mkdir(exist_ok=True)
    validation.to_csv(VALIDATION_OUTPUT, index=False)
    costs.to_csv(COST_OUTPUT, index=False)
    parameter_set.to_csv(PARAMETER_OUTPUT, index=False)
    parameter_changes.to_csv(PARAMETER_CHANGES_OUTPUT, index=False)
    comparison.to_csv(COMPARISON_OUTPUT, index=False)

    protected_after = file_hashes(PROTECTED_FILES)
    if protected_before != protected_after:
        changed = [key for key in protected_before if protected_before[key] != protected_after.get(key)]
        raise ExtensionError(f"Protected official files changed: {changed}")
    spec_after = primary_spec_hash_status()
    if spec_after != spec:
        raise ExtensionError("PRIMARY_SPEC_HASH status changed during the extension")

    counts = {
        "comparison_rows": int(len(comparison)),
        "cell_class_changes": int(comparison["class_changed_flag"].sum()),
        "country_policy_class_changes": int(comparison["country_policy_class_changed_flag"].sum()),
        "policy_rank_row_changes": int(comparison["policy_rank_changed_flag"].sum()),
        "primary_five_policy_rank_row_changes": int(
            comparison["primary_five_policy_rank_changed_flag"].sum()
        ),
        "crosses_v1_changes": int(comparison["crosses_v1_changed_flag"].sum()),
        "crosses_v1_10_changes": int(comparison["crosses_v1_10_changed_flag"].sum()),
        "debt_guardrail_changes": int(comparison["debt_guardrail_changed_flag"].sum()),
    }
    amendment = pd.DataFrame(
        [
            {
                "run_id": RUN_ID,
                "amendment_id": EXTENSION_ID,
                "extension_type": EXTENSION_TYPE,
                "amendment_text": (
                    "Post-baseline robustness extension using newly declared ENAHO 2024 Sumaria microdata. "
                    "The official PIP aggregate GMI cost remains unchanged and is used only as comparator; "
                    "the microdata cost is a labelled variant."
                ),
                "new_input_series": True,
                "input_snapshot_id": INPUT_SNAPSHOT_ID,
                "input_snapshot_manifest_sha256": sha256_file(SNAPSHOT_MANIFEST),
                "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
                "robustness_parameter_set_id": PARAMETER_SET_ID,
                "primary_welfare_concept": PRIMARY_WELFARE_CONCEPT,
                "baseline_calibration_changed": False,
                "engine_changed": False,
                "official_results_changed": False,
                "official_classification_changed": False,
                "paper_changed": False,
                "primary_spec_hash_status": spec_after["status"],
                "primary_spec_hash_actual": spec_after["actual"],
                "primary_spec_hash_declared": spec_after["declared"],
                "protected_file_hashes_before_json": json.dumps(protected_before, sort_keys=True),
                "protected_file_hashes_after_json": json.dumps(protected_after, sort_keys=True),
                "protected_files_unchanged": True,
                "validation_output_sha256": sha256_file(VALIDATION_OUTPUT),
                "cost_output_sha256": sha256_file(COST_OUTPUT),
                "parameter_set_sha256": sha256_file(PARAMETER_OUTPUT),
                "parameter_changes_sha256": sha256_file(PARAMETER_CHANGES_OUTPUT),
                "comparison_output_sha256": sha256_file(COMPARISON_OUTPUT),
                **counts,
                "source_download_date": metadata["download_date"],
                "source_endpoint": metadata["source_url"],
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
    amendment.to_csv(AMENDMENT_OUTPUT, index=False)
    manifest = {
        "run_id": RUN_ID,
        "run_type": "robustness",
        "extension_id": EXTENSION_ID,
        "extension_type": EXTENSION_TYPE,
        "parameter_set_id": PARAMETER_SET_ID,
        "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
        "baseline_dataset_version": BASELINE_DATASET_VERSION,
        "extension_input_snapshot_id": INPUT_SNAPSHOT_ID,
        "primary_spec_hash": spec_after,
        "protected_files_unchanged": True,
        "official_gmi_provenance": official,
        "validation": validation.to_dict(orient="records"),
        **counts,
        "runtime_seconds": time.perf_counter() - started,
        "commit_sha_at_run": git_value(["rev-parse", "HEAD"]),
        "git_dirty_at_run": bool(git_value(["status", "--short"])),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Only PER GMI ideal/loaded policy costs change in memory. Income is primary because the official "
            "PIP anchor records welfare_type=income; expenditure is reported as a cost sensitivity only."
        ),
    }
    MANIFEST_OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "manifest": manifest,
        "validation": validation,
        "costs": costs,
        "parameter_changes": parameter_changes,
        "comparison": comparison,
    }


def main() -> int:
    outputs = write_outputs()
    print("ENAHO VALIDATION")
    print(outputs["validation"].to_string(index=False))
    print("\nGMI COSTS")
    print(outputs["costs"].to_string(index=False))
    print("\nRUN MANIFEST")
    print(json.dumps(outputs["manifest"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
