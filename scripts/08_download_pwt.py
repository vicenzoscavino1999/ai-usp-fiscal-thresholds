"""Download Penn World Table 10.01 from DataverseNL."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.0-stage1"
SOURCE_ID = "PWT_10_01"
SOURCE_URL = "https://dataverse.nl/dataset.xhtml?persistentId=doi:10.34894/QT5BCC"
DATAVERSE_API = "https://dataverse.nl/api/datasets/:persistentId?persistentId=doi:10.34894/QT5BCC"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_json(url: str, retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def request_bytes(url: str, retries: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            return response.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
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
    out_dir = raw_root / "pwt"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "pwt_country_year.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    try:
        catalog = request_json(DATAVERSE_API)
        files = ((catalog or {}).get("data") or {}).get("latestVersion", {}).get("files", [])
        data_file_id = None
        for file_info in files:
            data_file = file_info.get("dataFile", {})
            if data_file.get("filename") == "pwt1001.dta":
                data_file_id = data_file.get("id")
                break
        if data_file_id is None:
            raise RuntimeError("pwt1001.dta not found in Dataverse metadata")
        endpoint = f"https://dataverse.nl/api/access/datafile/{data_file_id}"
        content = request_bytes(endpoint)
        from io import BytesIO

        raw = pd.read_stata(
            BytesIO(content),
            columns=["countrycode", "year", "rgdpo", "rgdpe", "pop", "emp", "avh", "labsh", "rtfpna"],
        )
    except Exception as exc:  # noqa: BLE001
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": DATAVERSE_API,
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": f"PWT Dataverse pull failed after retries: {exc}",
            },
        )
        print(f"PWT pull failed: {exc}")
        return 2

    raw = raw[raw["countrycode"].isin(countries)]
    df = pd.DataFrame(
        {
            "country_id": raw["countrycode"],
            "year": pd.to_numeric(raw["year"], errors="coerce").astype("Int64"),
            "rgdpo": pd.to_numeric(raw.get("rgdpo"), errors="coerce"),
            "rgdpe": pd.to_numeric(raw.get("rgdpe"), errors="coerce"),
            "pop": pd.to_numeric(raw.get("pop"), errors="coerce"),
            "emp": pd.to_numeric(raw.get("emp"), errors="coerce"),
            "avh": pd.to_numeric(raw.get("avh"), errors="coerce"),
            "labsh": pd.to_numeric(raw.get("labsh"), errors="coerce"),
            "rtfpna": pd.to_numeric(raw.get("rtfpna"), errors="coerce"),
            "source_id": SOURCE_ID,
        }
    )
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoint,
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "notes": "PWT 10.01 Stata .dta via DataverseNL API.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
