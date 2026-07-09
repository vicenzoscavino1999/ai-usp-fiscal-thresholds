"""Build country-level Ookla Speedtest anchors from AWS Open Data tiles.

The public raw data are zoom-16 tiles. For the official 4-country calibration we
store a derived country-level raw table, with exact S3 URLs, local hashes for the
downloaded parquet cache, and a license note. The raw tile cache is internal to
the snapshot and is not part of public archival by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union


SCRIPT_VERSION = "0.1.0-stage4a"
SOURCE_ID = "OOKLA_SPEEDTEST_OPEN_DATA"
AWS_BUCKET_URL = "https://ookla-open-data.s3.amazonaws.com"
NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
ANCHOR_YEAR = 2024
ANCHOR_QUARTER = 4
ANCHOR_PERIOD_START = "2024-10-01"
BENCHMARK_COUNTRIES = [
    "AUT",
    "BEL",
    "CZE",
    "DNK",
    "EST",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "IRL",
    "ITA",
    "LVA",
    "LTU",
    "LUX",
    "NLD",
    "NOR",
    "POL",
    "PRT",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
    "TUR",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_bytes(url: str, retries: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def download_to_cache(url: str, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    payload = request_bytes(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def s3_url(service_type: str, year: int, quarter: int, period_start: str) -> str:
    filename = f"{period_start}_performance_{service_type}_tiles.parquet"
    key = f"parquet/performance/type={service_type}/year={year}/quarter={quarter}/{filename}"
    return f"{AWS_BUCKET_URL}/{quote(key, safe='/=')}"


def list_latest_period(service_type: str) -> dict[str, object] | None:
    prefix = f"parquet/performance/type={service_type}/"
    url = f"{AWS_BUCKET_URL}/?list-type=2&prefix={quote(prefix, safe='/=')}"
    try:
        payload = request_bytes(url)
    except Exception:  # noqa: BLE001
        return None
    root = ET.fromstring(payload)
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    keys = [node.text or "" for node in root.findall(".//s3:Key", ns)]
    periods = []
    for key in keys:
        if not key.endswith(".parquet"):
            continue
        parts = key.split("/")
        year = next((p.split("=", 1)[1] for p in parts if p.startswith("year=")), None)
        quarter = next((p.split("=", 1)[1] for p in parts if p.startswith("quarter=")), None)
        filename = parts[-1]
        if year and quarter and filename[:10].count("-") == 2:
            periods.append({"year": int(year), "quarter": int(quarter), "period_start": filename[:10], "key": key})
    if not periods:
        return None
    return sorted(periods, key=lambda row: (row["year"], row["quarter"]))[-1]


def load_country_geometries(path: Path, countries: list[str]) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    geometries: dict[str, list[object]] = {country: [] for country in countries}
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        candidates = [props.get(key) for key in ["ISO_A3", "ADM0_A3", "GU_A3", "BRK_A3"]]
        iso3 = next((code for code in candidates if code in geometries), None)
        if iso3:
            geometries[iso3].append(shape(feature["geometry"]))
    missing = [country for country, polys in geometries.items() if not polys]
    if missing:
        raise RuntimeError(f"Natural Earth geometry missing ISO_A3: {missing}")
    return {country: unary_union(polys) for country, polys in geometries.items()}


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return math.nan
    x = values[valid].to_numpy(dtype=float)
    w = weights[valid].to_numpy(dtype=float)
    order = np.argsort(x)
    x = x[order]
    w = w[order]
    cutoff = 0.5 * w.sum()
    return float(x[np.searchsorted(np.cumsum(w), cutoff, side="left")])


def aggregate_service(path: Path, service_type: str, geometries: dict[str, object]) -> list[dict[str, object]]:
    cols = ["tile_x", "tile_y", "avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"]
    df = pd.read_parquet(path, columns=cols)
    df = df.dropna(subset=["tile_x", "tile_y", "avg_d_kbps", "tests"]).copy()
    rows: list[dict[str, object]] = []
    xs = df["tile_x"].to_numpy(dtype=float)
    ys = df["tile_y"].to_numpy(dtype=float)
    for iso3, geom in geometries.items():
        minx, miny, maxx, maxy = geom.bounds
        bbox = (xs >= minx) & (xs <= maxx) & (ys >= miny) & (ys <= maxy)
        if not bbox.any():
            sub = df.iloc[0:0]
        else:
            candidate = df.loc[bbox].copy()
            inside = contains_xy(geom, candidate["tile_x"].to_numpy(dtype=float), candidate["tile_y"].to_numpy(dtype=float))
            sub = candidate.loc[inside].copy()
        rows.append(
            {
                "country_id": iso3,
                "service_type": service_type,
                "download_median_mbps": weighted_median(sub["avg_d_kbps"] / 1000.0, sub["tests"]),
                "upload_median_mbps": weighted_median(sub["avg_u_kbps"] / 1000.0, sub["tests"]),
                "latency_median_ms": weighted_median(sub["avg_lat_ms"], sub["tests"]),
                "download_mean_mbps_test_weighted": (
                    float(np.average(sub["avg_d_kbps"] / 1000.0, weights=sub["tests"])) if len(sub) else math.nan
                ),
                "tile_count": int(len(sub)),
                "tests": int(pd.to_numeric(sub["tests"], errors="coerce").fillna(0).sum()) if len(sub) else 0,
                "devices": int(pd.to_numeric(sub["devices"], errors="coerce").fillna(0).sum()) if len(sub) else 0,
                "aggregation_method": "country polygon contains tile centroid; test-weighted median of tile avg_d_kbps",
                "source_id": SOURCE_ID,
            }
        )
    return rows


def write_metadata(out_dir: Path, payload: dict[str, object]) -> None:
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://registry.opendata.aws/speedtest-global-performance/",
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        **payload,
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite target files inside --raw-root.")
    parser.add_argument("--year", type=int, default=ANCHOR_YEAR)
    parser.add_argument("--quarter", type=int, default=ANCHOR_QUARTER)
    parser.add_argument("--period-start", default=ANCHOR_PERIOD_START)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    out_dir = raw_root / "ookla"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "ookla_speedtest.parquet"
    if out_file.exists() and not args.overwrite:
        print(f"{out_file} exists; raw snapshot is immutable")
        return 0

    requested = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    countries = sorted(set(requested + BENCHMARK_COUNTRIES))
    ne_path = out_dir / "reference" / "ne_50m_admin_0_countries.geojson"
    download_to_cache(NATURAL_EARTH_URL, ne_path, args.overwrite)
    geometries = load_country_geometries(ne_path, countries)

    endpoints: list[str] = [NATURAL_EARTH_URL]
    hashes: dict[str, str] = {"natural_earth": sha256_file(ne_path)}
    latest = {service: list_latest_period(service) for service in ["fixed", "mobile"]}
    rows: list[dict[str, object]] = []
    for service in ["fixed", "mobile"]:
        service_periods = [
            {"year": args.year, "quarter": args.quarter, "period_start": args.period_start, "role": "anchor_2024q4"}
        ]
        latest_period = latest.get(service)
        if latest_period and (
            int(latest_period["year"]) != args.year or int(latest_period["quarter"]) != args.quarter
        ):
            service_periods.append(
                {
                    "year": int(latest_period["year"]),
                    "quarter": int(latest_period["quarter"]),
                    "period_start": str(latest_period["period_start"]),
                    "role": "latest_available",
                }
            )
        for period in service_periods:
            url = s3_url(service, int(period["year"]), int(period["quarter"]), str(period["period_start"]))
            endpoints.append(url)
            cache = out_dir / "cache" / f"{period['period_start']}_performance_{service}_tiles.parquet"
            download_to_cache(url, cache, args.overwrite)
            hashes[f"ookla_{service}_{period['year']}q{period['quarter']}"] = sha256_file(cache)
            for row in aggregate_service(cache, service, geometries):
                row.update(
                    {
                        "year": int(period["year"]),
                        "quarter": int(period["quarter"]),
                        "period_start": str(period["period_start"]),
                        "period_role": period["role"],
                        "source_url": url,
                        "benchmark_set_member": row["country_id"] in BENCHMARK_COUNTRIES,
                        "requested_country": row["country_id"] in requested,
                    }
                )
                rows.append(row)

    df = pd.DataFrame(rows)
    df.to_parquet(out_file, index=False)
    hashes["ookla_speedtest_parquet"] = sha256_file(out_file)
    write_metadata(
        out_dir,
        {
            "status": "ok",
            "query_or_endpoint": endpoints,
            "country_filter": requested,
            "benchmark_country_filter": BENCHMARK_COUNTRIES,
            "year_filter": f"{args.year}Q{args.quarter}",
            "raw_file_hash": hashes["ookla_speedtest_parquet"],
            "download_file_hashes": hashes,
            "latest_available_period_detected": latest,
            "license_notes": (
                "Ookla Open Data is published under CC BY-NC-SA 4.0. Internal snapshot use is OK "
                "for calibration review; public archiving of raw tile cache is deferred. The derived "
                "gap_index can be archived with attribution and license note."
            ),
            "normalization_inputs": {
                "official_gap_components": ["fixed download median Mbps", "mobile download median Mbps"],
                "aggregation_method": "country polygon contains tile centroid; test-weighted median of tile avg_d_kbps",
                "normalization_scope": "relative_to_frontier_benchmark_set",
                "gap_anchor_period": f"{args.year}Q{args.quarter}",
            },
            "notes": (
                "Country-level speed anchors derived from AWS Ookla parquet tiles. The official Gap uses "
                "the 2024Q4 anchor period; the latest available period is also downloaded and aggregated "
                "for source completeness. Older full history is not downloaded because it is not cheap."
            ),
        },
    )
    print(f"wrote {len(df)} rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
