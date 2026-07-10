"""Labelled post-baseline CASEN GMI microdata robustness extension for Chile."""

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


RUN_ID = "official_4c_gmimicro_chl_robustness_extension_baseline_official_v3"
EXTENSION_ID = "GMI_MICRODATA_STRONG_CHL_EXTENSION_2026_07_10"
EXTENSION_TYPE = "post_baseline_robustness_extension_new_input_series"
PARAMETER_SET_ID = "robustness-gmimicro-chl-v1"
BASELINE_PARAMETER_SET_ID = "baseline-official-v3"
BASELINE_DATASET_VERSION = "v1.0.1-official-4c"
INPUT_SNAPSHOT_ID = PARAMETER_SET_ID
EXPECTED_PRIMARY_SPEC_HASH = "0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81"
EXPECTED_PERSON_ROWS = 218_367
EXPECTED_VALID_PERSON_ROWS = 218_260
EXPECTED_HOUSEHOLDS = 78_654
OFFICIAL_CASEN_FGT0 = 0.172887668474524
OFFICIAL_CASEN_FGT1 = 0.0541874918475942
EXPECTED_PIP_LINE_LCU_ANNUAL = 1_825_919.8813
SNAPSHOT_DIR = ROOT / "data" / "raw_snapshots" / INPUT_SNAPSHOT_ID / "casen_2024"
SNAPSHOT_MANIFEST = ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{INPUT_SNAPSHOT_ID}.json"
VALIDATION_OUTPUT = ROOT / "reports" / "gmimicro_chl_casen_validation_2024.csv"
COST_OUTPUT = ROOT / "reports" / "gmimicro_chl_cost_comparison_baseline-official-v3.csv"
PARAMETER_OUTPUT = ROOT / "reports" / f"value_assignment_table_{PARAMETER_SET_ID}.csv"
PARAMETER_CHANGES_OUTPUT = ROOT / "reports" / f"value_assignment_changes_{BASELINE_PARAMETER_SET_ID}_to_{PARAMETER_SET_ID}.csv"
COMPARISON_OUTPUT = ROOT / "reports" / "robustness_gmimicro_chl_class_changes_baseline-official-v3.csv"
AMENDMENT_OUTPUT = ROOT / "reports" / "gmimicro_chl_robustness_amendment_registry_baseline-official-v3.csv"
MANIFEST_OUTPUT = ROOT / "reports" / f"run_manifest_{PARAMETER_SET_ID}.json"
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
    parquet = SNAPSHOT_DIR / "casen_2024_gmi_required_variables.parquet"
    metadata_path = SNAPSHOT_DIR / "metadata.json"
    missing = [str(path) for path in (parquet, metadata_path, SNAPSHOT_MANIFEST) if not path.exists()]
    if missing:
        raise ExtensionError("Run scripts/18_download_casen_2024.py first; missing: " + ", ".join(missing))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if sha256_file(parquet) != metadata["file_hashes"][parquet.name]:
        raise ExtensionError("CASEN normalized parquet hash mismatch")
    frame = pd.read_parquet(parquet)
    if len(frame) != EXPECTED_PERSON_ROWS or int(frame["folio"].nunique()) != EXPECTED_HOUSEHOLDS:
        raise ExtensionError("CASEN row or household count differs from the frozen metadata")
    return frame, metadata


