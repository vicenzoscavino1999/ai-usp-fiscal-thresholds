from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_robustness_schema_is_registered():
    schema = yaml.safe_load((ROOT / "reproducibility" / "config" / "schemas.yaml").read_text(encoding="utf-8"))
    schemas = schema["schemas"]
    assert "robustness_table" in schemas
    assert schemas["robustness_table"]["file"] == "robustness_table.csv"
    assert schemas["robustness_table"]["columns"]["run_type"]["allowed_values"] == ["robustness", "labeled_illustrative"]
    assert "diagnostic_result" in schemas
    assert "historical_window_plausibility_changes" in schemas


def test_robustness_6a_output_contract_if_present():
    output = ROOT / "results" / "official" / "robustness_table.csv"
    if not output.exists():
        return

    df = pd.read_csv(output)
    assert set(df["run_type"]) == {"robustness", "labeled_illustrative"}
    assert set(df["parameter_set_id"]) == {"baseline-official-v3"}
    assert set(df["baseline_parameter_set_id"]) == {"baseline-official-v3"}
    assert df["variant_id"].nunique() == 29
    assert len(df) == 29 * 480
    assert df[df["run_type"].eq("robustness")]["variant_id"].nunique() == 28

    headline = df[df["headline_cell"].astype(bool)]
    assert len(headline) == 29 * 4
    assert headline["baseline_reversed_flag"].astype(bool).any()

    r2b = headline[headline["variant_id"].str.startswith("R2b_conservative_q0_lambda_")]
    assert len(r2b) == 3 * 4
    assert (r2b["delta_v"] < 0).any()

    unavailable = headline[headline["variant_id"].isin(["R3_frontier_alt_year", "R12_non_resource_plausibility"])]
    assert unavailable["v_variant"].isna().all()
    assert set(unavailable["variant_cell_result_class"]) == {"not_available_in_snapshot"}

    window = ROOT / "results" / "official" / "historical_window_plausibility_changes.csv"
    if window.exists():
        w = pd.read_csv(window)
        assert set(w["percentile_sample"]) == {"2000plus", "2010plus", "2015plus", "excl_pandemic_2020_2021"}
        assert set(w["revenue_concept"]) == {"tax", "total_revenue"}


def test_policy_parameter_existing_spending_treatment_registered():
    report = ROOT / "reports" / "policy_parameter_official_4c.csv"
    if not report.exists():
        return

    policy_parameter = pd.read_csv(report)
    treatments = set(policy_parameter["existing_spending_treatment"])
    assert len(treatments) == 1
    treatment = next(iter(treatments))
    assert treatment.startswith("pure_layering_zero_existing_spending")
    assert "V_net=V_gross is conservative" in treatment
