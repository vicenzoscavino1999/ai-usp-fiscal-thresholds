from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_robustness_schema_is_registered():
    schema = yaml.safe_load((ROOT / "reproducibility" / "config" / "schemas.yaml").read_text(encoding="utf-8"))
    schemas = schema["schemas"]
    assert "robustness_table" in schemas
    assert schemas["robustness_table"]["file"] == "robustness_table.csv"
    assert schemas["robustness_table"]["columns"]["run_type"]["allowed_values"] == ["robustness"]
    assert "diagnostic_result" in schemas


def test_robustness_6a_output_contract_if_present():
    output = ROOT / "results" / "official" / "robustness_table.csv"
    if not output.exists():
        return

    df = pd.read_csv(output)
    assert set(df["run_type"]) == {"robustness"}
    assert set(df["parameter_set_id"]) == {"baseline-official-v3"}
    assert set(df["baseline_parameter_set_id"]) == {"baseline-official-v3"}
    assert df["variant_id"].nunique() == 28
    assert len(df) == 28 * 480

    headline = df[df["headline_cell"].astype(bool)]
    assert len(headline) == 28 * 4
    assert headline["baseline_reversed_flag"].astype(bool).any()

    trajectory = headline[headline["variant_id"].str.startswith("R2_trajectory_lambda_")]
    assert trajectory["abs_delta_v"].max() < 1e-12