def validate_casen(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    numeric = [
        "folio", "id_persona", "ytotcorh", "ypchtotcor", "ymonecorh", "yae", "nae",
        "numper", "expr", "lp", "li", "pobreza", "no_arrienda",
    ]
    df = frame.copy()
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    valid = (
        df["pobreza"].isin([1, 2, 3])
        & df["yae"].notna()
        & df["lp"].gt(0)
        & df["expr"].gt(0)
    )
    if int(valid.sum()) != EXPECTED_VALID_PERSON_ROWS:
        raise ExtensionError(f"Expected {EXPECTED_VALID_PERSON_ROWS} valid persons, found {int(valid.sum())}")
    valid_persons = df[valid].copy()
    poor_code = valid_persons["pobreza"].isin([1, 2])
    poor_line = valid_persons["yae"] < valid_persons["lp"]
    matches = poor_code.eq(poor_line)
    weights = valid_persons["expr"].astype(float)
    relative_gap = ((valid_persons["lp"] - valid_persons["yae"]) / valid_persons["lp"]).clip(lower=0.0)
    fgt0 = float(np.average(poor_line.astype(float), weights=weights))
    fgt1 = float(np.average(relative_gap, weights=weights))
    if int(matches.sum()) != EXPECTED_VALID_PERSON_ROWS:
        raise ExtensionError(f"CASEN pobreza classification mismatch: {int(matches.sum())}/{len(matches)}")
    if abs(fgt0 - OFFICIAL_CASEN_FGT0) > 5e-10 or abs(fgt1 - OFFICIAL_CASEN_FGT1) > 5e-10:
        raise ExtensionError(f"CASEN FGT gate failed: FGT0={fgt0}, FGT1={fgt1}")

    household_columns = [
        "expr", "ytotcorh", "ypchtotcor", "ymonecorh", "yae", "nae", "numper",
        "lp", "li", "pobreza", "no_arrienda",
    ]
    household_variation = {
        column: int((valid_persons.groupby("folio")[column].nunique(dropna=False) > 1).sum())
        for column in household_columns
    }
    if any(household_variation.values()):
        raise ExtensionError(f"CASEN household variables are not constant within folio: {household_variation}")
    households = (
        valid_persons.sort_values(["folio", "id_persona"])
        .drop_duplicates("folio")
        .reset_index(drop=True)
    )
    if len(households) != EXPECTED_HOUSEHOLDS:
        raise ExtensionError(f"Expected {EXPECTED_HOUSEHOLDS} valid households, found {len(households)}")
    population_household = float((households["expr"] * households["numper"]).sum())
    population_person = float(valid_persons["expr"].sum())
    if population_household != population_person:
        raise ExtensionError(
            f"CASEN person expansion mismatch: household={population_household}, person={population_person}"
        )
    ypc_derived = households["ytotcorh"] / households["numper"]
    ypc_difference = (ypc_derived - households["ypchtotcor"]).abs()
    if not ypc_difference.le(0.5).all():
        raise ExtensionError(f"ypchtotcor rounding difference exceeds CLP 0.50: {ypc_difference.max()}")
    validation = pd.DataFrame(
        [
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "FGT0_national_methodology",
                "recalculated_exact": fgt0, "official_exact": OFFICIAL_CASEN_FGT0,
                "recalculated_percent": 100.0 * fgt0, "official_percent": 100.0 * OFFICIAL_CASEN_FGT0,
                "assert_status": "PASS", "formula": "weighted mean[yae < lp], weight=expr on valid persons",
            },
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "FGT1_national_methodology",
                "recalculated_exact": fgt1, "official_exact": OFFICIAL_CASEN_FGT1,
                "recalculated_percent": 100.0 * fgt1, "official_percent": 100.0 * OFFICIAL_CASEN_FGT1,
                "assert_status": "PASS", "formula": "weighted mean[max(0,(lp-yae)/lp)], weight=expr",
            },
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "pobreza_classification",
                "recalculated_exact": float(matches.sum()), "official_exact": float(EXPECTED_VALID_PERSON_ROWS),
                "recalculated_percent": 100.0 * float(matches.mean()), "official_percent": 100.0,
                "assert_status": "PASS", "formula": f"pobreza in {{1,2}} equals yae < lp: {matches.sum()}/{len(matches)}",
            },
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "expr_constant_within_household",
                "recalculated_exact": float(household_variation["expr"]), "official_exact": 0.0,
                "recalculated_percent": np.nan, "official_percent": np.nan,
                "assert_status": "PASS", "formula": "number of folios with more than one expr value",
            },
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "person_expansion_identity",
                "recalculated_exact": population_household, "official_exact": population_person,
                "recalculated_percent": np.nan, "official_percent": np.nan,
                "assert_status": "PASS", "formula": "sum_households(expr*numper) = sum_valid_person_rows(expr)",
            },
            {
                "country_id": "CHL", "survey_year": 2024, "validation_object": "ypchtotcor_rounding",
                "recalculated_exact": float(ypc_difference.max()), "official_exact": 0.5,
                "recalculated_percent": np.nan, "official_percent": np.nan,
                "assert_status": "PASS", "formula": "max abs(ytotcorh/numper - ypchtotcor) <= CLP 0.50 monthly",
            },
        ]
    )
    return validation, households


