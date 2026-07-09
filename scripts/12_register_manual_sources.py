"""Create the manual source registry defined by Plan 01 Appendix A.5."""

from __future__ import annotations

import argparse
import shutil
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

SCRIPT_VERSION = "0.1.2-stage1"
SOURCE_ID = "MANUAL_SOURCE_REGISTRY"
SOURCE_URL = "Plan 01 Appendix A.2-A.5"
GRD_SOURCE_URL = "https://www.wider.unu.edu/database/government-revenue-dataset"
GRD_DOI_URL = "https://doi.org/10.35188/UNU-WIDER/GRD-2025"
GRD_CITATION = (
    "UNU-WIDER (2025). UNU-WIDER Government Revenue Dataset. Version 2025. "
    "Helsinki: UNU-WIDER. https://doi.org/10.35188/UNU-WIDER/GRD-2025"
)
GRD_FILES = {
    "central": "UNUWIDERGRD_2025_Central.xlsx",
    "general": "UNUWIDERGRD_2025_General.xlsx",
    "guide": "GRD_User_Guide_2025.pdf",
}

REGISTRY = [
    {
        "source_id": "INEI",
        "country_id": "PER",
        "source_type": "national_statistics",
        "status": "pending_exact_url",
        "source_url": "https://www.inei.gob.pe/",
        "instructions": "Register exact INEI national poverty-line file/API URL as a contrast only; baseline poverty-line LCU conversion uses PIP 8.30 PPP with WDI private-consumption PPP and CPI.",
        "expected_fields": "national poverty line value, currency, periodicity, price base, coverage, publication date",
        "hash_status": "pending_manual_file",
    },
    {
        "source_id": "BCRP",
        "country_id": "PER",
        "source_type": "central_bank_api",
        "status": "api_resolved",
        "source_url": "https://estadisticas.bcrp.gob.pe/estadisticas/series/api",
        "instructions": "BCRPData macro-fiscal contrast series are downloaded by 11_download_national_sources.py.",
        "expected_fields": "series_code, period, value, unit",
        "hash_status": "not_applicable_api",
    },
    {
        "source_id": "MEF_PER",
        "country_id": "PER",
        "source_type": "public_finance",
        "status": "pending_exact_url",
        "source_url": "https://www.mef.gob.pe/",
        "instructions": "Register exact MEF public finance file only if used downstream.",
        "expected_fields": "public finance series by year",
        "hash_status": "pending_manual_file",
    },
    {
        "source_id": "SUNAT_PER",
        "country_id": "PER",
        "source_type": "tax_authority_manual",
        "status": "manual_pending",
        "source_url": "https://www.sunat.gob.pe/estadisticasestudios/",
        "instructions": "Download SUNAT cuadros estadisticos Excel, store original file, compute sha256, and register before use.",
        "expected_fields": "tax revenue, VAT/IGV, income tax, excise, refunds, year",
        "hash_status": "pending_manual_file",
    },
    {
        "source_id": "SEDLAC_CEDLAS",
        "country_id": "PER",
        "source_type": "regional_poverty_labor_manual",
        "status": "manual_pending",
        "source_url": "https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/sedlac/",
        "instructions": "Download CEDLAS SEDLAC statistics Excel files manually; register original file path and sha256 before use.",
        "expected_fields": "survey_year, welfare_concept, poverty_headcount, poverty_gap, gini, deciles, informality",
        "hash_status": "pending_manual_file",
    },
    {
        "source_id": "GRD_UNU_WIDER_2025",
        "country_id": "ALL",
        "source_type": "fiscal_manual_fallback",
        "status": "manual_pending",
        "source_url": GRD_SOURCE_URL,
        "instructions": "If HDX lacks the Nov 2025 mirror, download GRD 2025 Excel/Stata from UNU-WIDER and register sha256.",
        "expected_fields": "country, year, total revenue, tax revenue, non-resource revenue, government level",
        "hash_status": "pending_manual_file",
    },
    {
        "source_id": "FRONTIER_NON_EU_AI_ADOPTION_USA",
        "country_id": "ALL_BENCHMARK_ECONOMIES",
        "source_type": "frontier_manual_benchmark",
        "status": "manual_pending",
        "source_url": "US Census AI Supplement or other approved non-EU benchmark source",
        "instructions": "Register non-EU AI adoption benchmark files manually; benchmark-set selection remains a Phase 1 calibration decision.",
        "expected_fields": "country_id, year, adoption_proxy, unit, survey_population",
        "hash_status": "pending_manual_file",
    },
    {"source_id": "INE_CHILE", "country_id": "CHL", "source_type": "national_statistics", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "BCCH", "country_id": "CHL", "source_type": "central_bank", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "DIPRES", "country_id": "CHL", "source_type": "public_finance", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "SII", "country_id": "CHL", "source_type": "tax_authority", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "DANE", "country_id": "COL", "source_type": "national_statistics", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "BANREP", "country_id": "COL", "source_type": "central_bank", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "MHCP_COL", "country_id": "COL", "source_type": "public_finance", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "DIAN", "country_id": "COL", "source_type": "tax_authority", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "INEGI", "country_id": "MEX", "source_type": "national_statistics", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "BANXICO", "country_id": "MEX", "source_type": "central_bank", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "SHCP", "country_id": "MEX", "source_type": "public_finance", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
    {"source_id": "SAT", "country_id": "MEX", "source_type": "tax_authority", "status": "pending_exact_url", "source_url": "", "instructions": "", "expected_fields": "", "hash_status": "pending_manual_file"},
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def is_unnamed(value: object) -> bool:
    return pd.isna(value) or str(value).startswith("Unnamed:")


def find_col(columns: pd.Index, *parts: str) -> object:
    expected = [part.lower() for part in parts]
    for column in columns:
        values = column if isinstance(column, tuple) else (column,)
        cleaned = [str(value).strip() for value in values if not is_unnamed(value)]
        lowered = [value.lower() for value in cleaned]
        pos = 0
        for want in expected:
            while pos < len(lowered) and lowered[pos] != want:
                pos += 1
            if pos == len(lowered):
                break
            pos += 1
        else:
            return column
    raise KeyError(" / ".join(parts))


def optional_col(columns: pd.Index, *parts: str) -> object | None:
    try:
        return find_col(columns, *parts)
    except KeyError:
        return None


def read_grd_sheet(path: Path, sheet: str, countries: list[str], government_level: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=[0, 1, 2])
    columns = raw.columns
    unit = "lcu_mn" if sheet == "LCU" else "gdp_ratio"
    mapping = {
        "database_source": find_col(columns, "Database source"),
        "government_reported": find_col(columns, "Govern-ment"),
        "data_status_code": find_col(columns, "datastatuscode"),
        "identifier": find_col(columns, "identifier"),
        "country_name": find_col(columns, "country"),
        "country_id": find_col(columns, "iso"),
        "data_status": find_col(columns, "Data status"),
        "fiscal_year": find_col(columns, "Fiscal year"),
        "year": find_col(columns, "year"),
        "region": find_col(columns, "Reg"),
        "income_group": find_col(columns, "Inc"),
        "currency": find_col(columns, "currency"),
        "gdp_lcu_mn": find_col(columns, "GDP lcu mn"),
        "common_gdp_series": find_col(columns, "Common GDP Series"),
        "revenue_data_scalar": find_col(columns, "Revenue Data Scalar"),
        "total_revenue_including_grants_inc_sc": find_col(columns, "Total Revenue", "Including Grants", "Inc SC"),
        "total_revenue_including_grants_ex_sc": find_col(columns, "Total Revenue", "Including Grants", "Ex SC"),
        "total_revenue_excluding_grants_inc_sc": find_col(columns, "Total Revenue", "Excluding Grants", "Inc SC"),
        "total_revenue_excluding_grants_ex_sc": find_col(columns, "Total Revenue", "Excluding Grants", "Ex SC"),
        "tax_revenue_including_sc": find_col(columns, "Taxes", "Including SC"),
        "tax_revenue_excluding_sc": find_col(columns, "Taxes", "Excluding SC"),
        "total_resource_revenue": find_col(columns, "Total Resource Revenue"),
        "total_non_resource_revenue_inc_sc": find_col(columns, "Total Non-Resource Revenue (inc SC)"),
        "resource_tax_revenue": find_col(columns, "Resource Taxes"),
        "non_resource_tax_revenue_including_sc": find_col(columns, "Non-Resource Tax", "Including SC"),
        "non_resource_tax_revenue_excluding_sc": find_col(columns, "Non-Resource Tax", "Excluding SC"),
        "general_notes": optional_col(columns, "General Notes"),
        "caution1": optional_col(columns, "Caution1 Accuracy, Quality or Comparability of data is questionable."),
        "caution1_notes": optional_col(columns, "Caution 1  Notes"),
        "caution2": optional_col(columns, "Caution2 Resource Revenues / taxes are significant but cannot be isolated from total revenues / taxes"),
        "caution3": optional_col(columns, "Caution3 Un-excluded Resource Revenue are Marginal, but Non-Negligible"),
        "resource_revenue_notes": optional_col(columns, "Resource Revenue Notes"),
        "caution4": optional_col(columns, "Caution 4 Inconsistencies with Social Contributions"),
        "social_contributions_notes": optional_col(columns, "Social contributions notes"),
    }
    out = pd.DataFrame()
    for name, column in mapping.items():
        out[name] = pd.NA if column is None else raw[column]
    out = out[out["country_id"].isin(countries)].copy()
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out = out[out["year"].notna()].copy()
    numeric_cols = [
        "fiscal_year",
        "gdp_lcu_mn",
        "common_gdp_series",
        "revenue_data_scalar",
        "total_revenue_including_grants_inc_sc",
        "total_revenue_including_grants_ex_sc",
        "total_revenue_excluding_grants_inc_sc",
        "total_revenue_excluding_grants_ex_sc",
        "tax_revenue_including_sc",
        "tax_revenue_excluding_sc",
        "total_resource_revenue",
        "total_non_resource_revenue_inc_sc",
        "resource_tax_revenue",
        "non_resource_tax_revenue_including_sc",
        "non_resource_tax_revenue_excluding_sc",
    ]
    for column in numeric_cols:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["government_level"] = government_level
    out["unit"] = unit
    out["canonical_total_revenue"] = out["total_revenue_excluding_grants_ex_sc"]
    out["canonical_tax_revenue"] = out["tax_revenue_excluding_sc"]
    out["canonical_mapping_note"] = (
        "GRD User Guide 2025 advises most users to rely on revenue and tax figures "
        "exclusive of social contributions for completeness and comparability. "
        "The canonical total-revenue field also excludes grants for domestic fiscal-capacity use; "
        "all total-revenue variants from the file are retained."
    )
    out["source_excel_file"] = path.name
    out["source_sheet"] = sheet
    out["source_id"] = "GRD"
    return out


def register_grd_2025(raw_root: Path, source_dir: Path, countries: list[str]) -> dict[str, object]:
    out_dir = raw_root / "grd"
    out_dir.mkdir(parents=True, exist_ok=True)
    source_paths = {key: source_dir / filename for key, filename in GRD_FILES.items()}
    missing = [str(path) for path in source_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing GRD manual files: " + "; ".join(missing))
    for path in source_paths.values():
        copy_file(path, out_dir / path.name)

    frames = []
    for level, filename in [("central_government", GRD_FILES["central"]), ("general_government", GRD_FILES["general"])]:
        workbook = out_dir / filename
        for sheet in ["LCU", "PCTGDP"]:
            frames.append(read_grd_sheet(workbook, sheet, countries, level))
    df = pd.concat(frames, ignore_index=True)
    df["download_date"] = datetime.now(timezone.utc).date().isoformat()
    df["grd_version"] = "2025"
    for column in df.select_dtypes(include=["object"]).columns:
        df[column] = df[column].astype("string")
    out_file = out_dir / "grd_revenue.parquet"
    df.to_parquet(out_file, index=False)

    file_hashes = {
        "UNUWIDERGRD_2025_Central.xlsx": sha256_file(out_dir / GRD_FILES["central"]),
        "UNUWIDERGRD_2025_General.xlsx": sha256_file(out_dir / GRD_FILES["general"]),
        "GRD_User_Guide_2025.pdf": sha256_file(out_dir / GRD_FILES["guide"]),
        "grd_revenue.parquet": sha256_file(out_file),
    }
    row_counts = (
        df.groupby(["country_id", "government_level", "unit"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["country_id", "government_level", "unit"])
    )
    metadata = {
        "source_id": "GRD",
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": GRD_SOURCE_URL,
        "query_or_endpoint": "Manual author download from UNU-WIDER GRD 2025 form",
        "country_filter": countries,
        "year_filter": f"{int(df['year'].min())}-{int(df['year'].max())}",
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        "status": "ok",
        "version": "2025",
        "raw_file_hash": file_hashes["grd_revenue.parquet"],
        "download_file_hashes": file_hashes,
        "raw_file_hashes": file_hashes,
        "source_files": list(file_hashes),
        "official_citation": GRD_CITATION,
        "doi": GRD_DOI_URL,
        "license_notes": "Manual author download after UNU-WIDER form completion; observe UNU-WIDER GRD terms for redistribution.",
        "mapping_notes": {
            "guide_file": GRD_FILES["guide"],
            "guide_basis": (
                "GRD User Guide 2025 says most users are advised to rely on revenue and tax "
                "figures exclusive of social contributions due to completeness and comparability."
            ),
            "canonical_total_revenue": "Total Revenue / Excluding Grants / Ex SC",
            "canonical_tax_revenue": "Taxes / Excluding SC",
            "unit_rows": {"LCU": "lcu_mn", "PCTGDP": "gdp_ratio"},
        },
        "row_counts_by_country_level_unit": row_counts.to_dict(orient="records"),
        "notes": "UNU-WIDER GRD 2025 manually registered by author; central and general workbooks converted to one filtered parquet retaining government_level.",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def grd_registration_payload(raw_root: Path) -> dict[str, object] | None:
    metadata_path = raw_root / "grd" / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if metadata.get("source_id") != "GRD" or metadata.get("status") != "ok":
        return None
    return metadata


def apply_grd_registry_status(rows: list[dict[str, str]], raw_root: Path) -> None:
    metadata = grd_registration_payload(raw_root)
    if not metadata:
        return
    hashes = metadata.get("download_file_hashes") or {}
    for row in rows:
        if row.get("source_id") == "GRD_UNU_WIDER_2025":
            row["status"] = "ok"
            row["source_url"] = str(metadata.get("source_url") or GRD_SOURCE_URL)
            row["instructions"] = (
                "GRD 2025 manual files registered and converted to grd/grd_revenue.parquet. "
                "Use metadata.json for file-level SHA-256 hashes and mapping notes."
            )
            row["expected_fields"] = "country, year, total revenue, tax revenue, non-resource revenue, government_level"
            row["hash_status"] = "sha256_registered"
            row["registered_files"] = json.dumps(hashes, sort_keys=True)
            row["official_citation"] = str(metadata.get("official_citation") or GRD_CITATION)


def include_row(row: dict[str, str], countries: list[str]) -> bool:
    country_id = row["country_id"]
    return country_id in countries or country_id in {"ALL", "ALL_BENCHMARK_ECONOMIES"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default="PER,CHL,COL,MEX")
    parser.add_argument("--raw-root", default=None, help="Raw snapshot root. Defaults to data/raw.")
    parser.add_argument("--register-grd-2025", action="store_true", help="Copy and convert author-downloaded GRD 2025 files into raw-root/grd.")
    parser.add_argument("--grd-source-dir", default=None, help="Directory containing UNUWIDERGRD_2025_* files.")
    args = parser.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    root = Path(__file__).resolve().parents[1]
    metadata_dir = root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    yml_file = metadata_dir / "manual_source_registry.yml"
    raw_root = Path(args.raw_root) if args.raw_root else root / "data" / "raw"
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    if args.register_grd_2025:
        if not args.grd_source_dir:
            raise SystemExit("--grd-source-dir is required with --register-grd-2025")
        register_grd_2025(raw_root, Path(args.grd_source_dir), countries)
    out_dir = raw_root / "manual"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "manual_source_registry.parquet"

    rows = [row for row in REGISTRY if include_row(row, countries)]
    apply_grd_registry_status(rows, raw_root)
    yml_payload = {
        "source_id": SOURCE_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Manual registry for sources without public API or with source-side file selection. "
            "Rows marked manual_pending introduce no data values into the pilot snapshot."
        ),
        "sources": rows,
    }
    yml_file.write_text(yaml.safe_dump(yml_payload, sort_keys=False), encoding="utf-8")
    df = pd.DataFrame(rows)
    df.to_parquet(out_file, index=False)
    payload = {
        "source_id": SOURCE_ID,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "query_or_endpoint": str(yml_file.relative_to(root)),
        "country_filter": countries,
        "year_filter": "not_applicable",
        "raw_file_hash": sha256_file(out_file),
        "script_name": Path(__file__).name,
        "script_version": SCRIPT_VERSION,
        "status": "ok",
        "manual_pending_count": int((df["status"] == "manual_pending").sum()) if not df.empty else 0,
        "notes": "Created metadata/manual_source_registry.yml and mirrored it as parquet for the snapshot manifest.",
    }
    (out_dir / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {len(df)} registry rows to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
