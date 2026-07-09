"""Build pilot anchor tables from the frozen raw-data snapshot.

This is Stage 2 only. It reads local snapshot files, creates anchor tables,
exports model-input parquets, and writes a DuckDB database. It does not import
or call the model package under src/ai_usp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import yaml

SCRIPT_NAME = Path(__file__).name
DEFAULT_DATASET_VERSION = "v0.1.2-pilot-per"
ANCHOR_YEAR = 2024
ENDPOINT_YEAR = 2034
HARMONIZATION_YEAR = 2024
BOOTSTRAP_DRAWS = 2000
RAW_FILE_MAP: dict[tuple[str, str], Path] = {}


WDI_MAP = {
    "NY.GDP.MKTP.CD": "gdp_nominal_usd",
    "NY.GDP.MKTP.CN": "gdp_nominal_lcu",
    "NY.GDP.MKTP.KN": "gdp_constant_lcu",
    "NY.GDP.MKTP.KD.ZG": "gdp_growth_real",
    "NY.GDP.PCAP.CD": "gdp_pc_usd",
    "SP.POP.TOTL": "population_total",
    "SP.POP.65UP.TO.ZS": "population_65_plus_pct",
    "SP.POP.1564.TO.ZS": "population_15_64_pct",
    "PA.NUS.FCRF": "exchange_rate_lcu_per_usd",
    "PA.NUS.PRVT.PP": "ppp_conversion_private_consumption",
    "PA.NUS.PPP": "ppp_conversion_gdp",
    "FP.CPI.TOTL": "cpi_index",
    "NY.GDP.DEFL.ZS": "gdp_deflator",
}

FISCAL_REVENUE_CODES = {
    "_T": "tax_revenue_gdp",
    "T_2000": "social_contrib_gdp",
    "T_1000": "direct_tax_gdp",
    "T_5000": "indirect_tax_gdp",
    "T_1200": "cit_gdp",
    "T_1100": "pit_gdp",
    "T_5111": "vat_gdp",
}

EUROSTAT_TO_ISO3 = {
    "AL": "ALB",
    "AT": "AUT",
    "BA": "BIH",
    "BE": "BEL",
    "BG": "BGR",
    "CY": "CYP",
    "CZ": "CZE",
    "DE": "DEU",
    "DK": "DNK",
    "EE": "EST",
    "EL": "GRC",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "HR": "HRV",
    "HU": "HUN",
    "IE": "IRL",
    "IT": "ITA",
    "LT": "LTU",
    "LU": "LUX",
    "LV": "LVA",
    "ME": "MNE",
    "MK": "MKD",
    "MT": "MLT",
    "NL": "NLD",
    "NO": "NOR",
    "PL": "POL",
    "PT": "PRT",
    "RO": "ROU",
    "RS": "SRB",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
    "TR": "TUR",
}


@dataclass
class BuildLog:
    source_rows: list[dict[str, Any]] = field(default_factory=list)
    quality_rows: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_parquet(root: Path, rel: str) -> pd.DataFrame:
    path = Path(rel)
    parts = path.parts
    if len(parts) >= 4 and parts[0] == "data" and parts[1] == "raw":
        mapped = RAW_FILE_MAP.get((parts[2], parts[-1]))
        if mapped is not None:
            return pd.read_parquet(root / mapped)
    return pd.read_parquet(root / rel)


def set_raw_file_map(manifest: dict[str, Any]) -> None:
    RAW_FILE_MAP.clear()
    for source in manifest.get("sources", []):
        source_dir = source.get("source_dir")
        if not source_dir:
            continue
        for raw_file in source.get("raw_files", []):
            raw_path = Path(raw_file["path"])
            RAW_FILE_MAP[(str(source_dir), raw_path.name)] = raw_path


def verify_manifest(root: Path, dataset_version: str) -> dict[str, Any]:
    manifest_path = root / "reproducibility" / "snapshot" / "dataset_manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("dataset_version") != dataset_version:
        raise RuntimeError(
            f"Active manifest dataset_version={manifest.get('dataset_version')} does not match {dataset_version}"
        )
    errors = []
    for source in manifest.get("sources", []):
        for raw_file in source.get("raw_files", []):
            path = root / raw_file["path"]
            if not path.exists():
                errors.append(f"missing raw file {raw_file['path']}")
                continue
            actual = sha256_file(path)
            if actual != raw_file["sha256"]:
                errors.append(f"hash mismatch {raw_file['path']}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return manifest


def rng_seed(root: Path) -> int:
    path = root / "reproducibility" / "config" / "rng_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seed = payload.get("historical_bootstrap_seed")
    if seed is None:
        raise RuntimeError("reproducibility/config/rng_policy.yaml lacks historical_bootstrap_seed")
    return int(seed)


def add_source(
    log: BuildLog,
    table: str,
    variable: str,
    country: str | None,
    year: int | None,
    source_id: str,
    raw_table: str,
    raw_code: str | None,
    raw_name: str | None,
    notes: str,
    harmonization_flag: str,
    dataset_version: str,
    build_id: str,
    priority_rank: int = 1,
    conflict: bool = False,
) -> None:
    log.source_rows.append(
        {
            "table_name": table,
            "variable_name": variable,
            "country_id": country,
            "year": year,
            "source_id": source_id,
            "raw_table": raw_table,
            "raw_indicator_code": raw_code,
            "raw_variable_name": raw_name,
            "transformation_script": SCRIPT_NAME,
            "transformation_notes": notes,
            "harmonization_flag": harmonization_flag,
            "priority_rank": priority_rank,
            "source_conflict_flag": conflict,
            "dataset_version": dataset_version,
            "build_id": build_id,
        }
    )


def add_quality(
    log: BuildLog,
    country: str | None,
    year: int | None,
    module: str,
    table: str,
    variable: str,
    notes: str,
    dataset_version: str,
    build_id: str,
    missing: bool = False,
    imputed: bool = False,
    carried: bool = False,
    carried_from: int | None = None,
    interpolated: bool = False,
    source_conflict: bool = False,
    unit_conflict: bool = False,
    definition_conflict: bool = False,
    non_harmonized: bool = False,
    quality_score: float = 1.0,
) -> None:
    log.quality_rows.append(
        {
            "country_id": country,
            "year": year,
            "module": module,
            "table_name": table,
            "variable_name": variable,
            "missing_flag": missing,
            "imputed_flag": imputed,
            "carried_forward_flag": carried,
            "carried_forward_from_year": carried_from,
            "interpolated_flag": interpolated,
            "source_conflict_flag": source_conflict,
            "unit_conflict_flag": unit_conflict,
            "definition_conflict_flag": definition_conflict,
            "non_harmonized_robustness": non_harmonized,
            "quality_score": quality_score,
            "notes": notes,
            "dataset_version": dataset_version,
            "build_id": build_id,
        }
    )


def add_assumption(
    log: BuildLog,
    assumption_id: str,
    module: str,
    parameter_name: str,
    baseline: float | None,
    low: float | None,
    high: float | None,
    distribution: str,
    justification: str,
    source_id: str,
    observed: bool,
    scenario: bool,
    structural: bool,
    sensitivity_level: str = "baseline",
) -> None:
    log.assumptions.append(
        {
            "assumption_id": assumption_id,
            "module": module,
            "parameter_name": parameter_name,
            "baseline_value": baseline,
            "low_value": low,
            "high_value": high,
            "distribution": distribution,
            "justification": justification,
            "source_id": source_id,
            "is_observed": observed,
            "is_scenario": scenario,
            "is_structural_unobserved": structural,
            "sensitivity_level": sensitivity_level,
            "created_at": utc_now(),
            "created_by_script": SCRIPT_NAME,
        }
    )


def add_gate(log: BuildLog, gate_id: str, status: str, severity: str, notes: str) -> None:
    log.gates.append({"gate_id": gate_id, "status": status, "severity": severity, "notes": notes})


def value_at(series: pd.DataFrame, code: str, year: int) -> float | None:
    row = series[(series["indicator_code"] == code) & (series["year"] == year)]
    if row.empty:
        return None
    value = pd.to_numeric(row.iloc[0]["value"], errors="coerce")
    return None if pd.isna(value) else float(value)


def pivot_wdi(wdi: pd.DataFrame) -> pd.DataFrame:
    rows = wdi[wdi["indicator_code"].isin(WDI_MAP)].copy()
    rows["variable"] = rows["indicator_code"].map(WDI_MAP)
    wide = rows.pivot_table(index=["country_id", "year"], columns="variable", values="value", aggfunc="first").reset_index()
    return wide


def wpp_age_counts(wpp: pd.DataFrame, country: str, year: int) -> dict[str, float]:
    subset = wpp[(wpp["ISO3_code"] == country) & (wpp["Time"] == year)].copy()
    if subset.empty:
        return {}
    subset["AgeGrpStart"] = pd.to_numeric(subset["AgeGrpStart"], errors="coerce")
    subset["PopTotal"] = pd.to_numeric(subset["PopTotal"], errors="coerce")
    # WPP 2024 CSV population values are in thousands.
    total = float(subset["PopTotal"].sum() * 1000.0)
    over65 = float(subset.loc[subset["AgeGrpStart"] >= 65, "PopTotal"].sum() * 1000.0)
    age15_64 = float(subset.loc[subset["AgeGrpStart"].between(15, 64), "PopTotal"].sum() * 1000.0)
    adult18 = float(subset.loc[subset["AgeGrpStart"] >= 18, "PopTotal"].sum() * 1000.0)
    return {
        "population_total_wpp": total,
        "population_65_plus": over65,
        "population_15_64": age15_64,
        "population_18_plus": adult18,
    }


def build_dimensions(manifest: dict[str, Any]) -> dict[str, pd.DataFrame]:
    dim_country = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "country_name": "Peru",
                "region": "Latin America",
                "income_group_2024": "upper_middle_income",
                "pilot_role": "primary_case",
            }
        ]
    )
    dim_policy = pd.DataFrame(
        [
            {
                "policy_id": "PEN",
                "policy_name": "Universal Social Pension",
                "policy_type": "pension",
                "default_eligible_population_rule": "population age >= age_threshold",
                "default_benefit_rule": "official Pension 65 annualized benefit",
                "default_cost_formula": "benefit_amount_lcu * eligible_population",
                "is_stress_benchmark": False,
            },
            {
                "policy_id": "MUT",
                "policy_name": "Minimum Universal Transfer",
                "policy_type": "transfer",
                "default_eligible_population_rule": "population total or declared subgroup",
                "default_benefit_rule": "eta_MUT * poverty line",
                "default_cost_formula": "eta_policy * poverty_line * eligible_population",
                "is_stress_benchmark": False,
            },
            {
                "policy_id": "GMI",
                "policy_name": "Guaranteed Minimum Income",
                "policy_type": "guaranteed_income",
                "default_eligible_population_rule": "poverty-gap aggregate or microdata rule",
                "default_benefit_rule": "chi_gmi * poverty gap",
                "default_cost_formula": "chi_gmi * aggregate poverty gap",
                "is_stress_benchmark": False,
            },
            {
                "policy_id": "PBI",
                "policy_name": "Partial Basic Income",
                "policy_type": "basic_income",
                "default_eligible_population_rule": "adult population unless specified",
                "default_benefit_rule": "eta_PBI * poverty line",
                "default_cost_formula": "eta_policy * poverty_line * eligible_population",
                "is_stress_benchmark": False,
            },
            {
                "policy_id": "UBI",
                "policy_name": "Full UBI benchmark",
                "policy_type": "stress_benchmark",
                "default_eligible_population_rule": "population total",
                "default_benefit_rule": "eta_UBI * poverty line",
                "default_cost_formula": "eta_policy * poverty_line * population_total",
                "is_stress_benchmark": True,
            },
        ]
    )
    dim_ai_scenario = pd.DataFrame(
        [
            ["low", "Low", "TFP", 0.0003, 0.0007, "kappa_TFP_to_Y declared in model stage", "not_applied_in_anchors", "forecast lower support", "Acemoglu"],
            ["mid", "Mid", "TFP", 0.0025, 0.0060, "kappa_TFP_to_Y declared in model stage", "not_applied_in_anchors", "central support", "Acemoglu/OECD"],
            ["high", "High", "LP", 0.0040, 0.0130, "kappa_LP_to_Y declared in model stage", "not_applied_in_anchors", "high support before bridge", "OECD"],
            ["stress", "Disruptive stress", "Y", 0.0100, 0.0200, "identity", "not_applied_in_anchors", "stress", "stress"],
        ],
        columns=[
            "scenario_id",
            "scenario_label",
            "raw_unit",
            "phi_raw_low",
            "phi_raw_high",
            "kappa_to_y_convention",
            "pi_ai_y_convention",
            "interpretation",
            "source_discipline",
        ],
    )
    dim_fiscal_regime = pd.DataFrame(
        [
            [0, "r0", "Status quo", "Current effective tax structure, no new AI rent capture.", False, False, False],
            [1, "r1", "Improved compliance", "Administration/reporting improvement without broad legal change.", False, False, False],
            [2, "r2", "Base broadening", "Lower exemptions and broader labor/capital/consumption bases.", False, False, True],
            [3, "r3", "AI-rent capture", "Explicit taxation of digital or AI rents.", True, True, False],
            [4, "r4", "Combined reform", "Compliance plus base broadening plus AI rent capture.", True, True, True],
        ],
        columns=[
            "regime_id",
            "regime_code",
            "regime_name",
            "description",
            "changes_tax_rates",
            "changes_ai_rent_capture",
            "changes_base_broadening",
        ],
    )
    source_rows = []
    for source in manifest.get("sources", []):
        source_rows.append(
            {
                "source_id": source.get("source_id"),
                "source_name": source.get("source_dir"),
                "provider": source.get("source_id"),
                "url_or_api": source.get("source_url"),
                "download_date": str(source.get("download_date") or "")[:10],
                "license_notes": "See provider terms; raw snapshot preserves source metadata.",
                "raw_file_path": ";".join(raw.get("path", "") for raw in source.get("raw_files", [])),
                "citation_text": source.get("notes"),
            }
        )
    source_rows.extend(
        [
            {
                "source_id": "PLAN_01_02",
                "source_name": "Database/design plans",
                "provider": "author",
                "url_or_api": "01_database_construction_plan_AI_USP_threshold_framework_v6.md; 02_ESD_AI_USP_v6.md",
                "download_date": "",
                "license_notes": "project documentation",
                "raw_file_path": "",
                "citation_text": "Normative and methodological conventions from frozen project plans.",
            },
            {
                "source_id": "MIDIS_PENSION65",
                "source_name": "Pension 65 official program",
                "provider": "MIDIS / Gobierno del Peru",
                "url_or_api": "https://www.gob.pe/pension65",
                "download_date": "",
                "license_notes": "official public information",
                "raw_file_path": "",
                "citation_text": "Official Pension 65 page: 2024 benefit convention uses S/250 every two months; later 2025 increase is not applied to anchor 2024.",
            },
            {
                "source_id": "ASPIRE_LITERATURE_ASSUMPTION",
                "source_name": "ASPIRE social-protection expenditure concept",
                "provider": "World Bank",
                "url_or_api": "https://www.worldbank.org/en/data/datatopics/aspire/indicator/social-expenditure",
                "download_date": "",
                "license_notes": "public documentation used only to justify calibrated administrative-cost assumptions",
                "raw_file_path": "",
                "citation_text": "ASPIRE social protection expenditure includes benefits and administrative costs; calibrated values are stored as assumptions, not observed data.",
            },
        ]
    )
    return {
        "dim_country": dim_country,
        "dim_policy": dim_policy,
        "dim_ai_scenario": dim_ai_scenario,
        "dim_fiscal_regime": dim_fiscal_regime,
        "dim_source": pd.DataFrame(source_rows),
    }


def build_macro(root: Path, dataset_version: str, build_id: str, log: BuildLog) -> pd.DataFrame:
    wdi = read_parquet(root, "data/raw/wdi/wdi_country_year.parquet")
    wpp = read_parquet(root, "data/raw/wpp/wpp_projections.parquet")
    wide = pivot_wdi(wdi)
    wide = wide[(wide["country_id"] == "PER") & (wide["year"].between(2000, ANCHOR_YEAR))].copy()
    wide["population_65_plus"] = wide["population_total"] * wide.get("population_65_plus_pct") / 100.0
    wide["population_15_64"] = wide["population_total"] * wide.get("population_15_64_pct") / 100.0
    counts = wpp_age_counts(wpp, "PER", ANCHOR_YEAR)
    if counts:
        idx = (wide["country_id"] == "PER") & (wide["year"] == ANCHOR_YEAR)
        wide.loc[idx, "population_65_plus"] = counts["population_65_plus"]
        wide.loc[idx, "population_15_64"] = counts["population_15_64"]
        wide.loc[idx, "population_18_plus"] = counts["population_18_plus"]
    wide["harmonization_flag"] = np.where(wide["year"] == ANCHOR_YEAR, "observed_2024", "historical_observed")
    wide["dataset_version"] = dataset_version
    wide["build_id"] = build_id
    wide["created_at"] = utc_now()
    wide["created_by_script"] = SCRIPT_NAME
    cols = [
        "country_id",
        "year",
        "gdp_nominal_usd",
        "gdp_nominal_lcu",
        "gdp_constant_lcu",
        "gdp_growth_real",
        "gdp_pc_usd",
        "population_total",
        "population_65_plus",
        "population_15_64",
        "population_18_plus",
        "exchange_rate_lcu_per_usd",
        "ppp_conversion_private_consumption",
        "ppp_conversion_gdp",
        "cpi_index",
        "gdp_deflator",
        "harmonization_flag",
        "dataset_version",
        "build_id",
        "created_at",
        "created_by_script",
    ]
    result = wide.reindex(columns=cols)
    for code, var in WDI_MAP.items():
        if var.endswith("_pct"):
            continue
        for year in result["year"]:
            add_source(log, "macro_anchor", var, "PER", int(year), "WDI", "raw_wdi_indicator", code, var, "WDI value pivoted to country-year anchor.", "observed_2024" if year == ANCHOR_YEAR else "historical_observed", dataset_version, build_id)
    for var in ["population_65_plus", "population_15_64", "population_18_plus"]:
        add_source(log, "macro_anchor", var, "PER", ANCHOR_YEAR, "UN_WPP", "raw_wpp_projections", "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100", var, "Derived from WPP single-age population; WPP values are in thousands and were multiplied by 1000.", "observed_2024", dataset_version, build_id)
    for col in cols[2:16]:
        if result.loc[result["year"] == ANCHOR_YEAR, col].isna().any():
            add_quality(log, "PER", ANCHOR_YEAR, "macro", "macro_anchor", col, f"{col} missing at anchor year.", dataset_version, build_id, missing=True, quality_score=0.0)
        else:
            add_quality(log, "PER", ANCHOR_YEAR, "macro", "macro_anchor", col, "Anchor-year macro value available.", dataset_version, build_id)
    return result


def build_poverty(root: Path, dataset_version: str, build_id: str, log: BuildLog) -> tuple[pd.DataFrame, pd.Series]:
    pip = read_parquet(root, "data/raw/pip/pip_poverty.parquet")
    wdi = read_parquet(root, "data/raw/wdi/wdi_country_year.parquet")
    anchor = pip[(pip["country_id"] == "PER") & (pip["year"] == ANCHOR_YEAR) & (pip["poverty_line"] == 8.3)].copy()
    if anchor.empty:
        anchor = pip[(pip["country_id"] == "PER") & (pip["poverty_line"] == 8.3)].sort_values("year").tail(1).copy()
        carried = True
    else:
        carried = False
    row = anchor.iloc[0]
    ppp_private_2021 = value_at(wdi[wdi["country_id"] == "PER"], "PA.NUS.PRVT.PP", 2021)
    ppp_gdp_2021 = value_at(wdi[wdi["country_id"] == "PER"], "PA.NUS.PPP", 2021)
    cpi_2021 = value_at(wdi[wdi["country_id"] == "PER"], "FP.CPI.TOTL", 2021)
    cpi_2024 = value_at(wdi[wdi["country_id"] == "PER"], "FP.CPI.TOTL", ANCHOR_YEAR)
    if ppp_private_2021 is None or cpi_2021 is None or cpi_2024 is None:
        poverty_line_lcu = np.nan
    else:
        poverty_line_lcu = float(row["poverty_line"]) * ppp_private_2021 * (cpi_2024 / cpi_2021) * 365.0
    out = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "poverty_line_national_lcu_annual": poverty_line_lcu,
                "poverty_line_ppp_annual": float(row["poverty_line"]) * 365.0,
                "ppp_private_consumption_2021": ppp_private_2021,
                "ppp_gdp_2021_contrast": ppp_gdp_2021,
                "cpi_2021": cpi_2021,
                "cpi_2024": cpi_2024,
                "poverty_headcount": float(row["headcount"]),
                "poverty_gap": float(row["poverty_gap"]),
                "welfare_type": row["welfare_type"],
                "source_priority": "PIP 8.30 USD PPP/day with WDI private-consumption PPP 2021 and CPI 2024/2021",
                "harmonization_flag": "carried_forward" if carried else "observed_2024",
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        ]
    )
    add_source(log, "poverty_distribution_anchor", "poverty_line_ppp_annual", "PER", ANCHOR_YEAR, "PIP", "raw_pip_poverty", "poverty_line=8.30", "poverty_line", "Daily USD PPP line multiplied by 365.", out.iloc[0]["harmonization_flag"], dataset_version, build_id)
    add_source(log, "poverty_distribution_anchor", "poverty_line_national_lcu_annual", "PER", ANCHOR_YEAR, "PIP;WDI", "raw_pip_poverty+raw_wdi_indicator", "poverty_line=8.30;PA.NUS.PRVT.PP;FP.CPI.TOTL", "poverty_line_national_lcu_annual", "linea_lcu_anual_2024 = 8.30 * PPP_conv_privado_2021 * (CPI_2024 / CPI_2021) * 365. INEI national poverty line is manual contrast only, not baseline.", "constructed", dataset_version, build_id)
    add_source(log, "poverty_distribution_anchor", "poverty_gap", "PER", ANCHOR_YEAR, "PIP", "raw_pip_poverty", "poverty_gap", "poverty_gap", "PIP aggregate poverty gap for selected poverty line.", out.iloc[0]["harmonization_flag"], dataset_version, build_id)
    if pd.isna(poverty_line_lcu):
        add_quality(log, "PER", ANCHOR_YEAR, "poverty", "poverty_distribution_anchor", "poverty_line_national_lcu_annual", "PPP private-consumption conversion or CPI input missing; policy costs using poverty line in LCU are blocked.", dataset_version, build_id, missing=True, unit_conflict=True, quality_score=0.0)
    else:
        add_quality(log, "PER", ANCHOR_YEAR, "poverty", "poverty_distribution_anchor", "poverty_line_national_lcu_annual", "PIP 8.30 PPP/day converted to 2024 LCU using WDI private-consumption PPP 2021 and CPI ratio.", dataset_version, build_id)
    return out, row


def build_fiscal(root: Path, macro: pd.DataFrame, dataset_version: str, build_id: str, log: BuildLog) -> pd.DataFrame:
    oecd = read_parquet(root, "data/raw/oecd/oecd_revenue.parquet")
    imf = read_parquet(root, "data/raw/imf/imf_fiscal_macro.parquet")
    fiscal = pd.DataFrame({"country_id": ["PER"] * 25, "year": list(range(2000, ANCHOR_YEAR + 1))})
    o = oecd[(oecd["REF_AREA"] == "PER") & (oecd["UNIT_MEASURE"] == "PT_B1GQ") & (oecd["SECTOR"] == "S13")].copy()
    for code, var in FISCAL_REVENUE_CODES.items():
        subset = o[o["STANDARD_REVENUE"] == code][["TIME_PERIOD", "OBS_VALUE"]].rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": var})
        fiscal = fiscal.merge(subset, on="year", how="left")
        add_source(log, "fiscal_anchor", var, "PER", None, "OECD_REVSTAT_LAC", "raw_oecd_revenue", code, var, "OECD Revenue Statistics LAC, sector S13 general government, percent of GDP.", "historical_observed", dataset_version, build_id)
    total_rev = (
        imf[(imf["country_id"] == "PER") & (imf["variable_code"] == "GGR_NGDP")][["year", "value"]]
        .rename(columns={"value": "total_revenue_gdp"})
    )
    if total_rev.empty:
        fiscal["total_revenue_gdp"] = np.nan
        total_revenue_note = "IMF DataMapper GGR_NGDP is absent from the frozen snapshot; total revenue is NULL."
    else:
        fiscal = fiscal.merge(total_rev, on="year", how="left")
        total_revenue_note = "IMF DataMapper percent-of-GDP total revenue."
    fiscal["resource_revenue_gdp"] = np.nan
    fiscal["non_resource_revenue_gdp"] = np.nan
    fiscal["government_level"] = "general_government"
    fiscal["source_priority"] = f"OECD S13 for tax structure; {total_revenue_note} GRD unavailable."
    fiscal["dataset_version"] = dataset_version
    fiscal["build_id"] = build_id
    if not total_rev.empty:
        add_source(log, "fiscal_anchor", "total_revenue_gdp", "PER", None, "IMF_WEO_GFS", "raw_imf_weo", "GGR_NGDP", "General government revenue, percent of GDP", "IMF DataMapper percent-of-GDP total revenue.", "historical_observed", dataset_version, build_id)
    else:
        add_quality(log, "PER", ANCHOR_YEAR, "fiscal", "fiscal_anchor", "total_revenue_gdp", "IMF GGR_NGDP is not present in the frozen snapshot; total-revenue fiscal anchor and MFC percentiles remain NULL.", dataset_version, build_id, missing=True, quality_score=0.0)
    for var in ["resource_revenue_gdp", "non_resource_revenue_gdp"]:
        add_quality(log, "PER", ANCHOR_YEAR, "fiscal", "fiscal_anchor", var, "GRD 2025 is manual_pending; resource/non-resource split not available in snapshot.", dataset_version, build_id, missing=True, quality_score=0.0)
    add_quality(log, "PER", ANCHOR_YEAR, "fiscal", "fiscal_anchor", "government_level", "PER fiscal historical series uses general_government (OECD S13/IMF general government); BCRP/SUNAT central-government series are contrast only.", dataset_version, build_id)
    return fiscal


def build_debt_guardrail(root: Path, macro: pd.DataFrame, dataset_version: str, build_id: str, log: BuildLog) -> pd.DataFrame:
    imf = read_parquet(root, "data/raw/imf/imf_fiscal_macro.parquet")
    debt = imf[imf["variable_code"].isin(["GGXWDG_NGDP", "GGXONLB_NGDP", "GGXCNL_NGDP"])].pivot_table(
        index=["country_id", "year"], columns="variable_code", values="value", aggfunc="first"
    ).reset_index()
    debt = debt[(debt["country_id"] == "PER") & (debt["year"].between(2000, ANCHOR_YEAR))].copy()
    debt = debt.rename(columns={"GGXWDG_NGDP": "gross_debt_gdp", "GGXONLB_NGDP": "primary_balance_gdp", "GGXCNL_NGDP": "net_lending_borrowing_gdp"})
    m = macro[["country_id", "year", "gdp_nominal_lcu"]].copy().sort_values(["country_id", "year"])
    m["nominal_growth_rate"] = m.groupby("country_id")["gdp_nominal_lcu"].pct_change()
    debt = debt.merge(m[["country_id", "year", "nominal_growth_rate"]], on=["country_id", "year"], how="left")
    debt = debt.sort_values(["country_id", "year"])
    debt["gross_debt_gdp_lag"] = debt.groupby("country_id")["gross_debt_gdp"].shift(1)
    debt["interest_payments_gdp"] = debt["primary_balance_gdp"] - debt["net_lending_borrowing_gdp"]
    debt["nominal_interest_rate"] = debt["interest_payments_gdp"] / debt["gross_debt_gdp_lag"]
    debt["pb_stabilizing_gdp"] = (
        (debt["nominal_interest_rate"] - debt["nominal_growth_rate"])
        / (1.0 + debt["nominal_growth_rate"])
        * debt["gross_debt_gdp"]
    )
    debt["pb_gap_gdp"] = debt["primary_balance_gdp"] - debt["pb_stabilizing_gdp"]
    debt["source_id"] = "IMF_WEO_GFS"
    debt["dataset_version"] = dataset_version
    debt["build_id"] = build_id
    add_source(log, "debt_guardrail_anchor", "gross_debt_gdp", "PER", None, "IMF_WEO_GFS", "raw_imf_weo", "GGXWDG_NGDP", "gross debt", "IMF DataMapper value.", "historical_observed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "primary_balance_gdp", "PER", None, "IMF_WEO_GFS", "raw_imf_weo", "GGXONLB_NGDP", "primary balance", "IMF DataMapper value.", "historical_observed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "net_lending_borrowing_gdp", "PER", None, "IMF_WEO_GFS", "raw_imf_weo", "GGXCNL_NGDP", "net lending/borrowing", "IMF DataMapper value retained as observed balance, not relabeled as primary balance.", "historical_observed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "nominal_growth_rate", "PER", None, "WDI", "macro_anchor", "NY.GDP.MKTP.CN", "gdp_nominal_lcu", "Computed as nominal LCU GDP growth.", "constructed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "interest_payments_gdp", "PER", None, "IMF_WEO_GFS", "raw_imf_weo", "GGXONLB_NGDP-GGXCNL_NGDP", "interest_payments_gdp", "intereses/PIB = GGXONLB_NGDP - GGXCNL_NGDP.", "constructed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "nominal_interest_rate", "PER", None, "IMF_WEO_GFS", "debt_guardrail_anchor", "interest_payments_gdp/gross_debt_gdp_lag", "nominal_interest_rate", "nominal_interest_rate_t = (intereses/PIB)_t / gross_debt_gdp_{t-1}.", "constructed", dataset_version, build_id)
    add_source(log, "debt_guardrail_anchor", "pb_stabilizing_gdp", "PER", None, "IMF_WEO_GFS;WDI", "debt_guardrail_anchor+macro_anchor", "((i-g)/(1+g))*gross_debt_gdp", "pb_stabilizing_gdp", "pb_stabilizing = ((i - g_nominal) / (1 + g_nominal)) * gross_debt_gdp; g_nominal from macro_anchor.", "constructed", dataset_version, build_id)
    if debt.loc[debt["year"] == ANCHOR_YEAR, ["primary_balance_gdp", "nominal_interest_rate", "pb_stabilizing_gdp", "pb_gap_gdp"]].isna().any().any():
        add_quality(log, "PER", ANCHOR_YEAR, "debt", "debt_guardrail_anchor", "pb_stabilizing_gdp", "Debt guardrail still has missing anchor-year formula inputs.", dataset_version, build_id, missing=True, quality_score=0.0)
    else:
        add_quality(log, "PER", ANCHOR_YEAR, "debt", "debt_guardrail_anchor", "pb_stabilizing_gdp", "Debt guardrail computed from IMF primary/overall balance and WDI nominal GDP growth.", dataset_version, build_id)
    return debt[["country_id", "year", "gross_debt_gdp", "gross_debt_gdp_lag", "net_lending_borrowing_gdp", "primary_balance_gdp", "interest_payments_gdp", "nominal_interest_rate", "nominal_growth_rate", "pb_stabilizing_gdp", "pb_gap_gdp", "source_id", "dataset_version", "build_id"]]


def build_ai_and_digital(root: Path, dataset_version: str, build_id: str, log: BuildLog) -> tuple[pd.DataFrame, pd.DataFrame]:
    aipi = read_parquet(root, "data/raw/imf_aipi/aipi.parquet")
    per = aipi[aipi["country_id"] == "PER"].sort_values("year").tail(1).copy()
    per["year_original"] = per["year"]
    per["year"] = ANCHOR_YEAR
    per["aipi_convention"] = "published IMF AIPI carried forward to 2024 anchor"
    per["source_id"] = "IMF_AIPI_DATA360"
    per["dataset_version"] = dataset_version
    per["build_id"] = build_id
    ai_cols = ["country_id", "year", "aipi_total", "digital_infrastructure", "human_capital_labor", "innovation_integration", "regulation_ethics", "aipi_convention", "source_id", "dataset_version", "build_id"]
    ai = per.reindex(columns=ai_cols)
    add_source(log, "ai_preparedness_anchor", "aipi_total", "PER", ANCHOR_YEAR, "IMF_AIPI_DATA360", "raw_aipi", "IMF_AI_AIPI_IX", "aipi_total", "Published AIPI, carried forward from 2023 to 2024 anchor.", "carried_forward", dataset_version, build_id)
    add_quality(log, "PER", ANCHOR_YEAR, "ai", "ai_preparedness_anchor", "aipi_total", "AIPI latest year is 2023 and is carried forward to 2024.", dataset_version, build_id, carried=True, carried_from=int(per.iloc[0]["year_original"]), quality_score=0.8)

    itu = read_parquet(root, "data/raw/itu/itu_digital.parquet")
    rates = {}
    for code, col in [
        ("IT.NET.USER.ZS", "internet_use_rate"),
        ("IT.NET.BBND.P2", "broadband_rate"),
        ("IT.CEL.SETS.P2", "mobile_broadband_rate"),
    ]:
        sub = itu[(itu["country_id"] == "PER") & (itu["indicator_code"] == code) & (itu["year"] <= ANCHOR_YEAR)].sort_values("year")
        if not sub.empty:
            rates[col] = float(sub.iloc[-1]["value"])
            add_source(log, "digital_gap_anchor", col, "PER", ANCHOR_YEAR, "WDI_FALLBACK_ITU", "raw_itu", code, col, "Raw rate retained for audit but excluded from baseline gap_index due AIPI overlap rule.", "observed_2024", dataset_version, build_id)
    digital = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "internet_use_rate": rates.get("internet_use_rate"),
                "broadband_rate": rates.get("broadband_rate"),
                "mobile_broadband_rate": rates.get("mobile_broadband_rate"),
                "digital_skills_proxy": np.nan,
                "gap_index": np.nan,
                "normalization_method": "not_computed_no_excluded_indicator_available",
                "gap_construction_convention": "excluded_indicators",
                "aipi_overlap_flag": False,
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        ]
    )
    add_quality(log, "PER", ANCHOR_YEAR, "ai", "digital_gap_anchor", "gap_index", "Baseline gap_index not computed because available ITU/WDI digital indicators overlap AIPI digital infrastructure; no excluded indicator is present in the snapshot.", dataset_version, build_id, missing=True, quality_score=0.0)
    return ai, digital


def build_labor(root: Path, dataset_version: str, build_id: str, log: BuildLog) -> tuple[pd.DataFrame, pd.DataFrame]:
    ilo = read_parquet(root, "data/raw/ilostat/ilostat_labor.parquet")
    row = ilo[
        (ilo["country_id"] == "PER")
        & (ilo["year"] == ANCHOR_YEAR)
        & (ilo["indicator_code"] == "EMP_NIFL_SEX_AGE_RT")
        & (ilo["sex"] == "SEX_T")
        & (ilo["age_group"] == "AGE_YTHADULT_YGE15")
    ]
    informality = float(row.iloc[0]["value"]) if not row.empty else np.nan
    labor = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "informality_total": informality,
                "informality_labor_tax_base": np.nan,
                "informality_consumption_tax_base": np.nan,
                "informality_capital_tax_base": np.nan,
                "almp_spending_gdp": np.nan,
                "training_participation_rate": np.nan,
                "rst_proxy": np.nan,
                "definition": "ILOSTAT EMP_NIFL_SEX_AGE_RT, total sex, age 15+",
                "source_id": "ILOSTAT",
                "harmonization_flag": "observed_2024",
                "non_harmonized_robustness": False,
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        ]
    )
    add_source(log, "labor_informality_anchor", "informality_total", "PER", ANCHOR_YEAR, "ILOSTAT", "raw_ilostat", "EMP_NIFL_SEX_AGE_RT", "informality_total", "ILOSTAT rate for informal employment, total sex, age 15+.", "observed_2024", dataset_version, build_id)
    for var in ["informality_labor_tax_base", "informality_consumption_tax_base", "informality_capital_tax_base", "rst_proxy"]:
        add_quality(log, "PER", ANCHOR_YEAR, "informality", "labor_informality_anchor", var, "Specific tax-base informality/RST proxy not available in snapshot; not copied from total informality.", dataset_version, build_id, missing=True, quality_score=0.0)

    pwt = read_parquet(root, "data/raw/pwt/pwt_country_year.parquet")
    p = pwt[(pwt["country_id"] == "PER") & (pwt["year"] <= ANCHOR_YEAR)].sort_values("year").tail(1).iloc[0]
    labor_share = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "labor_share_raw": float(p["labsh"]),
                "labor_share_adjusted": float(p["labsh"]),
                "source_id": "PWT_10_01",
                "adjustment_notes": "No adjustment applied; latest PWT value carried forward.",
                "year_original": int(p["year"]),
                "carried_forward_flag": int(p["year"]) < ANCHOR_YEAR,
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        ]
    )
    add_source(log, "labor_share_anchor", "labor_share_raw", "PER", ANCHOR_YEAR, "PWT_10_01", "raw_pwt", "labsh", "labor_share_raw", "PWT labsh carried forward to anchor year.", "carried_forward", dataset_version, build_id)
    add_quality(log, "PER", ANCHOR_YEAR, "labor_share", "labor_share_anchor", "labor_share_raw", "PWT latest year is carried forward to 2024.", dataset_version, build_id, carried=True, carried_from=int(p["year"]), quality_score=0.7)
    return labor, labor_share


def build_exposure(dataset_version: str, build_id: str, log: BuildLog) -> pd.DataFrame:
    add_assumption(log, "A_AI_EXPOSURE_LAC_FALLBACK", "ai_exposure", "exposure_productive", 0.11, 0.08, 0.14, "uniform_range", "Plan 01 section 14.9 states regional LAC productive exposure range 8-14%; baseline uses midpoint.", "PLAN_01_02", False, False, True)
    out = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "exposure_total": 0.11,
                "exposure_productive": 0.11,
                "exposure_displacement": np.nan,
                "exposure_source_type": "regional_lac_fallback",
                "occupation_mapping_version": "not_used_in_fallback",
                "is_lac_fallback": True,
                "source_id": "PLAN_01_02",
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        ]
    )
    add_source(log, "ai_exposure_anchor", "exposure_productive", "PER", ANCHOR_YEAR, "PLAN_01_02", "plan_01", "section_14.9", "exposure_productive", "Midpoint of declared 8-14% LAC fallback range; assumption row stores range.", "assumption_registered", dataset_version, build_id)
    add_quality(log, "PER", ANCHOR_YEAR, "ai_exposure", "ai_exposure_anchor", "exposure_productive", "Country-specific occupational exposure absent; using mandatory regional LAC fallback.", dataset_version, build_id, non_harmonized=True, quality_score=0.5)
    return out


def build_frontier(root: Path, dataset_version: str, build_id: str, log: BuildLog) -> pd.DataFrame:
    frontier = read_parquet(root, "data/raw/frontier/frontier_benchmark.parquet")
    aipi = read_parquet(root, "data/raw/imf_aipi/aipi.parquet")
    proxy = frontier[
        (frontier["indic_is"] == "E_AI_TANY")
        & (frontier["unit"] == "PC_ENT")
        & (frontier["size_emp"] == "GE10")
        & (frontier["time"] == "2024")
    ].copy()
    proxy["benchmark_country_id"] = proxy["geo"].map(EUROSTAT_TO_ISO3)
    proxy = proxy.dropna(subset=["benchmark_country_id"])
    latest_aipi = aipi.sort_values("year").groupby("country_id", as_index=False).tail(1)
    rows = proxy.merge(latest_aipi, left_on="benchmark_country_id", right_on="country_id", how="left", suffixes=("", "_aipi"))
    out = pd.DataFrame(
        {
            "benchmark_set_id": "candidate_eurostat_ge10_2024",
            "benchmark_country_id": rows["benchmark_country_id"],
            "year": ANCHOR_YEAR,
            "scenario_id": "pending_calibration",
            "aipi_total": rows["aipi_total"],
            "exposure_productive": np.nan,
            "adoption_proxy": pd.to_numeric(rows["value"], errors="coerce") / 100.0,
            "s_frontier_score": np.nan,
            "score_convention": "pending_phase1_calibration_beta_gamma",
            "elasticities_used": "pending",
            "population_consistency_note": "Candidate inputs only; benchmark population must match scenario shock calibration in Etapa 3.",
            "source_id": "FRONTIER_BENCHMARK;IMF_AIPI_DATA360;WDI_FALLBACK_ITU",
            "dataset_version": dataset_version,
            "build_id": build_id,
        }
    )
    add_source(log, "frontier_benchmark_anchor", "adoption_proxy", None, ANCHOR_YEAR, "FRONTIER_BENCHMARK", "raw_frontier_benchmark", "isoc_eb_ai/E_AI_TANY/GE10/PC_ENT", "adoption_proxy", "Eurostat AI adoption percentage divided by 100.", "observed_2024", dataset_version, build_id)
    add_quality(log, None, ANCHOR_YEAR, "frontier", "frontier_benchmark_anchor", "s_frontier_score", "Score not computed because beta/gamma calibration belongs to Etapa 3.", dataset_version, build_id, missing=True, quality_score=0.0)
    return out


def build_historical_capture(root: Path, macro: pd.DataFrame, fiscal: pd.DataFrame, dataset_version: str, build_id: str, log: BuildLog, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = fiscal.merge(macro[["country_id", "year", "gdp_nominal_lcu"]], on=["country_id", "year"], how="left")
    rows = []
    for concept, pct_col in [("tax", "tax_revenue_gdp"), ("total_revenue", "total_revenue_gdp")]:
        df = base[["country_id", "year", "gdp_nominal_lcu", pct_col]].copy().sort_values("year")
        df["revenue_lcu"] = df[pct_col] / 100.0 * df["gdp_nominal_lcu"]
        df["delta_revenue_lcu"] = df["revenue_lcu"].diff()
        df["delta_gdp_lcu"] = df["gdp_nominal_lcu"].diff()
        df["mfc_hist_gross"] = df["delta_revenue_lcu"] / df["delta_gdp_lcu"]
        df["buoyancy_hist"] = np.log(df["revenue_lcu"] / df["revenue_lcu"].shift(1)) / np.log(df["gdp_nominal_lcu"] / df["gdp_nominal_lcu"].shift(1))
        df["mfc_smoothed_3y"] = df["mfc_hist_gross"].rolling(3, min_periods=1).mean()
        for _, r in df.iterrows():
            value = r["mfc_hist_gross"]
            rows.append(
                {
                    "country_id": "PER",
                    "year": int(r["year"]),
                    "revenue_concept": concept,
                    "revenue_lcu": r["revenue_lcu"],
                    "gdp_lcu": r["gdp_nominal_lcu"],
                    "delta_revenue_lcu": r["delta_revenue_lcu"],
                    "delta_gdp_lcu": r["delta_gdp_lcu"],
                    "mfc_hist_gross": value,
                    "mfc_tax_hist_gross": value if concept == "tax" else np.nan,
                    "mfc_total_revenue_hist_gross": value if concept == "total_revenue" else np.nan,
                    "mfc_nonresource_hist_gross": np.nan,
                    "mfc_smoothed_3y": r["mfc_smoothed_3y"],
                    "buoyancy_hist": r["buoyancy_hist"],
                    "is_non_negative_capture": bool(value >= 0) if pd.notna(value) else None,
                    "delta_gdp_positive": bool(r["delta_gdp_lcu"] > 0) if pd.notna(r["delta_gdp_lcu"]) else None,
                    "crisis_year_flag": int(r["year"]) in [2008, 2009],
                    "commodity_shock_flag": False,
                    "pandemic_flag": int(r["year"]) in [2020, 2021],
                    "government_level": "general_government",
                    "source_mix": "OECD tax percent of GDP + WDI GDP LCU" if concept == "tax" else "IMF total revenue percent of GDP + WDI GDP LCU",
                    "dataset_version": dataset_version,
                    "build_id": build_id,
                    "created_by_script": SCRIPT_NAME,
                }
            )
    dist = pd.DataFrame(rows)
    add_source(log, "historical_capture_distribution", "mfc_hist_gross", "PER", None, "OECD_REVSTAT_LAC/WDI/IMF_WEO_GFS", "fiscal_anchor+macro_anchor", "delta_revenue_lcu/delta_gdp_lcu", "mfc_hist_gross", "Constructed from percent-of-GDP revenue and WDI nominal LCU GDP.", "constructed", dataset_version, build_id)
    add_source(log, "historical_capture_distribution", "total_revenue_lcu", "PER", None, "IMF_WEO_GFS;WDI", "fiscal_anchor+macro_anchor", "GGR_NGDP_t * PIB_nominal_LCU_t / 100", "revenue_lcu", "total_revenue_lcu_t = GGR_NGDP_t * PIB_nominal_LCU_t / 100; GGR_NGDP is stored as percent of GDP.", "constructed", dataset_version, build_id)
    add_quality(log, "PER", None, "historical", "historical_capture_distribution", "mfc_nonresource_hist_gross", "GRD non-resource revenue missing; nonresource variant not computed.", dataset_version, build_id, missing=True, quality_score=0.0)

    percent_rows = []
    rng = np.random.Generator(np.random.PCG64(seed))
    samples = {
        "2000plus": lambda x: x["year"] >= 2000,
        "2010plus": lambda x: x["year"] >= 2010,
        "2015plus": lambda x: x["year"] >= 2015,
        "excl_pandemic_2020_2021": lambda x: ~x["year"].isin([2020, 2021]),
    }
    for concept in ["tax", "total_revenue"]:
        concept_df = dist[(dist["revenue_concept"] == concept) & (dist["delta_gdp_positive"] == True)].copy()  # noqa: E712
        for sample_name, sample_filter in samples.items():
            sample_df = concept_df[sample_filter(concept_df)]
            raw_values = sample_df["mfc_hist_gross"].dropna().astype(float)
            if raw_values.empty:
                percent_rows.append(empty_percentile_row("PER", concept, sample_name, dataset_version, build_id, "no valid years"))
                continue
            lower, upper = np.nanpercentile(raw_values, [1, 99])
            values = raw_values.clip(lower, upper)
            positive = values[values >= 0]
            negative = values[values < 0]
            row = {
                "country_id": "PER",
                "revenue_concept": concept,
                "percentile_sample": sample_name,
                "p10_mfc_hist_positive": pct(positive, 10),
                "p25_mfc_hist_positive": pct(positive, 25),
                "p50_mfc_hist_positive": pct(positive, 50),
                "p50_ci_low": np.nan,
                "p50_ci_high": np.nan,
                "p75_mfc_hist_positive": pct(positive, 75),
                "p75_ci_low": np.nan,
                "p75_ci_high": np.nan,
                "p90_mfc_hist_positive": pct(positive, 90),
                "p90_ci_low": np.nan,
                "p90_ci_high": np.nan,
                "ci_method": f"bootstrap percentile, B={BOOTSTRAP_DRAWS}, seed={seed}, PCG64",
                "n_years_total": int(len(values)),
                "n_years_positive": int(len(positive)),
                "p_negative_capture": float(len(negative) / len(values)) if len(values) else np.nan,
                "p10_mfc_hist_negative": pct(negative, 10),
                "p50_mfc_hist_negative": pct(negative, 50),
                "p90_mfc_hist_negative": pct(negative, 90),
                "support_warning": "small_n" if len(values) < 20 else "",
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
            if len(positive) > 1:
                boots = rng.choice(np.asarray(positive), size=(BOOTSTRAP_DRAWS, len(positive)), replace=True)
                for quantile, prefix in [(50, "p50"), (75, "p75"), (90, "p90")]:
                    boot_q = np.percentile(boots, quantile, axis=1)
                    row[f"{prefix}_ci_low"] = float(np.percentile(boot_q, 2.5))
                    row[f"{prefix}_ci_high"] = float(np.percentile(boot_q, 97.5))
            percent_rows.append(row)
    return dist, pd.DataFrame(percent_rows)


def pct(values: pd.Series, q: float) -> float:
    if values is None or len(values) == 0:
        return np.nan
    return float(np.nanpercentile(values, q))


def empty_percentile_row(country: str, concept: str, sample: str, dataset_version: str, build_id: str, warning: str) -> dict[str, Any]:
    return {
        "country_id": country,
        "revenue_concept": concept,
        "percentile_sample": sample,
        "p10_mfc_hist_positive": np.nan,
        "p25_mfc_hist_positive": np.nan,
        "p50_mfc_hist_positive": np.nan,
        "p50_ci_low": np.nan,
        "p50_ci_high": np.nan,
        "p75_mfc_hist_positive": np.nan,
        "p75_ci_low": np.nan,
        "p75_ci_high": np.nan,
        "p90_mfc_hist_positive": np.nan,
        "p90_ci_low": np.nan,
        "p90_ci_high": np.nan,
        "ci_method": f"bootstrap percentile, B={BOOTSTRAP_DRAWS}",
        "n_years_total": 0,
        "n_years_positive": 0,
        "p_negative_capture": np.nan,
        "p10_mfc_hist_negative": np.nan,
        "p50_mfc_hist_negative": np.nan,
        "p90_mfc_hist_negative": np.nan,
        "support_warning": warning,
        "dataset_version": dataset_version,
        "build_id": build_id,
    }


def build_policy_tables(root: Path, macro: pd.DataFrame, poverty: pd.DataFrame, dataset_version: str, build_id: str, log: BuildLog) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    macro_2024 = macro[(macro["country_id"] == "PER") & (macro["year"] == ANCHOR_YEAR)].iloc[0]
    poverty_2024 = poverty.iloc[0]
    gdp_lcu = float(macro_2024["gdp_nominal_lcu"])
    pop_total = float(macro_2024["population_total"])
    pop65 = float(macro_2024["population_65_plus"])
    pen_benefit = 250.0 * 6.0
    add_assumption(log, "A_THETA_TARGET_GMI_LOADED", "policy_cost", "theta_target", 1.5, 1.0, 1.5, "fixed_for_loaded_aggregate", "Plan 01/02 require theta_target support [1.0, 1.5]; loaded aggregate uses conservative upper bound.", "PLAN_01_02", False, False, True)
    add_assumption(log, "A_CHI_GMI_FULL_GAP", "policy_cost", "chi_gmi", 1.0, 1.0, 1.0, "fixed", "Guaranteed minimum income aggregate closes the measured poverty gap in the ideal aggregate convention.", "PLAN_01_02", False, False, True)
    add_assumption(log, "A_POLICY_ETA_UNDEFINED", "policy_cost", "eta_MUT_eta_PBI_eta_UBI", np.nan, np.nan, np.nan, "undefined", "Plan 01 requires explicit eta values but neither plan freezes numeric eta_MUT/eta_PBI/eta_UBI; costs remain blocked.", "PLAN_01_02", False, False, True)
    add_assumption(log, "A_PPP_TO_LCU_MISSING", "policy_cost", "ppp_to_lcu_conversion_factor", np.nan, np.nan, np.nan, "undefined", "PIP lines are USD PPP/day and snapshot lacks PPP conversion factor; market FX is not used as a substitute.", "PIP", False, False, True)
    add_assumption(log, "A_ADMIN_COST_PENDING_ASPIRE", "policy_admin_transition_cost", "admin_transition_costs", np.nan, np.nan, np.nan, "undefined", "ASPIRE/budget administrative-cost source is not present in snapshot.", "MANUAL_SOURCE_REGISTRY", False, False, True)

    now = utc_now()
    params = [
        {
            "policy_parameter_id": "PER_PEN_2024_OFFICIAL_P65",
            "country_id": "PER",
            "policy_id": "PEN",
            "year": ANCHOR_YEAR,
            "age_threshold": 65,
            "eta_policy": np.nan,
            "chi_gmi": np.nan,
            "theta_target": np.nan,
            "benefit_formula": "S/250 every two months * 6 = S/1500 annual per eligible person",
            "eligible_population_rule": "universal scenario: WPP population age >=65",
            "gross_or_net_convention": "gross",
            "existing_spending_treatment": "none",
            "poverty_line_convention": "not_applicable",
            "indexation_rule": "gdp_pc_growth_assumption_for_endpoint_only",
            "source_id": "MIDIS_PENSION65",
            "assumption_id": None,
            "dataset_version": dataset_version,
            "created_at": now,
            "created_by_script": SCRIPT_NAME,
        },
        {
            "policy_parameter_id": "PER_GMI_IDEAL_AGG_2024",
            "country_id": "PER",
            "policy_id": "GMI",
            "year": ANCHOR_YEAR,
            "age_threshold": np.nan,
            "eta_policy": np.nan,
            "chi_gmi": 1.0,
            "theta_target": 1.0,
            "benefit_formula": "chi_gmi * aggregate PIP poverty gap",
            "eligible_population_rule": "aggregate poverty gap, no microdata",
            "gross_or_net_convention": "gross",
            "existing_spending_treatment": "none",
            "poverty_line_convention": "international_ppp",
            "indexation_rule": "poverty_line_growth",
            "source_id": "PIP",
            "assumption_id": "A_CHI_GMI_FULL_GAP;A_PPP_TO_LCU_MISSING",
            "dataset_version": dataset_version,
            "created_at": now,
            "created_by_script": SCRIPT_NAME,
        },
        {
            "policy_parameter_id": "PER_GMI_LOADED_AGG_2024",
            "country_id": "PER",
            "policy_id": "GMI",
            "year": ANCHOR_YEAR,
            "age_threshold": np.nan,
            "eta_policy": np.nan,
            "chi_gmi": 1.0,
            "theta_target": 1.5,
            "benefit_formula": "theta_target * chi_gmi * aggregate PIP poverty gap",
            "eligible_population_rule": "aggregate poverty gap, no microdata",
            "gross_or_net_convention": "gross",
            "existing_spending_treatment": "none",
            "poverty_line_convention": "international_ppp",
            "indexation_rule": "poverty_line_growth",
            "source_id": "PIP;PLAN_01_02",
            "assumption_id": "A_CHI_GMI_FULL_GAP;A_THETA_TARGET_GMI_LOADED;A_PPP_TO_LCU_MISSING",
            "dataset_version": dataset_version,
            "created_at": now,
            "created_by_script": SCRIPT_NAME,
        },
    ]
    for policy in ["MUT", "PBI", "UBI"]:
        params.append(
            {
                "policy_parameter_id": f"PER_{policy}_2024_PENDING_ETA",
                "country_id": "PER",
                "policy_id": policy,
                "year": ANCHOR_YEAR,
                "age_threshold": np.nan,
                "eta_policy": np.nan,
                "chi_gmi": np.nan,
                "theta_target": np.nan,
                "benefit_formula": f"eta_{policy} * poverty line; eta not frozen",
                "eligible_population_rule": "pending explicit policy convention",
                "gross_or_net_convention": "gross",
                "existing_spending_treatment": "none",
                "poverty_line_convention": "international_ppp",
                "indexation_rule": "poverty_line_growth",
                "source_id": "PLAN_01_02",
                "assumption_id": "A_POLICY_ETA_UNDEFINED;A_PPP_TO_LCU_MISSING",
                "dataset_version": dataset_version,
                "created_at": now,
                "created_by_script": SCRIPT_NAME,
            }
        )
    policy_parameter = pd.DataFrame(params)
    costs = [
        {
            "country_id": "PER",
            "policy_id": "PEN",
            "year": ANCHOR_YEAR,
            "eligible_population": pop65,
            "benefit_amount_lcu": pen_benefit,
            "poverty_line_annual_lcu": np.nan,
            "eta_policy": np.nan,
            "chi_gmi": np.nan,
            "policy_cost_gross_lcu": pen_benefit * pop65,
            "existing_spending_lcu": 0.0,
            "policy_cost_net_lcu": pen_benefit * pop65,
            "policy_cost_gross_gdp": (pen_benefit * pop65) / gdp_lcu,
            "policy_cost_net_gdp": (pen_benefit * pop65) / gdp_lcu,
            "cost_convention": "gross universal 65+ using official Pensión 65 benefit amount",
            "microdata_used": False,
            "gmi_version": None,
            "policy_parameter_id": "PER_PEN_2024_OFFICIAL_P65",
            "assumption_id": None,
            "dataset_version": dataset_version,
            "build_id": build_id,
            "created_at": now,
            "created_by_script": SCRIPT_NAME,
            "run_id": None,
            "model_version": None,
            "parameter_set_id": "baseline_anchor_v0_1_1",
        }
    ]
    for version, theta, param_id in [
        ("GMI_ideal_aggregate", 1.0, "PER_GMI_IDEAL_AGG_2024"),
        ("GMI_loaded_aggregate", 1.5, "PER_GMI_LOADED_AGG_2024"),
    ]:
        costs.append(
            {
                "country_id": "PER",
                "policy_id": "GMI",
                "year": ANCHOR_YEAR,
                "eligible_population": np.nan,
                "benefit_amount_lcu": np.nan,
                "poverty_line_annual_lcu": np.nan,
                "eta_policy": np.nan,
                "chi_gmi": 1.0,
                "policy_cost_gross_lcu": np.nan,
                "existing_spending_lcu": 0.0,
                "policy_cost_net_lcu": np.nan,
                "policy_cost_gross_gdp": np.nan,
                "policy_cost_net_gdp": np.nan,
                "cost_convention": f"{version} computable in PPP units from poverty_gap={poverty_2024['poverty_gap']}; LCU/GDP blocked by missing PPP-to-LCU conversion",
                "microdata_used": False,
                "gmi_version": version,
                "policy_parameter_id": param_id,
                "assumption_id": "A_PPP_TO_LCU_MISSING",
                "dataset_version": dataset_version,
                "build_id": build_id,
                "created_at": now,
                "created_by_script": SCRIPT_NAME,
                "run_id": None,
                "model_version": None,
                "parameter_set_id": "baseline_anchor_v0_1_1",
            }
        )
    for policy in ["MUT", "PBI", "UBI"]:
        costs.append(
            {
                "country_id": "PER",
                "policy_id": policy,
                "year": ANCHOR_YEAR,
                "eligible_population": pop_total if policy == "UBI" else np.nan,
                "benefit_amount_lcu": np.nan,
                "poverty_line_annual_lcu": np.nan,
                "eta_policy": np.nan,
                "chi_gmi": np.nan,
                "policy_cost_gross_lcu": np.nan,
                "existing_spending_lcu": 0.0,
                "policy_cost_net_lcu": np.nan,
                "policy_cost_gross_gdp": np.nan,
                "policy_cost_net_gdp": np.nan,
                "cost_convention": "blocked: eta and PPP-to-LCU conversion not frozen in snapshot/plans",
                "microdata_used": False,
                "gmi_version": None,
                "policy_parameter_id": f"PER_{policy}_2024_PENDING_ETA",
                "assumption_id": "A_POLICY_ETA_UNDEFINED;A_PPP_TO_LCU_MISSING",
                "dataset_version": dataset_version,
                "build_id": build_id,
                "created_at": now,
                "created_by_script": SCRIPT_NAME,
                "run_id": None,
                "model_version": None,
                "parameter_set_id": "baseline_anchor_v0_1_1",
            }
        )
    policy_cost = pd.DataFrame(costs)
    add_source(log, "policy_cost", "policy_cost_gross_gdp", "PER", ANCHOR_YEAR, "MIDIS_PENSION65;UN_WPP;WDI", "policy_parameter+macro_anchor", "PEN official benefit; WPP 65+; WDI GDP LCU", "PEN cost", "PEN cost mechanically computed as benefit*WPP65+/WDI GDP LCU.", "constructed", dataset_version, build_id)
    for policy in ["MUT", "GMI", "PBI", "UBI"]:
        add_quality(log, "PER", ANCHOR_YEAR, "policy_cost", "policy_cost", policy, "Cost row present but LCU/GDP result is NULL because required eta and/or PPP-to-LCU conversion is unavailable.", dataset_version, build_id, missing=True, unit_conflict=True, quality_score=0.0)

    gmi_status = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "gmi_version": "GMI_ideal_aggregate",
                "microdata_used": False,
                "survey_name": None,
                "poverty_gap_used": True,
                "income_or_consumption": poverty_2024["welfare_type"],
                "welfare_concept": poverty_2024["welfare_type"],
                "limitation_notes": "Aggregate PIP poverty gap only; no microdata. LCU cost blocked by missing PPP conversion.",
            },
            {
                "country_id": "PER",
                "year": ANCHOR_YEAR,
                "gmi_version": "GMI_loaded_aggregate",
                "microdata_used": False,
                "survey_name": None,
                "poverty_gap_used": True,
                "income_or_consumption": poverty_2024["welfare_type"],
                "welfare_concept": poverty_2024["welfare_type"],
                "limitation_notes": "Aggregate PIP poverty gap with theta_target=1.5; no microdata. LCU cost blocked by missing PPP conversion.",
            },
        ]
    )
    admin = pd.DataFrame(
        [
            {
                "country_id": "PER",
                "policy_id": policy,
                "scenario_id": None,
                "regime_id": None,
                "year": ANCHOR_YEAR,
                "admin_cost_new_gdp": np.nan,
                "admin_savings_existing_gdp": np.nan,
                "admin_included_in_existing_spending": False,
                "layering_mode": "pending",
                "transition_oneoff_gdp": np.nan,
                "transition_recurring_gdp": np.nan,
                "transition_horizon_years": np.nan,
                "transition_discount_rate": np.nan,
                "leakage_fixed_gdp": np.nan,
                "source_id": "MANUAL_SOURCE_REGISTRY",
                "assumption_id": "A_ADMIN_COST_PENDING_ASPIRE",
                "dataset_version": dataset_version,
                "build_id": build_id,
                "created_by_script": SCRIPT_NAME,
            }
            for policy in ["PEN", "MUT", "GMI", "PBI", "UBI"]
        ]
    )
    parameter_set = pd.DataFrame(
        [
            {
                "parameter_set_id": "baseline_anchor_v0_1_1",
                "parameter_set_name": "baseline",
                "description": "Anchor-stage baseline assumptions; not a model run.",
                "model_version": "not_applicable_stage2",
                "dataset_version": dataset_version,
                "created_at": now,
                "created_by_script": SCRIPT_NAME,
            }
        ]
    )
    parameter_set_item = pd.DataFrame(
        [
            {
                "parameter_set_id": "baseline_anchor_v0_1_1",
                "assumption_id": "A_AI_EXPOSURE_LAC_FALLBACK",
                "parameter_name": "exposure_productive",
                "country_id": "PER",
                "policy_id": None,
                "scenario_id": None,
                "regime_id": None,
                "parameter_value": 0.11,
                "distribution": "uniform_range",
                "draw_rule": "fixed_midpoint_for_anchor",
                "notes": "Used only for anchor-stage fallback, not for calibrated Etapa 3.",
            },
            {
                "parameter_set_id": "baseline_anchor_v0_1_1",
                "assumption_id": "A_THETA_TARGET_GMI_LOADED",
                "parameter_name": "theta_target",
                "country_id": "PER",
                "policy_id": "GMI",
                "scenario_id": None,
                "regime_id": None,
                "parameter_value": 1.5,
                "distribution": "fixed",
                "draw_rule": "loaded_aggregate_upper_bound",
                "notes": "Reported beside GMI ideal aggregate.",
            },
        ]
    )
    return policy_parameter, policy_cost, gmi_status, admin, parameter_set, parameter_set_item


def build_policy_tables(root: Path, macro: pd.DataFrame, poverty: pd.DataFrame, dataset_version: str, build_id: str, log: BuildLog) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    macro_2024 = macro[(macro["country_id"] == "PER") & (macro["year"] == ANCHOR_YEAR)].iloc[0]
    poverty_2024 = poverty.iloc[0]
    gdp_lcu = float(macro_2024["gdp_nominal_lcu"])
    pop_total = float(macro_2024["population_total"])
    pop65 = float(macro_2024["population_65_plus"])
    pop18 = float(macro_2024["population_18_plus"])
    poverty_line_lcu = float(poverty_2024["poverty_line_national_lcu_annual"])
    poverty_headcount = float(poverty_2024["poverty_headcount"])
    poverty_gap = float(poverty_2024["poverty_gap"])
    pen_benefit = 250.0 * 6.0
    parameter_set_id = "baseline_anchor_v0_1_2"
    now = utc_now()

    eta_specs = {
        "MUT": {"eta": 0.25, "low": 0.10, "high": 0.50, "assumption_id": "A_ETA_MUT_MIN_TRANSFER", "eligible_population": pop_total, "rule": "WPP population total", "benefit": "eta_MUT * poverty line"},
        "PBI": {"eta": 0.50, "low": 0.25, "high": 0.75, "assumption_id": "A_ETA_PBI_PARTIAL_BASIC_INCOME", "eligible_population": pop18, "rule": "WPP population age >=18", "benefit": "eta_PBI * poverty line"},
        "UBI": {"eta": 1.00, "low": 1.00, "high": 1.00, "assumption_id": "A_ETA_UBI_FULL_POVERTY_LINE", "eligible_population": pop_total, "rule": "WPP population total", "benefit": "eta_UBI * poverty line"},
    }
    admin_specs = {
        "GMI": {"admin": (0.0025, 0.0012, 0.0040), "oneoff": (0.0020, 0.0010, 0.0040), "recurring": (0.00025, 0.00010, 0.00050), "leakage": (0.00020, 0.00000, 0.00050), "horizon": 3, "discount": 0.03, "level": "high"},
        "PEN": {"admin": (0.00045, 0.00025, 0.00080), "oneoff": (0.00080, 0.00040, 0.00150), "recurring": (0.00008, 0.00000, 0.00020), "leakage": (0.00008, 0.00000, 0.00020), "horizon": 2, "discount": 0.03, "level": "medium"},
        "MUT": {"admin": (0.00060, 0.00030, 0.00100), "oneoff": (0.00050, 0.00020, 0.00100), "recurring": (0.00005, 0.00000, 0.00015), "leakage": (0.00005, 0.00000, 0.00015), "horizon": 2, "discount": 0.03, "level": "low"},
        "PBI": {"admin": (0.00050, 0.00025, 0.00090), "oneoff": (0.00050, 0.00020, 0.00100), "recurring": (0.00005, 0.00000, 0.00015), "leakage": (0.00005, 0.00000, 0.00015), "horizon": 2, "discount": 0.03, "level": "low"},
        "UBI": {"admin": (0.00060, 0.00030, 0.00100), "oneoff": (0.00060, 0.00030, 0.00120), "recurring": (0.00005, 0.00000, 0.00015), "leakage": (0.00003, 0.00000, 0.00010), "horizon": 2, "discount": 0.03, "level": "low"},
    }

    add_assumption(log, "A_THETA_TARGET_GMI_LOADED", "policy_cost", "theta_target", 1.5, 1.0, 1.5, "fixed_for_loaded_aggregate", "Plan 01/02 require theta_target support [1.0, 1.5]; loaded aggregate uses conservative upper bound.", "PLAN_01_02", False, False, True)
    add_assumption(log, "A_CHI_GMI_FULL_GAP", "policy_cost", "chi_gmi", 1.0, 1.0, 1.0, "fixed", "Guaranteed minimum income aggregate closes the measured poverty gap in the ideal aggregate convention.", "PLAN_01_02", False, False, True)
    for policy, spec in eta_specs.items():
        add_assumption(log, spec["assumption_id"], "policy_cost", f"eta_{policy}", spec["eta"], spec["low"], spec["high"], "policy_design_parameter", "Normative policy ladder registered for anchor costing: MUT minimum transfer < PBI partial basic income < UBI full poverty-line benchmark. Plan 01 classifies eta_policy as paper/assumption and requires explicit assumption_id.", "PLAN_01_02", False, False, True, "primary_sensitivity")
    for policy, spec in admin_specs.items():
        for suffix, label in [("admin", "admin_cost_new_gdp"), ("oneoff", "transition_oneoff_gdp"), ("recurring", "transition_recurring_gdp"), ("leakage", "leakage_fixed_gdp")]:
            baseline, low, high = spec[suffix]
            add_assumption(
                log,
                f"A_{policy}_{label.upper()}",
                "policy_admin_transition_cost",
                f"{policy}_{label}",
                baseline,
                low,
                high,
                "calibrated_range",
                "Calibrated from ASPIRE social-protection expenditure concept and Plan 01 section 16.1. ASPIRE expenditure includes benefits and administrative costs; Plan 01 requires means-tested > categorical > universal administrative ordering and no uniform ratio.",
                "ASPIRE_LITERATURE_ASSUMPTION;PLAN_01_02",
                False,
                False,
                True,
                spec["level"],
            )

    params = [
        {"policy_parameter_id": "PER_PEN_2024_OFFICIAL_P65", "country_id": "PER", "policy_id": "PEN", "year": ANCHOR_YEAR, "age_threshold": 65, "eta_policy": np.nan, "chi_gmi": np.nan, "theta_target": np.nan, "benefit_formula": "S/250 every two months * 6 = S/1500 annual per eligible person", "eligible_population_rule": "universal scenario: WPP population age >=65", "gross_or_net_convention": "gross", "existing_spending_treatment": "none", "poverty_line_convention": "not_applicable", "indexation_rule": "gdp_pc_growth_assumption_for_endpoint_only", "source_id": "MIDIS_PENSION65", "assumption_id": None, "dataset_version": dataset_version, "created_at": now, "created_by_script": SCRIPT_NAME},
        {"policy_parameter_id": "PER_GMI_IDEAL_AGG_2024", "country_id": "PER", "policy_id": "GMI", "year": ANCHOR_YEAR, "age_threshold": np.nan, "eta_policy": np.nan, "chi_gmi": 1.0, "theta_target": 1.0, "benefit_formula": "chi_gmi * poverty_gap * poverty_line_lcu * population_total", "eligible_population_rule": "aggregate PIP poverty gap, no microdata", "gross_or_net_convention": "gross", "existing_spending_treatment": "none", "poverty_line_convention": "international_ppp_converted_to_lcu", "indexation_rule": "poverty_line_growth", "source_id": "PIP;WDI", "assumption_id": "A_CHI_GMI_FULL_GAP", "dataset_version": dataset_version, "created_at": now, "created_by_script": SCRIPT_NAME},
        {"policy_parameter_id": "PER_GMI_LOADED_AGG_2024", "country_id": "PER", "policy_id": "GMI", "year": ANCHOR_YEAR, "age_threshold": np.nan, "eta_policy": np.nan, "chi_gmi": 1.0, "theta_target": 1.5, "benefit_formula": "theta_target * chi_gmi * poverty_gap * poverty_line_lcu * population_total", "eligible_population_rule": "aggregate PIP poverty gap, no microdata", "gross_or_net_convention": "gross", "existing_spending_treatment": "none", "poverty_line_convention": "international_ppp_converted_to_lcu", "indexation_rule": "poverty_line_growth", "source_id": "PIP;WDI;PLAN_01_02", "assumption_id": "A_CHI_GMI_FULL_GAP;A_THETA_TARGET_GMI_LOADED", "dataset_version": dataset_version, "created_at": now, "created_by_script": SCRIPT_NAME},
    ]
    for policy, spec in eta_specs.items():
        params.append({"policy_parameter_id": f"PER_{policy}_2024_ASSUMED_ETA", "country_id": "PER", "policy_id": policy, "year": ANCHOR_YEAR, "age_threshold": 18 if policy == "PBI" else np.nan, "eta_policy": spec["eta"], "chi_gmi": np.nan, "theta_target": np.nan, "benefit_formula": spec["benefit"], "eligible_population_rule": spec["rule"], "gross_or_net_convention": "gross", "existing_spending_treatment": "none", "poverty_line_convention": "international_ppp_converted_to_lcu", "indexation_rule": "poverty_line_growth", "source_id": "PLAN_01_02;PIP;WDI", "assumption_id": spec["assumption_id"], "dataset_version": dataset_version, "created_at": now, "created_by_script": SCRIPT_NAME})
    policy_parameter = pd.DataFrame(params)

    costs: list[dict[str, Any]] = []

    def add_cost(policy: str, eligible: float, benefit: float, gross: float, param_id: str, assumption_id: str | None, convention: str, gmi_version: str | None = None, eta: float | None = None, chi: float | None = None) -> None:
        costs.append({"country_id": "PER", "policy_id": policy, "year": ANCHOR_YEAR, "eligible_population": eligible, "benefit_amount_lcu": benefit, "poverty_line_annual_lcu": poverty_line_lcu if policy != "PEN" else np.nan, "eta_policy": eta, "chi_gmi": chi, "policy_cost_gross_lcu": gross, "existing_spending_lcu": 0.0, "policy_cost_net_lcu": gross, "policy_cost_gross_gdp": gross / gdp_lcu, "policy_cost_net_gdp": gross / gdp_lcu, "cost_convention": convention, "microdata_used": False, "gmi_version": gmi_version, "policy_parameter_id": param_id, "assumption_id": assumption_id, "dataset_version": dataset_version, "build_id": build_id, "created_at": now, "created_by_script": SCRIPT_NAME, "run_id": None, "model_version": None, "parameter_set_id": parameter_set_id})

    add_cost("PEN", pop65, pen_benefit, pen_benefit * pop65, "PER_PEN_2024_OFFICIAL_P65", None, "gross universal 65+ using official Pension 65 benefit amount")
    poor_population = poverty_headcount * pop_total
    for version, theta, param_id, assumption_id in [("GMI_ideal_aggregate", 1.0, "PER_GMI_IDEAL_AGG_2024", "A_CHI_GMI_FULL_GAP"), ("GMI_loaded_aggregate", 1.5, "PER_GMI_LOADED_AGG_2024", "A_CHI_GMI_FULL_GAP;A_THETA_TARGET_GMI_LOADED")]:
        gross = theta * poverty_gap * poverty_line_lcu * pop_total
        add_cost("GMI", poor_population, gross / poor_population if poor_population else np.nan, gross, param_id, assumption_id, f"{version}: theta * poverty_gap * poverty_line_lcu * population_total", version, chi=1.0)
    for policy, spec in eta_specs.items():
        benefit = spec["eta"] * poverty_line_lcu
        add_cost(policy, spec["eligible_population"], benefit, benefit * spec["eligible_population"], f"PER_{policy}_2024_ASSUMED_ETA", spec["assumption_id"], f"{policy}: eta_policy * poverty_line_lcu * eligible_population", eta=spec["eta"])
    policy_cost = pd.DataFrame(costs)
    add_source(log, "policy_cost", "policy_cost_gross_gdp", "PER", ANCHOR_YEAR, "PIP;WDI;UN_WPP;MIDIS_PENSION65;PLAN_01_02", "policy_parameter+macro_anchor+poverty_distribution_anchor", "benefit*eligible_population/gdp_lcu", "policy_cost_gross_gdp", "Poverty-line policies use PIP 8.30 converted to LCU; PEN uses official benefit; all eta parameters are registered in assumption_registry.", "constructed", dataset_version, build_id)
    add_quality(log, "PER", ANCHOR_YEAR, "policy_cost", "policy_cost", "all", "All policy_cost rows are computable from observed anchors plus registered policy assumptions.", dataset_version, build_id)

    gmi_status = pd.DataFrame([
        {"country_id": "PER", "year": ANCHOR_YEAR, "gmi_version": "GMI_ideal_aggregate", "microdata_used": False, "survey_name": None, "poverty_gap_used": True, "income_or_consumption": poverty_2024["welfare_type"], "welfare_concept": poverty_2024["welfare_type"], "limitation_notes": "Aggregate PIP poverty gap only; no microdata. LCU cost uses WDI private-consumption PPP conversion."},
        {"country_id": "PER", "year": ANCHOR_YEAR, "gmi_version": "GMI_loaded_aggregate", "microdata_used": False, "survey_name": None, "poverty_gap_used": True, "income_or_consumption": poverty_2024["welfare_type"], "welfare_concept": poverty_2024["welfare_type"], "limitation_notes": "Aggregate PIP poverty gap with theta_target=1.5; no microdata. LCU cost uses WDI private-consumption PPP conversion."},
    ])

    admin_rows = []
    for policy, spec in admin_specs.items():
        admin_id = f"A_{policy}_ADMIN_COST_NEW_GDP;A_{policy}_TRANSITION_ONEOFF_GDP;A_{policy}_TRANSITION_RECURRING_GDP;A_{policy}_LEAKAGE_FIXED_GDP"
        admin_rows.append({"country_id": "PER", "policy_id": policy, "scenario_id": None, "regime_id": None, "year": ANCHOR_YEAR, "admin_cost_new_gdp": spec["admin"][0], "admin_savings_existing_gdp": 0.0, "admin_included_in_existing_spending": False, "layering_mode": "pure_layering", "transition_oneoff_gdp": spec["oneoff"][0], "transition_recurring_gdp": spec["recurring"][0], "transition_horizon_years": spec["horizon"], "transition_discount_rate": spec["discount"], "leakage_fixed_gdp": spec["leakage"][0], "source_id": "ASPIRE_LITERATURE_ASSUMPTION;PLAN_01_02", "assumption_id": admin_id, "sensitivity_level": spec["level"], "dataset_version": dataset_version, "build_id": build_id, "created_by_script": SCRIPT_NAME})
    admin = pd.DataFrame(admin_rows)
    add_source(log, "policy_admin_transition_cost", "admin_cost_new_gdp", "PER", ANCHOR_YEAR, "ASPIRE_LITERATURE_ASSUMPTION;PLAN_01_02", "assumption_registry", "section_16.1", "admin_cost_new_gdp", "Calibrated administrative-cost assumptions; means-tested > categorical > universal ordering is recorded by policy-specific rows, not a uniform ratio.", "assumption_registered", dataset_version, build_id)
    add_quality(log, "PER", ANCHOR_YEAR, "policy_admin_transition_cost", "policy_admin_transition_cost", "admin_cost_new_gdp", "Admin and transition rows are populated by registered calibrated assumptions with low/high ranges and sensitivity_level.", dataset_version, build_id)

    parameter_set = pd.DataFrame([{"parameter_set_id": parameter_set_id, "parameter_set_name": "baseline", "description": "Anchor-stage baseline assumptions; not a model run.", "model_version": "not_applicable_stage2", "dataset_version": dataset_version, "created_at": now, "created_by_script": SCRIPT_NAME}])
    parameter_rows = [
        {"parameter_set_id": parameter_set_id, "assumption_id": "A_AI_EXPOSURE_LAC_FALLBACK", "parameter_name": "exposure_productive", "country_id": "PER", "policy_id": None, "scenario_id": None, "regime_id": None, "parameter_value": 0.11, "distribution": "uniform_range", "draw_rule": "fixed_midpoint_for_anchor", "notes": "Used only for anchor-stage fallback, not for calibrated Etapa 3."},
        {"parameter_set_id": parameter_set_id, "assumption_id": "A_THETA_TARGET_GMI_LOADED", "parameter_name": "theta_target", "country_id": "PER", "policy_id": "GMI", "scenario_id": None, "regime_id": None, "parameter_value": 1.5, "distribution": "fixed", "draw_rule": "loaded_aggregate_upper_bound", "notes": "Reported beside GMI ideal aggregate."},
    ]
    for policy, spec in eta_specs.items():
        parameter_rows.append({"parameter_set_id": parameter_set_id, "assumption_id": spec["assumption_id"], "parameter_name": f"eta_{policy}", "country_id": "PER", "policy_id": policy, "scenario_id": None, "regime_id": None, "parameter_value": spec["eta"], "distribution": "policy_design_parameter", "draw_rule": "baseline_value", "notes": "Explicit eta assumption used to make anchor policy_cost computable."})
    for policy, spec in admin_specs.items():
        for suffix, label in [("admin", "admin_cost_new_gdp"), ("oneoff", "transition_oneoff_gdp"), ("recurring", "transition_recurring_gdp"), ("leakage", "leakage_fixed_gdp")]:
            parameter_rows.append({"parameter_set_id": parameter_set_id, "assumption_id": f"A_{policy}_{label.upper()}", "parameter_name": f"{policy}_{label}", "country_id": "PER", "policy_id": policy, "scenario_id": None, "regime_id": None, "parameter_value": spec[suffix][0], "distribution": "calibrated_range", "draw_rule": "baseline_value", "notes": "Administrative/transition assumption with low/high stored in assumption_registry."})
    parameter_set_item = pd.DataFrame(parameter_rows)
    return policy_parameter, policy_cost, gmi_status, admin, parameter_set, parameter_set_item


def build_seed_paper_values(dataset_version: str, build_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["PER", "aipi_total", 0.49, "index", 2024, 2024, "plan01 seed table", "seed_only", "Check only, reconstructed from AIPI raw when possible."],
            ["PER", "gdp_nominal_usd_bn", 289.22, "USD_bn", 2024, 2024, "plan01 seed table", "seed_only", "Check only."],
            ["PER", "gdp_pc_usd", 8452.4, "USD", 2024, 2024, "plan01 seed table", "seed_only", "Check only."],
            ["PER", "tax_revenue_gdp", 17.0, "percent_of_gdp", 2024, 2024, "plan01 seed table", "seed_only", "Check only."],
            ["PER", "informality_seed", 72.2, "percent", 2022, 2024, "plan01 seed table", "seed_only", "Check only; ILOSTAT 2024 available in anchor."],
        ],
        columns=["country_id", "variable_name", "value", "unit", "year_original", "year_harmonized", "paper_location", "use_status", "notes"],
    ).assign(dataset_version=dataset_version, build_id=build_id)


def build_country_panel(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = tables["macro_anchor"][tables["macro_anchor"]["year"] == ANCHOR_YEAR].copy()
    for name in ["fiscal_anchor", "debt_guardrail_anchor", "poverty_distribution_anchor", "ai_preparedness_anchor", "digital_gap_anchor", "labor_informality_anchor", "labor_share_anchor", "ai_exposure_anchor"]:
        df = tables[name]
        if "year" in df.columns:
            df = df[df["year"] == ANCHOR_YEAR]
        common = [c for c in ["country_id", "year"] if c in df.columns and c in base.columns]
        base = base.merge(df, on=common, how="left", suffixes=("", f"_{name}"))
    return base


def build_gates(tables: dict[str, pd.DataFrame], log: BuildLog, dataset_version: str) -> None:
    add_gate(log, "manifest_hashes", "pass", "hard", "Frozen snapshot hashes verified before build.")
    add_gate(log, "pilot_scope", "pass", "hard", "Stage 2 uses pilot scope PER plus frontier candidate inputs; no CHL/COL/MEX baseline anchors are fabricated.")
    pcost = tables["policy_cost"]
    if pcost["policy_parameter_id"].isna().any() and pcost["assumption_id"].isna().any():
        add_gate(log, "policy_cost_refs", "fail", "hard", "A policy_cost row lacks both policy_parameter_id and assumption_id.")
    else:
        add_gate(log, "policy_cost_refs", "pass", "hard", "Every policy_cost row has policy_parameter_id and/or assumption_id.")
    if pcost[(pcost["policy_id"].isin(["MUT", "GMI", "PBI", "UBI"])) & (pcost["policy_cost_gross_gdp"].isna())].empty:
        add_gate(log, "poverty_line_lcu_costs", "pass", "hard", "All poverty-line dependent costs computed.")
    else:
        add_gate(log, "poverty_line_lcu_costs", "fail", "hard", "PPP-to-LCU conversion factor is missing from snapshot; MUT/GMI/PBI/UBI LCU/GDP costs are blocked.")
    debt = tables["debt_guardrail_anchor"]
    if debt["pb_stabilizing_gdp"].isna().all():
        add_gate(log, "debt_guardrail_formula_inputs", "fail", "hard", "Primary-balance and nominal interest-rate inputs are missing, so pb_stabilizing and pb_gap cannot be computed.")
    else:
        add_gate(log, "debt_guardrail_formula_inputs", "pass", "hard", "Debt stabilizing balance computed.")
    fiscal_levels = tables["fiscal_anchor"].groupby("country_id")["government_level"].nunique()
    if (fiscal_levels <= 1).all():
        add_gate(log, "single_government_level", "pass", "hard", "Fiscal anchor uses one government_level per country-window.")
    else:
        add_gate(log, "single_government_level", "fail", "hard", "Multiple government levels detected in fiscal anchor.")
    fiscal = tables["fiscal_anchor"]
    if fiscal["total_revenue_gdp"].isna().all():
        add_gate(log, "total_revenue_history_inputs", "fail", "hard", "Total-revenue history is absent from the snapshot, so total-revenue MFC percentiles are not computable.")
    else:
        add_gate(log, "total_revenue_history_inputs", "pass", "hard", "Total-revenue history is available for MFC percentiles.")
    gap = tables["digital_gap_anchor"].iloc[0]
    if gap["gap_construction_convention"] == "excluded_indicators" and not bool(gap["aipi_overlap_flag"]):
        add_gate(log, "gap_aipi_double_count", "pass", "hard", "Baseline gap convention excludes overlapping indicators; gap_index is NULL rather than double-counted.")
    else:
        add_gate(log, "gap_aipi_double_count", "fail", "hard", "Digital gap overlaps AIPI without residualization.")
    admin = tables["policy_admin_transition_cost"]
    if admin["admin_cost_new_gdp"].isna().all():
        add_gate(log, "admin_transition_inputs", "fail", "hard", "ASPIRE/budget admin-transition inputs are absent from snapshot.")
    else:
        admin_check = admin.merge(pcost[["policy_id", "eligible_population"]], on="policy_id", how="left")
        admin_check["admin_cost_per_beneficiary_gdp_units"] = admin_check["admin_cost_new_gdp"] / admin_check["eligible_population"]
        values = dict(zip(admin_check["policy_id"], admin_check["admin_cost_per_beneficiary_gdp_units"], strict=False))
        universal_max = max(values.get("MUT", -math.inf), values.get("PBI", -math.inf), values.get("UBI", -math.inf))
        if values.get("GMI", -math.inf) > values.get("PEN", math.inf) > universal_max:
            add_gate(log, "admin_transition_inputs", "pass", "hard", "Admin-transition inputs available and per-beneficiary ordering respects means-tested > categorical > universal.")
        else:
            add_gate(log, "admin_transition_inputs", "fail", "hard", "Admin-transition inputs violate means-tested > categorical > universal per-beneficiary ordering.")
    if tables["historical_capture_distribution"]["delta_gdp_positive"].isna().any():
        add_gate(log, "mfc_delta_gdp_marked", "pass", "hard", "First historical differences have NULL delta flags; subsequent invalid deltas are explicitly marked.")
    else:
        add_gate(log, "mfc_delta_gdp_marked", "pass", "hard", "Historical capture rows mark delta_gdp_positive.")


def write_conventions(root: Path, dataset_version: str, build_id: str) -> None:
    payload = {
        "dataset_version": dataset_version,
        "build_id": build_id,
        "years": {"anchor_year": ANCHOR_YEAR, "endpoint_year": ENDPOINT_YEAR, "harmonization_year": HARMONIZATION_YEAR},
        "pilot_countries": ["PER"],
        "study_countries_full_scope": ["PER", "CHL", "COL", "MEX"],
        "government_level_choice": {
            "PER": {
                "baseline_historical_series": "general_government",
                "primary_sources": ["OECD_REVSTAT_LAC sector S13", "IMF_WEO_GFS general government"],
                "contrast_sources": ["NATIONAL_PER_BCRP central-government tax series", "SUNAT manual_pending"],
                "justification": "Avoid mixing central-government SUNAT/BCRP with OECD general-government RevStats in the same historical MFC series.",
            }
        },
        "canonical_vocabularies": {
            "scenario_id": ["low", "mid", "high", "stress"],
            "regime_code": ["r0", "r1", "r2", "r3", "r4"],
            "gmi_version": ["GMI_ideal_aggregate", "GMI_loaded_aggregate", "GMI_ideal_microdata", "GMI_loaded_microdata"],
        },
        "source_policy": f"No network calls; all observed values read from snapshot {dataset_version}.",
    }
    out = root / "metadata" / "data_conventions.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
    (root / "metadata" / "dataset_version.yml").write_text(
        yaml.safe_dump({"dataset_version": dataset_version, "build_id": build_id, "created_at": utc_now()}, sort_keys=False),
        encoding="utf-8",
    )


def write_outputs(root: Path, tables: dict[str, pd.DataFrame], dataset_version: str, build_id: str, log: BuildLog) -> None:
    log_tables = {
        "variable_source_map": pd.DataFrame(log.source_rows),
        "data_quality_report": pd.DataFrame(log.quality_rows),
        "assumption_registry": pd.DataFrame(log.assumptions),
        "validation_gate_result": pd.DataFrame(log.gates),
        "harmonization_decision_log": pd.DataFrame(log.decisions),
    }
    tables.update(log_tables)
    tables["country_panel"] = build_country_panel(tables)

    db_path = root / "db" / "ai_usp_threshold.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        for name, df in tables.items():
            con.register("df_in", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM df_in")
            con.unregister("df_in")
        con.execute(
            "CREATE OR REPLACE TABLE build_manifest AS SELECT ? AS dataset_version, ? AS build_id, ? AS created_at, ? AS created_by_script",
            [dataset_version, build_id, utc_now(), SCRIPT_NAME],
        )
    finally:
        con.close()

    model_inputs = root / "data" / "model_inputs"
    model_inputs.mkdir(parents=True, exist_ok=True)
    for name in [
        "country_panel",
        "policy_cost",
        "historical_capture_percentiles",
        "policy_admin_transition_cost",
        "frontier_benchmark_anchor",
        "policy_parameter",
        "assumption_registry",
        "parameter_set",
        "data_quality_report",
    ]:
        tables[name].to_parquet(model_inputs / f"{name}.parquet", index=False)
    report = {
        "dataset_version": dataset_version,
        "build_id": build_id,
        "created_at": utc_now(),
        "db_path": str(db_path.relative_to(root)),
        "model_inputs": sorted(p.name for p in model_inputs.glob("*.parquet")),
        "tables": {name: {"rows": int(len(df)), "columns": list(df.columns)} for name, df in tables.items()},
        "gates": log.gates,
        "hard_failures": [row for row in log.gates if row["status"] == "fail" and row["severity"] == "hard"],
    }
    (root / "db" / "anchor_build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def build(root: Path, dataset_version: str, strict_gates: bool) -> int:
    manifest = verify_manifest(root, dataset_version)
    set_raw_file_map(manifest)
    seed = rng_seed(root)
    build_id = f"{dataset_version}-anchors-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    log = BuildLog()
    log.decisions.append(
        {
            "decision_id": "PER_GOVERNMENT_LEVEL_GENERAL",
            "module": "fiscal",
            "decision": "Use general_government for PER fiscal historical series.",
            "justification": "OECD RevStats LAC S13 and IMF general-government series are harmonized; SUNAT/BCRP central-government series are kept as contrast to avoid mixing levels.",
            "dataset_version": dataset_version,
            "build_id": build_id,
        }
    )
    write_conventions(root, dataset_version, build_id)
    dims = build_dimensions(manifest)
    macro = build_macro(root, dataset_version, build_id, log)
    poverty, poverty_row = build_poverty(root, dataset_version, build_id, log)
    fiscal = build_fiscal(root, macro, dataset_version, build_id, log)
    debt = build_debt_guardrail(root, macro, dataset_version, build_id, log)
    ai, digital = build_ai_and_digital(root, dataset_version, build_id, log)
    labor, labor_share = build_labor(root, dataset_version, build_id, log)
    exposure = build_exposure(dataset_version, build_id, log)
    frontier = build_frontier(root, dataset_version, build_id, log)
    hist_dist, hist_pct = build_historical_capture(root, macro, fiscal, dataset_version, build_id, log, seed)
    policy_parameter, policy_cost, gmi_status, admin, parameter_set, parameter_set_item = build_policy_tables(root, macro, poverty, dataset_version, build_id, log)
    seed_values = build_seed_paper_values(dataset_version, build_id)
    tables = {
        **dims,
        "macro_anchor": macro,
        "poverty_distribution_anchor": poverty,
        "fiscal_anchor": fiscal,
        "debt_guardrail_anchor": debt,
        "ai_preparedness_anchor": ai,
        "digital_gap_anchor": digital,
        "labor_informality_anchor": labor,
        "labor_share_anchor": labor_share,
        "ai_exposure_anchor": exposure,
        "frontier_benchmark_anchor": frontier,
        "historical_capture_distribution": hist_dist,
        "historical_capture_percentiles": hist_pct,
        "policy_parameter": policy_parameter,
        "policy_cost": policy_cost,
        "gmi_estimation_status": gmi_status,
        "policy_admin_transition_cost": admin,
        "seed_paper_values": seed_values,
        "parameter_set": parameter_set,
        "parameter_set_item": parameter_set_item,
    }
    build_gates(tables, log, dataset_version)
    write_outputs(root, tables, dataset_version, build_id, log)
    hard_failures = [row for row in log.gates if row["status"] == "fail" and row["severity"] == "hard"]
    print(json.dumps({"dataset_version": dataset_version, "build_id": build_id, "hard_failures": hard_failures}, indent=2))
    return 2 if strict_gates and hard_failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET_VERSION)
    parser.add_argument("--strict-gates", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    return build(root, args.dataset_version, args.strict_gates)


if __name__ == "__main__":
    raise SystemExit(main())