def official_inputs(inputs: dict[str, Any]) -> dict[str, float | str]:
    poverty = pd.read_parquet(ROOT / "data" / "model_inputs" / "poverty_distribution_anchor.parquet")
    poverty = poverty[poverty["country_id"].eq("CHL") & poverty["year"].eq(2024)]
    macro = pd.read_parquet(ROOT / "data" / "model_inputs" / "macro_anchor.parquet")
    macro = macro[macro["country_id"].eq("CHL") & macro["year"].eq(2024)]
    costs = inputs["policy_cost"]
    costs = costs[costs["country_id"].eq("CHL") & costs["policy_id"].eq("GMI")]
    if len(poverty) != 1 or len(macro) != 1 or len(costs) != 2:
        raise ExtensionError("Official CHL GMI provenance is not unique")
    p = poverty.iloc[0]
    if str(p["welfare_type"]) != "income" or float(p["poverty_line_ppp_daily"]) != 8.3:
        raise ExtensionError("Official CHL GMI anchor is not the expected PIP income/PPP 8.30 object")
    ideal = costs[costs["gmi_version"].eq("GMI_ideal_aggregate")].iloc[0]
    loaded = costs[costs["gmi_version"].eq("GMI_loaded_aggregate")].iloc[0]
    return {
        "gdp_nominal_lcu_2024": float(macro.iloc[0]["gdp_nominal_lcu"]),
        "official_population_total": float(macro.iloc[0]["population_total_wpp"]),
        "official_welfare_type": str(p["welfare_type"]),
        "official_poverty_line_lcu_annual": float(p["poverty_line_national_lcu_annual"]),
        "official_poverty_line_ppp_daily": float(p["poverty_line_ppp_daily"]),
        "official_poverty_headcount": float(p["poverty_headcount"]),
        "official_poverty_gap": float(p["poverty_gap"]),
        "official_source_year": int(p["source_year"]),
        "official_ideal_cost_lcu": float(ideal["policy_cost_gross_lcu"]),
        "official_loaded_cost_lcu": float(loaded["policy_cost_gross_lcu"]),
        "official_ideal_cost_gdp": float(ideal["policy_cost_gross_gdp"]),
        "official_loaded_cost_gdp": float(loaded["policy_cost_gross_gdp"]),
        "chi_gmi": float(ideal["chi_gmi"]),
        "theta_ideal": 1.0,
        "theta_loaded": float(loaded["policy_cost_gross_lcu"] / ideal["policy_cost_gross_lcu"]),
    }


