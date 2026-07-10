"""Fetch the CASEN 2024 input for the labelled Chile GMI microdata extension.

The SPSS source is preferred over RData because pyreadstat can project the
required columns during parsing. The source and normalized parquet remain in an
extension-only snapshot, isolated from every official baseline dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyreadstat
import requests


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "robustness-gmimicro-chl-v1"
SOURCE_ID = "MDSF_CASEN_2024"
YEAR = 2024
DATA_URL = (
    "https://observatorio.ministeriodesarrollosocial.gob.cl/"
    "storage/docs/casen/2024/casen_2024.sav"
)
CODEBOOK_URL = (
    "https://observatorio.ministeriodesarrollosocial.gob.cl/"
    "storage/docs/casen/2024/Libro_de_codigos_Casen_2024.xlsx"
)
PORTAL_URL = "https://observatorio.ministeriodesarrollosocial.gob.cl/encuesta-casen-2024"
SELECTED_COLUMNS = (
    "folio",
    "id_persona",
    "hogar",
    "ytotcorh",
    "ypchtotcor",
    "ymonecorh",
    "yae",
    "nae",
    "numper",
    "expr",
    "lp",
    "li",
    "pobreza",
    "no_arrienda",
)
EXPECTED_PERSON_ROWS = 218_367
EXPECTED_HOUSEHOLDS = 78_654


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


USER_AGENT = "ai-usp-fiscal-thresholds/GMI-micro-CHL-extension"


def _download_range(url: str, path: Path, start: int, end: int) -> int:
    response = requests.get(
        url,
        stream=True,
        timeout=(60, 600),
        headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"},
    )
    if response.status_code != 206 or not str(response.headers.get("Content-Range", "")).startswith(
        f"bytes {start}-{end}/"
    ):
        raise RuntimeError(f"Range download failed for {start}-{end}: HTTP {response.status_code}")
    size = 0
    with path.open("wb") as output:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                output.write(chunk)
                size += len(chunk)
    expected = end - start + 1
    if size != expected:
        raise RuntimeError(f"Range size mismatch for {start}-{end}: {size} != {expected}")
    return size


def download(url: str, destination: Path) -> dict[str, object]:
    head = requests.head(url, timeout=60, headers={"User-Agent": USER_AGENT})
    head.raise_for_status()
    total = int(head.headers.get("Content-Length", "0"))
    if total >= 100 * 1024 * 1024:
        workers = 8
        chunk_size = (total + workers - 1) // workers
        ranges = [
            (index, index * chunk_size, min(total - 1, (index + 1) * chunk_size - 1))
            for index in range(workers)
            if index * chunk_size < total
        ]
        part_paths = [destination.with_name(f".{destination.name}.part{index:02d}") for index, _, _ in ranges]
        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                sizes = list(
                    executor.map(
                        lambda item: _download_range(url, item[0], item[1], item[2]),
                        [(part_paths[i], start, end) for i, (_, start, end) in enumerate(ranges)],
                    )
                )
            with destination.open("wb") as output:
                for part_path in part_paths:
                    with part_path.open("rb") as part:
                        for chunk in iter(lambda: part.read(1024 * 1024), b""):
                            output.write(chunk)
            size = sum(sizes)
        finally:
            for part_path in part_paths:
                part_path.unlink(missing_ok=True)
        if size != total or destination.stat().st_size != total:
            raise RuntimeError(f"Assembled download size mismatch: {destination.stat().st_size} != {total}")
        return {
            "http_status": 206,
            "content_type": head.headers.get("Content-Type"),
            "content_length_header": str(total),
            "downloaded_bytes": size,
            "range_workers": workers,
        }

    response = requests.get(url, stream=True, timeout=(60, 600), headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    size = 0
    with destination.open("wb") as output:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                output.write(chunk)
                size += len(chunk)
    return {
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "content_length_header": response.headers.get("Content-Length"),
        "downloaded_bytes": size,
    }


def fetch(output_dir: Path, manifest_path: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded_at = datetime.now(timezone.utc).isoformat()
    sav_path = output_dir / "casen_2024.sav"
    codebook_path = output_dir / "Libro_de_codigos_Casen_2024.xlsx"
    data_response = download(DATA_URL, sav_path)
    codebook_response = download(CODEBOOK_URL, codebook_path)

    frame, source_metadata = pyreadstat.read_sav(
        str(sav_path),
        usecols=list(SELECTED_COLUMNS),
        apply_value_formats=False,
    )
    missing = [column for column in SELECTED_COLUMNS if column not in frame.columns]
    if missing:
        raise RuntimeError(f"CASEN 2024 is missing required variables: {missing}")
    if len(frame) != EXPECTED_PERSON_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_PERSON_ROWS} person rows, found {len(frame)}")
    if int(frame["folio"].nunique(dropna=True)) != EXPECTED_HOUSEHOLDS:
        raise RuntimeError(
            f"Expected {EXPECTED_HOUSEHOLDS} households, found {frame['folio'].nunique(dropna=True)}"
        )
    frame.insert(0, "survey_year", YEAR)
    frame.insert(0, "country_id", "CHL")
    parquet_path = output_dir / "casen_2024_gmi_required_variables.parquet"
    frame.to_parquet(parquet_path, index=False)

    hashes = {
        sav_path.name: sha256_file(sav_path),
        codebook_path.name: sha256_file(codebook_path),
        parquet_path.name: sha256_file(parquet_path),
    }
    metadata = {
        "source_id": SOURCE_ID,
        "snapshot_id": SNAPSHOT_ID,
        "download_date": downloaded_at,
        "source_url": DATA_URL,
        "codebook_url": CODEBOOK_URL,
        "portal_url": PORTAL_URL,
        "method": "direct_spss_anonymous",
        "status": "ok",
        "country_filter": ["CHL"],
        "survey_year": YEAR,
        "target_year": YEAR,
        "carried_forward_to_2024": False,
        "format_choice": (
            "SPSS selected because pyreadstat.read_sav(usecols=...) projects 14 required columns; "
            "the RData endpoint is gzip-transferred but expands to about 1.55 GB and pyreadr "
            "does not project columns during object loading."
        ),
        "parsing_library": f"pyreadstat {pyreadstat.__version__}",
        "column_projection": list(SELECTED_COLUMNS),
        "source_columns_documented": 877,
        "parsed_columns": int(source_metadata.number_columns),
        "source_rows": int(source_metadata.number_rows),
        "normalized_rows": int(len(frame)),
        "households": int(frame["folio"].nunique(dropna=True)),
        "raw_file_hash": hashes[sav_path.name],
        "file_hashes": hashes,
        "http": {"data": data_response, "codebook": codebook_response},
        "script_name": Path(__file__).name,
        "script_version": "1.0.0-post-baseline-extension",
        "notes": (
            "New CASEN 2024 input for a labelled post-baseline Chile GMI microdata robustness "
            "extension. It is isolated from every official baseline snapshot."
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
                "source_dir": "casen_2024",
                "source_id": SOURCE_ID,
                "status": "ok",
                "metadata_path": f"{relative_output}/metadata.json",
                "source_url": DATA_URL,
                "query_or_endpoint": DATA_URL,
                "raw_file_hash": hashes[sav_path.name],
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
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "raw_snapshots" / SNAPSHOT_ID / "casen_2024",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{SNAPSHOT_ID}.json",
    )
    args = parser.parse_args()
    frame = fetch(args.output_dir, args.manifest)
    print(
        f"CASEN {YEAR}: person_rows={len(frame)}, households={frame['folio'].nunique()}, "
        f"selected_columns={len(SELECTED_COLUMNS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
