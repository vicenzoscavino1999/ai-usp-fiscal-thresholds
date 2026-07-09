"""Materialize baseline-official-v3 measurement-uncertainty amendment.

Etapa 5B-R registers the author's third signature from 2026-07-09. The
deterministic engine is not touched. This script clones baseline-official-v2
and changes only the measurement-uncertainty treatment for the institutional
Theta_channel primitives A, Gap, and I.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


DATASET_VERSION = "v1.0.1-official-4c"
V2 = "baseline-official-v2"
V3 = "baseline-official-v3"
AUTHOR_DATE = "2026-07-09"
AUTHOR_NOTE = (
    "cumplimiento del vector Theta_channel del paper; incertidumbre de "
    "medicion informada por literatura"
)
SCRIPT_NAME = Path(__file__).name
MEASUREMENT_RULES = {
    "A_aipi_total": {
        "half_width": 0.05,
        "source_id": "Saisana_Saltelli_Tarantola_2005_JRSSA;Hoyland_Moene_Willumsen_2012_JDE",
        "note": (
            "A: incertidumbre de puntajes de indices compuestos. La literatura "
            "ancla la existencia y el orden de magnitud de la incertidumbre; "
            "el rango exacto +/-0.05 es declaracion del autor dentro de esa clase."
        ),
    },
    "Gap_excluded_indicators": {
        "half_width": 0.05,
        "source_id": "Saisana_Saltelli_Tarantola_2005_JRSSA;Hoyland_Moene_Willumsen_2012_JDE",
        "note": (
            "Gap: incertidumbre de puntajes de indices compuestos construidos "
            "desde cobertura ITU y velocidades Ookla excluidas del AIPI. La "
            "literatura ancla clase y orden de magnitud; +/-0.05 es declaracion "
            "del autor."
        ),
    },
    "I_adopt_informality": {
        "half_width": 0.04,
        "source_id": "Gasparini_Tornarolli_2007_CEDLAS_WP46;Gasparini_Tornarolli_2009_followup",
        "note": (
            "I: dispersion inter-definicion de informalidad en LAC. Gasparini "
            "y Tornarolli documentan brechas de varios puntos porcentuales; "
            "+/-0.04 es conservador frente a ese orden de magnitud."
        ),
    },
}
HONESTY_NOTE = (
    "Nota de honestidad: la literatura ancla la existencia y el orden de "
    "magnitud de la incertidumbre para esta clase de objetos; los valores "
    "exactos son declaracion del autor. La sensibilidad de intensidad del "
    "factor rho 0.3-0.8 cubre parcialmente rangos mas anchos."
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_table(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {table}").fetchdf()


def append_frame(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    cols = con.execute(f"DESCRIBE {table}").fetchdf()["column_name"].tolist()
    df = df.reindex(columns=cols)
    con.register("_df", df)
    con.execute(f"INSERT INTO {table} SELECT * FROM _df")
    con.unregister("_df")


def build_parameter_tables(values: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def materialize(root: Path) -> dict[str, Any]:
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        value_v2 = read_table(con, "value_assignment_table")
        value_v2 = value_v2[value_v2["parameter_set_id"].eq(V2)].copy()
        if value_v2.empty:
            raise RuntimeError(f"Missing {V2}; materialize baseline-official-v2 first.")

        value_v3 = value_v2.copy()
        value_v3["parameter_set_id"] = V3
        value_v3["dataset_version"] = DATASET_VERSION
        value_v3["build_id"] = "etapa_5B_R_baseline_official_v3_measurement_uncertainty"
        value_v3["created_at"] = now()
        value_v3["created_by_script"] = SCRIPT_NAME

        changed_rows = []
        for name, rule in MEASUREMENT_RULES.items():
            mask = value_v3["name"].eq(name) & value_v3["country_id"].notna()
            if not mask.any():
                raise RuntimeError(f"Missing v3 measurement rows for {name}")
            for idx in value_v3[mask].index:
                baseline = float(value_v3.at[idx, "baseline_value"])
                half_width = float(rule["half_width"])
                low = max(0.0, baseline - half_width)
                high = min(1.0, baseline + half_width)
                country = str(value_v3.at[idx, "country_id"])
                value_v3.at[idx, "low_value"] = low
                value_v3.at[idx, "high_value"] = high
                value_v3.at[idx, "support_type"] = "literature_informed_measurement_uncertainty"
                value_v3.at[idx, "source_id"] = rule["source_id"]
                value_v3.at[idx, "formula_id"] = "MEASUREMENT_UNCERTAINTY_PERT_AUTHOR_2026_07_09"
                value_v3.at[idx, "distribution"] = "bounded_PERT"
                value_v3.at[idx, "truncation_rule"] = "truncated_to_[0,1]_and_checked_q_bar_nonnegative"
                value_v3.at[idx, "audit_status"] = "author_approved"
                value_v3.at[idx, "author_approval_date"] = AUTHOR_DATE
                value_v3.at[idx, "author_approval_note"] = AUTHOR_NOTE
                value_v3.at[idx, "notes"] = f"{rule['note']} {HONESTY_NOTE}"
                value_v3.at[idx, "assumption_id"] = f"OFFICIAL_V3_MEASUREMENT_{name}_{country}"
                changed_rows.append(value_v3.loc[idx].to_dict())

        # Check q_bar >= 0 at the conservative measurement upper bounds with
        # central omega values. Regime uncertainty in omega is checked by the MC
        # support-valid gate draw by draw.
        wide = value_v3[value_v3["country_id"].notna()].pivot_table(
            index="country_id",
            columns="name",
            values=["baseline_value", "high_value"],
            aggfunc="first",
        )
        failures = []
        for country in wide.index:
            omega_i = float(wide.loc[country, ("baseline_value", "omega_I")])
            omega_g = float(wide.loc[country, ("baseline_value", "omega_G")])
            i_high = float(wide.loc[country, ("high_value", "I_adopt_informality")])
            g_high = float(wide.loc[country, ("high_value", "Gap_excluded_indicators")])
            q_bar_min = 1.0 - omega_i * i_high - omega_g * g_high
            if q_bar_min < 0.0:
                failures.append((country, q_bar_min))
        if failures:
            raise RuntimeError(f"q_bar high-bound coherence failed: {failures}")

        item_v3, registry_v3 = build_parameter_tables(value_v3)

        parameter_set_v2 = read_table(con, "parameter_set")
        parameter_set_v2 = parameter_set_v2[parameter_set_v2["parameter_set_id"].eq(V2)].copy()
        parameter_set_v3 = parameter_set_v2.copy()
        parameter_set_v3["parameter_set_id"] = V3
        parameter_set_v3["parameter_set_name"] = "baseline official v3"
        parameter_set_v3["description"] = (
            "Official Tier B calibration amendment: A, Gap, and I measurement "
            "uncertainty plus signed institutional dependency design."
        )
        parameter_set_v3["created_at"] = now()
        parameter_set_v3["created_by_script"] = SCRIPT_NAME

        changelog = pd.DataFrame(
            [
                {
                    "from_parameter_set_id": V2,
                    "to_parameter_set_id": V3,
                    "change_id": "J0",
                    "description": (
                        "A_aipi_total and Gap_excluded_indicators changed from fixed_observed "
                        "to bounded_PERT measurement uncertainty +/-0.05 absolute, truncated "
                        "to [0,1] and q_bar coherent."
                    ),
                    "direction": "measurement_uncertainty_author_signed",
                    "author_approval_date": AUTHOR_DATE,
                },
                {
                    "from_parameter_set_id": V2,
                    "to_parameter_set_id": V3,
                    "change_id": "J0_I",
                    "description": (
                        "I_adopt_informality changed from fixed_observed to bounded_PERT "
                        "measurement uncertainty +/-0.04 absolute, truncated to [0,1]."
                    ),
                    "direction": "measurement_uncertainty_author_signed",
                    "author_approval_date": AUTHOR_DATE,
                },
                {
                    "from_parameter_set_id": V2,
                    "to_parameter_set_id": V3,
                    "change_id": "J1",
                    "description": (
                        "Signed dependency design: institutional factor plus pairwise "
                        "cross-check; classification remains independent-baseline only."
                    ),
                    "direction": "dependency_structure_governance",
                    "author_approval_date": AUTHOR_DATE,
                },
            ]
        )

        for table, column in [
            ("value_assignment_table", "parameter_set_id"),
            ("parameter_set_item", "parameter_set_id"),
            ("calibrated_parameter_registry", "parameter_set_id"),
            ("parameter_set", "parameter_set_id"),
            ("threshold_assignment_table", "parameter_set_id"),
            ("input_audit_report", "parameter_set_id"),
            ("double_counting_audit", "parameter_set_id"),
            ("parameter_set_changelog", "to_parameter_set_id"),
        ]:
            con.execute(f"DELETE FROM {table} WHERE {column} = ?", [V3])

        append_frame(con, "value_assignment_table", value_v3)
        append_frame(con, "parameter_set_item", item_v3)
        append_frame(con, "calibrated_parameter_registry", registry_v3)
        append_frame(con, "parameter_set", parameter_set_v3)

        for table in ["threshold_assignment_table", "input_audit_report", "double_counting_audit"]:
            source = read_table(con, table)
            source = source[source["parameter_set_id"].eq(V2)].copy()
            source["parameter_set_id"] = V3
            if "notes" in source.columns:
                source["notes"] = source["notes"].astype(str) + " | Cloned for baseline-official-v3 measurement-uncertainty amendment."
            append_frame(con, table, source)
        append_frame(con, "parameter_set_changelog", changelog)
    finally:
        con.close()

    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    value_v3.to_csv(reports / f"value_assignment_table_{V3}.csv", index=False)
    item_v3.to_csv(reports / f"parameter_set_item_{V3}.csv", index=False)
    registry_v3.to_csv(reports / f"calibrated_parameter_registry_{V3}.csv", index=False)
    changelog.to_csv(reports / f"parameter_set_changelog_{V3}.csv", index=False)
    changed = pd.DataFrame(changed_rows)
    changed.to_csv(reports / f"value_assignment_changes_{V2}_to_{V3}.csv", index=False)
    return {
        "status": "OK",
        "parameter_set_id": V3,
        "value_rows": int(len(value_v3)),
        "changed_rows": int(len(changed)),
        "q_bar_check": "PASS",
    }


def main() -> int:
    print(json.dumps(materialize(repo_root()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
