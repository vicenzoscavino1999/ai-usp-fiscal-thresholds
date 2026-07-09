"""Build official 4-country anchors and pre-run calibration artifacts.

This is Etapa 4A only: it reads the frozen official raw snapshot, builds anchor
tables and the baseline-official-v1 calibration registry for author review. It
does not import or run the model engine under src/ai_usp.
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
DATASET_VERSION = "v1.0.0-official-4c"
PARAMETER_SET_ID = "baseline-official-v1"
ANCHOR_YEAR = 2024
BOOTSTRAP_DRAWS = 2000
COUNTRIES = ["PER", "CHL", "COL", "MEX"]
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
    "NE.IMP.GNFS.ZS": "imports_gdp_share",
    "NE.CON.TOTL.ZS": "final_consumption_gdp_share",
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
    "AT": "AUT",
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
    "NL": "NLD",
    "NO": "NOR",
    "PL": "POL",
    "PT": "PRT",
    "RO": "ROU",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
    "TR": "TUR",
}
COUNTRY_NAMES = {"PER": "Peru", "CHL": "Chile", "COL": "Colombia", "MEX": "Mexico"}
OFFICIAL_PENSION = {
    "PER": {
        "source_id": "MIDIS_PENSION65",
        "benefit_annual_lcu": 1500.0,
        "age_rule": "age>=65",
        "age_threshold": 65,
        "benefit_formula": "S/250 every two months * 6 = S/1500 annual",
        "citation": "https://www.gob.pe/pension65",
    },
    "CHL": {
        "source_id": "SP_CHILE_PGU_2024",
        "benefit_annual_lcu": 214296.0 * 12.0,
        "age_rule": "age>=65",
        "age_threshold": 65,
        "benefit_formula": "PGU maximum CLP 214,296 monthly from 2024-02-01 * 12",
        "citation": "https://www.spensiones.cl/portal/institucional/594/w3-article-15857.html",
    },
    "COL": {
        "source_id": "PROSPERIDAD_SOCIAL_COLOMBIA_MAYOR_2024",
        "benefit_annual_lcu": None,
        "age_rule": "female age>=54, male age>=59; COP 80,000 monthly under 80 and COP 225,000 monthly age>=80",
        "age_threshold": np.nan,
        "benefit_formula": "Colombia Mayor differential 2024: monthly 80,000 below 80; monthly 225,000 for 80+",
        "citation": "https://prosperidadsocial.gov.co/colombia-mayor/",
    },
    "MEX": {
        "source_id": "BIENESTAR_MEXICO_ADULTOS_MAYORES_2024",
        "benefit_annual_lcu": 6000.0 * 6.0,
        "age_rule": "age>=65",
        "age_threshold": 65,
        "benefit_formula": "MXN 6,000 bimonthly in 2024 * 6",
        "citation": "https://www.gob.mx/bienestar/prensa/2024-inicia-con-aumentos-a-pensiones-de-bienestar-anuncia-ariadna-montiel?idiom=es",
    },
}
AIPI_NOTE_URL = "https://www.imf.org/external/datamapper/AIPINote.pdf"


@dataclass
class Log:
    sources: list[dict[str, Any]] = field(default_factory=list)
    quality: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rng_policy(root: Path) -> dict[str, Any]:
    path = root / "reproducibility" / "config" / "rng_policy.yaml"
    if not path.exists():
        return {"historical_bootstrap_seed": 20240707, "historical_bootstrap_draws": BOOTSTRAP_DRAWS}
    policy = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "historical_bootstrap_seed" not in policy:
        raise RuntimeError("reproducibility/config/rng_policy.yaml lacks historical_bootstrap_seed")
    return policy


def verify_manifest(root: Path, dataset_version: str) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
    manifest_path = root / "reproducibility" / "snapshot" / f"dataset_manifest_{dataset_version}.json"
    if not manifest_path.exists():
        manifest_path = root / "reproducibility" / "snapshot" / "dataset_manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("dataset_version") != dataset_version:
        raise RuntimeError(f"Active manifest is {manifest.get('dataset_version')}, expected {dataset_version}")
    raw_map: dict[tuple[str, str], Path] = {}
    errors = []
    for source in manifest.get("sources", []):
        source_dir = source.get("source_dir")
        for raw_file in source.get("raw_files", []):
            rel = Path(str(raw_file["path"]).replace("\\", "/"))
            path = root / rel
            if not path.exists():
                errors.append(f"missing raw file {rel}")
                continue
            actual = sha256_file(path)
            if actual != raw_file["sha256"]:
                errors.append(f"hash mismatch {rel}")
            raw_map[(str(source_dir), rel.name)] = rel
    if errors:
        raise RuntimeError("; ".join(errors))
    return manifest, raw_map


def read_parquet(root: Path, raw_map: dict[tuple[str, str], Path], source_dir: str, filename: str) -> pd.DataFrame:
    rel = raw_map.get((source_dir, filename))
    if rel is None:
        raise RuntimeError(f"Missing {source_dir}/{filename} in manifest")
    return pd.read_parquet(root / rel)


def add_source(log: Log, **row: Any) -> None:
    row.setdefault("created_by_script", SCRIPT_NAME)
    log.sources.append(row)


def add_quality(log: Log, **row: Any) -> None:
    row.setdefault("created_by_script", SCRIPT_NAME)
    log.quality.append(row)


def add_assumption(
    log: Log,
    assumption_id: str,
    module: str,
    parameter_name: str,
    baseline: float | None,
    low: float | None,
    high: float | None,
    distribution: str,
    justification: str,
    source_id: str,
    country_id: str | None = None,
) -> None:
    log.assumptions.append(
        {
            "assumption_id": assumption_id,
            "module": module,
            "parameter_name": parameter_name,
            "country_id": country_id,
            "baseline_value": baseline,
            "low_value": low,
            "high_value": high,
            "distribution": distribution,
            "justification": justification,
            "source_id": source_id,
            "is_observed": False,
            "is_scenario": False,
            "is_structural_unobserved": True,
            "sensitivity_level": "baseline",
            "created_at": now(),
            "created_by_script": SCRIPT_NAME,
        }
    )


def last_value(df: pd.DataFrame, country: str, code_col: str, code: str, value_col: str, year_col: str = "year") -> float:
    sub = df[(df["country_id"] == country) & (df[code_col] == code) & (pd.to_numeric(df[year_col], errors="coerce") <= ANCHOR_YEAR)].copy()
    sub = sub.sort_values(year_col)
    if sub.empty:
        return math.nan
    return float(pd.to_numeric(sub.iloc[-1][value_col], errors="coerce"))


def pivot_wdi(wdi: pd.DataFrame) -> pd.DataFrame:
    rows = wdi[wdi["indicator_code"].isin(WDI_MAP)].copy()
    rows["variable"] = rows["indicator_code"].map(WDI_MAP)
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    return rows.pivot_table(index=["country_id", "year"], columns="variable", values="value", aggfunc="first").reset_index()


def wpp_counts(wpp: pd.DataFrame, country: str, year: int) -> dict[str, float]:
    sub = wpp[(wpp["ISO3_code"] == country) & (wpp["Time"] == year)].copy()
    if sub.empty:
        return {}
    sub["AgeGrpStart"] = pd.to_numeric(sub["AgeGrpStart"], errors="coerce")
    sub["PopMale"] = pd.to_numeric(sub.get("PopMale"), errors="coerce")
    sub["PopFemale"] = pd.to_numeric(sub.get("PopFemale"), errors="coerce")
    sub["PopTotal"] = pd.to_numeric(sub["PopTotal"], errors="coerce")
    return {
        "population_total_wpp": float(sub["PopTotal"].sum() * 1000.0),
        "population_65_plus": float(sub.loc[sub["AgeGrpStart"] >= 65, "PopTotal"].sum() * 1000.0),
        "population_80_plus": float(sub.loc[sub["AgeGrpStart"] >= 80, "PopTotal"].sum() * 1000.0),
        "population_15_64": float(sub.loc[sub["AgeGrpStart"].between(15, 64), "PopTotal"].sum() * 1000.0),
        "population_18_plus": float(sub.loc[sub["AgeGrpStart"] >= 18, "PopTotal"].sum() * 1000.0),
        "population_colombia_mayor_rule": float(
            (
                sub.loc[sub["AgeGrpStart"] >= 59, "PopMale"].sum()
                + sub.loc[sub["AgeGrpStart"] >= 54, "PopFemale"].sum()
            )
            * 1000.0
        ),
        "population_colombia_mayor_80_plus": float(sub.loc[sub["AgeGrpStart"] >= 80, "PopTotal"].sum() * 1000.0),
    }


def build_dimensions(manifest: dict[str, Any]) -> dict[str, pd.DataFrame]:
    dim_country = pd.DataFrame(
        [
            {"country_id": c, "country_name": COUNTRY_NAMES[c], "region": "Latin America", "income_group_2024": None, "pilot_role": "official_4c_scope"}
            for c in COUNTRIES
        ]
    )
    dim_policy = pd.DataFrame(
        [
            ["PEN", "Official social pension benchmark", "pension"],
            ["MUT", "Minimum Universal Transfer", "transfer"],
            ["GMI", "Guaranteed Minimum Income", "guaranteed_income"],
            ["PBI", "Partial Basic Income", "basic_income"],
            ["UBI", "Full UBI benchmark", "stress_benchmark"],
        ],
        columns=["policy_id", "policy_name", "policy_type"],
    )
    source_rows = []
    for source in manifest.get("sources", []):
        license_notes = source.get("license_notes") or "See provider terms; raw snapshot preserves metadata."
        if source.get("source_dir") == "ookla":
            license_notes = source.get("license_notes") or "CC BY-NC-SA 4.0; raw public archival deferred."
        source_rows.append(
            {
                "source_id": source.get("source_id"),
                "source_name": source.get("source_dir"),
                "provider": source.get("source_id"),
                "url_or_api": source.get("source_url"),
                "download_date": str(source.get("download_date") or "")[:10],
                "license_notes": license_notes,
                "raw_file_path": ";".join(raw.get("path", "") for raw in source.get("raw_files", [])),
                "citation_text": source.get("notes"),
            }
        )
    source_rows.extend(
        [
            {"source_id": "SP_CHILE_PGU_2024", "source_name": "Chile PGU official 2024", "provider": "Superintendencia de Pensiones Chile", "url_or_api": OFFICIAL_PENSION["CHL"]["citation"], "download_date": "", "license_notes": "official public information", "raw_file_path": "", "citation_text": OFFICIAL_PENSION["CHL"]["benefit_formula"]},
            {"source_id": "PROSPERIDAD_SOCIAL_COLOMBIA_MAYOR_2024", "source_name": "Colombia Mayor official 2024", "provider": "Prosperidad Social Colombia", "url_or_api": OFFICIAL_PENSION["COL"]["citation"], "download_date": "", "license_notes": "official public information", "raw_file_path": "", "citation_text": OFFICIAL_PENSION["COL"]["benefit_formula"]},
            {"source_id": "BIENESTAR_MEXICO_ADULTOS_MAYORES_2024", "source_name": "Mexico Pension Bienestar 2024", "provider": "Secretaria de Bienestar Mexico", "url_or_api": OFFICIAL_PENSION["MEX"]["citation"], "download_date": "", "license_notes": "official public information", "raw_file_path": "", "citation_text": OFFICIAL_PENSION["MEX"]["benefit_formula"]},
            {"source_id": "IMF_AIPI_NOTE_COMPONENTS", "source_name": "AIPI component note", "provider": "IMF", "url_or_api": AIPI_NOTE_URL, "download_date": "", "license_notes": "public documentation", "raw_file_path": "", "citation_text": "Used only to verify coverage/speed indicators are excluded from the AIPI component list."},
            {"source_id": "PLAN_01_02", "source_name": "Project plans", "provider": "author", "url_or_api": "01_database_construction_plan_AI_USP_threshold_framework_v6.md; 02_ESD_AI_USP_v6.md", "download_date": "", "license_notes": "project documentation", "raw_file_path": "", "citation_text": "Frozen methodological conventions."},
        ]
    )
    return {"dim_country": dim_country, "dim_policy": dim_policy, "dim_source": pd.DataFrame(source_rows)}


def build_macro(root: Path, raw_map: dict[tuple[str, str], Path], dataset_version: str, build_id: str, log: Log) -> pd.DataFrame:
    wdi = read_parquet(root, raw_map, "wdi", "wdi_country_year.parquet")
    wpp = read_parquet(root, raw_map, "wpp", "wpp_projections.parquet")
    wide = pivot_wdi(wdi)
    wide = wide[(wide["country_id"].isin(COUNTRIES)) & (wide["year"].between(2000, ANCHOR_YEAR))].copy()
    wide["population_65_plus"] = wide["population_total"] * wide.get("population_65_plus_pct") / 100.0
    wide["population_15_64"] = wide["population_total"] * wide.get("population_15_64_pct") / 100.0
    for country in COUNTRIES:
        counts = wpp_counts(wpp, country, ANCHOR_YEAR)
        idx = (wide["country_id"] == country) & (wide["year"] == ANCHOR_YEAR)
        for key, value in counts.items():
            wide.loc[idx, key] = value
        for var in ["gdp_nominal_lcu", "population_total", "ppp_conversion_private_consumption", "cpi_index"]:
            add_source(log, table_name="macro_anchor", variable_name=var, country_id=country, year=ANCHOR_YEAR, source_id="WDI;UN_WPP" if var.startswith("population_") else "WDI", transformation_notes="Official 4C macro anchor from WDI, with WPP single-age counts at anchor year where needed.", dataset_version=dataset_version, build_id=build_id)
    wide["harmonization_flag"] = np.where(wide["year"] == ANCHOR_YEAR, "observed_2024", "historical_observed")
    wide["dataset_version"] = dataset_version
    wide["build_id"] = build_id
    wide["created_at"] = now()
    wide["created_by_script"] = SCRIPT_NAME
    return wide


def build_poverty(root: Path, raw_map: dict[tuple[str, str], Path], macro: pd.DataFrame, dataset_version: str, build_id: str, log: Log) -> pd.DataFrame:
    pip = read_parquet(root, raw_map, "pip", "pip_poverty.parquet")
    rows = []
    for country in COUNTRIES:
        p = pip[(pip["country_id"] == country) & (pd.to_numeric(pip["poverty_line"], errors="coerce").round(2) == 8.30) & (pd.to_numeric(pip["year"], errors="coerce") <= ANCHOR_YEAR)].copy()
        if p.empty:
            raise RuntimeError(f"Missing PIP 8.30 poverty line for {country}")
        p = p.sort_values("year").iloc[-1]
        m = macro[(macro["country_id"] == country) & (macro["year"] == ANCHOR_YEAR)].iloc[0]
        m2021 = macro[(macro["country_id"] == country) & (macro["year"] == 2021)]
        if m2021.empty:
            raise RuntimeError(f"Missing 2021 macro row for PPP poverty conversion: {country}")
        m2021 = m2021.iloc[0]
        line_lcu = 8.30 * float(m2021["ppp_conversion_private_consumption"]) * (float(m["cpi_index"]) / float(m2021["cpi_index"])) * 365.0
        rows.append(
            {
                "country_id": country,
                "year": ANCHOR_YEAR,
                "poverty_line_ppp_daily": 8.30,
                "poverty_line_ppp_annual": 8.30 * 365.0,
                "poverty_line_national_lcu_annual": line_lcu,
                "poverty_headcount": float(p["headcount"]),
                "poverty_gap": float(p["poverty_gap"]),
                "mean_income_or_consumption": p.get("mean_income_or_consumption"),
                "welfare_type": p.get("welfare_type"),
                "source_year": int(p["year"]),
                "harmonization_flag": "observed_2024" if int(p["year"]) == ANCHOR_YEAR else f"carried_forward_from_{int(p['year'])}",
                "dataset_version": dataset_version,
                "build_id": build_id,
                "created_at": now(),
                "created_by_script": SCRIPT_NAME,
            }
        )
        add_source(log, table_name="poverty_distribution_anchor", variable_name="poverty_line_national_lcu_annual", country_id=country, year=ANCHOR_YEAR, source_id="PIP;WDI", transformation_notes="linea_lcu_anual_2024 = 8.30 * PPP_conv_privado_2021 * (CPI_2024 / CPI_2021) * 365.", dataset_version=dataset_version, build_id=build_id)
    return pd.DataFrame(rows)


def build_fiscal(root: Path, raw_map: dict[tuple[str, str], Path], macro: pd.DataFrame, dataset_version: str, build_id: str, log: Log) -> pd.DataFrame:
    oecd = read_parquet(root, raw_map, "oecd", "oecd_revenue.parquet")
    imf = read_parquet(root, raw_map, "imf", "imf_fiscal_macro.parquet")
    rows = []
    for country in COUNTRIES:
        base = pd.DataFrame({"country_id": country, "year": list(range(2000, ANCHOR_YEAR + 1))})
        o = oecd[(oecd["REF_AREA"] == country) & (oecd["UNIT_MEASURE"] == "PT_B1GQ") & (oecd["SECTOR"] == "S13")].copy()
        for code, var in FISCAL_REVENUE_CODES.items():
            sub = o[o["STANDARD_REVENUE"] == code][["TIME_PERIOD", "OBS_VALUE"]].rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": var})
            base = base.merge(sub, on="year", how="left")
        rev = imf[(imf["country_id"] == country) & (imf["variable_code"] == "GGR_NGDP")][["year", "value"]].rename(columns={"value": "total_revenue_gdp"})
        base = base.merge(rev, on="year", how="left")
        base["government_level"] = "general_government"
        base["dataset_version"] = dataset_version
        base["build_id"] = build_id
        base["created_at"] = now()
        base["created_by_script"] = SCRIPT_NAME
        rows.append(base)
        log.decisions.append(
            {
                "decision_id": f"{country}_GOVERNMENT_LEVEL_GENERAL",
                "module": "fiscal",
                "decision": "Use general_government for official 4C fiscal historical series.",
                "justification": "OECD RevStats LAC S13 and IMF general-government series keep the MFC window on one government level.",
                "country_id": country,
                "dataset_version": dataset_version,
                "build_id": build_id,
            }
        )
    return pd.concat(rows, ignore_index=True)


def build_debt(root: Path, raw_map: dict[tuple[str, str], Path], macro: pd.DataFrame, dataset_version: str, build_id: str) -> pd.DataFrame:
    imf = read_parquet(root, raw_map, "imf", "imf_fiscal_macro.parquet")
    parts = []
    for country in COUNTRIES:
        d = imf[(imf["country_id"] == country) & (imf["year"].between(2000, ANCHOR_YEAR))].pivot_table(index=["country_id", "year"], columns="variable_code", values="value", aggfunc="first").reset_index()
        d = d.rename(columns={"GGXWDG_NGDP": "gross_debt_gdp", "GGXONLB_NGDP": "primary_balance_gdp", "GGXCNL_NGDP": "net_lending_borrowing_gdp"})
        m = macro[macro["country_id"] == country][["country_id", "year", "gdp_nominal_lcu"]].copy()
        m["nominal_growth_rate"] = m.sort_values("year")["gdp_nominal_lcu"].pct_change()
        d = d.merge(m[["country_id", "year", "nominal_growth_rate"]], on=["country_id", "year"], how="left")
        d["gross_debt_gdp_lag"] = d.sort_values("year")["gross_debt_gdp"].shift(1)
        d["interest_payments_gdp"] = d["primary_balance_gdp"] - d["net_lending_borrowing_gdp"]
        d["nominal_interest_rate"] = d["interest_payments_gdp"] / d["gross_debt_gdp_lag"]
        d["pb_stabilizing_gdp"] = ((d["nominal_interest_rate"] - d["nominal_growth_rate"]) / (1 + d["nominal_growth_rate"])) * d["gross_debt_gdp"]
        d["pb_gap_gdp"] = d["primary_balance_gdp"] - d["pb_stabilizing_gdp"]
        d["dataset_version"] = dataset_version
        d["build_id"] = build_id
        d["created_at"] = now()
        d["created_by_script"] = SCRIPT_NAME
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def build_frontier(root: Path, raw_map: dict[tuple[str, str], Path], dataset_version: str, build_id: str) -> pd.DataFrame:
    raw = read_parquet(root, raw_map, "frontier", "frontier_benchmark.parquet")
    aipi = read_parquet(root, raw_map, "imf_aipi", "aipi.parquet")
    rows = raw.copy()
    rows["benchmark_country_id"] = rows.get("geo").map(EUROSTAT_TO_ISO3) if "geo" in rows else rows.get("benchmark_country_id")
    rows["year"] = pd.to_numeric(rows.get("time"), errors="coerce").astype("Int64") if "time" in rows else pd.NA
    rows["adoption_proxy"] = pd.to_numeric(rows["value"], errors="coerce") / 100.0
    rows = rows[(rows["benchmark_country_id"].isin(BENCHMARK_COUNTRIES)) & (rows["year"] == ANCHOR_YEAR)].copy()
    latest_aipi = aipi.sort_values("year").dropna(subset=["aipi_total"]).groupby("country_id").tail(1)[["country_id", "aipi_total"]]
    rows = rows.merge(latest_aipi.rename(columns={"country_id": "benchmark_country_id"}), on="benchmark_country_id", how="left")
    rows = rows[["benchmark_country_id", "year", "adoption_proxy", "aipi_total"]].dropna(subset=["adoption_proxy"])
    rows["benchmark_set_id"] = "baseline_oecd_eurostat_ge10_2024"
    rows["score_convention"] = "pending_official_run_S_NDC_beta1_gamma1_alpha0"
    rows["elasticities_used"] = "beta=1;gamma=1;alpha=0;computed_in_engine_not_in_4A"
    rows["population_consistency_note"] = "OECD/advanced Eurostat enterprise AI adoption benchmark matched to phi_mid population."
    rows["dataset_version"] = dataset_version
    rows["build_id"] = build_id
    return rows.reset_index(drop=True)


def latest_indicator(itu: pd.DataFrame, country: str, code: str, max_year: int = ANCHOR_YEAR) -> float:
    sub = itu[(itu["country_id"] == country) & (itu["indicator_code"] == code) & (pd.to_numeric(itu["year"], errors="coerce") <= max_year)].copy()
    if sub.empty:
        return math.nan
    sub = sub.sort_values("year")
    return float(pd.to_numeric(sub.iloc[-1]["value"], errors="coerce"))


def build_ai_gap(root: Path, raw_map: dict[tuple[str, str], Path], frontier: pd.DataFrame, dataset_version: str, build_id: str, log: Log) -> tuple[pd.DataFrame, pd.DataFrame]:
    aipi = read_parquet(root, raw_map, "imf_aipi", "aipi.parquet")
    itu = read_parquet(root, raw_map, "itu", "itu_digital.parquet")
    ookla = read_parquet(root, raw_map, "ookla", "ookla_speedtest.parquet")
    latest_aipi = aipi[aipi["country_id"].isin(COUNTRIES)].sort_values("year").groupby("country_id").tail(1).copy()
    ai = latest_aipi[["country_id", "aipi_total", "digital_infrastructure", "human_capital_labor", "innovation_integration", "regulation_ethics"]].copy()
    ai["year"] = ANCHOR_YEAR
    ai["source_year"] = latest_aipi["year"].to_numpy()
    ai["harmonization_flag"] = np.where(ai["source_year"] == ANCHOR_YEAR, "observed_2024", "carried_forward")
    ai["dataset_version"] = dataset_version
    ai["build_id"] = build_id
    ai["created_at"] = now()
    ai["created_by_script"] = SCRIPT_NAME

    speed = ookla[(ookla["year"] == ANCHOR_YEAR) & (ookla["quarter"] == 4)]
    fixed = speed[speed["service_type"] == "fixed"].set_index("country_id")["download_median_mbps"]
    mobile = speed[speed["service_type"] == "mobile"].set_index("country_id")["download_median_mbps"]
    bench_lte = [latest_indicator(itu, c, "ITU_COVERAGE_LTE_WIMAX") for c in BENCHMARK_COUNTRIES]
    bench_fixed = fixed.reindex(BENCHMARK_COUNTRIES).dropna()
    bench_mobile = mobile.reindex(BENCHMARK_COUNTRIES).dropna()
    means = {
        "coverage_lte_pct": float(np.nanmean(bench_lte)),
        "speed_fixed_download_mbps": float(bench_fixed.mean()),
        "speed_mobile_download_mbps": float(bench_mobile.mean()),
    }
    if any(not np.isfinite(v) or v <= 0 for v in means.values()):
        raise RuntimeError(f"Gap benchmark normalization means invalid: {means}")

    gap_rows = []
    for country in COUNTRIES:
        mobile_any = latest_indicator(itu, country, "ITU_COVERAGE_MOBILE_CELLULAR")
        coverage_3g = latest_indicator(itu, country, "ITU_COVERAGE_AT_LEAST_3G")
        lte = latest_indicator(itu, country, "ITU_COVERAGE_LTE_WIMAX")
        fixed_speed = float(fixed.get(country, math.nan))
        mobile_speed = float(mobile.get(country, math.nan))
        missing = [name for name, val in [("coverage_lte_pct", lte), ("speed_fixed_download_mbps", fixed_speed), ("speed_mobile_download_mbps", mobile_speed)] if not np.isfinite(val)]
        if missing:
            raise RuntimeError(f"Gap official inputs missing for {country}: {missing}")
        norm_lte = min(lte / means["coverage_lte_pct"], 1.0)
        norm_fixed = min(fixed_speed / means["speed_fixed_download_mbps"], 1.0)
        norm_mobile = min(mobile_speed / means["speed_mobile_download_mbps"], 1.0)
        composite = float(np.mean([norm_lte, norm_fixed, norm_mobile]))
        gap_index = 1.0 - composite
        gap_rows.append(
            {
                "country_id": country,
                "year": ANCHOR_YEAR,
                "coverage_mobile_cellular_pct": mobile_any,
                "coverage_3g_pct": coverage_3g,
                "coverage_lte_wimax_pct": lte,
                "speed_fixed_download_mbps": fixed_speed,
                "speed_mobile_download_mbps": mobile_speed,
                "coverage_lte_normalized": norm_lte,
                "speed_fixed_normalized": norm_fixed,
                "speed_mobile_normalized": norm_mobile,
                "connectivity_composite": composite,
                "gap_index": gap_index,
                "normalization_method": "relative_to_frontier_benchmark_set_mean_capped_at_1",
                "benchmark_set_id": "baseline_oecd_eurostat_ge10_2024",
                "benchmark_coverage_lte_pct_mean": means["coverage_lte_pct"],
                "benchmark_speed_fixed_mbps_mean": means["speed_fixed_download_mbps"],
                "benchmark_speed_mobile_mbps_mean": means["speed_mobile_download_mbps"],
                "gap_construction_convention": "excluded_indicators",
                "aipi_overlap_flag": False,
                "aipi_exclusion_verification": (
                    f"Verified against IMF AIPI note {AIPI_NOTE_URL}: AIPI component list does not include "
                    "mobile-network technology coverage or Ookla measured fixed/mobile download speeds."
                ),
                "dataset_version": dataset_version,
                "build_id": build_id,
                "created_at": now(),
                "created_by_script": SCRIPT_NAME,
            }
        )
        for var, source in [
            ("coverage_lte_wimax_pct", "ITU_DATAHUB"),
            ("speed_fixed_download_mbps", "OOKLA_SPEEDTEST_OPEN_DATA"),
            ("speed_mobile_download_mbps", "OOKLA_SPEEDTEST_OPEN_DATA"),
            ("gap_index", "ITU_DATAHUB;OOKLA_SPEEDTEST_OPEN_DATA;IMF_AIPI_NOTE_COMPONENTS"),
        ]:
            add_source(log, table_name="digital_gap_anchor", variable_name=var, country_id=country, year=ANCHOR_YEAR, source_id=source, transformation_notes=f"Excluded-indicator Gap input. Exclusion verified against {AIPI_NOTE_URL}.", dataset_version=dataset_version, build_id=build_id)
    return ai, pd.DataFrame(gap_rows)


def build_labor(root: Path, raw_map: dict[tuple[str, str], Path], dataset_version: str, build_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ilo = read_parquet(root, raw_map, "ilostat", "ilostat_labor.parquet")
    pwt = read_parquet(root, raw_map, "pwt", "pwt_country_year.parquet")
    labor_rows = []
    share_rows = []
    for country in COUNTRIES:
        sub = ilo[(ilo["country_id"] == country) & (ilo["indicator_code"] == "EMP_NIFL_SEX_AGE_RT") & (pd.to_numeric(ilo["year"], errors="coerce") <= ANCHOR_YEAR)].copy()
        if "sex" in sub:
            total = sub[sub["sex"].astype(str).isin(["SEX_T", "T", "Total", "TOTAL"])]
            if not total.empty:
                sub = total
        if sub.empty:
            raise RuntimeError(f"Missing ILOSTAT informality for {country}")
        sub = sub.sort_values("year").iloc[-1]
        labor_rows.append({"country_id": country, "year": ANCHOR_YEAR, "informality_total": float(sub["value"]), "informality_labor_tax_base": np.nan, "informality_consumption_tax_base": np.nan, "informality_capital_tax_base": np.nan, "rst_proxy": np.nan, "source_year": int(sub["year"]), "dataset_version": dataset_version, "build_id": build_id, "created_at": now(), "created_by_script": SCRIPT_NAME})
        ps = pwt[(pwt["country_id"] == country) & (pd.to_numeric(pwt["year"], errors="coerce") <= ANCHOR_YEAR)].sort_values("year")
        if ps.empty:
            raise RuntimeError(f"Missing PWT labor share for {country}")
        p = ps.iloc[-1]
        share_rows.append({"country_id": country, "year": ANCHOR_YEAR, "labor_share_raw": float(p["labsh"]), "labor_share_adjusted": float(p["labsh"]), "source_year": int(p["year"]), "adjustment_notes": "PWT labsh carried forward; no separate adjustment in 4A.", "dataset_version": dataset_version, "build_id": build_id, "created_at": now(), "created_by_script": SCRIPT_NAME})
    return pd.DataFrame(labor_rows), pd.DataFrame(share_rows)


def build_exposure(dataset_version: str, build_id: str, log: Log) -> pd.DataFrame:
    rows = []
    for country in COUNTRIES:
        rows.append({"country_id": country, "year": ANCHOR_YEAR, "exposure_productive": 0.11, "exposure_automation": 0.035, "exposure_augmentation": 0.11, "is_lac_fallback": True, "source_id": "PLAN_01_02;PAPER_LAC_AUTOMATION_RISK_ANCHOR", "assumption_id": "A_AI_EXPOSURE_LAC_FALLBACK", "dataset_version": dataset_version, "build_id": build_id, "created_at": now(), "created_by_script": SCRIPT_NAME})
        add_assumption(log, "A_AI_EXPOSURE_LAC_FALLBACK", "ai_exposure", "exposure_productive", 0.11, 0.08, 0.14, "bounded_PERT", "LAC fallback used for all official 4C countries pending occupation-specific exposure.", "PLAN_01_02", country)
    return pd.DataFrame(rows)


def pct(values: pd.Series, q: float) -> float:
    if values is None or len(values) == 0:
        return np.nan
    return float(np.nanpercentile(values, q))


def empty_percentile_row(country: str, government_level: str, concept: str, sample: str, dataset_version: str, build_id: str, warning: str, draws: int, seed: int) -> dict[str, Any]:
    return {
        "country_id": country,
        "government_level": government_level,
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
        "ci_method": f"bootstrap percentile, B={draws}, seed={seed}, PCG64",
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


def build_historical(macro: pd.DataFrame, fiscal: pd.DataFrame, dataset_version: str, build_id: str, rng_policy: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    dist_rows = []
    pct_rows = []
    seed = int(rng_policy["historical_bootstrap_seed"])
    draws = int(rng_policy.get("historical_bootstrap_draws", BOOTSTRAP_DRAWS))
    rng = np.random.Generator(np.random.PCG64(seed))
    samples = {
        "2000plus": lambda x: x["year"] >= 2000,
        "2010plus": lambda x: x["year"] >= 2010,
        "2015plus": lambda x: x["year"] >= 2015,
        "excl_pandemic_2020_2021": lambda x: ~x["year"].isin([2020, 2021]),
    }
    for country in COUNTRIES:
        m = macro[macro["country_id"] == country][["country_id", "year", "gdp_nominal_lcu"]]
        f = fiscal[fiscal["country_id"] == country][["country_id", "year", "tax_revenue_gdp", "total_revenue_gdp"]]
        base = m.merge(f, on=["country_id", "year"], how="left").sort_values("year")
        for concept, pct_col in [("tax", "tax_revenue_gdp"), ("total_revenue", "total_revenue_gdp")]:
            df = base[["country_id", "year", "gdp_nominal_lcu", pct_col]].copy().sort_values("year")
            df["revenue_concept"] = concept
            df["government_level"] = "general_government"
            df["revenue_lcu"] = pd.to_numeric(df[pct_col], errors="coerce") / 100.0 * df["gdp_nominal_lcu"]
            df["delta_revenue_lcu"] = df["revenue_lcu"].diff()
            df["delta_gdp_lcu"] = df["gdp_nominal_lcu"].diff()
            df["mfc_hist_gross"] = df["delta_revenue_lcu"] / df["delta_gdp_lcu"]
            df["mfc_tax_hist_gross"] = df["mfc_hist_gross"] if concept == "tax" else np.nan
            df["mfc_total_revenue_hist_gross"] = df["mfc_hist_gross"] if concept == "total_revenue" else np.nan
            df["mfc_nonresource_hist_gross"] = np.nan
            df["mfc_smoothed_3y"] = df["mfc_hist_gross"].rolling(3, min_periods=1).mean()
            df["buoyancy_hist"] = np.log(df["revenue_lcu"] / df["revenue_lcu"].shift(1)) / np.log(df["gdp_nominal_lcu"] / df["gdp_nominal_lcu"].shift(1))
            df["is_non_negative_capture"] = df["mfc_hist_gross"].map(lambda x: bool(x >= 0) if pd.notna(x) else None)
            df["delta_gdp_positive"] = df["delta_gdp_lcu"].map(lambda x: bool(x > 0) if pd.notna(x) else None)
            df["crisis_year_flag"] = df["year"].isin([2008, 2009])
            df["commodity_shock_flag"] = False
            df["pandemic_flag"] = df["year"].isin([2020, 2021])
            df["source_mix"] = "OECD tax percent of GDP + WDI GDP LCU" if concept == "tax" else "IMF total revenue percent of GDP + WDI GDP LCU"
            df["dataset_version"] = dataset_version
            df["build_id"] = build_id
            df["created_by_script"] = SCRIPT_NAME
            dist_rows.append(df)
    dist = pd.concat(dist_rows, ignore_index=True)

    for country in COUNTRIES:
        for concept in ["tax", "total_revenue"]:
            concept_df = dist[
                (dist["country_id"] == country)
                & (dist["revenue_concept"] == concept)
                & (dist["delta_gdp_positive"] == True)  # noqa: E712
            ].copy()
            for sample_name, sample_filter in samples.items():
                sample_df = concept_df[sample_filter(concept_df)]
                raw_values = sample_df["mfc_hist_gross"].dropna().astype(float)
                if raw_values.empty:
                    pct_rows.append(empty_percentile_row(country, "general_government", concept, sample_name, dataset_version, build_id, "no valid years", draws, seed))
                    continue
                lower, upper = np.nanpercentile(raw_values, [1, 99])
                values = raw_values.clip(lower, upper)
                positive = values[values >= 0]
                negative = values[values < 0]
                row = {
                    "country_id": country,
                    "government_level": "general_government",
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
                    "ci_method": f"bootstrap percentile, B={draws}, seed={seed}, PCG64",
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
                    boots = rng.choice(np.asarray(positive), size=(draws, len(positive)), replace=True)
                    for quantile, prefix in [(50, "p50"), (75, "p75"), (90, "p90")]:
                        boot_q = np.percentile(boots, quantile, axis=1)
                        row[f"{prefix}_ci_low"] = float(np.percentile(boot_q, 2.5))
                        row[f"{prefix}_ci_high"] = float(np.percentile(boot_q, 97.5))
                pct_rows.append(row)
    return dist, pd.DataFrame(pct_rows)


def build_policy(macro: pd.DataFrame, poverty: pd.DataFrame, dataset_version: str, build_id: str, log: Log) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    existing_spending_treatment = (
        "pure_layering_zero_existing_spending: current programs are not netted from the policy cost; "
        "V_net=V_gross is conservative relative to crediting existing budgets; official pension rows "
        "retain country normative sources, while synthetic GMI/MUT/PBI/UBI rows remain new-layer designs."
    )
    eta_specs = {"MUT": (0.25, 0.10, 0.40), "PBI": (0.50, 0.25, 0.75), "UBI": (1.00, 0.75, 1.00)}
    admin_specs = {
        "GMI": (0.0025, 0.0012, 0.0040),
        "PEN": (0.0012, 0.0006, 0.0020),
        "MUT": (0.0008, 0.0003, 0.0015),
        "PBI": (0.0006, 0.0002, 0.0012),
        "UBI": (0.0005, 0.0001, 0.0010),
    }
    params = []
    costs = []
    gmi = []
    admin = []
    for country in COUNTRIES:
        m = macro[(macro["country_id"] == country) & (macro["year"] == ANCHOR_YEAR)].iloc[0]
        p = poverty[poverty["country_id"] == country].iloc[0]
        pop_total = float(m["population_total_wpp"] if pd.notna(m.get("population_total_wpp")) else m["population_total"])
        pop65 = float(m["population_65_plus"])
        pop18 = float(m["population_18_plus"])
        pop80 = float(m.get("population_80_plus", np.nan))
        gdp_lcu = float(m["gdp_nominal_lcu"])
        line = float(p["poverty_line_national_lcu_annual"])
        poverty_gap = float(p["poverty_gap"])
        poor_pop = pop_total * float(p["poverty_headcount"])
        spec = OFFICIAL_PENSION[country]
        if country == "COL":
            eligible = float(m["population_colombia_mayor_rule"])
            under80 = max(0.0, eligible - pop80)
            gross = under80 * 80_000.0 * 12.0 + pop80 * 225_000.0 * 12.0
            benefit = gross / eligible if eligible else math.nan
        else:
            eligible = pop65
            benefit = float(spec["benefit_annual_lcu"])
            gross = benefit * eligible
        param_id = f"{country}_PEN_2024_OFFICIAL"
        params.append({"policy_parameter_id": param_id, "country_id": country, "policy_id": "PEN", "year": ANCHOR_YEAR, "age_threshold": spec["age_threshold"], "eta_policy": np.nan, "chi_gmi": np.nan, "theta_target": np.nan, "benefit_formula": spec["benefit_formula"], "eligible_population_rule": spec["age_rule"], "gross_or_net_convention": "gross", "existing_spending_treatment": existing_spending_treatment, "poverty_line_convention": "not_applicable", "indexation_rule": "endpoint_policy_review_required", "source_id": spec["source_id"], "assumption_id": None, "source_url": spec["citation"], "dataset_version": dataset_version, "created_at": now(), "created_by_script": SCRIPT_NAME})
        costs.append({"country_id": country, "policy_id": "PEN", "year": ANCHOR_YEAR, "eligible_population": eligible, "benefit_amount_lcu": benefit, "poverty_line_annual_lcu": np.nan, "eta_policy": np.nan, "chi_gmi": np.nan, "policy_cost_gross_lcu": gross, "existing_spending_lcu": 0.0, "policy_cost_net_lcu": gross, "policy_cost_gross_gdp": gross / gdp_lcu, "policy_cost_net_gdp": gross / gdp_lcu, "cost_convention": "official country pension benefit and age rule", "microdata_used": False, "gmi_version": None, "policy_parameter_id": param_id, "assumption_id": None, "dataset_version": dataset_version, "build_id": build_id, "parameter_set_id": PARAMETER_SET_ID})
        for version, theta in [("GMI_ideal_aggregate", 1.0), ("GMI_loaded_aggregate", 1.5)]:
            gross_gmi = theta * poverty_gap * line * pop_total
            pid = f"{country}_{version}_2024"
            params.append({"policy_parameter_id": pid, "country_id": country, "policy_id": "GMI", "year": ANCHOR_YEAR, "age_threshold": np.nan, "eta_policy": np.nan, "chi_gmi": 1.0, "theta_target": theta, "benefit_formula": "theta_target * chi_gmi * poverty_gap * poverty_line_lcu * population_total", "eligible_population_rule": "aggregate PIP poverty gap, no microdata", "gross_or_net_convention": "gross", "existing_spending_treatment": existing_spending_treatment, "poverty_line_convention": "international_ppp_converted_to_lcu", "indexation_rule": "poverty_line_growth", "source_id": "PIP;WDI;PLAN_01_02", "assumption_id": "A_CHI_GMI_FULL_GAP" if theta == 1.0 else "A_CHI_GMI_FULL_GAP;A_THETA_TARGET_GMI_LOADED", "source_url": "", "dataset_version": dataset_version, "created_at": now(), "created_by_script": SCRIPT_NAME})
            costs.append({"country_id": country, "policy_id": "GMI", "year": ANCHOR_YEAR, "eligible_population": poor_pop, "benefit_amount_lcu": gross_gmi / poor_pop if poor_pop else np.nan, "poverty_line_annual_lcu": line, "eta_policy": np.nan, "chi_gmi": 1.0, "policy_cost_gross_lcu": gross_gmi, "existing_spending_lcu": 0.0, "policy_cost_net_lcu": gross_gmi, "policy_cost_gross_gdp": gross_gmi / gdp_lcu, "policy_cost_net_gdp": gross_gmi / gdp_lcu, "cost_convention": version, "microdata_used": False, "gmi_version": version, "policy_parameter_id": pid, "assumption_id": "A_CHI_GMI_FULL_GAP" if theta == 1.0 else "A_CHI_GMI_FULL_GAP;A_THETA_TARGET_GMI_LOADED", "dataset_version": dataset_version, "build_id": build_id, "parameter_set_id": PARAMETER_SET_ID})
            gmi.append({"country_id": country, "year": ANCHOR_YEAR, "gmi_version": version, "microdata_used": False, "survey_name": None, "poverty_gap_used": True, "income_or_consumption": p["welfare_type"], "welfare_concept": p["welfare_type"], "limitation_notes": f"{version}; aggregate PIP poverty gap only; no microdata."})
        for policy, (eta, low, high) in eta_specs.items():
            eligible_pop = pop18 if policy == "PBI" else pop_total
            benefit_eta = eta * line
            gross_eta = benefit_eta * eligible_pop
            pid = f"{country}_{policy}_2024_ASSUMED_ETA"
            params.append({"policy_parameter_id": pid, "country_id": country, "policy_id": policy, "year": ANCHOR_YEAR, "age_threshold": 18 if policy == "PBI" else np.nan, "eta_policy": eta, "chi_gmi": np.nan, "theta_target": np.nan, "benefit_formula": f"eta_{policy} * poverty_line_lcu", "eligible_population_rule": "adult population" if policy == "PBI" else "total population", "gross_or_net_convention": "gross", "existing_spending_treatment": existing_spending_treatment, "poverty_line_convention": "international_ppp_converted_to_lcu", "indexation_rule": "poverty_line_growth", "source_id": "PLAN_01_02;PIP;WDI", "assumption_id": f"A_{policy}_ETA_POLICY", "source_url": "", "dataset_version": dataset_version, "created_at": now(), "created_by_script": SCRIPT_NAME})
            costs.append({"country_id": country, "policy_id": policy, "year": ANCHOR_YEAR, "eligible_population": eligible_pop, "benefit_amount_lcu": benefit_eta, "poverty_line_annual_lcu": line, "eta_policy": eta, "chi_gmi": np.nan, "policy_cost_gross_lcu": gross_eta, "existing_spending_lcu": 0.0, "policy_cost_net_lcu": gross_eta, "policy_cost_gross_gdp": gross_eta / gdp_lcu, "policy_cost_net_gdp": gross_eta / gdp_lcu, "cost_convention": "eta_policy * poverty_line_lcu * eligible_population", "microdata_used": False, "gmi_version": None, "policy_parameter_id": pid, "assumption_id": f"A_{policy}_ETA_POLICY", "dataset_version": dataset_version, "build_id": build_id, "parameter_set_id": PARAMETER_SET_ID})
            add_assumption(log, f"A_{policy}_ETA_POLICY", "policy_cost", f"eta_{policy}", eta, low, high, "policy_design_parameter", "Normative policy ladder registered for official 4C anchor costing.", "PLAN_01_02", country)
        for policy, values in admin_specs.items():
            admin.append({"country_id": country, "policy_id": policy, "scenario_id": None, "regime_id": None, "year": ANCHOR_YEAR, "admin_cost_new_gdp": values[0], "admin_savings_existing_gdp": 0.0, "admin_included_in_existing_spending": False, "layering_mode": "pure_layering", "transition_oneoff_gdp": values[0] * 0.8, "transition_recurring_gdp": values[0] * 0.1, "transition_horizon_years": 3, "transition_discount_rate": 0.03, "leakage_fixed_gdp": values[0] * 0.08, "source_id": "ASPIRE_LITERATURE_ASSUMPTION;PLAN_01_02", "assumption_id": f"A_{policy}_ADMIN_TRANSITION_4C", "sensitivity_level": "baseline", "dataset_version": dataset_version, "build_id": build_id, "created_by_script": SCRIPT_NAME})
            add_assumption(log, f"A_{policy}_ADMIN_TRANSITION_4C", "policy_admin_transition_cost", f"{policy}_admin_cost_new_gdp", values[0], values[1], values[2], "calibrated_range", "Administrative cost assumptions preserve means-tested > categorical > universal ordering.", "ASPIRE_LITERATURE_ASSUMPTION;PLAN_01_02", country)
    return pd.DataFrame(params), pd.DataFrame(costs), pd.DataFrame(gmi), pd.DataFrame(admin)


def logit_on_ceiling(q: float, q_bar: float) -> float:
    return math.log(q / (q_bar - q))


def bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_value_assignments(tables: dict[str, pd.DataFrame], dataset_version: str, build_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    cp = tables["country_panel"]
    frontier = tables["frontier_benchmark_anchor"]
    bench = frontier[frontier["benchmark_country_id"].isin(BENCHMARK_COUNTRIES)]
    avg_adoption = float(bench["adoption_proxy"].mean())
    avg_aipi = float(bench["aipi_total"].mean())
    epsilon = 1e-9
    epsilon_mu = 1e-6
    for country in COUNTRIES:
        r = cp[(cp["country_id"] == country) & (cp["year"] == ANCHOR_YEAR)].iloc[0]
        fiscal = tables["fiscal_anchor"][(tables["fiscal_anchor"]["country_id"] == country) & (tables["fiscal_anchor"]["year"] == ANCHOR_YEAR)].iloc[0]
        labor_share = float(r["labor_share_raw"])
        informality = float(r["informality_total"]) / 100.0
        gap = float(r["gap_index"])
        q_use = bounded(avg_adoption * float(r["aipi_total"]) / avg_aipi)
        q_low = bounded(q_use * 0.70)
        q_high = bounded(q_use * 1.30)
        omega_i = 0.50
        omega_g = 0.50
        q_bar = bounded(1.0 - omega_i * informality - omega_g * gap)
        q_adj = min(max(q_use, epsilon_mu), q_bar - epsilon_mu)
        mu = logit_on_ceiling(q_adj, q_bar) - float(r["aipi_total"]) + 0.50 * informality + 0.50 * gap
        consumption_share = float(r["final_consumption_gdp_share"]) / 100.0
        imports_share = float(r["imports_gdp_share"]) / 100.0
        m_m = bounded(imports_share / consumption_share)
        values = [
            ("A_aipi_total", "adoption_translation", float(r["aipi_total"]), 0.0, 1.0, "index_0_to_1", "IMF_AIPI_DATA360", "observed AIPI carried to 2024", "fixed_observed", "observed"),
            ("Gap_excluded_indicators", "adoption_translation", gap, 0.0, 1.0, "index_0_to_1", "ITU_DATAHUB;OOKLA_SPEEDTEST_OPEN_DATA;IMF_AIPI_NOTE_COMPONENTS", "gap_index = 1 - average(normalized LTE coverage, fixed speed, mobile speed); excluded indicators verified against AIPI note", "fixed_observed", "observed"),
            ("I_adopt_informality", "adoption_translation", informality, 0.0, 1.0, "share", "ILOSTAT", "country-specific informality anchor", "fixed_observed", "observed"),
            ("q_use_target", "adoption_translation", q_use, q_low, q_high, "share", "FRONTIER_BENCHMARK;IMF_AIPI_DATA360", "OECD-Eurostat benchmark adoption average scaled by country AIPI relative to benchmark AIPI; support +/-30%.", "bounded_PERT", "calibrated_parameter"),
            ("q_bar", "adoption_translation", q_bar, bounded(1 - 0.75 * informality - 0.75 * gap), bounded(1 - 0.25 * informality - 0.25 * gap), "share", "PAPER_ADOPTION_MODULE", "1 - omega_I*I - omega_G*Gap", "derived_bounded_PERT", "derived_parameter"),
            ("q_use_target_adj", "adoption_translation", q_adj, min(max(q_low, epsilon_mu), q_bar - epsilon_mu), min(max(q_high, epsilon_mu), q_bar - epsilon_mu), "share", "PLAN_02_SEC_7_3", "Target projected to interior support", "derived_bounded_PERT", "derived_parameter"),
            ("q_prod_t0", "adoption_translation", q_adj, min(max(q_low, epsilon_mu), q_bar - epsilon_mu), min(max(q_high, epsilon_mu), q_bar - epsilon_mu), "share", "PLAN_02_SEC_7_3", "Initial condition q_prod_t0=q_use_target_adj", "derived_bounded_PERT", "derived_parameter"),
            ("mu_t0_derived_not_free", "adoption_translation", mu, mu, mu, "unitless", "PLAN_02_SEC_7_3", "Derived by logit inversion; primitive is q_use_target, not mu", "fixed_derived", "derived_parameter"),
            ("labor_share", "fiscal_channels", labor_share, labor_share, labor_share, "share", "PWT_10_01", "country-specific PWT labsh", "fixed_observed", "observed"),
            ("tau_L_eff", "fiscal_channels", ((float(fiscal["pit_gdp"]) + float(fiscal["social_contrib_gdp"])) / 100.0) / labor_share, 0, 1, "effective_tax_rate", "OECD_REVSTAT_LAC;PWT_10_01", "(PIT_GDP+social_contrib_GDP)/labor_share_GDP", "fixed_derived", "derived_parameter"),
            ("tau_K_eff", "fiscal_channels", (float(fiscal["cit_gdp"]) / 100.0) / (1.0 - labor_share), 0, 1, "effective_tax_rate", "OECD_REVSTAT_LAC;PWT_10_01", "CIT_GDP/(1-labor_share)", "fixed_derived", "derived_parameter"),
            ("tau_C_eff", "fiscal_channels", (float(fiscal["vat_gdp"]) / 100.0) / consumption_share, 0, 1, "effective_tax_rate", "OECD_REVSTAT_LAC;WDI", "VAT_GDP/final_consumption_GDP_share", "fixed_derived", "derived_parameter"),
            ("E_prod", "fiscal_channels_labor", 0.11, 0.08, 0.14, "share_of_tasks_or_employment", "PLAN_01_02", "LAC fallback; is_lac_fallback=TRUE for official 4C until country occupation exposure is available.", "bounded_PERT", "calibrated_parameter"),
            ("E_auto", "fiscal_channels_labor", 0.035, 0.02, 0.05, "share_of_tasks_or_employment", "PAPER_LAC_AUTOMATION_RISK_ANCHOR", "LAC automation-risk anchor.", "bounded_PERT", "calibrated_parameter"),
            ("m_M", "fiscal_channels_consumption", m_m, m_m, m_m, "share", "WDI", "imports_GDP_share/final_consumption_GDP_share capped [0,1]", "fixed_derived", "derived_parameter"),
            ("theta_R_dom", "fiscal_channels_consumption", 1.0 - m_m, 1.0 - m_m, 1.0 - m_m, "share", "WDI;AUTHOR_CONVENTION_4A", "theta_R_dom anchored to (1-m_M) by author-review convention.", "fixed_derived", "derived_parameter"),
            ("tau_available_frozen_r0_note", "fiscal_channels_consumption", 1.0, 1.0, 1.0, "flag", "AUTHOR_CONVENTION_4A", "Disposable tax rates are frozen at r0 in the consumption chain; favorable second-order bias for r>=1 is declared.", "fixed_note", "calibrated_parameter"),
        ]
        for name, module, val, low, high, unit, source_id, notes, dist, vtype in values:
            rows.append({"parameter_set_id": PARAMETER_SET_ID, "name": name, "module": module, "country_id": country, "scenario_id": None, "policy_id": None, "regime_code": None, "value_type": vtype, "unit": unit, "baseline_value": val, "low_value": low, "high_value": high, "support_type": "official_4c_country_specific", "source_id": source_id, "formula_id": notes, "distribution": dist, "truncation_rule": "0_to_1" if unit in {"share", "index_0_to_1", "effective_tax_rate"} else "declared", "primary_spec_flag": True, "robustness_flag": False, "stress_flag": False, "double_counting_risk": "none", "double_counting_note": notes if name.startswith("Gap") else "none", "audit_status": "registered", "notes": notes, "is_lac_fallback": name in {"E_prod", "E_auto"}, "assumption_id": f"A4A_{country}_{name.upper()}", "dataset_version": dataset_version, "build_id": build_id, "created_at": now(), "created_by_script": SCRIPT_NAME})
    value = pd.DataFrame(rows)
    parameter_set = pd.DataFrame([{"parameter_set_id": PARAMETER_SET_ID, "parameter_set_name": "baseline official v1", "description": "Etapa 4A official 4-country calibration for author review only; no official baseline run.", "model_version": "pre_official_run_stage_4a", "dataset_version": dataset_version, "created_at": now(), "created_by_script": SCRIPT_NAME}])
    item = pd.DataFrame({"parameter_set_id": value["parameter_set_id"], "assumption_id": value["assumption_id"], "parameter_name": value["name"], "country_id": value["country_id"], "policy_id": value["policy_id"], "scenario_id": value["scenario_id"], "regime_id": None, "parameter_value": value["baseline_value"], "distribution": value["distribution"], "draw_rule": value["truncation_rule"], "notes": value["notes"]})
    registry = pd.DataFrame({"parameter_name": value["name"], "module": value["module"], "country_id": value["country_id"], "baseline_value": value["baseline_value"], "low_value": value["low_value"], "high_value": value["high_value"], "distribution": value["distribution"], "truncation_rule": value["truncation_rule"], "source_id": value["source_id"], "is_observed": value["value_type"].eq("observed"), "is_scenario": False, "is_structural_unobserved": value["value_type"].ne("observed"), "sensitivity_level": "baseline", "justification": value["notes"], "double_counting_note": value["double_counting_note"], "included_in_primary": value["primary_spec_flag"], "parameter_set_id": value["parameter_set_id"], "dataset_version": value["dataset_version"], "assumption_id": value["assumption_id"], "created_at": value["created_at"], "created_by_script": value["created_by_script"]})
    return value, parameter_set, item, registry


def build_country_panel(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = tables["macro_anchor"][tables["macro_anchor"]["year"] == ANCHOR_YEAR].copy()
    for name in ["fiscal_anchor", "debt_guardrail_anchor", "poverty_distribution_anchor", "ai_preparedness_anchor", "digital_gap_anchor", "labor_informality_anchor", "labor_share_anchor", "ai_exposure_anchor"]:
        df = tables[name]
        if "year" in df.columns:
            df = df[df["year"] == ANCHOR_YEAR].copy()
        common = [c for c in ["country_id", "year"] if c in df.columns and c in base.columns]
        base = base.merge(df, on=common, how="left", suffixes=("", f"_{name}"))
    return base


def write_outputs(root: Path, tables: dict[str, pd.DataFrame], log: Log, dataset_version: str, build_id: str) -> None:
    tables["variable_source_map"] = pd.DataFrame(log.sources) if log.sources else pd.DataFrame(columns=["table_name", "variable_name", "country_id", "year", "source_id", "transformation_notes", "dataset_version", "build_id", "created_by_script"])
    tables["data_quality_report"] = pd.DataFrame(log.quality) if log.quality else pd.DataFrame(columns=["country_id", "year", "module", "table_name", "variable_name", "notes", "dataset_version", "build_id", "created_by_script"])
    tables["assumption_registry"] = pd.concat([pd.DataFrame(log.assumptions), tables["calibrated_parameter_registry"].rename(columns={"justification": "justification"})], ignore_index=True, sort=False)
    tables["harmonization_decision_log"] = pd.DataFrame(log.decisions) if log.decisions else pd.DataFrame(columns=["decision_id", "module", "decision", "justification", "country_id", "dataset_version", "build_id"])
    tables["country_panel"] = build_country_panel(tables)
    db_path = root / "db" / "ai_usp_threshold.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        for name, df in tables.items():
            con.register("df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM df")
            con.unregister("df")
        con.execute("CREATE OR REPLACE TABLE build_manifest AS SELECT ? AS dataset_version, ? AS build_id, ? AS created_at, ? AS created_by_script", [dataset_version, build_id, now(), SCRIPT_NAME])
    finally:
        con.close()
    model_inputs = root / "data" / "model_inputs"
    model_inputs.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(model_inputs / f"{name}.parquet", index=False)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    tables["value_assignment_table"].to_csv(reports / f"value_assignment_table_{PARAMETER_SET_ID}.csv", index=False)
    tables["value_assignment_table"][tables["value_assignment_table"]["country_id"].isin(["CHL", "COL", "MEX"])].to_csv(reports / f"value_assignment_table_new_countries_{PARAMETER_SET_ID}.csv", index=False)
    tables["digital_gap_anchor"].to_csv(reports / f"gap_index_{PARAMETER_SET_ID}.csv", index=False)
    tables["policy_parameter"].to_csv(reports / "policy_parameter_official_4c.csv", index=False)
    source_manifest = tables["dim_source"][["source_name", "source_id", "url_or_api", "license_notes", "raw_file_path"]].copy()
    source_manifest.to_csv(reports / f"official_manifest_sources_{dataset_version}.csv", index=False)
    report = {"dataset_version": dataset_version, "build_id": build_id, "tables": {name: {"rows": int(len(df)), "columns": list(df.columns)} for name, df in tables.items()}, "hard_failures": []}
    (root / "db" / "anchor_build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_conventions(root: Path, dataset_version: str, build_id: str, gap: pd.DataFrame) -> None:
    payload = {
        "dataset_version": dataset_version,
        "build_id": build_id,
        "years": {"anchor_year": ANCHOR_YEAR, "endpoint_year": 2034, "harmonization_year": ANCHOR_YEAR},
        "official_countries": COUNTRIES,
        "government_level_choice": {
            country: {
                "baseline_historical_series": "general_government",
                "primary_sources": ["OECD_REVSTAT_LAC sector S13", "IMF_WEO_GFS general government"],
                "justification": "Maintain one fiscal level per country-window for historical capture and debt guardrail.",
            }
            for country in COUNTRIES
        },
        "adoption_gap_convention": {
            "gap_construction_convention": "excluded_indicators",
            "gap_index_formula": "1 - average(min(LTE/benchmark_mean_LTE,1), min(fixed_speed/benchmark_mean_fixed,1), min(mobile_speed/benchmark_mean_mobile,1))",
            "normalization_method": "relative_to_frontier_benchmark_set_mean_capped_at_1",
            "aipi_overlap_flag": False,
            "aipi_note_url": AIPI_NOTE_URL,
            "pilot_gap_zero_status": "historical diagnostic only; superseded for official 4C calibration by excluded coverage+speed Gap",
            "gap_values": dict(zip(gap["country_id"], gap["gap_index"], strict=False)),
        },
        "stage_4a_prerun_governance": {
            "parameter_set_id": PARAMETER_SET_ID,
            "no_official_baseline_run": True,
            "bias_notes": [
                "Disposable tax rates are frozen at r0 in the consumption chain; favorable second-order bias for r>=1 is declared.",
                "theta_R_dom is anchored to (1-m_M).",
            ],
            "gmi_grid_convention": "baseline grid should carry GMI_ideal_aggregate with warning; GMI_loaded_aggregate is a mandatory companion row for rankings.",
        },
    }
    out = root / "metadata" / "data_conventions.yml"
    out.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
    (root / "metadata" / "dataset_version.yml").write_text(yaml.safe_dump({"dataset_version": dataset_version, "build_id": build_id, "created_at": now()}, sort_keys=False), encoding="utf-8")


def build(root: Path, dataset_version: str) -> int:
    manifest, raw_map = verify_manifest(root, dataset_version)
    rng_policy = load_rng_policy(root)
    build_id = f"{dataset_version}-anchors-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    log = Log()
    dims = build_dimensions(manifest)
    macro = build_macro(root, raw_map, dataset_version, build_id, log)
    poverty = build_poverty(root, raw_map, macro, dataset_version, build_id, log)
    fiscal = build_fiscal(root, raw_map, macro, dataset_version, build_id, log)
    debt = build_debt(root, raw_map, macro, dataset_version, build_id)
    frontier = build_frontier(root, raw_map, dataset_version, build_id)
    ai, gap = build_ai_gap(root, raw_map, frontier, dataset_version, build_id, log)
    labor, labor_share = build_labor(root, raw_map, dataset_version, build_id)
    exposure = build_exposure(dataset_version, build_id, log)
    hist, hist_pct = build_historical(macro, fiscal, dataset_version, build_id, rng_policy)
    policy_parameter, policy_cost, gmi_status, admin = build_policy(macro, poverty, dataset_version, build_id, log)
    tables: dict[str, pd.DataFrame] = {
        **dims,
        "macro_anchor": macro,
        "poverty_distribution_anchor": poverty,
        "fiscal_anchor": fiscal,
        "debt_guardrail_anchor": debt,
        "ai_preparedness_anchor": ai,
        "digital_gap_anchor": gap,
        "labor_informality_anchor": labor,
        "labor_share_anchor": labor_share,
        "ai_exposure_anchor": exposure,
        "frontier_benchmark_anchor": frontier,
        "historical_capture_distribution": hist,
        "historical_capture_percentiles": hist_pct,
        "policy_parameter": policy_parameter,
        "policy_cost": policy_cost,
        "gmi_estimation_status": gmi_status,
        "policy_admin_transition_cost": admin,
    }
    tables["country_panel"] = build_country_panel(tables)
    value, parameter_set, parameter_item, registry = build_value_assignments(tables, dataset_version, build_id)
    tables["value_assignment_table"] = value
    tables["parameter_set"] = parameter_set
    tables["parameter_set_item"] = parameter_item
    tables["calibrated_parameter_registry"] = registry
    write_conventions(root, dataset_version, build_id, gap)
    write_outputs(root, tables, log, dataset_version, build_id)
    print(json.dumps({"dataset_version": dataset_version, "build_id": build_id, "parameter_set_id": PARAMETER_SET_ID, "gap_index": dict(zip(gap["country_id"], gap["gap_index"], strict=False))}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    return build(root, args.dataset_version)


if __name__ == "__main__":
    raise SystemExit(main())
