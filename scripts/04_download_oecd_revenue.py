"""Download OECD Revenue Statistics LAC through the OECD SDMX REST API."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.1-stage1"
SOURCE_ID = "OECD_REVSTAT_LAC"
DATAFLOW = "OECD.CTP.TPS,DSD_REV_COMP_LAC@DF_RSLAC"
STRUCTURE_URL = "https://sdmx.oecd.org/public/rest/dataflow/OECD.CTP.TPS/DSD_REV_COMP_LAC@DF_RSLAC/1.1?references=all"
DATA_URL_BASE = f"https://sdmx.oecd.org/public/rest/data/{DATAFLOW}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, headers: dict[str, str], retries: int = 4) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=90)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def dimension_ids(structure: dict[str, object]) -> list[str]:
    structures = ((structure.get("data") or {}).get("dataStructures") or []) if isinstance(structure.get("data"), dict) else []
    if not structures:
        raise RuntimeError("OECD SDMX structure has no dataStructures")
    dims = structures[0]["dataStructureComponents"]["dimensionList"]["dimensions"]
    ordered = sorted(dims, key=lambda item: item.get("position", 0))
    return [item["id"] for item in ordered]


def sdmx_key_for_country(dimensions: list[str], country: str) -> str:
    parts = [country if dim == "REF_AREA" else "" for dim in dimensions]
    return ".".join(parts)


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": DATA_URL_BASE,
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        **payload,
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "oecd"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "oecd_revenue.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    endpoints: list[str] = [STRUCTURE_URL]
    try:
        structure_response = get(
            STRUCTURE_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.sdmx.structure+json, application/json"},
        )
        dimensions = dimension_ids(structure_response.json())
        frames: list[pd.DataFrame] = []
        for country in countries:
            key = sdmx_key_for_country(dimensions, country)
            query_url = f"{DATA_URL_BASE}/{key}"
            endpoints.append(query_url)
            response = get(query_url, headers=HEADERS)
            frame = pd.read_csv(io.StringIO(response.text))
            if not frame.empty:
                frames.append(frame)
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": f"OECD SDMX pull failed after deriving structure/query: {exc}",
            },
        )
        print(f"OECD pull failed: {exc}")
        return 2

    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "OECD SDMX query returned no rows for requested countries.",
            },
        )
        return 2

    for column in ["TIME_PERIOD", "OBS_VALUE"]:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["source_id"] = SOURCE_ID
    df["download_date"] = datetime.now(timezone.utc).date().isoformat()
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "sdmx_dimensions": dimensions,
            "notes": "OECD Revenue Statistics LAC via SDMX; structure request precedes PER-filtered CSV data query.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
