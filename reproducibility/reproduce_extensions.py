"""Run all five registered post-baseline extensions with explicit prerequisites."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AUTHOR_HELD_COMMON = (
    "db/ai_usp_threshold.duckdb",
    "results/official/fiscal_space_result.csv",
    "results/official/country_policy_classification_final.csv",
)
OMEGA_DRAWS = tuple(
    f"results/official/draws/{name}.parquet"
    for name in (
        "country_scenario_draw",
        "draw_parameter_value",
        "fiscal_conversion_draw",
        "global_scenario_draw",
        "policy_cost_draw",
    )
)


def run(script: str) -> None:
    print(f"RUN {script}", flush=True)
    subprocess.run([sys.executable, script], cwd=ROOT, check=True)


def main() -> int:
    print("PREREQUISITE omega_I: author-held results/official/draws/*.parquet plus common db/results inputs")
    print("PREREQUISITE LS-raw: public UN SNA download with recorded hashes plus common db/results inputs")
    print("PREREQUISITE GMI-micro-PER-v2: public ENAHO 2024 download with recorded hash plus common db/results inputs")
    print("PREREQUISITE GMI-micro-CHL: public CASEN 2024 download with recorded hash plus common db/results inputs")
    print("PREREQUISITE paper-table re-export: tracked report CSVs only")

    required = (*AUTHOR_HELD_COMMON, *OMEGA_DRAWS)
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        print("REPRODUCE EXTENSIONS BLOCKED: required author-held inputs are absent:", file=sys.stderr)
        for relative in missing:
            print(f"  - {relative}", file=sys.stderr)
        print(
            "Restore the author's frozen db/results folders; they are intentionally not tracked by Git.",
            file=sys.stderr,
        )
        return 2

    try:
        run("scripts/16_download_un_sna_labor_share.py")
        run("scripts/run_ls_raw_robustness_extension.py")
        run("scripts/17_download_enaho_sumaria.py")
        run("scripts/run_gmi_microdata_robustness_extension.py")
        run("scripts/18_download_casen_2024.py")
        run("scripts/run_gmi_microdata_chl_robustness_extension.py")
        run("scripts/report_omega_i_sensitivity_extension.py")
        run("scripts/reexport_paper_tables_designed.py")
    except subprocess.CalledProcessError as exc:
        print(f"REPRODUCE EXTENSIONS FAIL: {exc.cmd} exited {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    print("REPRODUCE EXTENSIONS PASS: 5 extensions completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
