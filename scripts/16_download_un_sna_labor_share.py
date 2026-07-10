"""Fetch the post-baseline UN SNA raw labor-share robustness input.

The download is isolated from the official dataset snapshots. It preserves the
exact UNdata ZIP responses, derives a matched CoE/market-price-GDP series, and
records hashes in a dedicated extension manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "robustness-lsraw-v1"
SOURCE_ID = "UN_SNA"
COUNTRIES = {
    "PER": {"m49": "604", "expected_latest": 2023, "national_cross_check": "INEI 2025E: 0.2825"},
    "CHL": {"m49": "152", "expected_latest": 2023, "national_cross_check": "BCCh 2024: 0.3948"},
    "COL": {"m49": "170", "expected_latest": 2024, "national_cross_check": "DANE 2024p: 0.3369"},
    "MEX": {"m49": "484", "expected_latest": 2023, "national_cross_check": "INEGI 2024: 0.3004"},
}
GROUPS = {"compensation_of_employees": "401", "gdp_market_prices": "101"}
BASE_URL = "https://data.un.org/Handlers/DownloadHandler.ashx"
TABLE_URL = "https://data.un.org/Data.aspx?d=SNA&f=group_code%3A401"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def endpoint(m49: str, group_code: str) -> str:
    return (
        f"{BASE_URL}?DataFilter=country_code%3A{m49}%3Bgroup_code%3A{group_code}"
        "&DataMartId=SNA&Format=csv"
    )


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ai-usp-fiscal-thresholds/LS-raw-extension"})
    with urlopen(request, timeout=120) as response:
        payload = response.read()
    if not payload.startswith(b"PK"):
        raise RuntimeError(f"UNdata response is not a ZIP archive: {url}")
    return payload


def read_undata_zip(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"Expected one CSV in UNdata ZIP, found {csv_names}")
        frame = pd.read_csv(archive.open(csv_names[0]))
    frame["Year"] = pd.to_numeric(frame["Year"], errors="coerce")
    frame = frame[frame["Year"].notna()].copy()
    frame["Year"] = frame["Year"].astype(int)
    frame["Series"] = pd.to_numeric(frame["Series"], errors="coerce")
    frame["SNA System"] = pd.to_numeric(frame["SNA System"], errors="coerce")
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    return frame


def canonical_rows(frame: pd.DataFrame, *, concept: str) -> pd.DataFrame:
    common = (
        frame["SNA System"].eq(2008)
        & frame["Series"].eq(1000)
        & frame["Fiscal Year Type"].eq("Western calendar year")
    )
    if concept == "compensation_of_employees":
        selected = frame[
            common
            & frame["SNA93 Item Code"].eq("D.1")
            & frame["Sub Group"].eq("II.1.1 Generation of income account - Uses")
        ].copy()
    elif concept == "gdp_market_prices":
        selected = frame[
            common
            & frame["SNA93 Item Code"].eq("B.1*g")
            & frame["Sub Group"].eq("Expenditures of the gross domestic product")
        ].copy()
    else:
        raise ValueError(concept)
    if selected.empty or selected["Year"].duplicated().any():
        raise RuntimeError(f"UNdata canonical-row selection failed for {concept}")
    return selected[["Year", "Currency", "Value"]].sort_values("Year")


def fetch(output_dir: Path, manifest_path: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded_at = datetime.now(timezone.utc).isoformat()
    download_hashes: dict[str, str] = {}
    endpoints: list[str] = []
    series_frames: list[pd.DataFrame] = []

    for country, config in COUNTRIES.items():
        concept_frames: dict[str, pd.DataFrame] = {}
        concept_endpoints: dict[str, str] = {}
        for concept, group_code in GROUPS.items():
            url = endpoint(config["m49"], group_code)
            payload = download(url)
            file_name = f"UNdata_SNA_{country}_group_{group_code}.zip"
            path = output_dir / file_name
            path.write_bytes(payload)
            download_hashes[file_name] = sha256_bytes(payload)
            endpoints.append(url)
            concept_endpoints[concept] = url
            concept_frames[concept] = canonical_rows(read_undata_zip(payload), concept=concept)

        coe = concept_frames["compensation_of_employees"].rename(
            columns={"Currency": "coe_currency", "Value": "compensation_of_employees_lcu"}
        )
        gdp = concept_frames["gdp_market_prices"].rename(
            columns={"Currency": "gdp_currency", "Value": "gdp_market_prices_lcu"}
        )
        matched = coe.merge(gdp, on="Year", how="inner", validate="one_to_one")
        if matched.empty or not (matched["coe_currency"] == matched["gdp_currency"]).all():
            raise RuntimeError(f"CoE/GDP matching or currency validation failed for {country}")
        matched["labor_share_raw"] = (
            matched["compensation_of_employees_lcu"] / matched["gdp_market_prices_lcu"]
        )
        matched["country_id"] = country
        matched["source_year"] = matched["Year"].astype(int)
        matched["target_year"] = 2024
        latest_year = int(matched["source_year"].max())
        if latest_year != int(config["expected_latest"]):
            raise RuntimeError(
                f"Unexpected latest matched year for {country}: {latest_year}; "
                f"expected {config['expected_latest']}"
            )
        matched["is_latest_available"] = matched["source_year"].eq(latest_year)
        matched["carried_forward_to_2024"] = matched["is_latest_available"] & matched["source_year"].lt(2024)
        matched["source_id"] = SOURCE_ID
        matched["coe_endpoint"] = concept_endpoints["compensation_of_employees"]
        matched["gdp_endpoint"] = concept_endpoints["gdp_market_prices"]
        matched["national_cross_check_note"] = config["national_cross_check"]
        series_frames.append(matched.drop(columns=["Year"]))

    series = pd.concat(series_frames, ignore_index=True).sort_values(["country_id", "source_year"])
    parquet_path = output_dir / "un_sna_labor_share_raw.parquet"
    series.to_parquet(parquet_path, index=False)
    download_hashes[parquet_path.name] = sha256_file(parquet_path)
    latest = series[series["is_latest_available"]].copy()

    metadata = {
        "source_id": SOURCE_ID,
        "snapshot_id": SNAPSHOT_ID,
        "download_date": downloaded_at,
        "source_url": TABLE_URL,
        "query_or_endpoint": endpoints,
        "method": "direct_zip_csv",
        "status": "ok",
        "country_filter": list(COUNTRIES),
        "year_filter": "full matched SNA2008 series; latest common CoE/GDP year used at t0=2024",
        "numerator": "Compensation of employees (D.1), Table 4.1 group_code 401, generation of income account - Uses",
        "denominator": "GDP at market prices (B.1*g), group_code 101; never Table 4.1 balancing item",
        "series_filter": "SNA System=2008; Series=1000; Western calendar year",
        "raw_file_hash": download_hashes[parquet_path.name],
        "download_file_hashes": download_hashes,
        "latest_values": latest[
            [
                "country_id",
                "source_year",
                "target_year",
                "carried_forward_to_2024",
                "compensation_of_employees_lcu",
                "gdp_market_prices_lcu",
                "labor_share_raw",
                "national_cross_check_note",
            ]
        ].to_dict(orient="records"),
        "script_name": Path(__file__).name,
        "script_version": "1.0.0-post-baseline-extension",
        "notes": (
            "New input series for the declared LS raw-vs-adjusted robustness extension. "
            "It is isolated from every official baseline snapshot."
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
                "source_dir": "un_sna_labor_share",
                "source_id": SOURCE_ID,
                "status": "ok",
                "metadata_path": f"{relative_output}/metadata.json",
                "source_url": TABLE_URL,
                "query_or_endpoint": endpoints,
                "raw_file_hash": download_hashes[parquet_path.name],
                "hash_check": "ok",
                "raw_files": [
                    {"path": f"{relative_output}/{name}", "sha256": digest}
                    for name, digest in download_hashes.items()
                ],
            }
        ],
        "summary": {"ok": 1, "manual_pending": 0, "failed": 0, "missing": 0},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "raw_snapshots" / SNAPSHOT_ID / "un_sna_labor_share",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{SNAPSHOT_ID}.json",
    )
    args = parser.parse_args()
    latest = fetch(args.output_dir, args.manifest)
    print(latest[["country_id", "source_year", "carried_forward_to_2024", "labor_share_raw"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
