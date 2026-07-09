from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_diagnostics_6b_schema_is_registered():
    schema = yaml.safe_load((ROOT / "reproducibility" / "config" / "schemas.yaml").read_text(encoding="utf-8"))
    schemas = schema["schemas"]
    expected = {
        "diagnostic_placebo_ict_result",
        "diagnostic_negative_control_result",
        "diagnostic_loso_result",
        "diagnostic_channel_ablation_result",
        "diagnostic_no_rent_capture_result",
        "diagnostic_high_leakage_result",
        "diagnostic_sobol_result",
    }
    assert expected.issubset(set(schemas))
    assert "diagnostic" in schemas["diagnostic_result"]["columns"]["run_type"]["allowed_values"]


def test_diagnostics_6b_outputs_if_present():
    diagnostic_result = ROOT / "results" / "official" / "diagnostic_result.csv"
    if not diagnostic_result.exists():
        return

    diag = pd.read_csv(diagnostic_result)
    rows = diag[diag["run_type"].eq("diagnostic")]
    assert set(rows["variant_id"]) == {
        "D1_placebo_ict",
        "D2_negative_control_sectorial",
        "D3_leave_one_source_out",
        "D4_channel_ablation",
        "D5_no_rent_capture",
        "D6_high_leakage_stress",
        "D7_informalization_mirror",
        "D8_sobol_saltelli",
        "P0_informality_adoption_ablation",
    }
    assert rows.loc[rows["variant_id"].eq("D1_placebo_ict"), "verdict"].item() == "PASS"
    assert rows.loc[rows["variant_id"].eq("D3_leave_one_source_out"), "verdict"].item() == "PASS"
    assert rows.loc[rows["variant_id"].eq("D7_informalization_mirror"), "verdict"].item() == "not_applicable"

    placebo = pd.read_csv(ROOT / "results" / "official" / "diagnostic_placebo_ict_result.csv")
    assert len(placebo) == 120
    assert set(placebo["placebo_cell_class"]) == {"not_feasible"}
    assert placebo["v_placebo"].max() < 1.0

    negative = pd.read_csv(ROOT / "results" / "official" / "diagnostic_negative_control_result.csv")
    assert len(negative) == 480
    assert abs(negative["collapse_ratio"].median() - (0.035 / 0.11)) < 1e-12

    loso = pd.read_csv(ROOT / "results" / "official" / "diagnostic_loso_result.csv")
    evaluated = loso[loso["status"].isin(["PASS", "FAIL"])]
    assert len(evaluated) == 3
    assert set(evaluated["status"]) == {"PASS"}

    sobol = pd.read_csv(ROOT / "results" / "official" / "diagnostic_sobol_result.csv")
    assert len(sobol) == 30
    assert set(sobol["saltelli_n"]) == {1024}
    assert sobol.groupby(["country_id", "policy_variant_id", "scenario_id", "regime_id"]).size().eq(10).all()
