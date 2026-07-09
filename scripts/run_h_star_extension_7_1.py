"""Etapa 7.1 post-baseline H* horizon inversion.

This is a declared post-baseline extension. It derives the number of years of
frozen scenario persistence required to cross a threshold, without introducing
new calibration values or modifying the certified engine.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finalize_phase_b import save_paper_table
from scripts.run_official_tier_a import ANCHOR_YEAR, eligible_metric, sha256_file


RUN_ID = "official_4c_hstar_extension_baseline_official_v3"
RUN_TYPE = "post_baseline_extension"
MODEL_VERSION = "deterministic-engine-v1_hstar-extension"
PARAMETER_SET_ID = "baseline-official-v3"
SOURCE_DATASET_VERSION = "v1.0.1-official-4c"
HSTAR_DATASET_VERSION = "v1.1.0-official-4c"
REPORTING_CAP_YEARS = 25
XI_REPORTING = 0.10
XI_GRID = (0.0, 0.05, 0.10, 0.25, 0.50)
COUNTRIES = ("PER", "CHL", "COL", "MEX")
HEADLINE_CELLS = {
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
    ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
    ("PER", "PEN", "stress", "r2"),
    ("PER", "PEN", "stress", "r4"),
}
MANUAL_CHECK_CELLS = {
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
    ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
    ("PER", "PEN", "stress", "r4"),
}
CONVENTION_NOTE = (
    "H* extiende la persistencia congelada del escenario de H=10 a H variable; "
    "es un REQUERIMIENTO condicional (anos de persistencia necesarios), no un "
    "pronostico de calendario."
)
AMENDMENT_TEXT = (
    "extension post-baseline anadida tras resultados; estadistica DERIVADA de "
    "cantidades pre-registradas; no introduce parametros ni altera ningun "
    "resultado pre-registrado; PRIMARY_SPEC_HASH intacto"
)


@dataclass(frozen=True)
class HStarComputation:
    h_star: int | None
    status: str
    v_at_h_star: float | None
    v_at_h_minus_1: float | None
    endpoint_year_at_h_star: int | None
    flags: tuple[str, ...]
    v_by_h: dict[int, float]


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return clean(value.item())
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def primary_spec_hash_status() -> dict[str, Any]:
    spec = ROOT / "02_ESD_AI_USP_v6.md"
    hash_file = ROOT / "PRIMARY_SPEC_HASH.txt"
    actual = sha256_file(spec) if spec.exists() else None
    expected = None
    if hash_file.exists():
        for line in hash_file.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("sha256:"):
                expected = line.split(":", 1)[1].strip().lower()
                break
    return {
        "actual": actual,
        "expected": expected,
        "status": "PASS" if actual and expected and actual.lower() == expected.lower() else "WARN",
    }


def load_wpp() -> pd.DataFrame:
    path = ROOT / "data" / "raw_snapshots" / HSTAR_DATASET_VERSION / "wpp" / "wpp_projections.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing extended WPP snapshot {path}. Run scripts/14_download_wpp_projections.py "
            f"with --end-year 2050 and freeze {HSTAR_DATASET_VERSION}."
        )
    wpp = pd.read_parquet(path)
    if int(wpp["Time"].min()) > 2024 or int(wpp["Time"].max()) < 2050:
        raise RuntimeError(f"WPP snapshot must cover 2024-2050; found {wpp['Time'].min()}-{wpp['Time'].max()}")
    return wpp


def load_policy_cost_2024() -> pd.DataFrame:
    con = duckdb.connect(str(ROOT / "db" / "ai_usp_threshold.duckdb"))
    try:
        df = con.execute(
            """
            SELECT country_id, policy_id, gmi_version, policy_cost_gross_gdp
            FROM policy_cost
            WHERE dataset_version = ?
            """,
            [SOURCE_DATASET_VERSION],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        raise RuntimeError("policy_cost table is empty for source dataset.")
    df["policy_variant_id"] = df.apply(
        lambda r: r["policy_id"] if pd.isna(r["gmi_version"]) else f"{r['policy_id']}:{r['gmi_version']}",
        axis=1,
    )
    return df


def policy_ratio_by_h(wpp: pd.DataFrame, country: str, policy_id: str) -> dict[int, float]:
    anchor = eligible_metric(wpp, country, ANCHOR_YEAR, policy_id)
    if anchor <= 0.0:
        raise RuntimeError(f"Nonpositive WPP anchor metric for {country}/{policy_id}.")
    return {
        h: float(eligible_metric(wpp, country, ANCHOR_YEAR + h, policy_id) / anchor)
        for h in range(1, REPORTING_CAP_YEARS + 1)
    }


def ratio_cache(wpp: pd.DataFrame, policy_cost: pd.DataFrame) -> dict[tuple[str, str], dict[int, float]]:
    cache: dict[tuple[str, str], dict[int, float]] = {}
    for _, row in policy_cost.iterrows():
        country = str(row["country_id"])
        policy_variant = str(row["policy_variant_id"])
        policy = str(row["policy_id"])
        fixed = policy == "GMI"
        cache[(country, policy_variant)] = {h: 1.0 for h in range(1, REPORTING_CAP_YEARS + 1)} if fixed else policy_ratio_by_h(wpp, country, policy)
    return cache


def v_at_h(*, mfc_tilde_gross: float, annual_ai_growth: float, fixed_cost_gdp: float, cost_gdp: float, h: int) -> float:
    if cost_gdp <= 0.0:
        return float("nan")
    g_h = (1.0 + annual_ai_growth) ** h - 1.0
    return (mfc_tilde_gross * g_h - fixed_cost_gdp) / cost_gdp


def find_h_star(
    *,
    mfc_tilde_gross: float,
    annual_ai_growth: float,
    fixed_cost_gdp: float,
    cost_2024_gdp: float,
    ratios_by_h: dict[int, float],
    xi: float,
    requirement_basis: str,
    spb_plus_gdp: float = 0.0,
    cap_years: int = REPORTING_CAP_YEARS,
) -> HStarComputation:
    flags: list[str] = []
    if mfc_tilde_gross <= 0.0:
        flags.append("noncomputable_mfc_zero_or_negative")
    if annual_ai_growth <= 0.0:
        flags.append("noncomputable_g_ai_zero_or_negative")
    if cost_2024_gdp <= 0.0:
        flags.append("noncomputable_cost_zero_or_negative")
    if requirement_basis not in {"baseline", "debt_consistent"}:
        raise ValueError(f"Unknown requirement_basis: {requirement_basis}")
    if flags:
        return HStarComputation(None, "noncomputable", None, None, None, tuple(flags), {})

    v_by_h: dict[int, float] = {}
    previous_v: float | None = None
    for h in range(1, cap_years + 1):
        cost_h = cost_2024_gdp * ratios_by_h[h]
        v_h = v_at_h(
            mfc_tilde_gross=mfc_tilde_gross,
            annual_ai_growth=annual_ai_growth,
            fixed_cost_gdp=fixed_cost_gdp,
            cost_gdp=cost_h,
            h=h,
        )
        v_by_h[h] = v_h
        threshold = 1.0 + xi
        if requirement_basis == "debt_consistent":
            threshold += spb_plus_gdp / cost_h
        if v_h >= threshold:
            return HStarComputation(
                h,
                "crosses_within_cap",
                v_h,
                previous_v,
                ANCHOR_YEAR + h,
                tuple(flags),
                v_by_h,
            )
        previous_v = v_h
    flags.append("censored_beyond_defensible_horizon")
    return HStarComputation(None, "censored_beyond_defensible_horizon", None, previous_v, None, tuple(flags), v_by_h)


def threshold_for_h(*, xi: float, requirement_basis: str, spb_plus_gdp: float, cost_2024_gdp: float, ratios_by_h: dict[int, float], h: int) -> float:
    threshold = 1.0 + xi
    if requirement_basis == "debt_consistent":
        threshold += spb_plus_gdp / (cost_2024_gdp * ratios_by_h[h])
    return threshold


def source_table_hashes() -> dict[str, str]:
    official = ROOT / "results" / "official"
    names = [
        "fiscal_space_result.csv",
        "threshold_inversion_result.csv",
        "historical_plausibility_result.csv",
        "country_policy_classification_final.csv",
        "diagnostic_result.csv",
        "hypothesis_adjudication.csv",
    ]
    hashes = {name: sha256_file(official / name) for name in names if (official / name).exists()}
    mc = official / "monte_carlo_result.csv"
    if mc.exists():
        old_cols = [
            col
            for col in pd.read_csv(mc, nrows=0).columns.tolist()
            if col not in {"prob_h_star_le_10", "prob_h_star_le_25"}
        ]
        df = pd.read_csv(mc, usecols=old_cols)
        import hashlib

        h = hashlib.sha256()
        h.update("\x1f".join(old_cols).encode("utf-8"))
        h.update(pd.util.hash_pandas_object(df, index=False).to_numpy(dtype=np.uint64).tobytes())
        hashes["monte_carlo_result.csv::preexisting_columns_value_hash"] = h.hexdigest()
    return hashes


def load_spb_plus() -> dict[str, float]:
    con = duckdb.connect(str(ROOT / "db" / "ai_usp_threshold.duckdb"))
    try:
        df = con.execute(
            """
            SELECT country_id, baseline_value
            FROM value_assignment_table
            WHERE parameter_set_id = ? AND name = 'sPB_plus_gdp_ratio'
            """,
            [PARAMETER_SET_ID],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        con = duckdb.connect(str(ROOT / "db" / "ai_usp_threshold.duckdb"))
        try:
            df = con.execute(
                """
                SELECT country_id, baseline_value
                FROM value_assignment_table
                WHERE name = 'sPB_plus_gdp_ratio'
                QUALIFY ROW_NUMBER() OVER (PARTITION BY country_id ORDER BY parameter_set_id DESC) = 1
                """
            ).fetchdf()
        finally:
            con.close()
    return {str(r["country_id"]): float(r["baseline_value"]) for _, r in df.iterrows()}


def build_h_star_result(wpp: pd.DataFrame, policy_cost: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    fs = pd.read_csv(ROOT / "results" / "official" / "fiscal_space_result.csv")
    source_threshold = pd.read_csv(ROOT / "results" / "official" / "threshold_inversion_result.csv")
    source_flags = source_threshold[
        [
            "country_id",
            "policy_variant_id",
            "scenario_id",
            "regime_id",
            "requirement_basis",
            "xi",
            "flags",
        ]
    ].copy()
    policy_map = policy_cost.set_index(["country_id", "policy_variant_id"])["policy_cost_gross_gdp"].to_dict()
    ratios = ratio_cache(wpp, policy_cost)
    spb = load_spb_plus()
    source_hashes = source_table_hashes()
    source_fiscal_hash = source_hashes.get("fiscal_space_result.csv")

    rows: list[dict[str, Any]] = []
    for _, row in fs.iterrows():
        country = str(row["country_id"])
        policy_variant = str(row["policy_variant_id"])
        annual = float(row["phi_y_nominal"]) * float(row["translation_factor"])
        fixed_cost = float(row["mfc_tilde_gross"]) * float(row["g_ai_level"]) - float(row["fs_eff"])
        c2024 = float(policy_map[(country, policy_variant)])
        for basis in ("baseline", "debt_consistent"):
            ratio = ratios[(country, policy_variant)]
            comp = find_h_star(
                mfc_tilde_gross=float(row["mfc_tilde_gross"]),
                annual_ai_growth=annual,
                fixed_cost_gdp=fixed_cost,
                cost_2024_gdp=c2024,
                ratios_by_h=ratio,
                xi=float(row["xi"]),
                requirement_basis=basis,
                spb_plus_gdp=spb.get(country, 0.0),
            )
            threshold_at_h_star = (
                None
                if comp.h_star is None
                else threshold_for_h(
                    xi=float(row["xi"]),
                    requirement_basis=basis,
                    spb_plus_gdp=spb.get(country, 0.0),
                    cost_2024_gdp=c2024,
                    ratios_by_h=ratio,
                    h=comp.h_star,
                )
            )
            threshold_at_h_minus_1 = (
                None
                if comp.h_star is None or comp.h_star <= 1
                else threshold_for_h(
                    xi=float(row["xi"]),
                    requirement_basis=basis,
                    spb_plus_gdp=spb.get(country, 0.0),
                    cost_2024_gdp=c2024,
                    ratios_by_h=ratio,
                    h=comp.h_star - 1,
                )
            )
            rows.append(
                {
                    "run_id": RUN_ID,
                    "run_type": RUN_TYPE,
                    "model_version": MODEL_VERSION,
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": HSTAR_DATASET_VERSION,
                    "source_dataset_version": SOURCE_DATASET_VERSION,
                    "country_id": country,
                    "policy_id": row["policy_id"],
                    "policy_variant_id": policy_variant,
                    "gmi_version": row["gmi_version"] if not pd.isna(row["gmi_version"]) else None,
                    "scenario_id": row["scenario_id"],
                    "regime_id": row["regime_id"],
                    "requirement_basis": basis,
                    "xi": float(row["xi"]),
                    "h_star": comp.h_star,
                    "h_star_status": comp.status,
                    "h_star_reporting_cap": REPORTING_CAP_YEARS,
                    "endpoint_year_at_h_star": comp.endpoint_year_at_h_star,
                    "threshold_value": 1.0 + float(row["xi"]),
                    "threshold_at_h_star": threshold_at_h_star,
                    "threshold_at_h_minus_1": threshold_at_h_minus_1,
                    "v_at_h_star": comp.v_at_h_star,
                    "v_at_h_minus_1": comp.v_at_h_minus_1,
                    "mfc_tilde_gross": float(row["mfc_tilde_gross"]),
                    "phi_y_nominal": float(row["phi_y_nominal"]),
                    "translation_factor": float(row["translation_factor"]),
                    "annual_ai_growth": annual,
                    "fixed_cost_gdp": fixed_cost,
                    "cost_2024_gdp": c2024,
                    "cost_at_h_star_gdp": None if comp.h_star is None else c2024 * ratios[(country, policy_variant)][comp.h_star],
                    "spb_plus_gdp": spb.get(country, 0.0),
                    "flags": ";".join(comp.flags) if comp.flags else None,
                    "source_fiscal_space_hash": source_fiscal_hash,
                    "convention_note": CONVENTION_NOTE,
                }
            )
    hstar = pd.DataFrame(rows)
    hstar = hstar.merge(
        source_flags.rename(columns={"flags": "source_threshold_flags"}),
        on=["country_id", "policy_variant_id", "scenario_id", "regime_id", "requirement_basis", "xi"],
        how="left",
    )
    return hstar, build_manual_check_inputs(hstar, fs, ratios, policy_map, spb)


def build_manual_check_inputs(
    hstar: pd.DataFrame,
    fs: pd.DataFrame,
    ratios: dict[tuple[str, str], dict[int, float]],
    policy_map: dict[tuple[str, str], float],
    spb: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = fs[fs["xi"].eq(XI_REPORTING)].copy()
    for country, policy_variant, scenario, regime in sorted(MANUAL_CHECK_CELLS):
        row = base[
            base["country_id"].eq(country)
            & base["policy_variant_id"].eq(policy_variant)
            & base["scenario_id"].eq(scenario)
            & base["regime_id"].eq(regime)
        ].iloc[0]
        annual = float(row["phi_y_nominal"]) * float(row["translation_factor"])
        fixed_cost = float(row["mfc_tilde_gross"]) * float(row["g_ai_level"]) - float(row["fs_eff"])
        ratio = ratios[(country, policy_variant)]
        c2024 = float(policy_map[(country, policy_variant)])
        h_base = hstar[
            hstar["country_id"].eq(country)
            & hstar["policy_variant_id"].eq(policy_variant)
            & hstar["scenario_id"].eq(scenario)
            & hstar["regime_id"].eq(regime)
            & hstar["xi"].eq(XI_REPORTING)
            & hstar["requirement_basis"].eq("baseline")
        ].iloc[0]
        h_dc = hstar[
            hstar["country_id"].eq(country)
            & hstar["policy_variant_id"].eq(policy_variant)
            & hstar["scenario_id"].eq(scenario)
            & hstar["regime_id"].eq(regime)
            & hstar["xi"].eq(XI_REPORTING)
            & hstar["requirement_basis"].eq("debt_consistent")
        ].iloc[0]
        v_base = {
            str(ANCHOR_YEAR + h): v_at_h(
                mfc_tilde_gross=float(row["mfc_tilde_gross"]),
                annual_ai_growth=annual,
                fixed_cost_gdp=fixed_cost,
                cost_gdp=c2024 * ratio[h],
                h=h,
            )
            for h in range(1, REPORTING_CAP_YEARS + 1)
        }
        rows.append(
            {
                "run_id": RUN_ID,
                "country_id": country,
                "policy_variant_id": policy_variant,
                "scenario_id": scenario,
                "regime_id": regime,
                "xi": XI_REPORTING,
                "mfc_tilde_gross": float(row["mfc_tilde_gross"]),
                "phi_y_nominal": float(row["phi_y_nominal"]),
                "translation_factor_T": float(row["translation_factor"]),
                "annual_ai_growth_phi_times_T": annual,
                "fixed_cost_gdp": fixed_cost,
                "cost_2024_gdp": c2024,
                "spb_plus_gdp": spb.get(country, 0.0),
                "h_star_baseline": h_base["h_star"],
                "h_star_debt_consistent": h_dc["h_star"],
                "h_star_baseline_status": h_base["h_star_status"],
                "h_star_debt_consistent_status": h_dc["h_star_status"],
                "ratio_by_year_json": json.dumps({str(ANCHOR_YEAR + h): ratio[h] for h in range(1, REPORTING_CAP_YEARS + 1)}, sort_keys=True),
                "v_by_year_baseline_json": json.dumps(v_base, sort_keys=True),
                "convention_note": CONVENTION_NOTE,
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": HSTAR_DATASET_VERSION,
            }
        )
    return pd.DataFrame(rows)


def hstar_probabilities_for_mc(wpp: pd.DataFrame, policy_cost: pd.DataFrame) -> pd.DataFrame:
    draw_dir = ROOT / "results" / "official" / "draws"
    fcd = pd.read_parquet(draw_dir / "fiscal_conversion_draw.parquet")
    csd = pd.read_parquet(draw_dir / "country_scenario_draw.parquet")
    gsd = pd.read_parquet(draw_dir / "global_scenario_draw.parquet")
    pcd = pd.read_parquet(draw_dir / "policy_cost_draw.parquet")
    fcd = fcd[fcd["mc_mode"].eq("MC_independent_baseline")].copy()
    csd = csd[csd["mc_mode"].eq("MC_independent_baseline")][
        ["draw_id", "country_id", "scenario_id", "translation_factor"]
    ].copy()
    gsd = gsd[gsd["mc_mode"].eq("MC_independent_baseline")][
        ["draw_id", "country_id", "scenario_id", "phi_y_nominal"]
    ].copy()
    pcd = pcd[pcd["mc_mode"].eq("MC_independent_baseline")][
        ["draw_id", "country_id", "policy_variant_id", "cost_gross_gdp"]
    ].copy()
    ratios = ratio_cache(wpp, policy_cost)
    ratio_2034 = {
        key: eligible_metric(wpp, key[0], 2034, policy_cost[
            policy_cost["country_id"].eq(key[0]) & policy_cost["policy_variant_id"].eq(key[1])
        ].iloc[0]["policy_id"]) / eligible_metric(wpp, key[0], 2024, policy_cost[
            policy_cost["country_id"].eq(key[0]) & policy_cost["policy_variant_id"].eq(key[1])
        ].iloc[0]["policy_id"])
        if not str(policy_cost[
            policy_cost["country_id"].eq(key[0]) & policy_cost["policy_variant_id"].eq(key[1])
        ].iloc[0]["policy_id"]) == "GMI"
        else 1.0
        for key in ratios
    }
    fcd = fcd.merge(csd, on=["draw_id", "country_id", "scenario_id"], how="left")
    fcd = fcd.merge(gsd, on=["draw_id", "country_id", "scenario_id"], how="left")
    fcd = fcd.merge(pcd, on=["draw_id", "country_id", "policy_variant_id"], how="left")
    fcd["annual_ai_growth"] = fcd["phi_y_nominal"] * fcd["translation_factor"]

    rows: list[dict[str, Any]] = []
    group_cols = ["country_id", "policy_id", "policy_variant_id", "gmi_version", "scenario_id", "regime_id"]
    for key, grp in fcd.groupby(group_cols, dropna=False, sort=False):
        country = str(key[0])
        policy_variant = str(key[2])
        r2034 = ratio_2034[(country, policy_variant)]
        cost_2024 = grp["cost_gross_gdp"].to_numpy(dtype=float) / r2034
        annual = grp["annual_ai_growth"].to_numpy(dtype=float)
        mfc = grp["mfc_tilde_gross"].to_numpy(dtype=float)
        g10 = grp["g_ai_level"].to_numpy(dtype=float)
        v10 = grp["v_gross"].to_numpy(dtype=float)
        c10 = grp["cost_gross_gdp"].to_numpy(dtype=float)
        fixed = mfc * g10 - v10 * c10
        valid = (mfc > 0.0) & (annual > 0.0) & (cost_2024 > 0.0)
        crosses10 = valid & (v10 >= 1.0 + XI_REPORTING)
        crosses25 = np.zeros(len(grp), dtype=bool)
        for h in range(1, REPORTING_CAP_YEARS + 1):
            cost_h = cost_2024 * ratios[(country, policy_variant)][h]
            g_h = np.power(1.0 + annual, h) - 1.0
            v_h = (mfc * g_h - fixed) / cost_h
            crosses25 |= valid & (v_h >= 1.0 + XI_REPORTING)
        denom = len(grp)
        rows.append(
            {
                "country_id": country,
                "policy_id": key[1],
                "policy_variant_id": policy_variant,
                "gmi_version": None if pd.isna(key[3]) else key[3],
                "scenario_id": key[4],
                "regime_id": key[5],
                "prob_h_star_le_10": float(crosses10.sum() / denom),
                "prob_h_star_le_25": float(crosses25.sum() / denom),
            }
        )
    return pd.DataFrame(rows)


def update_monte_carlo_result(prob: pd.DataFrame) -> pd.DataFrame:
    path = ROOT / "results" / "official" / "monte_carlo_result.csv"
    mc = pd.read_csv(path)
    for col in ["prob_h_star_le_10", "prob_h_star_le_25"]:
        if col in mc.columns:
            mc = mc.drop(columns=[col])
    mc = mc.merge(
        prob,
        on=["country_id", "policy_id", "policy_variant_id", "gmi_version", "scenario_id", "regime_id"],
        how="left",
    )
    applicable = mc["mc_mode"].eq("MC_independent_baseline") & mc["prob_basis"].eq("all_draw")
    for col in ["prob_h_star_le_10", "prob_h_star_le_25"]:
        mc.loc[~applicable, col] = np.nan
    mc.to_csv(path, index=False)
    mc.to_csv(ROOT / "reports" / "monte_carlo_result_baseline-official-v3.csv", index=False)
    return mc


def table5b_time_to_threshold(hstar: pd.DataFrame, mc: pd.DataFrame) -> pd.DataFrame:
    h = hstar[
        hstar["xi"].eq(XI_REPORTING)
        & hstar.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)
    ].copy()
    keys = ["country_id", "policy_id", "policy_variant_id", "gmi_version", "scenario_id", "regime_id"]
    baseline = h[h["requirement_basis"].eq("baseline")][keys + ["h_star", "h_star_status"]].rename(
        columns={"h_star": "h_star_baseline", "h_star_status": "h_star_status_baseline"}
    )
    debt = h[h["requirement_basis"].eq("debt_consistent")][
        ["country_id", "policy_variant_id", "scenario_id", "regime_id", "h_star", "h_star_status"]
    ].rename(columns={"h_star": "h_star_debt_consistent", "h_star_status": "h_star_status_debt_consistent"})
    pivot = baseline.merge(
        debt,
        on=["country_id", "policy_variant_id", "scenario_id", "regime_id"],
        how="left",
    )
    probs = mc[
        mc["mc_mode"].eq("MC_independent_baseline")
        & mc["prob_basis"].eq("all_draw")
        & mc.apply(lambda r: (r["country_id"], r["policy_variant_id"], r["scenario_id"], r["regime_id"]) in HEADLINE_CELLS, axis=1)
    ][["country_id", "policy_variant_id", "scenario_id", "regime_id", "prob_h_star_le_10", "prob_h_star_le_25"]]
    table = pivot.merge(probs, on=["country_id", "policy_variant_id", "scenario_id", "regime_id"], how="left")
    table["note"] = (
        "H* censored at 25 years; values are conditional years of frozen scenario persistence, not calendar forecasts."
    )
    return table.sort_values(["country_id", "policy_variant_id", "scenario_id", "regime_id"])


def amendment_registry() -> pd.DataFrame:
    primary = primary_spec_hash_status()
    return pd.DataFrame(
        [
            {
                "run_id": RUN_ID,
                "amendment_id": "Q0_h_star_post_baseline_extension",
                "amendment_text": AMENDMENT_TEXT,
                "primary_spec_hash_status": primary["status"],
                "primary_spec_hash_actual": primary["actual"],
                "primary_spec_hash_expected": primary["expected"],
                "h_star_reporting_cap": REPORTING_CAP_YEARS,
                "convention_note": CONVENTION_NOTE,
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": HSTAR_DATASET_VERSION,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def update_threshold_assignment_table() -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    con = duckdb.connect(str(ROOT / "db" / "ai_usp_threshold.duckdb"))
    try:
        cols = con.execute("DESCRIBE threshold_assignment_table").fetchdf()["column_name"].tolist()
        existing = con.execute("SELECT * FROM threshold_assignment_table").fetchdf()
        if "threshold_id" in cols:
            rows = pd.DataFrame(
                [
                    {
                        "threshold_id": "h_star_reporting_cap",
                        "threshold_name": "H* reporting cap",
                        "threshold_value": float(REPORTING_CAP_YEARS),
                        "unit": "years",
                        "scope": "post_baseline_extension",
                        "rule": "H* > 25 is reported as censored_beyond_defensible_horizon, never as a number.",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                    },
                    {
                        "threshold_id": "h_star_convention_note",
                        "threshold_name": "H* convention note",
                        "threshold_value": np.nan,
                        "unit": "note",
                        "scope": "post_baseline_extension",
                        "rule": CONVENTION_NOTE,
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                    },
                    {
                        "threshold_id": "h_star_post_baseline_amendment",
                        "threshold_name": "H* post-baseline amendment",
                        "threshold_value": np.nan,
                        "unit": "note",
                        "scope": "post_baseline_extension",
                        "rule": AMENDMENT_TEXT,
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                    },
                ]
            )
            existing = existing[~existing["threshold_id"].isin(rows["threshold_id"])]
            out = pd.concat([existing, rows.reindex(columns=existing.columns)], ignore_index=True)
        else:
            rows = pd.DataFrame(
                [
                    {
                        "threshold_name": "h_star_reporting_cap",
                        "controls_decision": False,
                        "threshold_type": "reporting_cap",
                        "baseline_value": float(REPORTING_CAP_YEARS),
                        "sensitivity_values": "",
                        "action_on_fail": "H* > 25 is reported as censored_beyond_defensible_horizon.",
                        "source_section": "ETAPA_7_1_Q0_POST_BASELINE_DECLARATION",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                        "created_at": created_at,
                        "created_by_script": Path(__file__).name,
                    },
                    {
                        "threshold_name": "h_star_convention_note",
                        "controls_decision": False,
                        "threshold_type": "convention_note",
                        "baseline_value": np.nan,
                        "sensitivity_values": "",
                        "action_on_fail": CONVENTION_NOTE,
                        "source_section": "ETAPA_7_1_Q0_POST_BASELINE_DECLARATION",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                        "created_at": created_at,
                        "created_by_script": Path(__file__).name,
                    },
                ]
            )
            existing = existing[~existing["threshold_name"].isin(rows["threshold_name"])]
            out = pd.concat([existing, rows.reindex(columns=existing.columns)], ignore_index=True)
        con.register("_threshold_assignment", out)
        con.execute("CREATE OR REPLACE TABLE threshold_assignment_table AS SELECT * FROM _threshold_assignment")
        con.unregister("_threshold_assignment")
    finally:
        con.close()

    parquet = ROOT / "data" / "model_inputs" / "threshold_assignment_table.parquet"
    if parquet.exists():
        old = pd.read_parquet(parquet)
        if "threshold_name" in old.columns:
            rows = pd.DataFrame(
                [
                    {
                        "threshold_name": "h_star_reporting_cap",
                        "controls_decision": False,
                        "threshold_type": "reporting_cap",
                        "baseline_value": float(REPORTING_CAP_YEARS),
                        "sensitivity_values": "",
                        "action_on_fail": "H* > 25 is reported as censored_beyond_defensible_horizon.",
                        "source_section": "ETAPA_7_1_Q0_POST_BASELINE_DECLARATION",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                        "created_at": created_at,
                        "created_by_script": Path(__file__).name,
                    },
                    {
                        "threshold_name": "h_star_convention_note",
                        "controls_decision": False,
                        "threshold_type": "convention_note",
                        "baseline_value": np.nan,
                        "sensitivity_values": "",
                        "action_on_fail": CONVENTION_NOTE,
                        "source_section": "ETAPA_7_1_Q0_POST_BASELINE_DECLARATION",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                        "created_at": created_at,
                        "created_by_script": Path(__file__).name,
                    },
                    {
                        "threshold_name": "h_star_post_baseline_amendment",
                        "controls_decision": False,
                        "threshold_type": "amendment_registry",
                        "baseline_value": np.nan,
                        "sensitivity_values": "",
                        "action_on_fail": AMENDMENT_TEXT,
                        "source_section": "ETAPA_7_1_Q0_POST_BASELINE_DECLARATION",
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": HSTAR_DATASET_VERSION,
                        "created_at": created_at,
                        "created_by_script": Path(__file__).name,
                    },
                ]
            )
            old = old[~old["threshold_name"].isin(rows["threshold_name"])]
            pd.concat([old, rows.reindex(columns=old.columns)], ignore_index=True).to_parquet(parquet, index=False)


def update_manifest(pre_hashes: dict[str, str], post_hashes: dict[str, str]) -> None:
    official = ROOT / "results" / "official"
    manifest_path = official / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_manifest = ROOT / "reproducibility" / "snapshot" / f"dataset_manifest_{HSTAR_DATASET_VERSION}.json"
    manifest["dataset_version"] = HSTAR_DATASET_VERSION
    manifest["dataset_manifest_hash"] = sha256_file(dataset_manifest)
    manifest["h_star_extension"] = {
        "run_id": RUN_ID,
        "reporting_cap_years": REPORTING_CAP_YEARS,
        "source_dataset_version": SOURCE_DATASET_VERSION,
        "convention_note": CONVENTION_NOTE,
        "amendment_text": AMENDMENT_TEXT,
        "pre_registered_table_hashes_before": pre_hashes,
        "pre_registered_table_hashes_after": post_hashes,
        "pre_registered_hashes_unchanged": pre_hashes == post_hashes,
    }
    modes = list(manifest.get("run_modes") or [])
    if "h_star_post_baseline_extension" not in modes:
        modes.append("h_star_post_baseline_extension")
    manifest["run_modes"] = modes
    changelog = list(manifest.get("changelog") or [])
    entry = "Etapa 7.1: inversion de horizonte H* post-baseline; derivada de insumos firmados, sin recalibrar ni alterar resultados pre-registrados."
    if entry not in changelog:
        changelog.append(entry)
    manifest["changelog"] = changelog
    manifest["commit_sha"] = git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit"
    manifest["git_dirty"] = bool(git_value(["status", "--short"]))
    output_hashes = dict(manifest.get("output_hashes") or {})
    for path in official.glob("*.csv"):
        output_hashes[path.name] = sha256_file(path)
    output_hashes["manifest.json"] = sha256_file(manifest_path) if manifest_path.exists() else None
    manifest["output_hashes"] = output_hashes
    manifest["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    (ROOT / "reports" / "run_manifest_h_star_extension_baseline-official-v3.json").write_text(
        json.dumps(clean(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_outputs(hstar: pd.DataFrame, manual: pd.DataFrame, amendment: pd.DataFrame, table5b: pd.DataFrame) -> None:
    for path in [ROOT / "results" / "official", ROOT / "reports", ROOT / "results" / "paper_tables", ROOT / "reports" / "paper_tables"]:
        path.mkdir(parents=True, exist_ok=True)
    hstar.to_csv(ROOT / "results" / "official" / "h_star_result.csv", index=False)
    hstar.to_csv(ROOT / "reports" / "h_star_result_baseline-official-v3.csv", index=False)
    manual.to_csv(ROOT / "results" / "official" / "h_star_manual_check_inputs.csv", index=False)
    manual.to_csv(ROOT / "reports" / "h_star_manual_check_inputs_baseline-official-v3.csv", index=False)
    amendment.to_csv(ROOT / "results" / "official" / "h_star_amendment_registry.csv", index=False)
    amendment.to_csv(ROOT / "reports" / "h_star_amendment_registry_baseline-official-v3.csv", index=False)
    save_paper_table("table5b_time_to_threshold", table5b, "Time to threshold H* (post-baseline extension)", latex_rows=200)
    updated_manifest: pd.DataFrame | None = None
    for directory in [ROOT / "results" / "paper_tables", ROOT / "reports" / "paper_tables"]:
        manifest_path = directory / "paper_tables_manifest.csv"
        if not manifest_path.exists():
            continue
        manifest = pd.read_csv(manifest_path)
        manifest = manifest[~manifest["artifact_id"].eq("table5b_time_to_threshold")]
        manifest = pd.concat(
            [
                manifest,
                pd.DataFrame(
                    [
                        {
                            "artifact_id": "table5b_time_to_threshold",
                            "rows": len(table5b),
                            "caption": "Time to threshold H* (post-baseline extension)",
                            "csv": "table5b_time_to_threshold.csv",
                            "latex": "table5b_time_to_threshold.tex",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        manifest.to_csv(manifest_path, index=False)
        updated_manifest = manifest
    if updated_manifest is not None:
        save_paper_table("paper_tables_manifest", updated_manifest, "Paper table export manifest", latex_rows=None)


def archive_reference() -> dict[str, Any]:
    from reproducibility.run_all import archive_reference as archive

    return archive()


def run_h_star_extension(*, archive: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    update_threshold_assignment_table()
    pre_hashes = source_table_hashes()
    wpp = load_wpp()
    policy_cost = load_policy_cost_2024()
    hstar, manual = build_h_star_result(wpp, policy_cost)
    probs = hstar_probabilities_for_mc(wpp, policy_cost)
    mc = update_monte_carlo_result(probs)
    table5b = table5b_time_to_threshold(hstar, mc)
    amendment = amendment_registry()
    write_outputs(hstar, manual, amendment, table5b)
    post_hashes = source_table_hashes()
    # The old Monte Carlo columns are expected to be invariant; new H* columns are post-baseline.
    mc_value_key = "monte_carlo_result.csv::preexisting_columns_value_hash"
    invariant_keys = [k for k in pre_hashes if k != mc_value_key]
    unchanged = all(pre_hashes[k] == post_hashes.get(k) for k in invariant_keys) and (
        pre_hashes.get(mc_value_key) == post_hashes.get(mc_value_key)
    )
    update_manifest(pre_hashes, post_hashes)
    reference = archive_reference() if archive else None
    summary = {
        "status": "OK",
        "run_id": RUN_ID,
        "dataset_version": HSTAR_DATASET_VERSION,
        "source_dataset_version": SOURCE_DATASET_VERSION,
        "h_star_rows": int(len(hstar)),
        "manual_check_rows": int(len(manual)),
        "monte_carlo_rows_updated": int(len(mc)),
        "pre_registered_hashes_unchanged": bool(unchanged),
        "reference_archived": reference is not None,
        "runtime_seconds": time.perf_counter() - started,
    }
    (ROOT / "results" / "official" / "h_star_extension_summary.json").write_text(
        json.dumps(clean(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(clean(summary), indent=2, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-reference", action="store_true")
    args = parser.parse_args(argv)
    run_h_star_extension(archive=args.archive_reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
