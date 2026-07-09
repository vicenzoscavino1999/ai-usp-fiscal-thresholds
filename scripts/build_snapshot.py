"""Freeze and verify the Stage 1 raw-data snapshot manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SOURCES = [
    ("wdi", "wdi_country_year.parquet"),
    ("pip", "pip_poverty.parquet"),
    ("sedlac", "sedlac_lac.parquet"),
    ("oecd", "oecd_revenue.parquet"),
    ("grd", "grd_revenue.parquet"),
    ("imf", "imf_fiscal_macro.parquet"),
    ("ilostat", "ilostat_labor.parquet"),
    ("pwt", "pwt_country_year.parquet"),
    ("itu", "itu_digital.parquet"),
    ("imf_aipi", "aipi.parquet"),
    ("national", None),
    ("manual", "manual_source_registry.parquet"),
    ("frontier", "frontier_benchmark.parquet"),
    ("wpp", "wpp_projections.parquet"),
    ("ookla", "ookla_speedtest.parquet"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_version_name(version: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", version)


def preserve_existing_manifest(out_path: Path, dataset_version: str) -> None:
    if not out_path.exists():
        return
    try:
        existing = load_json(out_path)
    except Exception:  # noqa: BLE001
        return
    old_version = str(existing.get("dataset_version") or "unknown")
    if old_version == dataset_version:
        return
    backup = out_path.with_name(f"dataset_manifest_{safe_version_name(old_version)}.json")
    if not backup.exists():
        backup.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")


def source_entry(root: Path, raw_root: Path, source_dir: str, expected_file: str | None) -> dict[str, object]:
    directory = raw_root / source_dir
    metadata_path = directory / "metadata.json"
    entry: dict[str, object] = {
        "source_dir": source_dir,
        "expected_file": expected_file,
        "metadata_path": str(metadata_path.relative_to(root)),
    }
    if not metadata_path.exists():
        entry.update({"status": "missing", "raw_files": [], "notes": "metadata.json not found"})
        return entry
    metadata = load_json(metadata_path)
    raw_files = []
    for parquet in sorted(directory.glob("*.parquet")):
        raw_files.append({"path": str(parquet.relative_to(root)), "sha256": sha256_file(parquet)})
    declared_hash = metadata.get("raw_file_hash")
    hash_check = "not_applicable"
    if raw_files and declared_hash:
        hash_check = "ok" if raw_files[0]["sha256"] == declared_hash else "mismatch"
    elif metadata.get("status") == "ok":
        hash_check = "missing_raw_file"
    entry.update(
        {
            "source_id": metadata.get("source_id"),
            "status": metadata.get("status", "unknown"),
            "raw_file_hash": declared_hash,
            "hash_check": hash_check,
            "raw_files": raw_files,
            "download_date": metadata.get("download_date"),
            "source_url": metadata.get("source_url"),
            "query_or_endpoint": metadata.get("query_or_endpoint"),
            "country_filter": metadata.get("country_filter"),
            "year_filter": metadata.get("year_filter"),
            "script_name": metadata.get("script_name"),
            "script_version": metadata.get("script_version"),
            "notes": metadata.get("notes"),
        }
    )
    for optional_key in [
        "manual_registration",
        "manual_registered_sources",
        "filter_applied",
        "download_file_hash",
        "download_file_hashes",
        "bcrp_series_codes",
        "sdmx_dimensions",
        "input_completeness_checks",
        "available_hdx_resources",
        "license_notes",
        "normalization_inputs",
    ]:
        if optional_key in metadata:
            entry[optional_key] = metadata[optional_key]
    return entry


def freeze(root: Path, dataset_version: str, raw_root_arg: str | None = None) -> int:
    raw_root = Path(raw_root_arg) if raw_root_arg else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    sources = [
        source_entry(root, raw_root, source_dir, expected_file)
        for source_dir, expected_file in EXPECTED_SOURCES
    ]
    manifest = {
        "dataset_version": dataset_version,
        "run_label": "pilot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_schema_version": "0.1.1-stage1",
        "sources": sources,
        "summary": {
            "ok": sum(1 for source in sources if source.get("status") == "ok"),
            "manual_pending": sum(1 for source in sources if source.get("status") == "manual_pending"),
            "failed": sum(1 for source in sources if source.get("status") == "failed"),
            "missing": sum(1 for source in sources if source.get("status") == "missing"),
        },
    }
    out_path = root / "reproducibility" / "snapshot" / "dataset_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preserve_existing_manifest(out_path, dataset_version)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    versioned = out_path.with_name(f"dataset_manifest_{safe_version_name(dataset_version)}.json")
    versioned.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["summary"], indent=2))
    return 0


def check(root: Path) -> int:
    manifest_path = root / "reproducibility" / "snapshot" / "dataset_manifest.json"
    manifest = load_json(manifest_path)
    errors: list[str] = []
    for source in manifest.get("sources", []):
        for raw_file in source.get("raw_files", []):
            path = root / raw_file["path"]
            if not path.exists():
                errors.append(f"missing file: {raw_file['path']}")
                continue
            actual = sha256_file(path)
            if actual != raw_file["sha256"]:
                errors.append(f"hash mismatch: {raw_file['path']}")
        if source.get("status") == "ok" and source.get("hash_check") not in {"ok", "not_applicable"}:
            errors.append(f"bad hash_check for {source.get('source_dir')}: {source.get('hash_check')}")
    if errors:
        print("\n".join(errors))
        return 1
    print("dataset_manifest.json hashes verified")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-version", default="v0.1.2-pilot-per")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--from-frozen", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.freeze:
        return freeze(root, args.dataset_version, args.raw_root)
    if args.check:
        return check(root)
    if args.from_frozen:
        print("build-from-frozen-dataset no implementado en Etapa 1")
        return 1
    parser.error("use --freeze, --check, or --from-frozen")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
