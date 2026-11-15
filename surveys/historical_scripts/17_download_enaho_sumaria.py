"""Fetch ENAHO 2024 Sumaria for the labelled GMI microdata extension.

The extension snapshot is isolated from the official frozen datasets. The
original INEI ZIP and selected Stata file are preserved with SHA-256 hashes;
the normalized parquet contains only the variables required by the extension.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "robustness-gmimicro-per-v1"
SOURCE_ID = "INEI_ENAHO_SUMARIA"
YEAR = 2024
SURVEY_CODE = 966
MODULE = 34
SOURCE_URL = (
    "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/"
    f"STATA/{SURVEY_CODE}-Modulo{MODULE}.zip"
)
PORTAL_URL = "https://proyectos.inei.gob.pe/microdatos/"
REQUIRED_COLUMNS = (
    "GASHOG2D",
    "INGHOG2D",
    "MIEPERHO",
    "FACTOR07",
    "POBREZA",
    "LINEA",
    "LINPE",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "ai-usp-fiscal-thresholds/GMI-micro-extension"})
    with urlopen(request, timeout=300) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if not zipfile.is_zipfile(destination):
        raise RuntimeError(f"INEI response is not a ZIP archive: {url}")


def select_standard_sumaria(archive: zipfile.ZipFile) -> str:
    candidates = [name for name in archive.namelist() if Path(name).name.lower() == "sumaria-2024.dta"]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one standard sumaria-2024.dta (excluding alternate 12g files); "
            f"found {candidates}"
        )
    return candidates[0]


def fetch(output_dir: Path, manifest_path: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded_at = datetime.now(timezone.utc).isoformat()
    zip_path = output_dir / f"{SURVEY_CODE}-Modulo{MODULE}.zip"
    download(SOURCE_URL, zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        member = select_standard_sumaria(archive)
        dta_path = output_dir / "sumaria-2024.dta"
        with archive.open(member) as source, dta_path.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
        archive_listing = [
            {"name": info.filename, "uncompressed_bytes": info.file_size}
            for info in archive.infolist()
        ]

    frame = pd.read_stata(dta_path, convert_categoricals=False)
    actual_by_upper = {str(column).upper(): column for column in frame.columns}
    missing = [column for column in REQUIRED_COLUMNS if column not in actual_by_upper]
    if missing:
        raise RuntimeError(f"ENAHO Sumaria is missing required variables: {missing}")
    normalized = frame[[actual_by_upper[column] for column in REQUIRED_COLUMNS]].copy()
    normalized.columns = list(REQUIRED_COLUMNS)
    normalized.insert(0, "survey_year", YEAR)
    normalized.insert(0, "country_id", "PER")
    parquet_path = output_dir / "enaho_sumaria_2024_required_variables.parquet"
    normalized.to_parquet(parquet_path, index=False)

    hashes = {
        zip_path.name: sha256_file(zip_path),
        dta_path.name: sha256_file(dta_path),
        parquet_path.name: sha256_file(parquet_path),
    }
    metadata = {
        "source_id": SOURCE_ID,
        "snapshot_id": SNAPSHOT_ID,
        "download_date": downloaded_at,
        "source_url": SOURCE_URL,
        "portal_url": PORTAL_URL,
        "query_or_endpoint": SOURCE_URL,
        "method": "direct_zip_stata_anonymous",
        "status": "ok",
        "country_filter": ["PER"],
        "survey_year": YEAR,
        "target_year": YEAR,
        "carried_forward_to_2024": False,
        "survey_code": SURVEY_CODE,
        "module": MODULE,
        "selected_archive_member": member,
        "archive_listing": archive_listing,
        "record_count": int(len(normalized)),
        "required_variables": list(REQUIRED_COLUMNS),
        "raw_file_hash": hashes[zip_path.name],
        "file_hashes": hashes,
        "script_name": Path(__file__).name,
        "script_version": "1.0.0-post-baseline-extension",
        "notes": (
            "New ENAHO 2024 Sumaria input for a labelled post-baseline GMI microdata "
            "robustness extension. It is isolated from every official baseline snapshot."
        ),
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    relative_output = output_dir.relative_to(ROOT).as_posix()
    manifest = {
        "dataset_version": SNAPSHOT_ID,
        "run_label": "post_baseline_robustness_extension_new_input_series",
        "created_at": downloaded_at,
        "manifest_schema_version": "0.1.1-stage1-extension",
        "baseline_dataset_version_unchanged": "v1.0.1-official-4c",
        "sources": [
            {
                "source_dir": "enaho_sumaria",
                "source_id": SOURCE_ID,
                "status": "ok",
                "metadata_path": f"{relative_output}/metadata.json",
                "source_url": SOURCE_URL,
                "query_or_endpoint": SOURCE_URL,
                "raw_file_hash": hashes[zip_path.name],
                "hash_check": "ok",
                "raw_files": [
                    {"path": f"{relative_output}/{name}", "sha256": digest}
                    for name, digest in hashes.items()
                ],
            }
        ],
        "summary": {"ok": 1, "manual_pending": 0, "failed": 0, "missing": 0},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "raw_snapshots" / SNAPSHOT_ID / "enaho_sumaria",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{SNAPSHOT_ID}.json",
    )
    args = parser.parse_args()
    frame = fetch(args.output_dir, args.manifest)
    print(f"ENAHO Sumaria {YEAR}: rows={len(frame)}, variables={len(REQUIRED_COLUMNS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
