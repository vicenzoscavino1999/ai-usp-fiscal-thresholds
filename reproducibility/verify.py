"""Strict deterministic-output verifier for the reproduction package."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CURRENT = ROOT / "results" / "official"
DEFAULT_REFERENCE = ROOT / "reproducibility" / "reference"
DEFAULT_SCHEMAS = ROOT / "reproducibility" / "config" / "schemas.yaml"
DEFAULT_TOLERANCES = ROOT / "reproducibility" / "config" / "tolerances.yaml"
NULL_SENTINEL = "<NULL>"


@dataclass
class VerifyResult:
    passed: bool = True
    messages: list[str] = field(default_factory=list)
    file_status: dict[str, str] = field(default_factory=dict)

    def fail(self, message: str) -> None:
        self.passed = False
        self.messages.append(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def column_spec(raw: Any) -> tuple[str, bool, list[Any] | None]:
    if isinstance(raw, str):
        return raw, False, None
    return str(raw["type"]), bool(raw.get("nullable", False)), raw.get("allowed_values")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, keep_default_na=True)


def key_frame(df: pd.DataFrame, keys: list[str]) -> pd.Series:
    parts = []
    for key in keys:
        s = df[key]
        if pd.api.types.is_numeric_dtype(s):
            parts.append(s.map(lambda x: NULL_SENTINEL if pd.isna(x) else f"{float(x):.12g}"))
        else:
            parts.append(s.astype("string").fillna(NULL_SENTINEL))
    return pd.Series(["|".join(vals) for vals in zip(*parts, strict=False)], index=df.index)


def validate_schema(df: pd.DataFrame, schema: dict[str, Any], label: str, result: VerifyResult) -> None:
    expected_cols = list(schema["columns"].keys())
    actual_cols = list(df.columns)
    missing = [col for col in expected_cols if col not in actual_cols]
    extra = [col for col in actual_cols if col not in expected_cols]
    if missing:
        result.fail(f"{label}: missing columns {missing}")
    if extra:
        result.fail(f"{label}: extra columns {extra}")
    if missing or extra:
        return
    for col, raw_spec in schema["columns"].items():
        typ, nullable, allowed_values = column_spec(raw_spec)
        if not nullable and df[col].isna().any():
            result.fail(f"{label}: non-nullable column has NaN: {col}")
            continue
        nonnull = df[col].dropna()
        if allowed_values is not None:
            allowed = set(map(str, allowed_values))
            bad = sorted(set(nonnull.astype("string")) - allowed)
            if bad:
                result.fail(f"{label}: column {col} has values outside allowed set: {bad}")
        if typ == "float":
            converted = pd.to_numeric(nonnull, errors="coerce")
            if converted.isna().any():
                result.fail(f"{label}: column is not float-compatible: {col}")
        elif typ == "int":
            converted = pd.to_numeric(nonnull, errors="coerce")
            if converted.isna().any() or not np.all(np.isclose(converted, np.round(converted))):
                result.fail(f"{label}: column is not int-compatible: {col}")
        elif typ == "bool":
            allowed = {True, False, "True", "False", "true", "false", 1, 0}
            if not nonnull.map(lambda x: x in allowed).all():
                result.fail(f"{label}: column is not bool-compatible: {col}")
        elif typ == "string":
            pass
        else:
            result.fail(f"{label}: unknown schema type {typ} for {col}")


def compare_values(
    current: pd.DataFrame,
    reference: pd.DataFrame,
    schema: dict[str, Any],
    tolerances: dict[str, Any],
    label: str,
    result: VerifyResult,
) -> None:
    keys = schema["primary_key"]
    current = current.copy()
    reference = reference.copy()
    current["_key"] = key_frame(current, keys)
    reference["_key"] = key_frame(reference, keys)
    if current["_key"].duplicated().any():
        result.fail(f"{label}: duplicate current primary keys")
        return
    if reference["_key"].duplicated().any():
        result.fail(f"{label}: duplicate reference primary keys")
        return
    cur_keys = set(current["_key"])
    ref_keys = set(reference["_key"])
    missing = sorted(ref_keys - cur_keys)
    extra = sorted(cur_keys - ref_keys)
    if missing:
        result.fail(f"{label}: missing rows by key, first={missing[:5]} total={len(missing)}")
    if extra:
        result.fail(f"{label}: extra rows by key, first={extra[:5]} total={len(extra)}")
    if missing or extra:
        return
    current = current.set_index("_key").sort_index()
    reference = reference.set_index("_key").sort_index()
    default_tol = tolerances.get("default_float", {"atol": 1e-10, "rtol": 1e-8})
    exact_cols = set(tolerances.get("exact_columns", []))
    for col, raw_spec in schema["columns"].items():
        typ, nullable, _allowed_values = column_spec(raw_spec)
        a = current[col]
        b = reference[col]
        both_null = a.isna() & b.isna()
        if nullable:
            a = a[~both_null]
            b = b[~both_null]
        if len(a) != len(b):
            result.fail(f"{label}: null mismatch in {col}")
            continue
        if typ in {"float", "int"}:
            av = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
            bv = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
            if col in exact_cols or typ == "int":
                ok = (av == bv) | (np.isnan(av) & np.isnan(bv))
            else:
                ok = np.isclose(av, bv, atol=float(default_tol["atol"]), rtol=float(default_tol["rtol"]), equal_nan=True)
            if not np.all(ok):
                idx = np.where(~ok)[0][0]
                result.fail(f"{label}: numeric mismatch {col} at key={a.index[idx]} current={av[idx]} reference={bv[idx]}")
        else:
            av = a.astype("string").fillna(NULL_SENTINEL)
            bv = b.astype("string").fillna(NULL_SENTINEL)
            neq = av.ne(bv)
            if neq.any():
                key = av.index[neq.to_numpy()][0]
                result.fail(f"{label}: exact mismatch {col} at key={key} current={av.loc[key]} reference={bv.loc[key]}")


def verify_dataset_hash(current_dir: Path, reference_dir: Path, root: Path, result: VerifyResult) -> None:
    current_manifest_path = current_dir / "manifest.json"
    reference_manifest_path = reference_dir / "reference_manifest.json"
    if not current_manifest_path.exists():
        result.fail("current manifest.json missing")
        return
    if not reference_manifest_path.exists():
        result.fail("reference_manifest.json missing")
        return
    current_manifest = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    reference_manifest = json.loads(reference_manifest_path.read_text(encoding="utf-8"))
    current_hash = current_manifest.get("dataset_manifest_hash")
    reference_hash = reference_manifest.get("dataset_manifest_hash")
    if current_hash != reference_hash:
        result.fail(f"dataset hash mismatch: current={current_hash} reference={reference_hash}")
    dataset_version = current_manifest.get("dataset_version")
    snapshot_path = root / "reproducibility" / "snapshot" / f"dataset_manifest_{dataset_version}.json"
    if snapshot_path.exists():
        actual_hash = sha256_file(snapshot_path)
        if actual_hash != current_hash:
            result.fail(f"snapshot hash mismatch: actual={actual_hash} manifest={current_hash}")


def verify_reference(
    current_dir: Path = DEFAULT_CURRENT,
    reference_dir: Path = DEFAULT_REFERENCE,
    schemas_path: Path = DEFAULT_SCHEMAS,
    tolerances_path: Path = DEFAULT_TOLERANCES,
    root: Path = ROOT,
) -> VerifyResult:
    result = VerifyResult()
    schemas = load_yaml(schemas_path).get("schemas", {})
    all_tolerances = load_yaml(tolerances_path)
    verify_dataset_hash(current_dir, reference_dir, root, result)
    for name, schema in schemas.items():
        if schema.get("future_schema_only"):
            continue
        file_name = schema["file"]
        try:
            cur = read_csv(current_dir / file_name)
            ref = read_csv(reference_dir / file_name)
        except FileNotFoundError as exc:
            result.fail(f"{name}: missing file {exc}")
            result.file_status[file_name] = "FAIL"
            continue
        before = len(result.messages)
        validate_schema(cur, schema, f"{name}:current", result)
        validate_schema(ref, schema, f"{name}:reference", result)
        if len(result.messages) == before:
            tolerance_tier = schema.get("tolerance_tier", "tier_A")
            tolerances = all_tolerances.get(tolerance_tier, all_tolerances.get("tier_A", {}))
            compare_values(cur, ref, schema, tolerances, name, result)
        result.file_status[file_name] = "PASS" if len(result.messages) == before else "FAIL"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMAS)
    parser.add_argument("--tolerances", type=Path, default=DEFAULT_TOLERANCES)
    args = parser.parse_args(argv)
    result = verify_reference(args.current, args.reference, args.schemas, args.tolerances, ROOT)
    payload = {
        "status": "PASS" if result.passed else "FAIL",
        "files": result.file_status,
        "messages": result.messages,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