def build_costs(households: pd.DataFrame, official: dict[str, float | str]) -> pd.DataFrame:
    gdp = float(official["gdp_nominal_lcu_2024"])
    pip_line = float(official["official_poverty_line_lcu_annual"])
    if abs(pip_line - EXPECTED_PIP_LINE_LCU_ANNUAL) > 1e-3:
        raise ExtensionError(f"Unexpected official PIP line: {pip_line}")
    person_weight = households["expr"] * households["numper"]
    population_casen = float(person_weight.sum())
    primary_annual_pc = 12.0 * households["ytotcorh"] / households["numper"]
    monetary_annual_pc = 12.0 * households["ymonecorh"] / households["numper"]
    concepts: list[dict[str, Any]] = []
    for concept, variable, welfare in [
        ("primary_total_corrected_income", "ytotcorh/numper", primary_annual_pc),
        ("monetary_income_sensitivity", "ymonecorh/numper", monetary_annual_pc),
    ]:
        shortfall = (pip_line - welfare).clip(lower=0.0)
        concepts.append(
            {
                "concept": concept,
                "variable": variable,
                "primary": concept.startswith("primary_"),
                "policy_variant_z": "pip_ppp_8_30_line",
                "poverty_line_variable": "PIP_PPP_8_30_constant_lcu_annual",
                "poverty_line_value": pip_line,
                "poverty_line_type": "constant",
                "poverty_line_min": pip_line,
                "poverty_line_max": pip_line,
                "gap_lcu": float((person_weight * shortfall).sum()),
                "fgt0": float(np.average(welfare < pip_line, weights=person_weight)),
                "fgt1": float(np.average(shortfall / pip_line, weights=person_weight)),
                "note": (
                    "Raw ytotcorh includes imputed rent and is the closest unharmonized CASEN total-income "
                    "analogue to PIP/CEDLAS income."
                    if concept.startswith("primary_")
                    else "Monetary-income sensitivity excludes imputed rent."
                ),
            }
        )
    national_shortfall = (households["lp"] - households["yae"]).clip(lower=0.0)
    national_line_annual = 12.0 * households["lp"]
    concepts.append(
        {
            "concept": "national_methodology_reference",
            "variable": "yae",
            "primary": False,
            "policy_variant_z": "national_methodology",
            "poverty_line_variable": "lp",
            "poverty_line_value": float(np.average(national_line_annual, weights=person_weight)),
            "poverty_line_type": "dual_renter_nonrenter_adult_equivalent",
            "poverty_line_min": float(national_line_annual.min()),
            "poverty_line_max": float(national_line_annual.max()),
            "gap_lcu": float((households["expr"] * 12.0 * households["nae"] * national_shortfall).sum()),
            "fgt0": OFFICIAL_CASEN_FGT0,
            "fgt1": OFFICIAL_CASEN_FGT1,
            "note": "Different policy threshold z and equivalence scale; not comparable with official PIP GMI cost.",
        }
    )

    rows: list[dict[str, Any]] = []
    for item in concepts:
        for targeting, theta in [
            ("ideal", float(official["theta_ideal"])),
            ("loaded", float(official["theta_loaded"])),
        ]:
            cost_lcu = theta * float(official["chi_gmi"]) * item["gap_lcu"]
            official_lcu = float(official[f"official_{targeting}_cost_lcu"])
            official_gdp = float(official[f"official_{targeting}_cost_gdp"])
            rows.append(
                {
                    "parameter_set_id": PARAMETER_SET_ID,
                    "country_id": "CHL",
                    "policy_id": "GMI",
                    "micro_gmi_version": f"GMI_{targeting}_microdata_{item['concept']}",
                    "baseline_gmi_version": f"GMI_{targeting}_aggregate",
                    "welfare_concept": item["concept"],
                    "welfare_variable": item["variable"],
                    "income_period_source": "monthly",
                    "annualization_factor": 12.0,
                    "primary_variant": item["primary"],
                    "policy_variant_z": item["policy_variant_z"],
                    "poverty_line_variable": item["poverty_line_variable"],
                    "poverty_line_value": item["poverty_line_value"],
                    "poverty_line_value_unit": "CLP_per_person_or_adult_equivalent_per_year",
                    "poverty_line_type": item["poverty_line_type"],
                    "poverty_line_min": item["poverty_line_min"],
                    "poverty_line_max": item["poverty_line_max"],
                    "survey_year": 2024,
                    "carried_forward_to_2024": False,
                    "chi_gmi": float(official["chi_gmi"]),
                    "theta_target": theta,
                    "expanded_population_casen": population_casen,
                    "population_official_wpp": float(official["official_population_total"]),
                    "population_difference": population_casen - float(official["official_population_total"]),
                    "fgt0_micro": item["fgt0"],
                    "fgt1_micro": item["fgt1"],
                    "pip_harmonized_headcount": float(official["official_poverty_headcount"]),
                    "pip_harmonized_gap": float(official["official_poverty_gap"]),
                    "aggregate_gap_lcu_annual": item["gap_lcu"],
                    "cost_micro_lcu": cost_lcu,
                    "cost_micro_gdp": cost_lcu / gdp,
                    "cost_official_aggregate_lcu": official_lcu,
                    "cost_official_aggregate_gdp": official_gdp,
                    "difference_lcu": cost_lcu - official_lcu,
                    "difference_gdp": cost_lcu / gdp - official_gdp,
                    "difference_percent_vs_official": 100.0 * (cost_lcu / official_lcu - 1.0),
                    "gdp_nominal_lcu_2024": gdp,
                    "source_id": "MDSF_CASEN_2024;PIP;WDI",
                    "concept_note": item["note"],
                    "robustness_flag": True,
                }
            )
    return pd.DataFrame(rows)


