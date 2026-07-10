"""Post-baseline deterministic robustness extension for raw labor shares.

This runner swaps only the fiscal labor-share chain in an in-memory copy of
baseline-official-v3. Official calibration, DuckDB tables, engine mechanics,
results, classifications, and the primary-specification hash remain untouched.
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


RUN_ID = "official_4c_lsraw_robustness_extension_baseline_official_v3"
EXTENSION_ID = "LS_RAW_VS_ADJUSTED_ROBUSTNESS_EXTENSION_2026_07_10"
EXTENSION_TYPE = "post_baseline_robustness_extension_new_input_series"
PARAMETER_SET_ID = "robustness-lsraw-v1"
BASELINE_PARAMETER_SET_ID = "baseline-official-v3"
BASELINE_DATASET_VERSION = "v1.0.1-official-4c"
INPUT_SNAPSHOT_ID = "robustness-lsraw-v1"
EXPECTED_PRIMARY_SPEC_HASH = "0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81"
SNAPSHOT_DIR = ROOT / "data" / "raw_snapshots" / INPUT_SNAPSHOT_ID / "un_sna_labor_share"
SNAPSHOT_MANIFEST = ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{INPUT_SNAPSHOT_ID}.json"
PARAMETER_OUTPUT = ROOT / "reports" / f"value_assignment_table_{PARAMETER_SET_ID}.csv"
PARAMETER_CHANGES_OUTPUT = ROOT / "reports" / f"value_assignment_changes_{BASELINE_PARAMETER_SET_ID}_to_{PARAMETER_SET_ID}.csv"
COMPARISON_OUTPUT = ROOT / "reports" / "robustness_lsraw_class_changes_baseline-official-v3.csv"
AMENDMENT_OUTPUT = ROOT / "reports" / "lsraw_robustness_amendment_registry_baseline-official-v3.csv"
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
    ROOT / "reproducibility" / "reference" / "fiscal_space_result.csv",
    ROOT / "reproducibility" / "reference" / "country_policy_classification_final.csv",
    ROOT / "paper" / "main.tex",
)
CHANGED_PARAMETER_NAMES = (
    "labor_share",
    "LS_labor_share",
    "tau_L_eff",
    "tau_K_eff",
    "tau_L_disp",
    "tau_K_disp",
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
    status = "PASS" if actual == declared == EXPECTED_PRIMARY_SPEC_HASH else "FAIL"
    return {"status": status, "actual": actual, "declared": declared or "missing"}


def load_latest_labor_share() -> tuple[pd.DataFrame, dict[str, Any]]:
    parquet = SNAPSHOT_DIR / "un_sna_labor_share_raw.parquet"
    metadata_path = SNAPSHOT_DIR / "metadata.json"
    missing = [str(path) for path in (parquet, metadata_path, SNAPSHOT_MANIFEST) if not path.exists()]
    if missing:
        raise ExtensionError("Run scripts/16_download_un_sna_labor_share.py first; missing: " + ", ".join(missing))
    frame = pd.read_parquet(parquet)
    latest = frame[frame["is_latest_available"].astype(bool)].copy()
    if set(latest["country_id"]) != set(mc.COUNTRIES) or len(latest) != len(mc.COUNTRIES):
        raise ExtensionError("UN SNA latest-value coverage is not exactly the four official countries")
    if not latest["labor_share_raw"].between(0.0, 1.0).all():
        raise ExtensionError("UN SNA raw labor shares are outside [0,1]")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_hash = metadata["download_file_hashes"][parquet.name]
    if sha256_file(parquet) != expected_hash:
        raise ExtensionError("UN SNA normalized parquet hash mismatch")
    return latest, metadata


def build_parameter_set(inputs: dict[str, Any], latest: pd.DataFrame, metadata: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    values = inputs["values"].copy()
    if set(values["parameter_set_id"].dropna().unique()) != {BASELINE_PARAMETER_SET_ID}:
        raise ExtensionError("Input calibration is not exclusively baseline-official-v3")
    values["parameter_set_id"] = PARAMETER_SET_ID
    build_id = f"{PARAMETER_SET_ID}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    values["build_id"] = build_id
    values["created_at"] = datetime.now(timezone.utc).isoformat()
    values["created_by_script"] = Path(__file__).name
    fiscal = inputs["fiscal_anchor"]
    fiscal = fiscal[fiscal["year"].eq(2024)].set_index("country_id")
    latest_by_country = latest.set_index("country_id")
    changes: list[dict[str, Any]] = []

    for country in mc.COUNTRIES:
        raw = latest_by_country.loc[country]
        ls_raw = float(raw["labor_share_raw"])
        revenue = fiscal.loc[country]
        tau_l = ((float(revenue["pit_gdp"]) + float(revenue["social_contrib_gdp"])) / 100.0) / ls_raw
        tau_k = (float(revenue["cit_gdp"]) / 100.0) / (1.0 - ls_raw)
        replacements = {
            "labor_share": ls_raw,
            "LS_labor_share": ls_raw,
            "tau_L_eff": tau_l,
            "tau_K_eff": tau_k,
            "tau_L_disp": tau_l,
            "tau_K_disp": tau_k,
        }
        for name, new_value in replacements.items():
            mask = values["name"].eq(name) & values["country_id"].eq(country)
            if int(mask.sum()) != 1:
                raise ExtensionError(f"Expected one {name} row for {country}, found {int(mask.sum())}")
            old_value = float(inputs["values"].loc[mask, "baseline_value"].iloc[0])
            values.loc[mask, ["baseline_value", "low_value", "high_value"]] = new_value
            values.loc[mask, "primary_spec_flag"] = False
            values.loc[mask, "robustness_flag"] = True
            values.loc[mask, "stress_flag"] = False
            values.loc[mask, "audit_status"] = "registered_post_baseline_robustness"
            values.loc[mask, "distribution"] = "fixed"
            values.loc[mask, "support_type"] = "post_baseline_robustness_new_input_series"
            if "labor_share" in name.lower():
                values.loc[mask, "value_type"] = "observed"
                values.loc[mask, "unit"] = "share"
                values.loc[mask, "source_id"] = "UN_SNA_TABLE_4_1_GROUP401;UN_SNA_GROUP101"
                values.loc[mask, "formula_id"] = "D1_compensation_of_employees/group101_GDP_market_prices"
            else:
                values.loc[mask, "value_type"] = "derived_parameter"
                values.loc[mask, "unit"] = "effective_tax_rate"
                values.loc[mask, "source_id"] = "OECD_REVSTAT_LAC;UN_SNA_TABLE_4_1_GROUP401;UN_SNA_GROUP101"
                values.loc[mask, "formula_id"] = (
                    "(PIT_GDP+social_contrib_GDP)/LS_raw" if "L_" in name else "CIT_GDP/(1-LS_raw)"
                )
            note = (
                "Raw compensation-of-employees share, no mixed-income adjustment; "
                f"source_year={int(raw['source_year'])}, carried_forward_to_2024={bool(raw['carried_forward_to_2024'])}; "
                f"CoE endpoint={raw['coe_endpoint']}; GDP endpoint={raw['gdp_endpoint']}; "
                f"national cross-check: {raw['national_cross_check_note']}; difference vs PWT labsh combines "
                "mixed-income adjustment with year/revision/methodology differences. "
                "Shocks, including kappa_LP_to_Y_high, remain frozen at baseline by extension design."
            )
            values.loc[mask, "notes"] = note
            changes.append(
                {
                    "parameter_set_id": PARAMETER_SET_ID,
                    "baseline_parameter_set_id": BASELINE_PARAMETER_SET_ID,
                    "country_id": country,
                    "name": name,
                    "baseline_value_official": old_value,
                    "robustness_value": new_value,
                    "delta": new_value - old_value,
                    "source_year": int(raw["source_year"]),
                    "target_year": 2024,
                    "carried_forward_to_2024": bool(raw["carried_forward_to_2024"]),
                    "source_id": values.loc[mask, "source_id"].iloc[0],
                    "source_endpoint_coe": raw["coe_endpoint"],
                    "source_endpoint_gdp": raw["gdp_endpoint"],
                    "download_date": metadata["download_date"],
                    "formula_id": values.loc[mask, "formula_id"].iloc[0],
                    "robustness_flag": True,
                    "notes": note,
                }
            )
    return values, pd.DataFrame(changes)


def ordinal_rank(frame: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    key = ["country_id", "scenario_id", "regime_id"]
    ranked_parts = []
    for _, group in frame.groupby(key, sort=True):
        ranked = group.sort_values([value_col, "policy_variant_id"], ascending=[False, True]).copy()
        ranked[output_col] = np.arange(1, len(ranked) + 1, dtype=int)
        ranked_parts.append(ranked)
    return pd.concat(ranked_parts, ignore_index=True)


def build_comparison(inputs: dict[str, Any]) -> pd.DataFrame:
    baseline = pd.read_csv(ROOT / "results" / "official" / "fiscal_space_result.csv")
    baseline = baseline[baseline["xi"].eq(robustness.XI)].copy()
    if len(baseline) != 480:
        raise ExtensionError(f"Expected 480 official baseline cells at xi=0.10, found {len(baseline)}")
    baseline_classes = baseline[
        ["country_id", "policy_id", "gmi_version", "country_policy_result_class"]
    ].drop_duplicates()
    variant = robustness.Variant(
        variant_id="LS_raw_vs_adjusted",
        family="post_baseline_LS_raw_vs_adjusted",
        label="UN SNA raw compensation-of-employees share; no mixed-income adjustment",
    )
    raw_grid, diagnostics = robustness.run_variant(
        ROOT,
        inputs,
        variant,
        baseline,
        baseline_classes,
        gap_resid={},
    )
    if diagnostics or len(raw_grid) != 480:
        raise ExtensionError(f"Unexpected LS-raw runner output: rows={len(raw_grid)}, diagnostics={diagnostics}")

    merge_keys = ["country_id", "policy_id", "policy_variant_id", "scenario_id", "regime_id"]
    baseline = ordinal_rank(baseline, "v_gross", "policy_rank_baseline")
    raw_grid = ordinal_rank(raw_grid, "v_gross", "policy_rank_lsraw")
    base_cols = merge_keys + [
        "gmi_version",
        "v_gross",
        "cell_result_class",
        "country_policy_result_class",
        "historical_tax_class",
        "historical_tax_borderline",
        "historical_total_revenue_class",
        "historical_total_revenue_borderline",
        "policy_rank_baseline",
    ]
    raw_cols = merge_keys + [
        "v_gross",
        "variant_cell_result_class",
        "variant_country_policy_result_class",
        "historical_tax_class",
        "historical_tax_borderline",
        "historical_total_revenue_class",
        "historical_total_revenue_borderline",
        "policy_rank_lsraw",
    ]
    result = baseline[base_cols].merge(
        raw_grid[raw_cols],
        on=merge_keys,
        how="outer",
        validate="one_to_one",
        suffixes=("_baseline", "_lsraw"),
        indicator=True,
    )
    if len(result) != 480 or not result["_merge"].eq("both").all():
        raise ExtensionError("Baseline/LS-raw grid key matching failed")
    result = result.drop(columns="_merge")
    result = result.rename(
        columns={
            "v_gross_baseline": "v_baseline",
            "v_gross_lsraw": "v_lsraw",
            "cell_result_class": "baseline_cell_result_class",
            "variant_cell_result_class": "lsraw_cell_result_class",
            "country_policy_result_class": "baseline_country_policy_result_class",
            "variant_country_policy_result_class": "lsraw_country_policy_result_class",
        }
    )
    result["delta_v"] = result["v_lsraw"] - result["v_baseline"]
    result["class_changed_flag"] = result["baseline_cell_result_class"] != result["lsraw_cell_result_class"]
    result["country_policy_class_changed_flag"] = (
        result["baseline_country_policy_result_class"] != result["lsraw_country_policy_result_class"]
    )
    result["policy_rank_changed_flag"] = result["policy_rank_baseline"] != result["policy_rank_lsraw"]
    result.insert(0, "extension_id", EXTENSION_ID)
    result.insert(0, "run_id", RUN_ID)
    result["run_type"] = "robustness"
    result["extension_type"] = EXTENSION_TYPE
    result["parameter_set_id"] = PARAMETER_SET_ID
    result["baseline_parameter_set_id"] = BASELINE_PARAMETER_SET_ID
    result["baseline_dataset_version"] = BASELINE_DATASET_VERSION
    result["extension_input_snapshot_id"] = INPUT_SNAPSHOT_ID
    return result.sort_values(merge_keys).reset_index(drop=True)


def git_value(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_outputs() -> dict[str, Any]:
    started = time.perf_counter()
    spec = primary_spec_hash_status()
    if spec["status"] != "PASS":
        raise ExtensionError(f"PRIMARY_SPEC_HASH gate failed: {spec}")
    protected_before = file_hashes(PROTECTED_FILES)
    latest, metadata = load_latest_labor_share()
    inputs = mc.load_inputs(ROOT)
    parameter_set, parameter_changes = build_parameter_set(inputs, latest, metadata)
    inputs = {**inputs, "values": parameter_set}
    comparison = build_comparison(inputs)

    PARAMETER_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    parameter_set.to_csv(PARAMETER_OUTPUT, index=False)
    parameter_changes.to_csv(PARAMETER_CHANGES_OUTPUT, index=False)
    comparison.to_csv(COMPARISON_OUTPUT, index=False)

    protected_after = file_hashes(PROTECTED_FILES)
    protected_unchanged = protected_before == protected_after
    if not protected_unchanged:
        changed = [key for key in protected_before if protected_before[key] != protected_after.get(key)]
        raise ExtensionError(f"Protected official files changed: {changed}")
    spec_after = primary_spec_hash_status()
    if spec_after != spec:
        raise ExtensionError("PRIMARY_SPEC_HASH status changed during the extension")

    class_changes = int(comparison["class_changed_flag"].sum())
    country_policy_class_changes = int(comparison["country_policy_class_changed_flag"].sum())
    rank_changes = int(comparison["policy_rank_changed_flag"].sum())
    amendment = pd.DataFrame(
        [
            {
                "run_id": RUN_ID,
                "amendment_id": EXTENSION_ID,
                "extension_type": EXTENSION_TYPE,
                "amendment_text": (
                    "Post-baseline robustness extension using a newly declared UN SNA raw labor-share input; "
                    "baseline calibration, certified engine, official results, official classifications, and "
                    "PRIMARY_SPEC_HASH remain unchanged."
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
                "protected_files_unchanged": protected_unchanged,
                "parameter_set_sha256": sha256_file(PARAMETER_OUTPUT),
                "parameter_changes_sha256": sha256_file(PARAMETER_CHANGES_OUTPUT),
                "comparison_output_sha256": sha256_file(COMPARISON_OUTPUT),
                "comparison_rows": len(comparison),
                "cell_class_changes": class_changes,
                "country_policy_class_changes": country_policy_class_changes,
                "policy_rank_row_changes": rank_changes,
                "source_download_date": metadata["download_date"],
                "source_endpoints_json": json.dumps(metadata["query_or_endpoint"]),
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
        "protected_files_unchanged": protected_unchanged,
        "comparison_rows": len(comparison),
        "cell_class_changes": class_changes,
        "country_policy_class_changes": country_policy_class_changes,
        "policy_rank_row_changes": rank_changes,
        "runtime_seconds": time.perf_counter() - started,
        "commit_sha_at_run": git_value(["rev-parse", "HEAD"]),
        "git_dirty_at_run": bool(git_value(["status", "--short"])),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Only the fiscal LS chain changes: LS_labor_share, tau_L_eff, tau_K_eff, tau_L_disp, "
            "and tau_K_disp. Adoption, shocks (including the high-scenario LP bridge), costs, and ceilings "
            "remain identical to baseline-official-v3."
        ),
    }
    MANIFEST_OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"manifest": manifest, "latest": latest, "parameter_changes": parameter_changes, "comparison": comparison}


def main() -> int:
    outputs = write_outputs()
    print(json.dumps(outputs["manifest"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
