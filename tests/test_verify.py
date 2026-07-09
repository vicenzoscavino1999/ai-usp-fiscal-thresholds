import json
from pathlib import Path

import pandas as pd
import yaml

from reproducibility.verify import verify_reference


def _fixture(tmp_path: Path):
    current = tmp_path / "current"
    reference = tmp_path / "reference"
    current.mkdir()
    reference.mkdir()
    df = pd.DataFrame(
        [
            {"id": "a", "xi": 0.10, "value": 1.0, "flag": True, "note": None},
            {"id": "b", "xi": 0.10, "value": 2.0, "flag": False, "note": "ok"},
        ]
    )
    df.to_csv(current / "result.csv", index=False)
    df.to_csv(reference / "result.csv", index=False)
    (current / "manifest.json").write_text(
        json.dumps({"dataset_version": "test", "dataset_manifest_hash": "hash-ok"}),
        encoding="utf-8",
    )
    (reference / "reference_manifest.json").write_text(
        json.dumps({"dataset_version": "test", "dataset_manifest_hash": "hash-ok"}),
        encoding="utf-8",
    )
    schemas = tmp_path / "schemas.yaml"
    schemas.write_text(
        yaml.safe_dump(
            {
                "schemas": {
                    "result": {
                        "file": "result.csv",
                        "primary_key": ["id", "xi"],
                        "columns": {
                            "id": "string",
                            "xi": "float",
                            "value": "float",
                            "flag": "bool",
                            "note": {"type": "string", "nullable": True},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    tolerances = tmp_path / "tolerances.yaml"
    tolerances.write_text(
        yaml.safe_dump({"tier_A": {"default_float": {"atol": 1e-10, "rtol": 1e-8}, "exact_columns": ["xi"]}}),
        encoding="utf-8",
    )
    return current, reference, schemas, tolerances


def test_verify_clean_passes(tmp_path):
    current, reference, schemas, tolerances = _fixture(tmp_path)
    result = verify_reference(current, reference, schemas, tolerances, tmp_path)
    assert result.passed


def test_verify_perturbed_fails(tmp_path):
    current, reference, schemas, tolerances = _fixture(tmp_path)
    df = pd.read_csv(current / "result.csv")
    df.loc[0, "value"] = 1.01
    df.to_csv(current / "result.csv", index=False)
    result = verify_reference(current, reference, schemas, tolerances, tmp_path)
    assert not result.passed
    assert any("numeric mismatch" in msg for msg in result.messages)


def test_verify_missing_rows_fails(tmp_path):
    current, reference, schemas, tolerances = _fixture(tmp_path)
    df = pd.read_csv(current / "result.csv").iloc[:1]
    df.to_csv(current / "result.csv", index=False)
    result = verify_reference(current, reference, schemas, tolerances, tmp_path)
    assert not result.passed
    assert any("missing rows" in msg for msg in result.messages)


def test_verify_nan_fails(tmp_path):
    current, reference, schemas, tolerances = _fixture(tmp_path)
    df = pd.read_csv(current / "result.csv")
    df.loc[0, "value"] = None
    df.to_csv(current / "result.csv", index=False)
    result = verify_reference(current, reference, schemas, tolerances, tmp_path)
    assert not result.passed
    assert any("non-nullable column has NaN" in msg for msg in result.messages)


def test_verify_dataset_hash_mismatch_fails(tmp_path):
    current, reference, schemas, tolerances = _fixture(tmp_path)
    (current / "manifest.json").write_text(
        json.dumps({"dataset_version": "test", "dataset_manifest_hash": "hash-bad"}),
        encoding="utf-8",
    )
    result = verify_reference(current, reference, schemas, tolerances, tmp_path)
    assert not result.passed
    assert any("dataset hash mismatch" in msg for msg in result.messages)
