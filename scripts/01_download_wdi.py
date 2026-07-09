"""Download WDI country-year indicators for the raw WDI table."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_VERSION = "0.1.2-stage1"
SOURCE_ID = "WDI"
SOURCE_URL = "https://api.worldbank.org/v2"
INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP (current US$)",
    "NY.GDP.MKTP.CN": "GDP (current LCU)",
    "NY.GDP.MKTP.KN": "GDP (constant LCU)",
    "NY.GDP.MKTP.KD.ZG": "GDP growth (annual %)",
    "NY.GDP.PCAP.CD": "GDP per capita (current US$)",
    "SP.POP.TOTL": "Population, total",
    "SP.POP.65UP.TO.ZS": "Population ages 65 and above (% of total)",
    "SP.POP.1564.TO.ZS": "Population ages 15-64 (% of total)",
    "FP.CPI.TOTL": "Consumer price index",
    "NY.GDP.DEFL.ZS": "GDP deflator",
    "PA.NUS.FCRF": "Official exchange rate",
    "PA.NUS.PRVT.PP": "PPP conversion factor, private consumption (LCU per international $)",
    "PA.NUS.PPP": "PPP conversion factor, GDP (LCU per international $)",
    "NE.IMP.GNFS.ZS": "Imports of goods and services (% of GDP)",
    "NE.CON.TOTL.ZS": "Final consumption expenditure (% of GDP)",
    "GC.TAX.TOTL.GD.ZS": "Tax revenue (% of GDP)",
    "GC.REV.XGRT.GD.ZS": "Revenue, excluding grants (% of GDP)",
    "IT.NET.USER.ZS": "Individuals using the Internet (% of population)",
    "IT.CEL.SETS.P2": "Mobile cellular subscriptions (per 100 people)",
    "IT.NET.BBND.P2": "Fixed broadband subscriptions (per 100 people)",
    "IT.NET.SECR.P6": "Secure Internet servers (per 1 million people)",
    "EG.ELC.ACCS.ZS": "Access to electricity (% of population)",
    "GB.XPD.RSDV.GD.ZS": "Research and development expenditure (% of GDP)",
}


def parse_countries(value: str) -> list[str]:
    return [c.strip().upper() for c in value.split(",") if c.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_json(url: str, params: dict[str, str], retries: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
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
    countries = parse_countries(args.countries)
    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "wdi"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "wdi_country_year.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    rows: list[dict[str, object]] = []
    endpoints: list[str] = []
    for country in countries:
        for code, fallback_name in INDICATORS.items():
            url = f"{SOURCE_URL}/country/{country}/indicator/{code}"
            params = {"format": "json", "per_page": "20000"}
            endpoints.append(requests.Request("GET", url, params=params).prepare().url or url)
            data = get_json(url, params)
            if not isinstance(data, list) or len(data) < 2 or data[1] is None:
                continue
            for item in data[1]:
                iso3 = item.get("countryiso3code") or country
                year = item.get("date")
                rows.append(
                    {
                        "country_id": iso3,
                        "indicator_code": code,
                        "indicator_name": (item.get("indicator") or {}).get("value") or fallback_name,
                        "year": int(year) if year is not None else None,
                        "value": item.get("value"),
                        "unit": item.get("unit") or "",
                        "source_id": SOURCE_ID,
                        "download_date": datetime.now(timezone.utc).date().isoformat(),
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        write_metadata(
            out_dir,
            {
                "status": "failed",
                "query_or_endpoint": endpoints,
                "country_filter": countries,
                "year_filter": "all",
                "raw_file_hash": None,
                "notes": "World Bank API returned no rows.",
            },
        )
        return 2
    df = df[["country_id", "indicator_code", "indicator_name", "year", "value", "unit", "source_id", "download_date"]]
    df.to_parquet(out_file, index=False)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": countries,
            "year_filter": "all",
            "raw_file_hash": sha256_file(out_file),
            "notes": "WDI API pull for Plan 01 raw_wdi_indicator.",
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
