"""Post-baseline omega_I sensitivity reporting extension.

The extension reads the frozen official Monte Carlo draw tables and reuses the
official driver-ranking machinery. It does not generate Monte Carlo draws or
modify calibration, model mechanics, official results, or classifications.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_official_monte_carlo as mc


EXTENSION_ID = "OMEGA_I_REPORTING_EXTENSION_2026_07_10"
EXTENSION_RUN_ID = "official_4c_omega_i_reporting_extension_baseline_official_v3"
EXPECTED_PRIMARY_SPEC_HASH = "0080d502a50db430998b56ebc6419ee181c90a1331cd2b650bb25db298523f81"
OFFICIAL_RANKING = ROOT / "reports" / "driver_ranking_baseline-official-v3.csv"
OUTPUT_RANKING = ROOT / "reports" / "driver_ranking_full_omega_i_extension_baseline-official-v3.csv"
AMENDMENT_REGISTRY = ROOT / "reports" / "omega_i_reporting_extension_amendment_registry_baseline-official-v3.csv"
DRAW_DIR = ROOT / "results" / "official" / "draws"
DRAW_FILES = (
    "global_scenario_draw.parquet",
    "country_scenario_draw.parquet",
    "policy_cost_draw.parquet",
    "fiscal_conversion_draw.parquet",
    "draw_parameter_value.parquet",
)
PROTECTED_FILES = (
    ROOT / "reports" / "driver_ranking_baseline-official-v3.csv",
    ROOT / "reports" / "monte_carlo_result_baseline-official-v3.csv",
    ROOT / "reports" / "country_policy_classification_final_baseline-official-v3.csv",
    ROOT / "reports" / "fiscal_space_result_baseline-official-v2.csv",
    ROOT / "results" / "official" / "driver_ranking.csv",
    ROOT / "results" / "official" / "monte_carlo_result.csv",
    ROOT / "results" / "official" / "country_policy_classification_final.csv",
    ROOT / "results" / "official" / "fiscal_space_result.csv",
    ROOT / "reproducibility" / "reference" / "driver_ranking.csv",
)


class ExtensionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def primary_spec_hash_status() -> dict[str, str]:
    hash_file = ROOT / "PRIMARY_SPEC_HASH.txt"
    plan_file = ROOT / "02_ESD_AI_USP_v6.md"
    declared = None
    for line in hash_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("sha256:"):
            declared = line.split(":", 1)[1].strip()
            break
    actual = sha256_file(plan_file)
    status = "PASS" if actual == declared == EXPECTED_PRIMARY_SPEC_HASH else "FAIL"
    return {
        "status": status,
        "actual": actual,
        "declared": declared or "missing",
        "expected": EXPECTED_PRIMARY_SPEC_HASH,
    }


def hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in paths
        if path.exists()
    }


def load_stored_draws() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    paths = tuple(DRAW_DIR / name for name in DRAW_FILES)
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise ExtensionError("Missing frozen draw files: " + ", ".join(missing))
    draw_hashes = hashes(paths)
    fiscal = pd.read_parquet(
        DRAW_DIR / "fiscal_conversion_draw.parquet",
        columns=[
            "run_id",
            "mc_mode",
            "draw_id",
            "country_id",
            "policy_id",
            "policy_variant_id",
            "scenario_id",
            "regime_id",
            "v_gross",
            "parameter_set_id",
            "dataset_version",
        ],
    )
    parameters = pd.read_parquet(
        DRAW_DIR / "draw_parameter_value.parquet",
        columns=[
            "run_id",
            "mc_mode",
            "draw_id",
            "parameter_name",
            "country_id",
            "scenario_id",
            "policy_id",
            "regime_id",
            "parameter_value",
            "drawn_flag",
            "parameter_set_id",
            "dataset_version",
        ],
    )
    for name, frame in {"fiscal_conversion_draw": fiscal, "draw_parameter_value": parameters}.items():
        if set(frame["run_id"].dropna().unique()) != {mc.RUN_ID}:
            raise ExtensionError(f"{name} does not contain only the official run {mc.RUN_ID}")
        if set(frame["mc_mode"].dropna().unique()) != {mc.MC_MODE}:
            raise ExtensionError(f"{name} does not contain only {mc.MC_MODE}")
        if set(frame["parameter_set_id"].dropna().unique()) != {mc.PARAMETER_SET_ID}:
            raise ExtensionError(f"{name} parameter_set_id mismatch")
        if set(frame["dataset_version"].dropna().unique()) != {mc.DATASET_VERSION}:
            raise ExtensionError(f"{name} dataset_version mismatch")
    omega = parameters[parameters["parameter_name"].eq("omega_I") & parameters["drawn_flag"].astype(bool)]
    counts = omega.groupby("country_id")["draw_id"].nunique().to_dict()
    if counts != {"CHL": 5000, "COL": 5000, "MEX": 5000, "PER": 5000}:
        raise ExtensionError(f"omega_I stored-draw coverage mismatch: {counts}")
    return {
        "fiscal_conversion_draw": fiscal,
        "draw_parameter_value": parameters,
    }, draw_hashes


def max_numeric_difference(expected: pd.DataFrame, actual: pd.DataFrame) -> float:
    numeric = [col for col in expected.columns if pd.api.types.is_numeric_dtype(expected[col])]
    if not numeric:
        return 0.0
    differences = []
    for col in numeric:
        left = pd.to_numeric(expected[col], errors="coerce")
        right = pd.to_numeric(actual[col], errors="coerce")
        both_nan = left.isna() & right.isna()
        differences.append((left - right).abs().mask(both_nan, 0.0).max())
    return float(np.nanmax(differences))


def validate_official_ranking(base: dict[str, Any]) -> dict[str, Any]:
    expected = pd.read_csv(OFFICIAL_RANKING)
    reproduced = mc.build_driver_ranking(base)
    if list(expected.columns) != list(reproduced.columns):
        raise ExtensionError("Official ranking column mismatch")
    expected_bytes = OFFICIAL_RANKING.read_bytes()
    reproduced_bytes = reproduced.to_csv(index=False).encode("utf-8")
    expected_sha = hashlib.sha256(expected_bytes).hexdigest()
    reproduced_sha = hashlib.sha256(reproduced_bytes).hexdigest()
    max_abs_diff = max_numeric_difference(expected, reproduced)
    exact = expected_bytes == reproduced_bytes
    if not exact:
        raise ExtensionError(
            "Official ranking reproduction gate failed: "
            f"expected_sha256={expected_sha}, reproduced_sha256={reproduced_sha}, "
            f"max_abs_diff={max_abs_diff:.17g}"
        )
    return {
        "expected": expected,
        "reproduced": reproduced,
        "exact": exact,
        "expected_sha256": expected_sha,
        "reproduced_sha256": reproduced_sha,
        "max_abs_diff_after_csv_read": max_abs_diff,
    }


def build_full_driver_ranking(base: dict[str, Any]) -> pd.DataFrame:
    fiscal = base["draw_frames"]["fiscal_conversion_draw"]
    parameters = base["draw_frames"]["draw_parameter_value"]
    parameters = parameters[parameters["drawn_flag"].astype(bool)].copy()
    rows: list[dict[str, Any]] = []
    for cell_key in sorted(mc.HEADLINE_COMPARISON_CELLS):
        country, policy_variant_id, scenario, regime = cell_key
        cell = fiscal[
            fiscal["country_id"].eq(country)
            & fiscal["policy_variant_id"].eq(policy_variant_id)
            & fiscal["scenario_id"].eq(scenario)
            & fiscal["regime_id"].eq(regime)
        ][["draw_id", "v_gross", "policy_id"]].copy()
        if cell.empty:
            raise ExtensionError(f"Missing stored V draws for headline cell {cell_key}")
        policy_id = str(cell["policy_id"].iloc[0])
        applicable = parameters[
            parameters.apply(
                lambda row: mc.parameter_scope_applies(
                    row,
                    country=country,
                    policy_id=policy_id,
                    scenario=scenario,
                    regime=regime,
                ),
                axis=1,
            )
        ]
        grouped = applicable.groupby(
            ["parameter_name", "country_id", "scenario_id", "policy_id", "regime_id"],
            dropna=False,
        )
        for scope, group in grouped:
            merged = cell.merge(group[["draw_id", "parameter_value"]], on="draw_id", how="inner")
            if len(merged) < 10 or merged["parameter_value"].nunique() < 3:
                continue
            spearman = float(merged["parameter_value"].corr(merged["v_gross"], method="spearman"))
            if not np.isfinite(spearman):
                continue
            p10 = float(np.nanpercentile(merged["parameter_value"], 10))
            p90 = float(np.nanpercentile(merged["parameter_value"], 90))
            record = group.iloc[0]
            value_key = mc.value_key_from_parameter_record(record)
            try:
                v_p10 = mc.compute_cell_v_with_override(
                    inputs=base["inputs"],
                    country=country,
                    scenario=scenario,
                    regime=regime,
                    policy_variant_id=policy_variant_id,
                    key=value_key,
                    value=p10,
                )
                v_p90 = mc.compute_cell_v_with_override(
                    inputs=base["inputs"],
                    country=country,
                    scenario=scenario,
                    regime=regime,
                    policy_variant_id=policy_variant_id,
                    key=value_key,
                    value=p90,
                )
                tornado_range = abs(v_p90 - v_p10)
            except Exception:
                v_p10 = np.nan
                v_p90 = np.nan
                tornado_range = np.nan
            rows.append(
                {
                    "run_id": mc.RUN_ID,
                    "country_id": country,
                    "policy_variant_id": policy_variant_id,
                    "scenario_id": scenario,
                    "regime_id": regime,
                    "parameter_name": scope[0],
                    "parameter_country_id": None if pd.isna(scope[1]) else scope[1],
                    "parameter_scenario_id": None if pd.isna(scope[2]) else scope[2],
                    "parameter_policy_id": None if pd.isna(scope[3]) else scope[3],
                    "parameter_regime_id": None if pd.isna(scope[4]) else scope[4],
                    "spearman_rho_with_v_gross": spearman,
                    "abs_spearman_rho": abs(spearman),
                    "parameter_p10": p10,
                    "parameter_p90": p90,
                    "v_gross_at_parameter_p10_others_central": v_p10,
                    "v_gross_at_parameter_p90_others_central": v_p90,
                    "tornado_abs_range": tornado_range,
                    "parameter_set_id": mc.PARAMETER_SET_ID,
                    "dataset_version": mc.DATASET_VERSION,
                }
            )
    ranking = pd.DataFrame(rows)
    if ranking.empty:
        raise ExtensionError("Full driver ranking is empty")
    ranking["rank_within_cell"] = (
        ranking.sort_values(
            ["country_id", "policy_variant_id", "scenario_id", "regime_id", "abs_spearman_rho"],
            ascending=[True, True, True, True, False],
        )
        .groupby(["country_id", "policy_variant_id", "scenario_id", "regime_id"])
        .cumcount()
        + 1
    )
    return ranking.sort_values(
        ["country_id", "policy_variant_id", "scenario_id", "regime_id", "rank_within_cell"]
    ).reset_index(drop=True)


def validate_full_top_ten(full: pd.DataFrame, official: pd.DataFrame) -> None:
    top_ten = full[full["rank_within_cell"] <= 10].reset_index(drop=True)
    top_ten = top_ten.reindex(columns=official.columns)
    if top_ten.to_csv(index=False).encode("utf-8") != OFFICIAL_RANKING.read_bytes():
        raise ExtensionError("Full-ranking top ten does not reproduce the official ranking")


def amendment_row(
    *,
    validation: dict[str, Any],
    full: pd.DataFrame,
    primary: dict[str, str],
    draw_hashes: dict[str, str],
    protected_before: dict[str, str],
    protected_after: dict[str, str],
    output_sha256: str,
) -> pd.DataFrame:
    omega_rows = full[full["parameter_name"].eq("omega_I")]
    return pd.DataFrame(
        [
            {
                "run_id": EXTENSION_RUN_ID,
                "amendment_id": EXTENSION_ID,
                "amendment_text": (
                    "Post-baseline reporting extension derived from frozen official Monte Carlo draws; "
                    "no new calibrated parameter, Monte Carlo draw, model result, or classification was introduced or altered."
                ),
                "extension_type": "post_baseline_reporting_extension",
                "source_run_id": mc.RUN_ID,
                "draw_source": "results/official/draws/*.parquet",
                "draw_source_mode": "stored_official_draws_only",
                "new_mc_draws_generated": False,
                "calibration_changed": False,
                "engine_changed": False,
                "official_results_changed": False,
                "classification_changed": False,
                "validation_status": "PASS" if validation["exact"] else "FAIL",
                "validation_exact_csv_match": bool(validation["exact"]),
                "validation_official_rows": int(len(validation["expected"])),
                "validation_reproduced_rows": int(len(validation["reproduced"])),
                "validation_max_abs_diff_after_csv_read": validation["max_abs_diff_after_csv_read"],
                "official_driver_sha256": validation["expected_sha256"],
                "reproduced_driver_sha256": validation["reproduced_sha256"],
                "full_ranking_rows": int(len(full)),
                "headline_cell_count": int(
                    full.groupby(["country_id", "policy_variant_id", "scenario_id", "regime_id"]).ngroups
                ),
                "omega_i_row_count": int(len(omega_rows)),
                "primary_spec_hash_status": primary["status"],
                "primary_spec_hash_actual": primary["actual"],
                "primary_spec_hash_declared": primary["declared"],
                "primary_spec_hash_expected": primary["expected"],
                "draw_file_hashes_json": json.dumps(draw_hashes, sort_keys=True),
                "protected_file_hashes_before_json": json.dumps(protected_before, sort_keys=True),
                "protected_file_hashes_after_json": json.dumps(protected_after, sort_keys=True),
                "protected_files_unchanged": protected_before == protected_after,
                "extension_output_sha256": output_sha256,
                "parameter_set_id": mc.PARAMETER_SET_ID,
                "dataset_version": mc.DATASET_VERSION,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def run_extension(*, validate_only: bool = False) -> dict[str, Any]:
    primary = primary_spec_hash_status()
    if primary["status"] != "PASS":
        raise ExtensionError(f"PRIMARY_SPEC_HASH mismatch: {primary}")
    protected_before = hashes(PROTECTED_FILES)
    draw_frames, draw_hashes = load_stored_draws()
    base = {"draw_frames": draw_frames, "inputs": mc.load_inputs(ROOT)}
    validation = validate_official_ranking(base)
    if validate_only:
        return {
            "status": "PASS",
            "validation_exact_csv_match": True,
            "validation_rows": len(validation["expected"]),
            "official_driver_sha256": validation["expected_sha256"],
            "reproduced_driver_sha256": validation["reproduced_sha256"],
            "primary_spec_hash": primary["actual"],
        }
    full = build_full_driver_ranking(base)
    validate_full_top_ten(full, validation["expected"])
    omega_rows = full[full["parameter_name"].eq("omega_I")]
    if len(omega_rows) != len(mc.HEADLINE_COMPARISON_CELLS):
        raise ExtensionError(f"Expected one omega_I row per headline cell, found {len(omega_rows)}")
    output = full.copy()
    output["extension_id"] = EXTENSION_ID
    output.to_csv(OUTPUT_RANKING, index=False)
    output_sha256 = sha256_file(OUTPUT_RANKING)
    protected_after = hashes(PROTECTED_FILES)
    if protected_before != protected_after:
        OUTPUT_RANKING.unlink(missing_ok=True)
        raise ExtensionError("A protected official file changed during the extension")
    registry = amendment_row(
        validation=validation,
        full=full,
        primary=primary,
        draw_hashes=draw_hashes,
        protected_before=protected_before,
        protected_after=protected_after,
        output_sha256=output_sha256,
    )
    registry.to_csv(AMENDMENT_REGISTRY, index=False)
    return {
        "status": "PASS",
        "extension_id": EXTENSION_ID,
        "validation_exact_csv_match": True,
        "validation_rows": len(validation["expected"]),
        "official_driver_sha256": validation["expected_sha256"],
        "full_ranking_rows": len(output),
        "headline_cell_count": output.groupby(
            ["country_id", "policy_variant_id", "scenario_id", "regime_id"]
        ).ngroups,
        "omega_i_row_count": len(omega_rows),
        "primary_spec_hash": primary["actual"],
        "protected_files_unchanged": True,
        "output": OUTPUT_RANKING.relative_to(ROOT).as_posix(),
        "amendment_registry": AMENDMENT_REGISTRY.relative_to(ROOT).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    result = run_extension(validate_only=args.validate_only)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
