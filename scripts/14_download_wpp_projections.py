"""Download UN WPP 2024 single-age/sex medium projections from bulk CSV."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "UN_WPP"
WPP_BASE_URL = "https://population.un.org/wpp/"
DOWNLOADS_JSON_URL = "https://population.un.org/wpp/assets/downloads.json"
TARGET_FILENAME = "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, retries: int = 4) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=180)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def find_target_path(node: object) -> str | None:
    if isinstance(node, dict):
        path = node.get("Path")
        if isinstance(path, str) and path.endswith(TARGET_FILENAME):
            return path
        for value in node.values():
            found = find_target_path(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_target_path(item)
            if found:
                return found
    return None


def exact_download_url() -> str:
    downloads = get(DOWNLOADS_JSON_URL).json()
    relative_path = find_target_path(downloads)
    if not relative_path:
        raise RuntimeError(f"{TARGET_FILENAME} not found in WPP downloads.json")
    return urllib.parse.urljoin(WPP_BASE_URL, relative_path.replace(" ", "%20"))


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": WPP_BASE_URL,
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        **payload,
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--start-year", type=int, default=2024)
    parser.add_argument("--end-year", type=int, default=2035)
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "wpp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "wpp_projections.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    try:
        download_url = exact_download_url()
        payload = get(download_url).content
        chunks: list[pd.DataFrame] = []
        dtype = {"Notes": "string", "ISO3_code": "string", "ISO2_code": "string", "SDMX_code": "string"}
        for chunk in pd.read_csv(io.BytesIO(payload), compression="gzip", chunksize=200_000, dtype=dtype):
            filtered = chunk[
                chunk["ISO3_code"].isin(countries)
                & chunk["Time"].between(args.start_year, args.end_year)
            ].copy()
            if not filtered.empty:
                chunks.append(filtered)
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": DOWNLOADS_JSON_URL,
                "country_filter": countries,
                "year_filter": f"{args.start_year}-{args.end_year}",
                "raw_file_hash": None,
                "notes": f"UN WPP bulk CSV pull failed: {exc}",
            },
        )
        print(f"WPP pull failed: {exc}")
        return 2

    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": download_url,
                "country_filter": countries,
                "year_filter": f"{args.start_year}-{args.end_year}",
                "raw_file_hash": None,
                "download_file_hash": sha256_bytes(payload),
                "notes": "UN WPP bulk CSV returned no rows after ISO3/year filter.",
            },
        )
        return 2

    df["source_id"] = SOURCE_ID
    df["download_date"] = datetime.now(timezone.utc).date().isoformat()
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": download_url,
            "country_filter": countries,
            "year_filter": f"{args.start_year}-{args.end_year}",
            "raw_file_hash": sha256_file(out_file),
            "download_file_hash": sha256_bytes(payload),
            "filter_applied": {
                "ISO3_code": countries,
                "Time": [args.start_year, args.end_year],
                "Variant": "Medium",
                "file": TARGET_FILENAME,
            },
            "notes": (
                "UN WPP 2024 bulk CSV, Standard Projections, single-age/sex, medium variant. "
                "No five-year age groups or 65+/15-64/18+ aggregates are constructed in raw ingest."
            ),
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