def build_parameter_set(
    inputs: dict[str, Any], costs: pd.DataFrame, metadata: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    values = inputs["values"].copy()
    if set(values["parameter_set_id"].dropna().unique()) != {BASELINE_PARAMETER_SET_ID}:
        raise ExtensionError("Input calibration is not exclusively baseline-official-v3")
    values["parameter_set_id"] = PARAMETER_SET_ID
    values["build_id"] = f"{PARAMETER_SET_ID}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    values["created_at"] = datetime.now(timezone.utc).isoformat()
    values["created_by_script"] = Path(__file__).name
    primary = costs[costs["primary_variant"]].set_index("baseline_gmi_version")
    changes: list[dict[str, Any]] = []
    for targeting in ("ideal", "loaded"):
        baseline_version = f"GMI_{targeting}_aggregate"
        name = f"policy_cost_gross_gdp_{baseline_version}"
        mask = values["country_id"].eq("CHL") & values["name"].eq(name)
        if int(mask.sum()) != 1:
            raise ExtensionError(f"Expected one official value-assignment row for CHL/{name}")
        old = float(values.loc[mask, "baseline_value"].iloc[0])
        new = float(primary.loc[baseline_version, "cost_micro_gdp"])
        values.loc[mask, ["baseline_value", "low_value", "high_value"]] = new
        values.loc[mask, "primary_spec_flag"] = False
        values.loc[mask, "robustness_flag"] = True
        values.loc[mask, "stress_flag"] = False
        values.loc[mask, "value_type"] = "observed_microdata_derived_cost"
        values.loc[mask, "support_type"] = "post_baseline_robustness_new_input_series"
        values.loc[mask, "source_id"] = "MDSF_CASEN_2024;PIP;WDI"
        values.loc[mask, "formula_id"] = (
            "theta_target*chi_gmi*sum(expr*numper*"
            "max(0,PIP_line_CLP_annual-12*ytotcorh/numper))/GDP_2024"
        )
        values.loc[mask, "distribution"] = "fixed"
        values.loc[mask, "audit_status"] = "registered_post_baseline_robustness"
        values.loc[mask, "notes"] = (
            "Labelled CHL GMI microdata-strong variant using CASEN 2024 raw total corrected "
            "household income and the same constant PIP PPP 8.30 line as the official aggregate cost; "
            f"source={metadata['source_url']}."
        )
        changes.append(
            {
                "parameter_set_id": PARAMETER_SET_ID,
                "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
                "country_id": "CHL",
                "name": name,
                "baseline_value_official": old,
                "robustness_value": new,
                "delta": new - old,
                "source_year": 2024,
                "target_year": 2024,
                "carried_forward_to_2024": False,
                "source_id": "MDSF_CASEN_2024;PIP;WDI",
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
            policy_cost["country_id"].eq("CHL")
            & policy_cost["policy_id"].eq("GMI")
            & policy_cost["gmi_version"].eq(version)
        )
        if int(mask.sum()) != 1:
            raise ExtensionError(f"Expected one policy-cost row for CHL/{version}")
        for column in ["policy_cost_gross_lcu", "policy_cost_net_lcu"]:
            policy_cost.loc[mask, column] = float(row["cost_micro_lcu"])
        for column in ["policy_cost_gross_gdp", "policy_cost_net_gdp"]:
            policy_cost.loc[mask, column] = float(row["cost_micro_gdp"])
        policy_cost.loc[mask, "cost_convention"] = f"labelled_{row['micro_gmi_version']}"
        policy_cost.loc[mask, "microdata_used"] = True
        policy_cost.loc[mask, "parameter_set_id"] = PARAMETER_SET_ID
    return policy_cost


def ordinal_rank(frame: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    parts = []
    for _, group in frame.groupby(["country_id", "scenario_id", "regime_id"], sort=True):
        ranked = group.sort_values([value_col, "policy_variant_id"], ascending=[False, True]).copy()
        ranked[output_col] = np.arange(1, len(ranked) + 1, dtype=int)
        parts.append(ranked)
    return pd.concat(parts, ignore_index=True)


def add_primary_five_rank(frame: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    keys = ["country_id", "policy_id", "policy_variant_id", "scenario_id", "regime_id"]
    primary = frame[~frame["gmi_version"].eq("GMI_loaded_aggregate")].copy()
    primary = ordinal_rank(primary, value_col, output_col)
    return frame.merge(primary[keys + [output_col]], on=keys, how="left", validate="one_to_one")


def build_comparison(inputs: dict[str, Any]) -> pd.DataFrame:
    baseline = pd.read_csv(ROOT / "results" / "official" / "fiscal_space_result.csv")
    baseline = baseline[baseline["xi"].eq(robustness.XI)].copy()
    if len(baseline) != 480:
        raise ExtensionError(f"Expected 480 baseline cells at xi=0.10, found {len(baseline)}")
    baseline_classes = baseline[
        ["country_id", "policy_id", "gmi_version", "country_policy_result_class"]
    ].drop_duplicates()
    variant = robustness.Variant(
        variant_id="GMI_microdata_strong_CHL_PIP_line",
        family="post_baseline_GMI_microdata_strong",
        label="CASEN 2024 raw total corrected income at the official constant PIP PPP 8.30 line",
    )
    grid, diagnostics = robustness.run_variant(ROOT, inputs, variant, baseline, baseline_classes, gap_resid={})
    if diagnostics or len(grid) != 480:
        raise ExtensionError(f"Unexpected CHL GMI-micro runner output: rows={len(grid)}, diagnostics={diagnostics}")
    baseline = ordinal_rank(baseline, "v_gross", "policy_rank_baseline")
    grid = ordinal_rank(grid, "v_gross", "policy_rank_micro")
    baseline = add_primary_five_rank(baseline, "v_gross", "primary_five_policy_rank_baseline")
    grid = add_primary_five_rank(grid, "v_gross", "primary_five_policy_rank_micro")
    keys = ["country_id", "policy_id", "policy_variant_id", "scenario_id", "regime_id"]
    base_columns = keys + [
        "gmi_version", "v_gross", "cost_gross_gdp", "crosses_v1", "crosses_v1_10",
        "debt_guardrail_pass", "cell_result_class", "country_policy_result_class",
        "historical_tax_class", "historical_tax_borderline", "historical_total_revenue_class",
        "historical_total_revenue_borderline", "policy_rank_baseline", "primary_five_policy_rank_baseline",
    ]
    variant_columns = keys + [
        "v_gross", "cost_gross_gdp", "crosses_v1", "crosses_v1_10", "debt_guardrail_pass",
        "variant_cell_result_class", "variant_country_policy_result_class", "historical_tax_class",
        "historical_tax_borderline", "historical_total_revenue_class", "historical_total_revenue_borderline",
        "policy_rank_micro", "primary_five_policy_rank_micro",
    ]
    merged = baseline[base_columns].merge(
        grid[variant_columns], on=keys, how="outer", validate="one_to_one",
        suffixes=("_baseline", "_micro"), indicator=True,
    )
    if len(merged) != 480 or not merged["_merge"].eq("both").all():
        raise ExtensionError("Baseline/CHL GMI-micro grid key matching failed")
    result = merged[merged["country_id"].eq("CHL") & merged["policy_id"].eq("GMI")].copy()
    if len(result) != 40:
        raise ExtensionError(f"Expected 40 CHL GMI cells, found {len(result)}")
    result = result.drop(columns="_merge").rename(
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
    result["micro_gmi_version"] = result["baseline_gmi_version"].map(
        {
            "GMI_ideal_aggregate": "GMI_ideal_microdata_primary_total_corrected_income",
            "GMI_loaded_aggregate": "GMI_loaded_microdata_primary_total_corrected_income",
        }
    )
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
    validation, households = validate_casen(frame)
    inputs = mc.load_inputs(ROOT)
    official = official_inputs(inputs)
    costs = build_costs(households, official)
    primary_costs = costs[costs["primary_variant"]]
    if len(primary_costs) != 2:
        raise ExtensionError(f"Expected two primary cost rows, found {len(primary_costs)}")
    if not primary_costs["poverty_line_type"].eq("constant").all():
        raise ExtensionError("Primary CHL GMI cost does not use a constant poverty line")
    if not np.allclose(
        primary_costs["poverty_line_value"].to_numpy(float),
        float(official["official_poverty_line_lcu_annual"]), rtol=0.0, atol=1e-6,
    ):
        raise ExtensionError("Primary CHL GMI cost did not use the official PIP line")
    parameter_set, parameter_changes = build_parameter_set(inputs, costs, metadata)
    variant_inputs = {
        **inputs,
        "values": parameter_set,
        "policy_cost": in_memory_policy_cost(inputs, costs),
    }
    comparison = build_comparison(variant_inputs)

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
        "primary_five_policy_rank_row_changes": int(comparison["primary_five_policy_rank_changed_flag"].sum()),
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
                    "Post-baseline robustness extension using newly declared CASEN 2024 microdata for Chile. "
                    "The official PIP aggregate GMI cost remains unchanged; the primary microdata cost uses "
                    "the same constant PIP PPP 8.30 threshold and is a labelled comparator."
                ),
                "new_input_series": True,
                "input_snapshot_id": INPUT_SNAPSHOT_ID,
                "input_snapshot_manifest_sha256": sha256_file(SNAPSHOT_MANIFEST),
                "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
                "robustness_parameter_set_id": PARAMETER_SET_ID,
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
        "source_format": "SPSS",
        "source_sha256": metadata["raw_file_hash"],
        "column_projection": metadata["column_projection"],
        "primary_spec_hash": spec_after,
        "protected_files_unchanged": True,
        "official_gmi_provenance": official,
        "validation": json.loads(validation.to_json(orient="records")),
        **counts,
        "runtime_seconds": time.perf_counter() - started,
        "commit_sha_at_run": git_value(["rev-parse", "HEAD"]),
        "git_dirty_at_run": bool(git_value(["status", "--short"])),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Only CHL GMI ideal/loaded policy costs change in memory. Primary: 12*ytotcorh/numper at the "
            "constant official PIP line. ymonecorh is a sensitivity; yae/lp is a different national policy."
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
    print("CASEN VALIDATION")
    print(outputs["validation"].to_string(index=False))
    print("\nGMI COSTS")
    print(outputs["costs"].to_string(index=False))
    print("\nRUN MANIFEST")
    print(json.dumps(outputs["manifest"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
