from pathlib import Path

import pandas as pd
import yaml

from reproducibility.verify import VerifyResult, validate_schema
from scripts.run_official_monte_carlo import THRESHOLD_SUFFIX, THRESHOLDS


ROOT = Path(__file__).resolve().parents[1]


def test_monte_carlo_threshold_grid_is_canonical():
    assert THRESHOLDS == (1.00, 1.05, 1.10, 1.25, 1.50)
    assert set(THRESHOLD_SUFFIX.values()) == {"1_00", "1_05", "1_10", "1_25", "1_50"}

    schema = yaml.safe_load((ROOT / "reproducibility" / "config" / "schemas.yaml").read_text(encoding="utf-8"))
    columns = schema["schemas"]["monte_carlo_result"]["columns"]
    for stem in ["prob_v_ge", "prob_debt_consistent", "failure_severity_mean", "failure_severity_median"]:
        assert f"{stem}_1_05" in columns
        assert f"{stem}_1_35" not in columns

    output = ROOT / "results" / "official" / "monte_carlo_result.csv"
    if output.exists():
        actual_cols = set(pd.read_csv(output, nrows=1).columns)
        assert "prob_v_ge_1_05" in actual_cols
        assert "prob_v_ge_1_35" not in actual_cols


def test_final_classification_vocab_is_enforced():
    schema = {
        "columns": {
            "final_country_policy_result_class": {
                "type": "string",
                "allowed_values": [
                    "robustly_feasible",
                    "conditionally_feasible",
                    "fragile_feasible",
                    "not_feasible",
                    "stress_benchmark_only",
                ],
            }
        }
    }
    result = VerifyResult()
    validate_schema(
        pd.DataFrame([{"final_country_policy_result_class": "fragile_or_not_feasible_probability_below_0_50"}]),
        schema,
        "classification",
        result,
    )
    assert not result.passed
    assert any("outside allowed set" in message for message in result.messages)
