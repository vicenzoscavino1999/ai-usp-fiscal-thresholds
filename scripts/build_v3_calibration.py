"""Build baseline-pilot-v3 calibration rows from baseline-pilot-v2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "ai_usp_threshold.duckdb"
REPORTS_DIR = ROOT / "reports"
DATASET_VERSION = "v0.1.2-pilot-per"
PREVIOUS_PARAMETER_SET_ID = "baseline-pilot-v2"
PARAMETER_SET_ID = "baseline-pilot-v3"
SCRIPT_NAME = "build_v3_calibration.py"
FRONTIER_SET_ID = "baseline_oecd_eurostat_ge10_2024"
CREATED_AT = datetime.now(timezone.utc).isoformat()

E_PROD_FRONTIER_NOTE = (
    "exposición productiva de economías avanzadas: mayor share de tareas cognitivas "
    "aumentables que LAC (8-14%); low = paridad LAC; high = cota exploratoria; "
    "pendiente de ancla bibliográfica del autor"
)
CHI_KBASE_NOTE = (
    "share del excedente no-laboral que es base corporativa gravable; 1.0 solo como "
    "variante favorable etiquetada; anclar con cuentas nacionales si el snapshot lo "
    "permite, documentándolo"
)
CHI_DOM_NOTE = "share doméstica de la base corporativa incremental; author-review con soporte pendiente."


def _fetch(con: duckdb.DuckDBPyConnection, table: str, parameter_col: str = "parameter_set_id") -> pd.DataFrame:
    return con.execute(
        f"SELECT * FROM {table} WHERE {parameter_col} = ?",
        [PREVIOUS_PARAMETER_SET_ID],
    ).fetchdf()


def _write_append(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"INSERT INTO {table} SELECT * FROM _df")
    con.unregister("_df")


def _update_value_row(df: pd.DataFrame, name: str, **updates) -> None:
    mask = df["name"].eq(name)
    if not mask.any():
        raise RuntimeError(f"Missing value_assignment row {name}")
    for col, value in updates.items():
        df.loc[mask, col] = value


def _update_registry_row(df: pd.DataFrame, parameter_name: str, **updates) -> None:
    mask = df["parameter_name"].eq(parameter_name)
    if not mask.any():
        raise RuntimeError(f"Missing registry row {parameter_name}")
    for col, value in updates.items():
        df.loc[mask, col] = value


def _add_value_row(df: pd.DataFrame, row: dict) -> pd.DataFrame:
    full_row = {col: None for col in df.columns}
    full_row.update(row)
    return pd.concat([df, pd.DataFrame([full_row])], ignore_index=True)


def _export_value_report(df: pd.DataFrame) -> None:
    cols = [
        "name",
        "module",
        "country_id",
        "scenario_id",
        "policy_id",
        "regime_code",
        "baseline_value",
        "low_value",
        "high_value",
        "unit",
        "distribution",
        "support_type",
        "source_id",
        "formula_id",
        "double_counting_risk",
        "double_counting_note",
        "audit_status",
        "notes",
    ]
    df[cols].to_csv(REPORTS_DIR / f"value_assignment_table_{PARAMETER_SET_ID}.csv", index=False)


def main() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    value_df = _fetch(con, "value_assignment_table")
    registry_df = _fetch(con, "calibrated_parameter_registry")
    item_df = _fetch(con, "parameter_set_item")
    threshold_df = _fetch(con, "threshold_assignment_table")
    input_audit_df = _fetch(con, "input_audit_report")
    double_count_df = _fetch(con, "double_counting_audit")

    for df in (value_df, registry_df, item_df, threshold_df, input_audit_df, double_count_df):
        df["parameter_set_id"] = PARAMETER_SET_ID
        if "created_at" in df.columns:
            df["created_at"] = CREATED_AT
        if "created_by_script" in df.columns:
            df["created_by_script"] = SCRIPT_NAME

    _update_value_row(
        value_df,
        "chi_Kbase",
        value_type="calibrated_parameter",
        baseline_value=0.70,
        low_value=0.55,
        high_value=0.85,
        support_type="author_review_capital_base_share",
        source_id="AUTHOR_REVIEW_PENDING_NATIONAL_ACCOUNTS;PLAN_02_SEC_7_4_1",
        formula_id=CHI_KBASE_NOTE,
        distribution="bounded_PERT",
        truncation_rule="0_to_1",
        audit_status="registered_author_review",
        notes=CHI_KBASE_NOTE,
        assumption_id="A3B1_V3_CHI_KBASE",
    )
    _update_value_row(
        value_df,
        "chi_dom",
        value_type="calibrated_parameter",
        baseline_value=0.95,
        low_value=0.85,
        high_value=1.00,
        support_type="author_review_domestic_capital_share",
        source_id="AUTHOR_REVIEW_PENDING_NATIONAL_ACCOUNTS;PLAN_02_SEC_7_4_1",
        formula_id=CHI_DOM_NOTE,
        distribution="bounded_PERT",
        truncation_rule="0_to_1",
        audit_status="registered_author_review",
        notes=CHI_DOM_NOTE,
        assumption_id="A3B1_V3_CHI_DOM",
    )
    _update_value_row(
        value_df,
        "epsilon",
        notes=(
            "Frozen numerical floor epsilon=1e-9 for support checks and de-flooring; "
            "reported explicitly in traces so it is not mistaken for zero."
        ),
        formula_id="epsilon floor for tilde_x=epsilon+(1-epsilon)x and de-flooring in inversions",
    )
    _update_value_row(
        value_df,
        "epsilon_mu",
        notes=(
            "Frozen logit inversion floor epsilon_mu=1e-6; q_use_target_adj is projected "
            "to [epsilon_mu, q_bar-epsilon_mu]."
        ),
        formula_id="epsilon_mu floor for q_use_target interior projection and mu inversion",
    )
    value_df = _add_value_row(
        value_df,
        {
            "name": "E_prod_frontier",
            "module": "frontier_benchmark",
            "value_type": "calibrated_parameter",
            "unit": "share_of_tasks_or_employment",
            "baseline_value": 0.17,
            "low_value": 0.11,
            "high_value": 0.25,
            "support_type": "author_review_frontier_productive_exposure",
            "source_id": "AUTHOR_REVIEW_PENDING_BIBLIOGRAPHIC_ANCHOR;PLAN_01_SEC_14_10;PLAN_02_SEC_10_6",
            "formula_id": E_PROD_FRONTIER_NOTE,
            "distribution": "bounded_PERT",
            "truncation_rule": "0_to_1",
            "primary_spec_flag": True,
            "robustness_flag": False,
            "stress_flag": False,
            "double_counting_risk": "none",
            "audit_status": "registered_author_review",
            "notes": E_PROD_FRONTIER_NOTE,
            "dataset_version": DATASET_VERSION,
            "parameter_set_id": PARAMETER_SET_ID,
            "assumption_id": "A3B1_V3_E_PROD_FRONTIER",
            "created_at": CREATED_AT,
            "created_by_script": SCRIPT_NAME,
            "double_counting_note": "none",
        },
    )

    for parameter_name, baseline, low, high, note, assumption_id in [
        ("chi_Kbase", 0.70, 0.55, 0.85, CHI_KBASE_NOTE, "A3B1_V3_CHI_KBASE"),
        ("chi_dom", 0.95, 0.85, 1.00, CHI_DOM_NOTE, "A3B1_V3_CHI_DOM"),
    ]:
        _update_registry_row(
            registry_df,
            parameter_name,
            baseline_value=baseline,
            low_value=low,
            high_value=high,
            distribution="bounded_PERT",
            truncation_rule="0_to_1",
            source_id="AUTHOR_REVIEW_PENDING_NATIONAL_ACCOUNTS;PLAN_02_SEC_7_4_1",
            is_observed=False,
            is_structural_unobserved=True,
            sensitivity_level="high",
            justification=note,
            included_in_primary=True,
            assumption_id=assumption_id,
            created_at=CREATED_AT,
            created_by_script=SCRIPT_NAME,
        )
    _update_registry_row(
        registry_df,
        "epsilon",
        justification="Frozen numerical floor epsilon=1e-9 for support checks and de-flooring.",
        created_at=CREATED_AT,
        created_by_script=SCRIPT_NAME,
    )
    _update_registry_row(
        registry_df,
        "epsilon_mu",
        justification="Frozen logit inversion floor epsilon_mu=1e-6 for target projection.",
        created_at=CREATED_AT,
        created_by_script=SCRIPT_NAME,
    )
    registry_df = pd.concat(
        [
            registry_df,
            pd.DataFrame(
                [
                    {
                        "parameter_name": "E_prod_frontier",
                        "module": "frontier_benchmark",
                        "baseline_value": 0.17,
                        "low_value": 0.11,
                        "high_value": 0.25,
                        "distribution": "bounded_PERT",
                        "truncation_rule": "0_to_1",
                        "source_id": "AUTHOR_REVIEW_PENDING_BIBLIOGRAPHIC_ANCHOR;PLAN_01_SEC_14_10;PLAN_02_SEC_10_6",
                        "is_observed": False,
                        "is_scenario": False,
                        "is_structural_unobserved": True,
                        "sensitivity_level": "high",
                        "justification": E_PROD_FRONTIER_NOTE,
                        "double_counting_note": "none",
                        "included_in_primary": True,
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": DATASET_VERSION,
                        "assumption_id": "A3B1_V3_E_PROD_FRONTIER",
                        "created_at": CREATED_AT,
                        "created_by_script": SCRIPT_NAME,
                    }
                ],
                columns=registry_df.columns,
            ),
        ],
        ignore_index=True,
    )

    # Keep parameter_set_item concise but mirror the changed primary scalars.
    for name, value, assumption_id, notes in [
        ("chi_Kbase", 0.70, "A3B1_V3_CHI_KBASE", CHI_KBASE_NOTE),
        ("chi_dom", 0.95, "A3B1_V3_CHI_DOM", CHI_DOM_NOTE),
        ("E_prod_frontier", 0.17, "A3B1_V3_E_PROD_FRONTIER", E_PROD_FRONTIER_NOTE),
    ]:
        item_df = item_df[item_df["parameter_name"] != name]
        item_df = pd.concat(
            [
                item_df,
                pd.DataFrame(
                    [
                        {
                            "parameter_set_id": PARAMETER_SET_ID,
                            "assumption_id": assumption_id,
                            "parameter_name": name,
                            "country_id": None,
                            "policy_id": None,
                            "scenario_id": None,
                            "regime_id": None,
                            "parameter_value": value,
                            "distribution": "bounded_PERT",
                            "draw_rule": "author_review_registered",
                            "notes": notes,
                        }
                    ],
                    columns=item_df.columns,
                ),
            ],
            ignore_index=True,
        )

    parameter_set_df = pd.DataFrame(
        [
            {
                "parameter_set_id": PARAMETER_SET_ID,
                "parameter_set_name": "baseline pilot v3",
                "description": "Etapa 3B.1 calibration: frontier exposure parameter, capital-chain ranges, floor reporting.",
                "model_version": "deterministic_engine_stage_3b1",
                "dataset_version": DATASET_VERSION,
                "created_at": CREATED_AT,
                "created_by_script": SCRIPT_NAME,
            }
        ]
    )
    changelog_df = pd.DataFrame(
        [
            {
                "from_parameter_set_id": PREVIOUS_PARAMETER_SET_ID,
                "to_parameter_set_id": PARAMETER_SET_ID,
                "change_id": "F1",
                "change_text": "Registered E_prod_frontier=0.17 [0.11,0.25] and materialized frontier benchmark exposure; removed fallback exposure=1.0.",
                "dataset_version": DATASET_VERSION,
                "created_at": CREATED_AT,
                "created_by_script": SCRIPT_NAME,
            },
            {
                "from_parameter_set_id": PREVIOUS_PARAMETER_SET_ID,
                "to_parameter_set_id": PARAMETER_SET_ID,
                "change_id": "F2",
                "change_text": "Recalibrated chi_Kbase=0.70 [0.55,0.85] and chi_dom=0.95 [0.85,1.00] as author-review capital-chain priors.",
                "dataset_version": DATASET_VERSION,
                "created_at": CREATED_AT,
                "created_by_script": SCRIPT_NAME,
            },
            {
                "from_parameter_set_id": PREVIOUS_PARAMETER_SET_ID,
                "to_parameter_set_id": PARAMETER_SET_ID,
                "change_id": "F3",
                "change_text": "Echo frozen floors epsilon=1e-9 and epsilon_mu=1e-6 in calibration reports and traces.",
                "dataset_version": DATASET_VERSION,
                "created_at": CREATED_AT,
                "created_by_script": SCRIPT_NAME,
            },
        ]
    )

    frontier_df = con.execute(
        """
        SELECT * FROM frontier_benchmark_anchor
        WHERE dataset_version = ?
          AND benchmark_set_id = ?
          AND scenario_id = ?
        ORDER BY benchmark_country_id
        """,
        [DATASET_VERSION, FRONTIER_SET_ID, PREVIOUS_PARAMETER_SET_ID],
    ).fetchdf()
    frontier_df["scenario_id"] = PARAMETER_SET_ID
    frontier_df["exposure_productive"] = 0.17
    epsilon = 1e-9
    frontier_df["s_frontier_score"] = (
        (epsilon + (1 - epsilon) * frontier_df["exposure_productive"])
        * (epsilon + (1 - epsilon) * frontier_df["adoption_proxy"])
    )
    frontier_df["score_convention"] = "NDC_baseline_declared_E_prod_frontier"
    frontier_df["elasticities_used"] = "alpha=0; beta=1; gamma=1; E_prod_frontier=0.17"
    frontier_df["population_consistency_note"] = (
        "OECD/advanced Eurostat enterprise AI adoption benchmark matched to phi_mid population; "
        "E_prod_frontier=0.17 registered as author-review productive exposure for advanced economies."
    )

    floor_report = value_df[value_df["name"].isin(["epsilon", "epsilon_mu"])][
        ["name", "baseline_value", "low_value", "high_value", "unit", "support_type", "source_id", "formula_id", "notes"]
    ]
    changes_report = value_df[
        value_df["name"].isin(["E_prod_frontier", "chi_Kbase", "chi_dom", "epsilon", "epsilon_mu"])
    ][
        ["name", "module", "baseline_value", "low_value", "high_value", "distribution", "audit_status", "notes"]
    ]

    for table, column in [
        ("value_assignment_table", "parameter_set_id"),
        ("calibrated_parameter_registry", "parameter_set_id"),
        ("parameter_set_item", "parameter_set_id"),
        ("parameter_set", "parameter_set_id"),
        ("threshold_assignment_table", "parameter_set_id"),
        ("input_audit_report", "parameter_set_id"),
        ("double_counting_audit", "parameter_set_id"),
        ("parameter_set_changelog", "to_parameter_set_id"),
    ]:
        con.execute(f"DELETE FROM {table} WHERE {column} = ?", [PARAMETER_SET_ID])
    con.execute(
        "DELETE FROM frontier_benchmark_anchor WHERE dataset_version = ? AND benchmark_set_id = ? AND scenario_id = ?",
        [DATASET_VERSION, FRONTIER_SET_ID, PARAMETER_SET_ID],
    )

    _write_append(con, "value_assignment_table", value_df)
    _write_append(con, "calibrated_parameter_registry", registry_df)
    _write_append(con, "parameter_set_item", item_df)
    _write_append(con, "parameter_set", parameter_set_df)
    _write_append(con, "threshold_assignment_table", threshold_df)
    _write_append(con, "input_audit_report", input_audit_df)
    _write_append(con, "double_counting_audit", double_count_df)
    _write_append(con, "parameter_set_changelog", changelog_df)
    _write_append(con, "frontier_benchmark_anchor", frontier_df)
    con.close()

    _export_value_report(value_df)
    changes_report.to_csv(
        REPORTS_DIR / f"value_assignment_changes_{PREVIOUS_PARAMETER_SET_ID}_to_{PARAMETER_SET_ID}.csv",
        index=False,
    )
    changelog_df.to_csv(REPORTS_DIR / f"parameter_set_changelog_{PARAMETER_SET_ID}.csv", index=False)
    floor_report.to_csv(REPORTS_DIR / f"frozen_floor_values_{PARAMETER_SET_ID}.csv", index=False)

    print(f"OK parameter_set_id={PARAMETER_SET_ID}")
    print(f"value_assignment_rows={len(value_df)}")
    print(f"frontier_rows={len(frontier_df)}")


if __name__ == "__main__":
    main()
