from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_informality_ablation_schema_registered():
    schemas = yaml.safe_load((ROOT / "reproducibility" / "config" / "schemas.yaml").read_text(encoding="utf-8"))["schemas"]
    assert "informality_adoption_ablation_result" in schemas
    columns = schemas["informality_adoption_ablation_result"]["columns"]
    assert "delta_q_bar" in columns
    assert "delta_v" in columns


def test_phase_b_closure_outputs_if_present():
    ablation_path = ROOT / "results" / "official" / "informality_adoption_ablation_result.csv"
    if not ablation_path.exists():
        return

    ablation = pd.read_csv(ablation_path)
    assert len(ablation) == 480
    assert ablation["delta_q_bar"].max() > 0
    assert ablation["delta_q_prod"].abs().max() == 0
    assert ablation["delta_v"].abs().max() == 0
    assert not ablation["crossing_changed"].astype(bool).any()

    hyp = pd.read_csv(ROOT / "results" / "official" / "hypothesis_adjudication.csv")
    h3 = hyp[hyp["hypothesis_id"].eq("H3")].iloc[0]
    assert h3["verdict"] == "MIXED"
    assert not bool(h3["preliminary_flag"])
    assert "max_abs_delta_v=0" in h3["evidence_summary"]

    final = pd.read_csv(ROOT / "results" / "official" / "country_policy_classification_final.csv")
    chl_gmi = final[final["country_id"].eq("CHL") & final["policy_id"].eq("GMI")]
    assert not chl_gmi.empty
    assert chl_gmi["classification_note"].str.contains("D2 caveat").all()


def test_paper_tables_manifest_if_present():
    manifest = ROOT / "results" / "paper_tables" / "paper_tables_manifest.csv"
    if not manifest.exists():
        return

    df = pd.read_csv(manifest)
    required = {
        "table1_anchors",
        "table8_final_classification",
        "appendix_d_placebo_ict",
        "appendix_k_computational_validation_tests",
        "master_calibration_matrix",
        "bias_ledger",
    }
    assert required.issubset(set(df["artifact_id"]))
