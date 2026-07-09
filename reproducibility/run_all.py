"""Reproduction harness for deterministic Tier A official results."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET_VERSION = "v1.0.1-official-4c"
PARAMETER_SET_ID = "baseline-official-v2"
RUN_LABEL = "official"
REFERENCE_TAG = "official-tierB-baseline-official-v3"
REFERENCE_CHANGELOG = [
    "correccion de clase historica del objeto requerido; V intacto",
    "restaurado esquema canonico de historical_capture_percentiles segun plan 01 seccion 15.5; clases titulares sin cambios",
    "Etapa 5A: Monte Carlo independiente, robustez historica r0, convergencia Tier B y clasificacion final probabilistica; motor certificado intacto.",
    "Etapa 5A.1: grilla MC canonica 1.00/1.05/1.10/1.25/1.50, vocabulario final canonico y matriz rank-correlated traducida a primitivos imponibles.",
    "Etapa 5B-R: baseline-official-v3 con incertidumbre de medicion A/Gap/I; dependencia institucional factor + cross-check par-a-par; clasificacion final sigue usando solo MC_independent_baseline.",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def package_versions() -> dict[str, str]:
    packages = ["numpy", "scipy", "pandas", "duckdb", "pyarrow", "pyyaml"]
    result = {}
    for pkg in packages:
        try:
            result[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            result[pkg] = "missing"
    return result


def verify_snapshot_manifest(dataset_version: str) -> tuple[str, list[str]]:
    manifest_path = ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{dataset_version}.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing snapshot manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for source in manifest.get("sources", []):
        for raw in source.get("raw_files", []):
            path = ROOT / Path(str(raw["path"]).replace("\\", "/"))
            if not path.exists():
                errors.append(f"missing raw file {raw['path']}")
            elif sha256_file(path) != raw.get("sha256"):
                errors.append(f"hash mismatch {raw['path']}")
    return sha256_file(manifest_path), errors


def primary_spec_hash_status() -> dict[str, Any]:
    spec = ROOT / "02_ESD_AI_USP_v6.md"
    hash_file = ROOT / "PRIMARY_SPEC_HASH.txt"
    actual = sha256_file(spec) if spec.exists() else None
    expected = None
    if hash_file.exists():
        for line in hash_file.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("sha256:"):
                expected = line.split(":", 1)[1].strip().lower()
                break
    return {
        "actual": actual,
        "expected": expected,
        "status": "PASS" if actual and expected and actual.lower() == expected.lower() else "WARN",
    }


def preflight(dataset_version: str, parameter_set_id: str, run_label: str) -> dict[str, Any]:
    dataset_hash, snapshot_errors = verify_snapshot_manifest(dataset_version)
    env = {
        "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
    }
    payload = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "packages": package_versions(),
        "dataset_version": dataset_version,
        "dataset_manifest_hash": dataset_hash,
        "snapshot_hash_status": "PASS" if not snapshot_errors else "FAIL",
        "snapshot_errors": snapshot_errors,
        "parameter_set_id": parameter_set_id,
        "run_label": run_label,
        "primary_spec_hash": primary_spec_hash_status(),
        "git_commit": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty": bool(git_value(["status", "--short"])),
        "env": env,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "preflight_official.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if snapshot_errors:
        raise RuntimeError("Snapshot preflight failed: " + "; ".join(snapshot_errors))
    return payload


def archive_reference() -> dict[str, Any]:
    from reproducibility.verify import DEFAULT_SCHEMAS, load_yaml

    current = ROOT / "results" / "official"
    reference = ROOT / "reproducibility" / "reference"
    if reference.exists():
        for child in reference.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    reference.mkdir(parents=True, exist_ok=True)
    schemas = load_yaml(DEFAULT_SCHEMAS).get("schemas", {})
    files = []
    for schema in schemas.values():
        if schema.get("future_schema_only"):
            continue
        files.append(schema["file"])
    files.append("manifest.json")
    checksums = {}
    for file_name in files:
        src = current / file_name
        if not src.exists():
            raise RuntimeError(f"Cannot archive missing output {src}")
        dst = reference / file_name
        shutil.copy2(src, dst)
        checksums[file_name] = sha256_file(dst)
    current_manifest = json.loads((current / "manifest.json").read_text(encoding="utf-8"))
    reference_manifest = {
        "tag": REFERENCE_TAG,
        "commit": git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit",
        "git_dirty_at_reference_creation": bool(git_value(["status", "--short"])),
        "dataset_version": current_manifest.get("dataset_version"),
        "dataset_manifest_hash": current_manifest.get("dataset_manifest_hash"),
        "parameter_set_id": current_manifest.get("parameter_set_id"),
        "run_id": current_manifest.get("run_id"),
        "changelog": REFERENCE_CHANGELOG,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": checksums,
    }
    (reference / "reference_manifest.json").write_text(json.dumps(reference_manifest, indent=2, sort_keys=True), encoding="utf-8")
    checksum_lines = [f"{digest}  {name}" for name, digest in sorted(checksums.items())]
    checksum_lines.append(f"{sha256_file(reference / 'reference_manifest.json')}  reference_manifest.json")
    (reference / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return reference_manifest


def run_official(dataset_version: str, parameter_set_id: str, run_label: str, archive: bool, tier: str = "A") -> dict[str, Any]:
    if dataset_version != DATASET_VERSION:
        raise RuntimeError(f"Only {DATASET_VERSION} is implemented for Etapa 4B.")
    if parameter_set_id != PARAMETER_SET_ID:
        raise RuntimeError(f"Only {PARAMETER_SET_ID} is implemented for Etapa 4B.")
    if run_label != RUN_LABEL:
        raise RuntimeError(f"Only run_label={RUN_LABEL} is implemented for Etapa 4B.")
    started = time.perf_counter()
    pre = preflight(dataset_version, parameter_set_id, run_label)
    from scripts.build_official_4c_anchors import build as build_anchors
    from scripts.materialize_official_v2_author_signature import build as materialize_v2
    from scripts.run_official_tier_a import run_tier_a

    build_anchors(ROOT, dataset_version)
    materialize_v2(ROOT)
    outputs = run_tier_a(ROOT, write=True)
    mc_outputs = None
    if tier == "B":
        from scripts.run_official_monte_carlo import run_monte_carlo

        mc_outputs = run_monte_carlo(ROOT, m_draws=5000, persist_draws=True)
    reference = archive_reference() if archive else None
    payload = {
        "status": "OK",
        "preflight": pre,
        "run_manifest": outputs["manifest"],
        "monte_carlo_rows": None if mc_outputs is None else int(len(mc_outputs["monte_carlo_result"])),
        "reference_manifest": reference,
        "runtime_seconds_total": time.perf_counter() - started,
    }
    (ROOT / "results" / "run_all_official_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-env-only", action="store_true")
    parser.add_argument("--tier", default="A")
    parser.add_argument("--run-label", default=RUN_LABEL)
    parser.add_argument("--parameter-set-id", default=PARAMETER_SET_ID)
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    parser.add_argument("--archive-reference", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.check_env_only:
        payload = {
            "python": platform.python_version(),
            "executable": sys.executable,
            "packages": package_versions(),
        }
        print(json.dumps(payload, indent=2))
        return 0
    if args.tier not in {"A", "B"}:
        raise SystemExit("Only Tier A and Tier B are implemented.")
    payload = run_official(args.dataset_version, args.parameter_set_id, args.run_label, args.archive_reference, tier=args.tier)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "dataset_version": args.dataset_version,
                "parameter_set_id": args.parameter_set_id,
                "run_label": args.run_label,
                "runtime_seconds_total": payload["runtime_seconds_total"],
                "reference_archived": payload["reference_manifest"] is not None,
                "monte_carlo_rows": payload.get("monte_carlo_rows"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
