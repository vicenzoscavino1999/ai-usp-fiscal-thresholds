"""Download ITU digital indicators for all economies.

The legacy WDI fallback is retained for audit/frontier inputs that already feed
AIPI, while the ITU DataHub coverage collection is added for the official
excluded-indicator Gap construction.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.2.0-stage4a"
SOURCE_ID = "ITU_DATAHUB_WDI_FALLBACK"
SOURCE_URL = "https://api.worldbank.org/v2"
ITU_DATAHUB_COVERAGE_URL = "https://api.datahub.itu.int/v2/data/download/byid/100095/iscollection/true"
WDI_INDICATORS = {
    "IT.NET.USER.ZS": "Individuals using the Internet (% of population)",
    "IT.CEL.SETS.P2": "Mobile cellular subscriptions (per 100 people)",
    "IT.NET.BBND.P2": "Fixed broadband subscriptions (per 100 people)",
    "IT.NET.SECR.P6": "Secure Internet servers (per 1 million people)",
}
ITU_COVERAGE_SERIES = {
    194: "ITU_COVERAGE_MOBILE_CELLULAR",
    430: "ITU_COVERAGE_AT_LEAST_3G",
    19306: "ITU_COVERAGE_LTE_WIMAX",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_json(url: str, params: dict[str, str], retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=90)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def get_bytes(url: str, retries: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
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


def is_full_country_snapshot(out_file: Path, metadata_path: Path) -> bool:
    metadata = load_json(metadata_path)
    if metadata.get("country_filter") != "ALL":
        return False
    if not out_file.exists():
        return False
    try:
        df = pd.read_parquet(out_file, columns=["country_id"])
        return df["country_id"].dropna().astype(str).nunique() > 4
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the target raw file inside --raw-root.")
    args = parser.parse_args()
    declared_countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "itu"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "itu_digital.parquet"
    metadata_path = out_dir / "metadata.json"
    if not args.overwrite and is_full_country_snapshot(out_file, metadata_path):
        print(f"{out_file} exists with country_filter=ALL; raw snapshot is immutable")
        return 0
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    rows: list[dict[str, object]] = []
    endpoints: list[str] = []
    for code, fallback_name in WDI_INDICATORS.items():
        url = f"{SOURCE_URL}/country/all/indicator/{code}"
        params = {"format": "json", "per_page": "20000"}
        endpoints.append(requests.Request("GET", url, params=params).prepare().url or url)
        data = get_json(url, params)
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            continue
        for item in data[1]:
            iso3 = item.get("countryiso3code")
            if not iso3:
                continue
            rows.append(
                {
                    "country_id": iso3,
                    "country_name": (item.get("country") or {}).get("value"),
                    "year": int(item.get("date")) if item.get("date") is not None else None,
                    "indicator_code": code,
                    "indicator_name": (item.get("indicator") or {}).get("value") or fallback_name,
                    "value": item.get("value"),
                    "unit": item.get("unit") or "",
                    "source_id": "WDI_FALLBACK_ITU",
                    "download_date": datetime.now(timezone.utc).date().isoformat(),
                    "aipi_overlap_status": "overlaps_aipi_component",
                }
            )

    coverage_status = "ok"
    coverage_hash = None
    coverage_file = None
    try:
        payload = get_bytes(ITU_DATAHUB_COVERAGE_URL)
        coverage_hash = hashlib.sha256(payload).hexdigest()
        endpoints.append(ITU_DATAHUB_COVERAGE_URL)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise RuntimeError("ITU DataHub coverage ZIP has no CSV member")
            coverage_file = csv_names[0]
            coverage = pd.read_csv(io.BytesIO(zf.read(coverage_file)), encoding="utf-8-sig")
        coverage = coverage[pd.to_numeric(coverage["seriesID"], errors="coerce").isin(ITU_COVERAGE_SERIES)].copy()
        for _, item in coverage.iterrows():
            series_id = int(item["seriesID"])
            iso3 = item.get("entityIso")
            if not isinstance(iso3, str) or not iso3:
                continue
            rows.append(
                {
                    "country_id": iso3,
                    "country_name": item.get("entityName"),
                    "year": int(item.get("dataYear")) if pd.notna(item.get("dataYear")) else None,
                    "indicator_code": ITU_COVERAGE_SERIES[series_id],
                    "indicator_name": item.get("seriesName"),
                    "value": pd.to_numeric(item.get("dataValue"), errors="coerce"),
                    "unit": item.get("seriesUnits") or "%",
                    "source_id": "ITU_DATAHUB",
                    "download_date": datetime.now(timezone.utc).date().isoformat(),
                    "aipi_overlap_status": "verified_excluded_from_aipi_components",
                }
            )
    except Exception as exc:  # noqa: BLE001
        coverage_status = f"failed: {exc}"
    df = pd.DataFrame(rows)
    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": "ALL",
                "declared_pilot_countries": declared_countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "ITU/WDI digital pull returned no rows for country/all.",
            },
        )
        return 2
    df = df[
        [
            "country_id",
            "country_name",
            "year",
            "indicator_code",
            "indicator_name",
            "value",
            "unit",
            "source_id",
            "download_date",
            "aipi_overlap_status",
        ]
    ]
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": "ALL",
            "declared_pilot_countries": declared_countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "n_countries": int(df["country_id"].nunique()),
            "itu_datahub_coverage": {
                "status": coverage_status,
                "collection_url": ITU_DATAHUB_COVERAGE_URL,
                "zip_sha256": coverage_hash,
                "csv_member": coverage_file,
                "series": ITU_COVERAGE_SERIES,
                "aipi_exclusion_verification": (
                    "AIPI Note digital-infrastructure component list includes internet users, fixed telephone, "
                    "mobile subscribers, broadband subscriptions, wireless broadband, cost of internet access, "
                    "secure servers and e-commerce/public-service proxies; it does not list mobile-network "
                    "coverage technology series."
                ),
            },
            "notes": (
                "Plan 01 rule keeps frontier/benchmark inputs unfiltered. This script captures all economies "
                "even when --countries is passed. ITU DataHub coverage series are the official excluded "
                "digital Gap inputs; legacy WDI fallback rows are retained only for audit/frontier context."
            ),
        },
    )
    print(f"wrote {len(df)} rows across {df['country_id'].nunique()} countries to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
