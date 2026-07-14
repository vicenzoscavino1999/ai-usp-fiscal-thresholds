"""Recompute committed post-baseline extension outputs without rewriting them."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import report_omega_i_sensitivity_extension as omega
from scripts import reexport_paper_tables_designed as table_export
from scripts import run_gmi_microdata_chl_robustness_extension as gmi_chl
from scripts import run_gmi_microdata_robustness_extension as gmi_per
from scripts import run_ls_raw_robustness_extension as ls_raw
from scripts import run_official_monte_carlo as mc


# These fields describe execution provenance rather than scientific content.
# Prefix matching applies only to entries ending in "*".
VOLATILE_COLUMNS = (
    "created_at*",
    "build_id",
    "runtime_seconds",
    "commit_sha_at_run",
    "git_dirty_at_run",
    "download_date",
)
ATOL = 1e-10
RTOL = 1e-8


class ExtensionVerifyError(RuntimeError):
    pass


@dataclass
class ComparisonCount:
    files: int = 0
    stable_columns: int = 0
    numeric_values: int = 0

    def add(self, other: "ComparisonCount") -> None:
        self.files += other.files
        self.stable_columns += other.stable_columns
        self.numeric_values += other.numeric_values


def is_volatile(column: str) -> bool:
    for pattern in VOLATILE_COLUMNS:
        if pattern.endswith("*") and column.startswith(pattern[:-1]):
            return True
        if column == pattern:
            return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_frame(label: str, actual: pd.DataFrame, expected_path: Path) -> ComparisonCount:
    if not expected_path.is_file():
        raise ExtensionVerifyError(f"{label}: committed output missing: {expected_path.relative_to(ROOT)}")
    expected = pd.read_csv(expected_path)
    actual = actual.copy()
    expected_columns = [column for column in expected.columns if not is_volatile(column)]
    actual_columns = [column for column in actual.columns if not is_volatile(column)]
    if expected_columns != actual_columns:
        raise ExtensionVerifyError(
            f"{label}: stable columns differ; expected={expected_columns}, actual={actual_columns}"
        )
    if len(expected) != len(actual):
        raise ExtensionVerifyError(f"{label}: row count differs; expected={len(expected)} actual={len(actual)}")

    numeric_values = 0
    for column in expected_columns:
        left = expected[column].reset_index(drop=True)
        right = actual[column].reset_index(drop=True)
        numeric = pd.api.types.is_numeric_dtype(left) and not pd.api.types.is_bool_dtype(left)
        if numeric:
            left_values = pd.to_numeric(left, errors="coerce").to_numpy(dtype=float)
            right_values = pd.to_numeric(right, errors="coerce").to_numpy(dtype=float)
            ok = np.isclose(left_values, right_values, atol=ATOL, rtol=RTOL, equal_nan=True)
            if not np.all(ok):
                row = int(np.flatnonzero(~ok)[0])
                raise ExtensionVerifyError(
                    f"{label}: numeric mismatch column={column} row={row} "
                    f"committed={left_values[row]} recomputed={right_values[row]}"
                )
            numeric_values += int(np.count_nonzero(~(np.isnan(left_values) & np.isnan(right_values))))
        else:
            left_values = left.astype("string").fillna("<NULL>")
            right_values = right.astype("string").fillna("<NULL>")
            mismatch = left_values.ne(right_values)
            if mismatch.any():
                row = int(np.flatnonzero(mismatch.to_numpy())[0])
                raise ExtensionVerifyError(
                    f"{label}: exact mismatch column={column} row={row} "
                    f"committed={left_values.iloc[row]!r} recomputed={right_values.iloc[row]!r}"
                )
    print(
        f"EXTENSION PASS {label}: rows={len(expected)} stable_columns={len(expected_columns)} "
        f"numeric_comparisons={numeric_values}"
    )
    return ComparisonCount(1, len(expected_columns), numeric_values)


def verify_omega(inputs: dict[str, object]) -> ComparisonCount:
    draw_frames, _draw_hashes = omega.load_stored_draws()
    base = {"draw_frames": draw_frames, "inputs": inputs}
    full = omega.build_full_driver_ranking(base)
    official = pd.read_csv(omega.OFFICIAL_RANKING)
    top_ten = full[full["rank_within_cell"] <= 10].reset_index(drop=True)
    top_ten = top_ten.reindex(columns=official.columns)
    compare_frame("omega_I/full_top_ten_gate", top_ten, omega.OFFICIAL_RANKING)
    full["extension_id"] = omega.EXTENSION_ID
    return compare_frame("omega_I/full_driver_ranking", full, omega.OUTPUT_RANKING)


def verify_ls_raw(inputs: dict[str, object]) -> ComparisonCount:
    latest, metadata = ls_raw.load_latest_labor_share()
    parameter_set, changes = ls_raw.build_parameter_set(inputs, latest, metadata)
    comparison = ls_raw.build_comparison({**inputs, "values": parameter_set})
    total = ComparisonCount()
    for label, frame, path in (
        ("LS-raw/parameter_set", parameter_set, ls_raw.PARAMETER_OUTPUT),
        ("LS-raw/parameter_changes", changes, ls_raw.PARAMETER_CHANGES_OUTPUT),
        ("LS-raw/class_comparison", comparison, ls_raw.COMPARISON_OUTPUT),
    ):
        total.add(compare_frame(label, frame, path))
    return total


def verify_gmi_per(inputs: dict[str, object]) -> ComparisonCount:
    frame, metadata = gmi_per.load_microdata()
    official = gmi_per.official_inputs(inputs)
    validation = gmi_per.validate_enaho(frame, official)
    costs = gmi_per.build_costs(frame, official)
    parameter_set, changes = gmi_per.build_parameter_set(inputs, costs, metadata)
    variant_inputs = {
        **inputs,
        "values": parameter_set,
        "policy_cost": gmi_per.in_memory_policy_cost(inputs, costs),
    }
    comparison = gmi_per.build_comparison(variant_inputs, costs)
    total = ComparisonCount()
    for label, output, path in (
        ("GMI-micro-PER/validation", validation, gmi_per.VALIDATION_OUTPUT),
        ("GMI-micro-PER/costs", costs, gmi_per.COST_OUTPUT),
        ("GMI-micro-PER/parameter_set", parameter_set, gmi_per.PARAMETER_OUTPUT),
        ("GMI-micro-PER/parameter_changes", changes, gmi_per.PARAMETER_CHANGES_OUTPUT),
        ("GMI-micro-PER/class_comparison", comparison, gmi_per.COMPARISON_OUTPUT),
    ):
        total.add(compare_frame(label, output, path))
    return total


def verify_gmi_chl(inputs: dict[str, object]) -> ComparisonCount:
    frame, metadata = gmi_chl.load_microdata()
    validation, households = gmi_chl.validate_casen(frame)
    official = gmi_chl.official_inputs(inputs)
    costs = gmi_chl.build_costs(households, official)
    parameter_set, changes = gmi_chl.build_parameter_set(inputs, costs, metadata)
    variant_inputs = {
        **inputs,
        "values": parameter_set,
        "policy_cost": gmi_chl.in_memory_policy_cost(inputs, costs),
    }
    comparison = gmi_chl.build_comparison(variant_inputs)
    total = ComparisonCount()
    for label, output, path in (
        ("GMI-micro-CHL/validation", validation, gmi_chl.VALIDATION_OUTPUT),
        ("GMI-micro-CHL/costs", costs, gmi_chl.COST_OUTPUT),
        ("GMI-micro-CHL/parameter_set", parameter_set, gmi_chl.PARAMETER_OUTPUT),
        ("GMI-micro-CHL/parameter_changes", changes, gmi_chl.PARAMETER_CHANGES_OUTPUT),
        ("GMI-micro-CHL/class_comparison", comparison, gmi_chl.COMPARISON_OUTPUT),
    ):
        total.add(compare_frame(label, output, path))
    return total


def verify_table_reexport() -> ComparisonCount:
    targets = tuple(
        ROOT / "paper" / "tables" / name
        for name in (
            "table1_anchors.tex",
            "table2_policy_costs.tex",
            "table3_primary_specification.tex",
            "table4_vgross_baseline.tex",
            "table5_threshold_inversion.tex",
            "table5b_time_to_threshold.tex",
            "table6_historical_plausibility.tex",
            "table7_monte_carlo.tex",
        )
    )
    def run_export() -> None:
        result = subprocess.run(
            [sys.executable, str(Path(table_export.__file__).resolve())],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ExtensionVerifyError(
                "paper-table re-export failed:\n" + result.stdout + "\n" + result.stderr
            )

    preexisting = all(path.is_file() for path in targets)
    targets[0].parent.mkdir(parents=True, exist_ok=True)
    if preexisting:
        before = {path: sha256_file(path) for path in targets}
    else:
        run_export()
        before = {path: sha256_file(path) for path in targets}
    run_export()
    after = {path: sha256_file(path) for path in targets}
    if before != after:
        changed = [path.relative_to(ROOT).as_posix() for path in targets if before[path] != after[path]]
        raise ExtensionVerifyError("paper-table re-export is not idempotent: " + ", ".join(changed))
    git_status = "not_available_hash_idempotence_used"
    if (ROOT / ".git").exists():
        diff = subprocess.run(
            ["git", "diff", "--exit-code", "--", *[path.relative_to(ROOT).as_posix() for path in targets]],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if diff.returncode != 0:
            raise ExtensionVerifyError("paper-table re-export left a tracked diff:\n" + diff.stdout)
        git_status = "empty"
    print(
        "EXTENSION PASS paper-table-reexport: "
        f"files={len(targets)} idempotent=True source={'committed_targets' if preexisting else 'fresh_two_pass'} "
        f"git_diff={git_status}"
    )
    return ComparisonCount(files=len(targets))


def enaho_restricted_input_present() -> bool:
    """ENAHO required-variables microdata (GMI-micro-PER) is author-held and not
    redistributable; the public package omits it. True only when it is present."""
    return any(gmi_per.SNAPSHOT_DIR.glob("*required_variables.parquet"))


def verify_extensions(require_restricted: bool = False) -> ComparisonCount:
    inputs = mc.load_inputs(ROOT)
    total = ComparisonCount()
    verified = 0
    for verifier in (verify_omega, verify_ls_raw, verify_gmi_chl):
        total.add(verifier(inputs))
        verified += 1
    total.add(verify_table_reexport())
    verified += 1
    # GMI-micro-PER recomputes from ENAHO microdata, which is author-held and not
    # redistributable. The public package omits it, so this extension is skipped
    # unless the input is present (or --require-restricted forces a failure).
    if enaho_restricted_input_present():
        total.add(verify_gmi_per(inputs))
        verified += 1
        enaho_status = "verified"
    elif require_restricted:
        raise ExtensionVerifyError(
            "GMI-micro-PER requires the ENAHO required-variables microdata, which is absent. "
            "Fetch it (free from INEI) with `python scripts/17_download_enaho_sumaria.py`, "
            "or run `make reproduce-public` to skip this restricted extension."
        )
    else:
        enaho_status = "skipped"
        print(
            "EXTENSION SKIPPED (restricted, non-redistributable input absent): GMI-micro-PER "
            "-- ENAHO microdata is author-held; fetch with `python scripts/17_download_enaho_sumaria.py` "
            "then `make reproduce-restricted` to include it."
        )
    print("VOLATILE COLUMNS EXCLUDED: " + ", ".join(VOLATILE_COLUMNS))
    print(
        f"EXTENSIONS VERIFY PASS: {verified} extensions verified (GMI-micro-PER {enaho_status}), "
        f"{total.files} committed files, "
        f"{total.stable_columns} stable columns, {total.numeric_values} numeric comparisons"
    )
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-restricted",
        action="store_true",
        help="Fail if the restricted, author-held ENAHO extension input is absent "
        "(default: skip it and pass on the public extensions).",
    )
    args = parser.parse_args()
    try:
        verify_extensions(require_restricted=args.require_restricted)
    except (ExtensionVerifyError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"EXTENSIONS VERIFY FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
