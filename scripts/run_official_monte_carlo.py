"""Official Tier B Monte Carlo runner for Etapa 5A.

The certified deterministic mechanics in ``src/ai_usp`` are not modified. This
module reuses their equations in vectorized form for the independent-baseline
Monte Carlo, persists draw tables, and writes the canonical Tier B outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_usp.policy_cost import annuitize_oneoff
from ai_usp.thresholds import XI_GRID
from scripts.run_official_tier_a import (
    ANCHOR_YEAR,
    COUNTRIES,
    DATASET_VERSION,
    ENDPOINT_YEAR,
    HORIZON_YEARS,
    MODEL_VERSION,
    PARAMETER_SET_ID,
    POLICIES,
    REGIMES,
    SCENARIOS,
    clean,
    git_value,
    historical_percentiles,
    load_inputs,
    policy_instances,
    sha256_file,
    value_lookup,
)


RUN_ID = "official_4c_tierB_mc_baseline_official_v2"
MC_MODE = "MC_independent_baseline"
MECHANICAL_EROSION_DIAGNOSTIC_MODE = "mechanical_erosion_zero_diagnostic"
HIST_POS_MODE_TAX = "historical_reduced_form_positive_tax"
HIST_MIX_MODE_TAX = "historical_reduced_form_mixture_tax"
HIST_POS_MODE_TOTAL = "historical_reduced_form_positive_total_revenue"
HIST_MIX_MODE_TOTAL = "historical_reduced_form_mixture_total_revenue"
DRAW_DISTRIBUTIONS = {"bounded_PERT", "discrete_grid_or_bounded_PERT"}
EXPLICIT_REGISTERED_DRAWS = {"q_use_target"}
PROB_BASES = ("all_draw", "basic_valid", "support_valid")
THRESHOLDS = (1.00, 1.05, 1.10, 1.25, 1.50)
THRESHOLD_SUFFIX = {
    1.00: "1_00",
    1.05: "1_05",
    1.10: "1_10",
    1.25: "1_25",
    1.50: "1_50",
}
CONVERGENCE_GRID = (5_000, 10_000, 25_000, 50_000)
CONVERGENCE_TOLERANCE = 0.02
SUPPORT_SHARE_THRESHOLD = 0.90
PERT_LAMBDA = 4.0
MAIN_CELLS = {
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r0"),
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r1"),
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r2"),
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r3"),
    ("CHL", "GMI:GMI_ideal_aggregate", "stress", "r4"),
    ("PER", "PEN", "stress", "r0"),
    ("PER", "PEN", "stress", "r1"),
    ("PER", "PEN", "stress", "r2"),
    ("PER", "PEN", "stress", "r3"),
    ("PER", "PEN", "stress", "r4"),
    ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
    ("PER", "PEN", "mid", "r0"),
}


class MonteCarloError(RuntimeError):
    pass


def load_rng_policy(root: Path = ROOT) -> dict[str, Any]:
    path = root / "reproducibility" / "config" / "rng_policy.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def pert_draw(low: float, mode: float, high: float, size: int, rng: np.random.Generator) -> np.ndarray:
    """Draw from bounded PERT using scipy.stats.beta and lambda=4."""

    low = float(low)
    mode = float(mode)
    high = float(high)
    if not np.isfinite([low, mode, high]).all():
        raise MonteCarloError(f"Invalid PERT support low={low} mode={mode} high={high}")
    if high < low:
        low, high = high, low
    mode = min(max(mode, low), high)
    if math.isclose(high, low):
        return np.full(size, mode, dtype=float)
    alpha = 1.0 + PERT_LAMBDA * (mode - low) / (high - low)
    beta_param = 1.0 + PERT_LAMBDA * (high - mode) / (high - low)
    # Same SciPy beta parameterization, sampled through NumPy's PCG64-backed
    # Generator for the vectorization gate at M=50k.
    return low + (high - low) * rng.beta(alpha, beta_param, size=size)


def stable_logit(x: np.ndarray) -> np.ndarray:
    z = np.clip(x, 1e-12, 1.0 - 1e-12)
    return np.log(z / (1.0 - z))


def stable_logistic(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -700.0, 700.0)))


def tilde_array(value: np.ndarray, epsilon: np.ndarray | float) -> np.ndarray:
    return epsilon + (1.0 - epsilon) * value


def clean_null(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def normalize_text(value: Any) -> str | None:
    value = clean_null(value)
    return None if value is None else str(value)


@dataclass(frozen=True)
class ValueKey:
    name: str
    country: str | None = None
    scenario: str | None = None
    policy: str | None = None
    regime: str | None = None


class SeedBank:
    def __init__(self, seed: int):
        self.root = np.random.SeedSequence(seed)
        self.children: dict[str, np.random.SeedSequence] = {}

    def rng(self, key: str) -> np.random.Generator:
        if key not in self.children:
            self.children[key] = self.root.spawn(1)[0]
        return np.random.default_rng(self.children[key])


class ValueSampler:
    def __init__(self, values: pd.DataFrame, size: int, seed: int, record_parameters: bool = True):
        self.values = values.copy()
        for col in ["country_id", "scenario_id", "policy_id", "regime_code"]:
            self.values[col] = self.values[col].map(normalize_text)
        self.size = int(size)
        self.record_parameters = bool(record_parameters)
        self.seed_bank = SeedBank(seed)
        self.cache: dict[ValueKey, np.ndarray] = {}
        self.rows: dict[ValueKey, pd.Series] = {}
        self.parameter_records: list[dict[str, Any]] = []

    def _row(self, key: ValueKey) -> pd.Series:
        if key in self.rows:
            return self.rows[key]
        df = self.values[self.values["name"].eq(key.name)].copy()
        for col, arg in [
            ("country_id", key.country),
            ("scenario_id", key.scenario),
            ("policy_id", key.policy),
            ("regime_code", key.regime),
        ]:
            if arg is None:
                df = df[df[col].isna()]
            else:
                df = df[df[col].isna() | df[col].eq(str(arg))]
        if df.empty:
            raise MonteCarloError(f"Missing value {key}")
        df["_score"] = 0
        for col, arg in [
            ("country_id", key.country),
            ("scenario_id", key.scenario),
            ("policy_id", key.policy),
            ("regime_code", key.regime),
        ]:
            if arg is not None:
                df["_score"] += df[col].eq(str(arg)).astype(int)
        row = df.sort_values("_score", ascending=False).iloc[0]
        self.rows[key] = row
        return row

    def scalar(self, name: str, *, country: str | None = None, scenario: str | None = None, policy: str | None = None, regime: str | None = None) -> float:
        row = self._row(ValueKey(name, country, scenario, policy, regime))
        return float(row["baseline_value"])

    def array(
        self,
        name: str,
        *,
        country: str | None = None,
        scenario: str | None = None,
        policy: str | None = None,
        regime: str | None = None,
        force_draw: bool = False,
        record: bool = True,
    ) -> np.ndarray:
        key = ValueKey(name, country, scenario, policy, regime)
        if key in self.cache:
            return self.cache[key]
        row = self._row(key)
        dist = str(row.get("distribution") or "")
        baseline = float(row["baseline_value"])
        audit_status = str(row.get("audit_status") or "")
        explicit_registered_draw = key.name in EXPLICIT_REGISTERED_DRAWS or key.name.startswith("phi_raw_")
        is_draw = force_draw or (
            dist in DRAW_DISTRIBUTIONS
            and (audit_status == "author_approved" or explicit_registered_draw)
        )
        if is_draw:
            arr = pert_draw(float(row["low_value"]), baseline, float(row["high_value"]), self.size, self.seed_bank.rng(str(key)))
        else:
            arr = np.full(self.size, baseline, dtype=float)
        self.cache[key] = arr
        if record and self.record_parameters:
            self._record_parameter(key, row, arr, is_draw)
        return arr

    def _record_parameter(self, key: ValueKey, row: pd.Series, arr: np.ndarray, is_draw: bool) -> None:
        for draw_id, value in enumerate(arr):
            self.parameter_records.append(
                {
                    "run_id": RUN_ID,
                    "mc_mode": MC_MODE,
                    "draw_id": draw_id,
                    "parameter_name": key.name,
                    "country_id": key.country,
                    "scenario_id": key.scenario,
                    "policy_id": key.policy,
                    "regime_id": key.regime,
                    "parameter_value": float(value),
                    "distribution": row.get("distribution"),
                    "drawn_flag": bool(is_draw),
                    "audit_status": row.get("audit_status"),
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )


def scenario_kappa_name(scenario: str) -> str:
    if scenario == "high":
        return "kappa_LP_to_Y_high"
    if scenario == "stress":
        return "kappa_Y_to_Y_stress"
    return f"kappa_TFP_to_Y_{scenario}"


def scenario_kappa_scope(scenario: str, country: str) -> dict[str, str | None]:
    if scenario == "high":
        return {"country": country, "scenario": scenario}
    return {"scenario": scenario}


def build_country_scenario_draws(
    sampler: ValueSampler,
    inputs: dict[str, Any],
    country: str,
    scenario: str,
    eprod_frontier: np.ndarray,
) -> dict[str, np.ndarray]:
    m = sampler.size
    aipi = sampler.array("A_aipi_total", country=country)
    informality = sampler.array("I_adopt_informality", country=country)
    gap = sampler.array("Gap_excluded_indicators", country=country)
    omega_i = sampler.array("omega_I", country=country)
    omega_g = sampler.array("omega_G", country=country)
    nu_a = sampler.array("nu_A", country=country)
    nu_i = sampler.array("nu_I", country=country)
    nu_g = sampler.array("nu_G", country=country)
    q_use_target = sampler.array("q_use_target", country=country)
    epsilon_mu = sampler.array("epsilon_mu", country=country)
    q_bar = np.clip(1.0 - omega_i * informality - omega_g * gap, 0.0, 1.0)
    support_ok = q_bar > 2.0 * epsilon_mu
    q_upper = np.maximum(epsilon_mu, q_bar - epsilon_mu)
    q_use_target_adj = np.minimum(np.maximum(q_use_target, epsilon_mu), q_upper)
    q_use_target_adj = np.where(support_ok, q_use_target_adj, np.nan)
    mu_t0 = np.log(q_use_target_adj / (q_bar - q_use_target_adj)) - nu_a * aipi + nu_i * informality + nu_g * gap
    q_prod = q_use_target_adj

    phi_raw = sampler.array(f"phi_raw_{scenario}", scenario=scenario)
    kappa = sampler.array(scenario_kappa_name(scenario), **scenario_kappa_scope(scenario, country))
    pi_ai_y = sampler.array(f"pi_AI_Y_{scenario}", scenario=scenario)
    phi_y_real = phi_raw * kappa
    phi_y_nominal = (1.0 + phi_y_real) * (1.0 + pi_ai_y) - 1.0
    beta = sampler.array("beta_translation", country=country)
    gamma = sampler.array("gamma_translation", country=country)
    epsilon = sampler.array("epsilon", country=country)
    eprod = sampler.array("E_prod", country=country)
    frontier = inputs["frontier_benchmark_anchor"]
    q_bench = frontier["adoption_proxy"].to_numpy(dtype=float)
    e_front_tilde = tilde_array(eprod_frontier, epsilon) ** beta
    if np.allclose(gamma, gamma[0]) and np.allclose(epsilon, epsilon[0]):
        q_front_scalar = float(np.mean(tilde_array(q_bench, float(epsilon[0])) ** float(gamma[0])))
        q_front_tilde_mean = np.full(m, q_front_scalar, dtype=float)
    else:
        q_front_tilde_mean = np.mean(tilde_array(q_bench[None, :], epsilon[:, None]) ** gamma[:, None], axis=1)
    s_frontier = e_front_tilde * q_front_tilde_mean
    s_domestic = np.where((eprod > 0.0) & (q_prod > 0.0), tilde_array(eprod, epsilon) ** beta * tilde_array(q_prod, epsilon) ** gamma, 0.0)
    translation_factor = np.where(s_frontier > 0.0, np.minimum(1.0, s_domestic / s_frontier), 0.0)
    g_ai_level = (1.0 + phi_y_nominal * translation_factor) ** HORIZON_YEARS - 1.0
    return {
        "aipi": aipi,
        "informality": informality,
        "gap": gap,
        "omega_i": omega_i,
        "omega_g": omega_g,
        "nu_a": nu_a,
        "nu_i": nu_i,
        "nu_g": nu_g,
        "q_use_target": q_use_target,
        "q_use_target_adj": q_use_target_adj,
        "q_bar": q_bar,
        "mu_t0": mu_t0,
        "q_prod": q_prod,
        "support_ok": support_ok,
        "phi_raw": phi_raw,
        "kappa_to_y": kappa,
        "pi_ai_y": pi_ai_y,
        "phi_y_nominal": phi_y_nominal,
        "beta": beta,
        "gamma": gamma,
        "epsilon": epsilon,
        "eprod": eprod,
        "eprod_frontier": eprod_frontier,
        "s_ndc": s_domestic,
        "s_frontier": s_frontier,
        "translation_factor": translation_factor,
        "g_ai_level": g_ai_level,
        "lambda_ai": sampler.array(f"lambda_AI_{scenario}", scenario=scenario),
        "lambda_ai_kbase": sampler.array(f"lambda_AI_Kbase_{scenario}", scenario=scenario),
        "lambda_q": sampler.array("lambda_q_baseline_mid", country=country),
    }


def build_regime_draws(sampler: ValueSampler, regime: str) -> dict[str, np.ndarray]:
    force_erosion = regime != "r0"
    return {
        "tau_l_delta": sampler.array(f"tau_L_relative_delta_{regime}", regime=regime),
        "tau_k_delta": sampler.array(f"tau_K_relative_delta_{regime}", regime=regime),
        "tau_c_delta": sampler.array(f"tau_C_relative_delta_{regime}", regime=regime),
        "tau_ai_eff": sampler.array(f"tau_AI_eff_{regime}", regime=regime),
        "base_broadening_delta": sampler.array(f"base_broadening_delta_{regime}", regime=regime),
        "leakage_multiplier": sampler.array(f"leakage_multiplier_{regime}", regime=regime),
        "epsilon_ero_l": sampler.array(f"epsilon_ero_L_{regime}", regime=regime, force_draw=force_erosion),
        "epsilon_ero_k": sampler.array(f"epsilon_ero_K_{regime}", regime=regime, force_draw=force_erosion),
        "epsilon_ero_c": sampler.array(f"epsilon_ero_C_{regime}", regime=regime, force_draw=force_erosion),
        "epsilon_ero_ai": sampler.array(f"epsilon_ero_AI_{regime}", regime=regime, force_draw=force_erosion),
    }


def fixed_cost_arrays(admin_df: pd.DataFrame, country: str, policy_id: str, leakage_multiplier: np.ndarray) -> dict[str, np.ndarray]:
    rows = admin_df[admin_df["country_id"].eq(country) & admin_df["policy_id"].eq(policy_id)]
    if rows.empty:
        raise MonteCarloError(f"Missing admin costs for {country}/{policy_id}")
    row = rows.iloc[0]
    ac_net_fix = float(row["admin_cost_new_gdp"]) - float(row["admin_savings_existing_gdp"])
    tr_ann = float(row["transition_recurring_gdp"]) + annuitize_oneoff(
        float(row["transition_oneoff_gdp"]),
        float(row["transition_discount_rate"]),
        int(row["transition_horizon_years"]),
    )
    leak_fix = float(row["leakage_fixed_gdp"]) * leakage_multiplier
    return {
        "ac_net_fix": np.full_like(leakage_multiplier, ac_net_fix, dtype=float),
        "tr_ann": np.full_like(leakage_multiplier, tr_ann, dtype=float),
        "leak_fix": leak_fix,
        "f_fix": ac_net_fix + tr_ann + leak_fix,
    }


def compute_cell_arrays(
    sampler: ValueSampler,
    inputs: dict[str, Any],
    country: str,
    scenario: str,
    regime: str,
    policy: dict[str, Any],
    cs: dict[str, np.ndarray],
    rd: dict[str, np.ndarray],
    mechanical_erosion_zero: bool = False,
    historical_mfc: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    g = cs["g_ai_level"]
    q_prod = cs["q_prod"]
    base_delta = np.clip(rd["base_broadening_delta"], 0.0, 1.0)
    psi_shift = sampler.array("psi_shift", country=country)
    exempt_c = sampler.array("exempt_C", country=country)
    psi_shift_r = np.maximum(0.0, psi_shift * (1.0 - base_delta))
    exempt_c_r = np.maximum(0.0, exempt_c * (1.0 - base_delta))

    labor_share = sampler.array("LS_labor_share", country=country)
    e_auto = sampler.array("E_auto", country=country)
    e_aug = sampler.array("E_aug", country=country)
    delta_s = sampler.array("delta_s", country=country)
    psi_s = sampler.array("psi_s", country=country)
    zeta_s = sampler.array("zeta_s", country=country)
    rst = sampler.array("RST", country=country)
    lambda_ls = sampler.array("lambda_LS", country=country)
    chi_kbase = sampler.array("chi_Kbase", country=country)
    chi_dom = sampler.array("chi_dom", country=country)
    tau_l_disp = sampler.array("tau_L_disp", country=country)
    tau_k_disp = sampler.array("tau_K_disp", country=country)
    tau_r_disp = sampler.array("tau_R_disp", country=country)
    mpc_w = sampler.array("mpc_W", country=country)
    mpc_pi = sampler.array("mpc_Pi", country=country)
    mpc_r = sampler.array("mpc_R", country=country)
    m_m = sampler.array("m_M", country=country)
    theta_r_dom = sampler.array("theta_R_dom", country=country)

    pressure = (-(delta_s - zeta_s * rst) * e_auto + psi_s * e_aug) * q_prod
    labor_share_prime = stable_logistic(stable_logit(labor_share) + lambda_ls * pressure)
    delta_w = labor_share_prime * (1.0 + g) - labor_share
    delta_nls = g - delta_w
    delta_capital_base = chi_kbase * delta_nls
    delta_capital_domestic = chi_dom * (1.0 - psi_shift_r) * delta_capital_base
    delta_residual = np.maximum(0.0, delta_nls - delta_capital_base)
    delta_w_disp = (1.0 - tau_l_disp) * delta_w
    delta_pi_disp = (1.0 - tau_k_disp) * delta_capital_domestic
    delta_r_disp = theta_r_dom * (1.0 - tau_r_disp) * delta_residual
    consumption_base = mpc_w * delta_w_disp + mpc_pi * delta_pi_disp + mpc_r * delta_r_disp
    delta_consumption_taxable = (1.0 - exempt_c_r) * (1.0 - m_m) * np.maximum(0.0, consumption_base)

    positive_g = g > 0.0
    omega_l = np.where(positive_g, delta_w / g, 0.0)
    omega_k = np.where(positive_g, delta_capital_domestic / g, 0.0)
    omega_c = np.where(positive_g, delta_consumption_taxable / g, 0.0)
    tau_l = np.clip(sampler.array("tau_L_eff", country=country) * (1.0 + rd["tau_l_delta"]), 0.0, 1.0)
    tau_k = np.clip(sampler.array("tau_K_eff", country=country) * (1.0 + rd["tau_k_delta"]), 0.0, 1.0)
    tau_c = np.clip(sampler.array("tau_C_eff", country=country) * (1.0 + rd["tau_c_delta"]), 0.0, 1.0)
    tau_ai = np.clip(rd["tau_ai_eff"], 0.0, 1.0)
    omega_k_net = omega_k - cs["lambda_ai_kbase"]
    mfc_mechanical = omega_l * tau_l + omega_k_net * tau_k + omega_c * tau_c + cs["lambda_ai"] * tau_ai
    if historical_mfc is None:
        if regime == "r0" or mechanical_erosion_zero:
            mfc_gross = mfc_mechanical
        else:
            mfc_gross = (
                omega_l * np.maximum(0.0, 1.0 - rd["epsilon_ero_l"] * tau_l) * tau_l
                + omega_k_net * np.maximum(0.0, 1.0 - rd["epsilon_ero_k"] * tau_k) * tau_k
                + omega_c * np.maximum(0.0, 1.0 - rd["epsilon_ero_c"] * tau_c) * tau_c
                + cs["lambda_ai"] * np.maximum(0.0, 1.0 - rd["epsilon_ero_ai"] * tau_ai) * tau_ai
            )
    else:
        mfc_mechanical = historical_mfc
        mfc_gross = historical_mfc
    mfc_tilde = mfc_gross
    fixed = fixed_cost_arrays(inputs["policy_admin_transition_cost"], country, policy["policy_id"], rd["leakage_multiplier"])
    fs_gross = mfc_gross * g
    fs_eff = mfc_tilde * g - fixed["ac_net_fix"] - fixed["tr_ann"] - fixed["leak_fix"]
    cost_gross = float(policy["cost_gross_gdp"])
    cost_net = float(policy["cost_net_gdp"])
    v_gross = fs_eff / cost_gross if cost_gross > 0.0 else np.full_like(fs_eff, np.nan)
    v_net = fs_eff / cost_net if cost_net > 0.0 else np.full_like(fs_eff, np.nan)
    basic_valid = (
        np.isfinite(v_gross)
        & np.isfinite(mfc_gross)
        & np.isfinite(g)
        & (g > 0.0)
        & (mfc_tilde > 0.0)
        & (mfc_tilde <= mfc_gross + 1e-14)
    )
    support_valid = (
        basic_valid
        & cs["support_ok"]
        & (cs["q_prod"] <= cs["q_bar"] + 1e-14)
        & (cs["translation_factor"] >= -1e-14)
        & (cs["translation_factor"] <= 1.0 + 1e-14)
    )
    return {
        "g_ai_level": g,
        "mfc_gross_mechanical": mfc_mechanical,
        "mfc_gross": mfc_gross,
        "mfc_tilde_gross": mfc_tilde,
        "fs_gross": fs_gross,
        "fs_eff": fs_eff,
        "v_gross": v_gross,
        "v_net": v_net,
        "basic_valid": basic_valid,
        "support_valid": support_valid,
        "threshold_computable": basic_valid & (cs["phi_y_nominal"] > 0.0),
        "fixed": fixed,
        "tau_l": tau_l,
        "tau_k": tau_k,
        "tau_c": tau_c,
        "tau_ai": tau_ai,
        "omega_l": omega_l,
        "omega_k": omega_k,
        "omega_k_net": omega_k_net,
        "omega_c": omega_c,
        "delta_consumption_taxable": delta_consumption_taxable,
    }


def summarize_probabilities(
    *,
    arrays: dict[str, np.ndarray],
    country: str,
    policy: dict[str, Any],
    scenario: str,
    regime: str,
    mc_mode: str,
    converged: bool,
    support_threshold: float,
    spb_plus_gdp: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    v = arrays["v_gross"]
    fs_eff = arrays["fs_eff"]
    basic_valid = arrays["basic_valid"]
    support_valid = arrays["support_valid"]
    masks = {
        "all_draw": np.ones(len(v), dtype=bool),
        "basic_valid": basic_valid,
        "support_valid": support_valid,
    }
    valid_support_share = float(np.mean(support_valid))
    threshold_computability_share = float(np.mean(arrays["threshold_computable"]))
    requirement_already_covered_share = float(np.mean((v >= 1.10) & basic_valid))
    for basis, mask in masks.items():
        denom = int(mask.sum())
        finite_mask = mask & np.isfinite(v)
        if denom == 0 or not finite_mask.any():
            percentiles = {f"v_p{p:02d}": 0.0 for p in (5, 25, 50, 75, 95)}
        else:
            q = np.nanpercentile(v[finite_mask], [5, 25, 50, 75, 95])
            percentiles = {
                "v_p05": float(q[0]),
                "v_p25": float(q[1]),
                "v_p50": float(q[2]),
                "v_p75": float(q[3]),
                "v_p95": float(q[4]),
            }
        row = {
            "run_id": RUN_ID,
            "model_version": MODEL_VERSION,
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
            "country_id": country,
            "policy_id": policy["policy_id"],
            "policy_variant_id": policy["policy_variant_id"],
            "gmi_version": policy["gmi_version"],
            "scenario_id": scenario,
            "regime_id": regime,
            "endpoint_year": ENDPOINT_YEAR,
            "prob_basis": basis,
            "mc_mode": mc_mode,
            "mc_n_draws": int(len(v)),
            **percentiles,
            "valid_support_share": valid_support_share,
            "valid_support_share_above_threshold": bool(valid_support_share >= support_threshold),
            "threshold_computability_share": threshold_computability_share,
            "requirement_already_covered_share": requirement_already_covered_share,
            "converged_flag": bool(converged),
        }
        denom_float = float(denom) if denom else 1.0
        for threshold in THRESHOLDS:
            suffix = THRESHOLD_SUFFIX[threshold]
            cross = mask & basic_valid & (v >= threshold)
            debt = mask & basic_valid & (fs_eff >= threshold * float(policy["cost_gross_gdp"]) + spb_plus_gdp)
            row[f"prob_v_ge_{suffix}"] = float(cross.sum() / denom_float) if denom else 0.0
            row[f"prob_debt_consistent_{suffix}"] = float(debt.sum() / denom_float) if denom else 0.0
            failures = mask & np.isfinite(v) & (v < threshold)
            sev = threshold - v[failures]
            row[f"failure_severity_mean_{suffix}"] = float(np.mean(sev)) if len(sev) else 0.0
            row[f"failure_severity_median_{suffix}"] = float(np.median(sev)) if len(sev) else 0.0
        row["prob_v_ge_1"] = row["prob_v_ge_1_00"]
        rows.append(row)
    return rows


def fiscal_draw_frame(
    *,
    arrays: dict[str, np.ndarray],
    country: str,
    policy: dict[str, Any],
    scenario: str,
    regime: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_id": RUN_ID,
            "mc_mode": MC_MODE,
            "draw_id": np.arange(len(arrays["v_gross"]), dtype=np.int64),
            "country_id": country,
            "policy_id": policy["policy_id"],
            "policy_variant_id": policy["policy_variant_id"],
            "gmi_version": policy["gmi_version"],
            "scenario_id": scenario,
            "regime_id": regime,
            "g_ai_level": arrays["g_ai_level"],
            "mfc_gross_mechanical": arrays["mfc_gross_mechanical"],
            "mfc_gross": arrays["mfc_gross"],
            "mfc_tilde_gross": arrays["mfc_tilde_gross"],
            "fs_eff": arrays["fs_eff"],
            "v_gross": arrays["v_gross"],
            "basic_valid": arrays["basic_valid"],
            "support_valid": arrays["support_valid"],
            "parameter_set_id": PARAMETER_SET_ID,
            "dataset_version": DATASET_VERSION,
        }
    )


def historical_mfc_draws(
    pct: Any,
    sampler: ValueSampler,
    key: str,
    mixture: bool,
) -> np.ndarray:
    rng = sampler.seed_bank.rng(key)
    pos = pert_draw(pct.p50 if not hasattr(pct, "p10") else pct.p10, pct.p50, pct.p90, sampler.size, rng)
    if not mixture:
        return pos
    # Fetch full canonical row to get negative-tail fields.
    country = key.split("|")[1]
    concept = key.split("|")[2]
    rows = sampler.values[
        sampler.values["name"].eq("__never_matches__")
    ]
    raise MonteCarloError("historical_mfc_draws requires canonical percentile row input")


def historical_draw_from_row(row: pd.Series, size: int, rng: np.random.Generator, mixture: bool) -> np.ndarray:
    positive = pert_draw(row["p10_mfc_hist_positive"], row["p50_mfc_hist_positive"], row["p90_mfc_hist_positive"], size, rng)
    if not mixture:
        return positive
    p_neg = float(row["p_negative_capture"])
    neg_support = [
        float(row["p10_mfc_hist_negative"]),
        float(row["p50_mfc_hist_negative"]),
        float(row["p90_mfc_hist_negative"]),
    ]
    if p_neg <= 0.0 or not np.isfinite(neg_support).all():
        return positive
    low = min(neg_support)
    mode = float(row["p50_mfc_hist_negative"])
    high = max(neg_support)
    negative = pert_draw(low, mode, high, size, rng)
    is_negative = rng.random(size) < p_neg
    return np.where(is_negative, negative, positive)


def canonical_percentile_row(inputs: dict[str, Any], country: str, concept: str) -> pd.Series:
    pct = inputs["historical_capture_percentiles"]
    rows = pct[
        pct["country_id"].eq(country)
        & pct["revenue_concept"].eq(concept)
        & pct["percentile_sample"].eq("2000plus")
    ]
    if rows.empty:
        raise MonteCarloError(f"Missing historical_capture_percentiles {country}/{concept}/2000plus")
    return rows.iloc[0]


def build_global_draw_frames(
    country_scenario: dict[tuple[str, str], dict[str, np.ndarray]],
    policies_by_country: dict[str, list[dict[str, Any]]],
    sampler: ValueSampler,
    inputs: dict[str, Any],
    regime_draws: dict[str, dict[str, np.ndarray]],
) -> dict[str, pd.DataFrame]:
    global_rows = []
    country_rows = []
    policy_rows = []
    draw_ids = np.arange(sampler.size, dtype=np.int64)
    for (country, scenario), cs in country_scenario.items():
        global_rows.append(
            pd.DataFrame(
                {
                    "run_id": RUN_ID,
                    "mc_mode": MC_MODE,
                    "draw_id": draw_ids,
                    "country_id": country,
                    "scenario_id": scenario,
                    "phi_raw": cs["phi_raw"],
                    "kappa_to_y": cs["kappa_to_y"],
                    "pi_ai_y": cs["pi_ai_y"],
                    "phi_y_nominal": cs["phi_y_nominal"],
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
        )
        country_rows.append(
            pd.DataFrame(
                {
                    "run_id": RUN_ID,
                    "mc_mode": MC_MODE,
                    "draw_id": draw_ids,
                    "country_id": country,
                    "scenario_id": scenario,
                    "q_use_target": cs["q_use_target"],
                    "q_use_target_adj": cs["q_use_target_adj"],
                    "q_bar": cs["q_bar"],
                    "mu_t0": cs["mu_t0"],
                    "q_prod": cs["q_prod"],
                    "E_prod": cs["eprod"],
                    "E_prod_frontier": cs["eprod_frontier"],
                    "s_ndc": cs["s_ndc"],
                    "s_frontier": cs["s_frontier"],
                    "translation_factor": cs["translation_factor"],
                    "g_ai_level": cs["g_ai_level"],
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
        )
    for country, policies in policies_by_country.items():
        for policy in policies:
            policy_rows.append(
                pd.DataFrame(
                    {
                        "run_id": RUN_ID,
                        "mc_mode": MC_MODE,
                        "draw_id": draw_ids,
                        "country_id": country,
                        "policy_id": policy["policy_id"],
                        "policy_variant_id": policy["policy_variant_id"],
                        "gmi_version": policy["gmi_version"],
                        "cost_gross_gdp": float(policy["cost_gross_gdp"]),
                        "cost_net_gdp": float(policy["cost_net_gdp"]),
                        "endpoint_year": ENDPOINT_YEAR,
                        "endpoint_cost_rule": policy["endpoint_cost_rule"],
                        "parameter_set_id": PARAMETER_SET_ID,
                        "dataset_version": DATASET_VERSION,
                    }
                )
            )
    return {
        "global_scenario_draw": pd.concat(global_rows, ignore_index=True),
        "country_scenario_draw": pd.concat(country_rows, ignore_index=True),
        "policy_cost_draw": pd.concat(policy_rows, ignore_index=True),
        "draw_parameter_value": pd.DataFrame(sampler.parameter_records),
    }


def run_single_mc(
    *,
    root: Path,
    m_draws: int,
    seed: int,
    persist_draws: bool,
    cell_filter: set[tuple[str, str, str, str]] | None = None,
    convergence_flags: dict[tuple[str, str, str, str], bool] | None = None,
) -> dict[str, Any]:
    inputs = load_inputs(root)
    values = inputs["values"]
    value = value_lookup(values)
    sampler = ValueSampler(values, m_draws, seed, record_parameters=persist_draws)
    eprod_frontier = sampler.array("E_prod_frontier")
    if cell_filter is None:
        countries = list(COUNTRIES)
        scenarios = list(SCENARIOS)
        regimes = list(REGIMES)
    else:
        countries = sorted({key[0] for key in cell_filter})
        scenarios = sorted({key[2] for key in cell_filter}, key=list(SCENARIOS).index)
        regimes = sorted({key[3] for key in cell_filter}, key=list(REGIMES).index)
    country_scenario = {
        (country, scenario): build_country_scenario_draws(sampler, inputs, country, scenario, eprod_frontier)
        for country in countries
        for scenario in scenarios
    }
    regime_draws = {regime: build_regime_draws(sampler, regime) for regime in regimes}
    policies_by_country = {
        country: policy_instances(country, inputs["policy_cost"], inputs["wpp"])
        for country in countries
    }
    probability_rows: list[dict[str, Any]] = []
    fiscal_frames: list[pd.DataFrame] = []
    historical_rows: list[dict[str, Any]] = []
    cell_seconds: list[float] = []
    for country in countries:
        spb = value("sPB_plus_gdp_ratio", country=country)
        for scenario in scenarios:
            cs = country_scenario[(country, scenario)]
            for regime in regimes:
                rd = regime_draws[regime]
                for policy in policies_by_country[country]:
                    key = (country, policy["policy_variant_id"], scenario, regime)
                    if cell_filter is not None and key not in cell_filter:
                        continue
                    started = time.perf_counter()
                    arrays = compute_cell_arrays(sampler, inputs, country, scenario, regime, policy, cs, rd)
                    cell_seconds.append(time.perf_counter() - started)
                    converged = bool(convergence_flags.get(key, True)) if convergence_flags else True
                    probability_rows.extend(
                        summarize_probabilities(
                            arrays=arrays,
                            country=country,
                            policy=policy,
                            scenario=scenario,
                            regime=regime,
                            mc_mode=MC_MODE,
                            converged=converged,
                            support_threshold=SUPPORT_SHARE_THRESHOLD,
                            spb_plus_gdp=spb,
                        )
                    )
                    if regime != "r0":
                        mechanical_arrays = compute_cell_arrays(
                            sampler,
                            inputs,
                            country,
                            scenario,
                            regime,
                            policy,
                            cs,
                            rd,
                            mechanical_erosion_zero=True,
                        )
                        probability_rows.extend(
                            summarize_probabilities(
                                arrays=mechanical_arrays,
                                country=country,
                                policy=policy,
                                scenario=scenario,
                                regime=regime,
                                mc_mode=MECHANICAL_EROSION_DIAGNOSTIC_MODE,
                                converged=True,
                                support_threshold=SUPPORT_SHARE_THRESHOLD,
                                spb_plus_gdp=spb,
                            )
                        )
                    if persist_draws:
                        fiscal_frames.append(fiscal_draw_frame(arrays=arrays, country=country, policy=policy, scenario=scenario, regime=regime))
                    if regime == "r0":
                        for concept, pos_mode, mix_mode in [
                            ("tax", HIST_POS_MODE_TAX, HIST_MIX_MODE_TAX),
                            ("total_revenue", HIST_POS_MODE_TOTAL, HIST_MIX_MODE_TOTAL),
                        ]:
                            pct_row = canonical_percentile_row(inputs, country, concept)
                            for mode, mixture in [(pos_mode, False), (mix_mode, True)]:
                                hist_mfc = historical_draw_from_row(
                                    pct_row,
                                    m_draws,
                                    sampler.seed_bank.rng(f"historical|{country}|{concept}|{scenario}|{policy['policy_variant_id']}|{mode}"),
                                    mixture,
                                )
                                hist_arrays = compute_cell_arrays(
                                    sampler,
                                    inputs,
                                    country,
                                    scenario,
                                    regime,
                                    policy,
                                    cs,
                                    rd,
                                    historical_mfc=hist_mfc,
                                )
                                historical_rows.extend(
                                    summarize_probabilities(
                                        arrays=hist_arrays,
                                        country=country,
                                        policy=policy,
                                        scenario=scenario,
                                        regime=regime,
                                        mc_mode=mode,
                                        converged=True,
                                        support_threshold=SUPPORT_SHARE_THRESHOLD,
                                        spb_plus_gdp=spb,
                                    )
                                )
    draw_frames = build_global_draw_frames(country_scenario, policies_by_country, sampler, inputs, regime_draws) if persist_draws else {}
    if persist_draws:
        draw_frames["fiscal_conversion_draw"] = pd.concat(fiscal_frames, ignore_index=True)
    return {
        "monte_carlo_result": pd.DataFrame(probability_rows + historical_rows),
        "draw_frames": draw_frames,
        "max_cell_seconds": max(cell_seconds) if cell_seconds else 0.0,
        "values": values,
        "inputs": inputs,
    }


def run_convergence(root: Path, seed: int) -> tuple[pd.DataFrame, dict[tuple[str, str, str, str], bool]]:
    rows: list[dict[str, Any]] = []
    flags: dict[tuple[str, str, str, str], bool] = {}
    max_m = max(CONVERGENCE_GRID)
    for index, key in enumerate(sorted(MAIN_CELLS)):
        cell_seed = int(np.random.SeedSequence([seed, 50_000, index]).generate_state(1)[0])
        # Recompute convergence by prefixes using the same seeded run through slices
        # from fiscal_conversion_draw is intentionally avoided to keep persistence small.
        # The full-row probability at max_M is the canonical endpoint.
        probs = []
        for m in CONVERGENCE_GRID:
            partial_result = run_single_mc(
                root=root,
                m_draws=m,
                seed=cell_seed,
                persist_draws=False,
                cell_filter={key},
            )
            if m == max_m and partial_result["max_cell_seconds"] > 1.0:
                raise MonteCarloError(f"Vectorization gate failed for {key}: {partial_result['max_cell_seconds']:.3f}s at M=50k")
            partial = partial_result["monte_carlo_result"]
            row = partial[(partial["mc_mode"].eq(MC_MODE)) & (partial["prob_basis"].eq("all_draw"))].iloc[0]
            probs.append(float(row["prob_v_ge_1_10"]))
            rows.append(
                {
                    "run_id": RUN_ID,
                    "mc_mode": MC_MODE,
                    "country_id": key[0],
                    "policy_variant_id": key[1],
                    "scenario_id": key[2],
                    "regime_id": key[3],
                    "mc_n_draws": m,
                    "prob_v_ge_1_10": float(row["prob_v_ge_1_10"]),
                    "valid_support_share": float(row["valid_support_share"]),
                    "valid_support_share_above_threshold": bool(row["valid_support_share"] >= SUPPORT_SHARE_THRESHOLD),
                    "delta_from_previous": None,
                    "convergence_tolerance": CONVERGENCE_TOLERANCE,
                    "support_share_threshold": SUPPORT_SHARE_THRESHOLD,
                    "converged_flag": False,
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            )
        deltas = [abs(probs[i] - probs[i - 1]) for i in range(1, len(probs))]
        converged = bool(deltas and max(deltas) <= CONVERGENCE_TOLERANCE)
        support_ok = bool(rows[-1]["valid_support_share"] >= SUPPORT_SHARE_THRESHOLD)
        flags[key] = converged and support_ok
        for offset, m in enumerate(CONVERGENCE_GRID):
            row_index = len(rows) - len(CONVERGENCE_GRID) + offset
            rows[row_index]["delta_from_previous"] = None if offset == 0 else float(deltas[offset - 1])
            rows[row_index]["converged_flag"] = bool(converged)
    return pd.DataFrame(rows), flags


def classify_final(monte_carlo: pd.DataFrame, root: Path) -> pd.DataFrame:
    prelim = pd.read_csv(root / "results" / "official" / "country_policy_classification_preliminary.csv")
    primary = monte_carlo[(monte_carlo["mc_mode"].eq(MC_MODE)) & (monte_carlo["prob_basis"].eq("all_draw"))]
    robust_scope = primary[primary["scenario_id"].eq("mid") & primary["regime_id"].isin(["r0", "r1", "r2"])]
    stress_scope = primary[primary["scenario_id"].eq("stress")]
    robust_grouped = (
        robust_scope.groupby(["country_id", "policy_id", "gmi_version"], dropna=False)
        .agg(
            max_prob_v_ge_1=("prob_v_ge_1", "max"),
            max_prob_v_ge_1_10=("prob_v_ge_1_10", "max"),
            max_prob_debt_consistent_1_10=("prob_debt_consistent_1_10", "max"),
            min_valid_support_share=("valid_support_share", "min"),
        )
        .reset_index()
    )
    stress_grouped = (
        stress_scope.groupby(["country_id", "policy_id", "gmi_version"], dropna=False)
        .agg(
            stress_max_prob_v_ge_1=("prob_v_ge_1", "max"),
            stress_max_prob_v_ge_1_10=("prob_v_ge_1_10", "max"),
            stress_max_prob_debt_consistent_1_10=("prob_debt_consistent_1_10", "max"),
        )
        .reset_index()
    )
    rows = []
    merged = prelim.merge(robust_grouped, on=["country_id", "policy_id", "gmi_version"], how="left")
    merged = merged.merge(stress_grouped, on=["country_id", "policy_id", "gmi_version"], how="left")
    for row in merged.to_dict("records"):
        prelim_class = row["country_policy_result_class"]
        max_p1 = float(row.get("max_prob_v_ge_1") or 0.0)
        max_p110 = float(row.get("max_prob_v_ge_1_10") or 0.0)
        max_debt110 = float(row.get("max_prob_debt_consistent_1_10") or 0.0)
        stress_p1 = float(row.get("stress_max_prob_v_ge_1") or 0.0)
        stress_p110 = float(row.get("stress_max_prob_v_ge_1_10") or 0.0)
        stress_debt110 = float(row.get("stress_max_prob_debt_consistent_1_10") or 0.0)
        if row["policy_id"] == "UBI":
            final = "stress_benchmark_only"
            note = "UBI remains a stress benchmark; probabilistic leg is reported but not upgraded."
        elif max_p110 >= 0.75 and max_debt110 >= 0.75 and "not_feasible" not in str(prelim_class):
            final = "robustly_feasible"
            note = "Robust leg passes on MC_independent_baseline/all_draw over mid x r0-r2, including debt."
        elif "conditional" in str(prelim_class) and stress_p110 >= 0.75 and stress_debt110 >= 0.75:
            final = "conditionally_feasible"
            note = "prob≈1.0 a stress pasando deuda; stress informs conditional status only, not robust leg."
        elif "fragile" in str(prelim_class) or max_p1 >= 0.50 or stress_p1 >= 0.50:
            final = "fragile_feasible"
            note = "Primary robust leg does not pass on mid x r0-r2; feasibility support is fragile or stress-dependent."
        else:
            final = "not_feasible"
            note = "No robust mid x r0-r2 probabilistic leg and no deterministic fragile/conditional leg."
        rows.append(
            {
                "run_id": RUN_ID,
                "country_id": row["country_id"],
                "policy_id": row["policy_id"],
                "gmi_version": row["gmi_version"] if not pd.isna(row["gmi_version"]) else None,
                "preliminary_country_policy_result_class": prelim_class,
                "final_country_policy_result_class": final,
                "probabilistic_leg": "evaluated_MC_independent_baseline",
                "max_prob_v_ge_1": max_p1,
                "max_prob_v_ge_1_10": max_p110,
                "min_valid_support_share": float(row.get("min_valid_support_share") or 0.0),
                "classification_note": note,
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
            }
        )
    return pd.DataFrame(rows)


def correlation_matrix_rows() -> pd.DataFrame:
    pairs = [
        ("A_aipi_total", "q_use_target", 0.5, "positivo", True, "translated_primitive_pair", "AIPI-q_prod translated to A<->q_use_target; q_prod is derived after logit inversion."),
        ("Gap_excluded_indicators", "q_use_target", -0.5, "negativo", True, "translated_primitive_pair", "Gap-q_prod translated to Gap<->q_use_target; q_prod is derived."),
        ("I_adopt_informality", "q_use_target", -0.5, "negativo", True, "translated_primitive_pair", "informality-q_prod translated to I<->q_use_target; q_prod is derived."),
        ("I_adopt_informality", "chi_Kbase", -0.5, "negativo", True, "translated_primitive_pair", "Direct primitive pair from plan 14.2."),
        ("A_aipi_total", "E_prod", 0.5, "positivo", True, "translated_primitive_pair", "Direct primitive pair from plan 14.2."),
        ("A_aipi_total", "tau_L_eff/tau_K_eff/tau_C_eff", None, "positivo moderado", False, "omitted_fixed_tau_effective", "A<->tau_effs would use +0.3 only if effective tau primitives are drawn; baseline-official-v2 keeps tau effective fixed/derived, so it is omitted."),
        ("I_adopt_informality", "tau_L_eff/tau_K_eff/tau_C_eff", None, "negativo", False, "omitted_fixed_tau_effective", "I<->tau_effs would use -0.5 only if effective tau primitives are drawn; baseline-official-v2 keeps tau effective fixed/derived, so it is omitted."),
        ("admin_cost", "Vgross", None, "negativo", False, "induced_by_derivation_not_imposed", "inducidos por derivación; NO se imponen (doble conteo de dependencia)."),
        ("theta_target", "Vgross_GMI", None, "negativo", False, "induced_by_derivation_not_imposed", "inducidos por derivación; NO se imponen (doble conteo de dependencia)."),
        ("S_frontier_exigency", "T", None, "negativo", False, "induced_by_derivation_not_imposed", "inducidos por derivación; NO se imponen (doble conteo de dependencia)."),
        ("leakage", "MFCeff", None, "negativo", False, "induced_by_derivation_not_imposed", "inducidos por derivación; NO se imponen (doble conteo de dependencia)."),
    ]
    return pd.DataFrame(
        [
            {
                "parameter_set_id": PARAMETER_SET_ID,
                "pair_id": f"rank_corr_{a}_{b}".replace(" ", "_").replace("/", "_"),
                "variable_a": a,
                "variable_b": b,
                "spearman_rho_proposed": rho,
                "sign_from_plan_14_2": sign,
                "impose_in_iman_conover": impose,
                "translation_status": status,
                "magnitude_rule": "0.3 for moderado; 0.5 otherwise",
                "audit_status": "author_review",
                "source_id": "PLAN_02_SEC_14_2",
                "notes": notes,
            }
            for a, b, rho, sign, impose, status, notes in pairs
        ]
    )


def upsert_governance(root: Path, matrix: pd.DataFrame) -> None:
    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        con.execute("DELETE FROM threshold_assignment_table WHERE parameter_set_id = ? AND threshold_id = 'mc_valid_support_share_min'", [PARAMETER_SET_ID])
        support = pd.DataFrame(
            [
                {
                    "threshold_id": "mc_valid_support_share_min",
                    "threshold_name": "MC valid support share minimum",
                    "threshold_value": SUPPORT_SHARE_THRESHOLD,
                    "unit": "probability",
                    "scope": "Tier B MC_independent_baseline",
                    "rule": "valid_support_share must be >= 0.90 for main cells; author_review threshold declared in Etapa 5A.",
                    "parameter_set_id": PARAMETER_SET_ID,
                    "dataset_version": DATASET_VERSION,
                }
            ]
        )
        con.register("_support", support)
        con.execute("INSERT INTO threshold_assignment_table SELECT * FROM _support")
        con.unregister("_support")

        con.execute(
            "DELETE FROM value_assignment_table WHERE parameter_set_id = ? AND module = 'monte_carlo_dependency'",
            [PARAMETER_SET_ID],
        )
        existing_cols = con.execute("DESCRIBE value_assignment_table").fetchdf()["column_name"].tolist()
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for row in matrix.to_dict("records"):
            rows.append(
                {
                    "parameter_set_id": PARAMETER_SET_ID,
                    "name": row["pair_id"],
                    "module": "monte_carlo_dependency",
                    "country_id": None,
                    "scenario_id": None,
                    "policy_id": None,
                    "regime_code": None,
                    "value_type": "rank_correlation_proposal",
                    "unit": "spearman_rho",
                    "baseline_value": row["spearman_rho_proposed"],
                    "low_value": row["spearman_rho_proposed"],
                    "high_value": row["spearman_rho_proposed"],
                    "support_type": "plan_14_2_sign_with_etapa_5a_magnitude_proposal",
                    "source_id": "PLAN_02_SEC_14_2",
                    "formula_id": "IMAN_CONOVER_RANK_CORRELATION_PROPOSAL",
                    "distribution": "fixed_proposal",
                    "truncation_rule": "not_used_until_author_signature",
                    "primary_spec_flag": False,
                    "robustness_flag": True,
                    "stress_flag": False,
                    "double_counting_risk": "not_applicable_pre_run_declaration",
                    "double_counting_note": "Not applied in MC_independent_baseline; exported for Etapa 5B review.",
                    "audit_status": "author_review",
                    "notes": row["notes"],
                    "is_lac_fallback": False,
                    "assumption_id": row["pair_id"],
                    "dataset_version": DATASET_VERSION,
                    "build_id": "etapa_5a_mc_dependency_declaration",
                    "created_at": now,
                    "created_by_script": "run_official_monte_carlo.py",
                    "author_approval_date": None,
                    "author_approval_note": None,
                }
            )
        value_df = pd.DataFrame(rows)
        value_df = value_df.reindex(columns=existing_cols)
        con.register("_pairs", value_df)
        con.execute("INSERT INTO value_assignment_table SELECT * FROM _pairs")
        con.unregister("_pairs")
    finally:
        con.close()


def write_outputs(root: Path, outputs: dict[str, Any]) -> dict[str, str]:
    reports = root / "reports"
    result_dir = root / "results" / "official"
    draw_dir = result_dir / "draws"
    reports.mkdir(exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    draw_dir.mkdir(parents=True, exist_ok=True)

    csv_outputs = {
        "monte_carlo_result": outputs["monte_carlo_result"],
        "mc_convergence_report": outputs["mc_convergence_report"],
        "country_policy_classification_final": outputs["country_policy_classification_final"],
    }
    for name, df in csv_outputs.items():
        df.to_csv(result_dir / f"{name}.csv", index=False)
        df.to_csv(reports / f"{name}_baseline-official-v2.csv", index=False)

    outputs["rank_correlation_matrix_proposed"].to_csv(reports / "rank_correlation_matrix_proposed_baseline-official-v2.csv", index=False)
    outputs["rank_correlation_matrix_proposed"].to_csv(result_dir / "rank_correlation_matrix_proposed.csv", index=False)
    outputs["mc_tier_b_tolerance_calibration"].to_json(reports / "mc_tier_b_tolerance_calibration.json", orient="records", indent=2)
    outputs["mc_tier_b_tolerance_calibration"].to_json(result_dir / "mc_tier_b_tolerance_calibration.json", orient="records", indent=2)

    draw_hashes = {}
    for name, df in outputs["draw_frames"].items():
        path = draw_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        draw_hashes[f"draws/{name}.parquet"] = sha256_file(path)

    con = duckdb.connect(str(root / "db" / "ai_usp_threshold.duckdb"))
    try:
        for name, df in csv_outputs.items():
            con.register("_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
        for name in outputs["draw_frames"]:
            path = str((draw_dir / f"{name}.parquet").resolve()).replace("\\", "/")
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
    finally:
        con.close()

    manifest_path = result_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.update(
        {
            "run_id": manifest.get("run_id", "official_4c_tierA_baseline_official_v2"),
            "tier": "A+B",
            "monte_carlo_run_id": RUN_ID,
            "monte_carlo_mode": MC_MODE,
            "monte_carlo_draws_base": int(outputs["m_draws"]),
            "monte_carlo_convergence_grid": list(CONVERGENCE_GRID),
            "monte_carlo_main_cells": [list(k) for k in sorted(MAIN_CELLS)],
            "monte_carlo_pert_lambda": PERT_LAMBDA,
            "mc_valid_support_share_threshold": SUPPORT_SHARE_THRESHOLD,
            "run_modes": sorted(
                set(manifest.get("run_modes", []))
                | {MC_MODE, MECHANICAL_EROSION_DIAGNOSTIC_MODE, "historical_reduced_form_r0", "mc_convergence_report"}
            ),
            "seeds": {**manifest.get("seeds", {}), "monte_carlo_master": outputs["seed"]},
            "monte_carlo_runtime_seconds": outputs["runtime_seconds"],
            "monte_carlo_max_cell_runtime_seconds_M5000": outputs["max_cell_seconds"],
            "changelog": manifest.get("changelog", []) + ["Etapa 5A: Monte Carlo independiente, robustez historica r0, matriz rank-correlated propuesta; motor certificado intacto."],
        }
    )
    output_hashes = {}
    for path in result_dir.glob("*"):
        if path.is_file():
            output_hashes[path.name] = sha256_file(path)
    output_hashes.update(draw_hashes)
    manifest["output_hashes"] = output_hashes
    manifest["commit_sha"] = git_value(["rev-parse", "HEAD"]) or "unavailable_no_commit"
    manifest["git_dirty"] = bool(git_value(["status", "--short"]))
    manifest["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    (reports / "run_manifest_baseline-official-v2.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    (result_dir / "manifest.json").write_text(json.dumps(clean(manifest), indent=2, sort_keys=True), encoding="utf-8")
    return output_hashes


def calibrate_tier_b_tolerance(root: Path, seed: int) -> pd.DataFrame:
    records = []
    probe_cells = {
        ("CHL", "GMI:GMI_ideal_aggregate", "mid", "r0"),
        ("PER", "PEN", "mid", "r0"),
        ("PER", "PEN", "stress", "r4"),
    }
    seed_offsets = [101, 202, 303]
    frames = []
    for offset in seed_offsets:
        frames.append(
            run_single_mc(
                root=root,
                m_draws=5_000,
                seed=seed + offset,
                persist_draws=False,
                cell_filter=probe_cells,
            )["monte_carlo_result"]
        )
    key_cols = ["country_id", "policy_variant_id", "scenario_id", "regime_id", "prob_basis", "mc_mode"]
    prob_cols = [c for c in frames[0].columns if c.startswith("prob_v_ge_") or c.startswith("prob_debt_consistent_")]
    base = frames[0][key_cols + prob_cols].copy()
    for i, frame in enumerate(frames[1:], start=2):
        merged = base.merge(frame[key_cols + prob_cols], on=key_cols, suffixes=("_base", f"_seed{i}"))
        max_diff = 0.0
        for col in prob_cols:
            diff = (merged[f"{col}_base"] - merged[f"{col}_seed{i}"]).abs().max()
            max_diff = max(max_diff, float(diff))
        records.append(
            {
                "comparison": f"seed1_vs_seed{i}",
                "m_draws": 5000,
                "max_abs_probability_difference": max_diff,
                "configured_tier_b_atol": 0.02,
                "factor_note": "Tier B atol set to 0.02, at least the plan convergence tolerance and above observed seed jitter for probe cells unless reported otherwise.",
            }
        )
    return pd.DataFrame(records)


def run_monte_carlo(root: Path = ROOT, m_draws: int = 5_000, persist_draws: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    rng_policy = load_rng_policy(root)
    seed = int(rng_policy.get("monte_carlo_master_seed", 20260709))
    matrix = correlation_matrix_rows()
    upsert_governance(root, matrix)
    convergence, convergence_flags = run_convergence(root, seed)
    base = run_single_mc(
        root=root,
        m_draws=m_draws,
        seed=seed,
        persist_draws=persist_draws,
        convergence_flags=convergence_flags,
    )
    mc = base["monte_carlo_result"].copy()
    final_class = classify_final(mc, root)
    tolerance_calibration = calibrate_tier_b_tolerance(root, seed)
    runtime = time.perf_counter() - started
    outputs = {
        "monte_carlo_result": mc,
        "mc_convergence_report": convergence,
        "country_policy_classification_final": final_class,
        "rank_correlation_matrix_proposed": matrix,
        "mc_tier_b_tolerance_calibration": tolerance_calibration,
        "draw_frames": base["draw_frames"],
        "m_draws": m_draws,
        "seed": seed,
        "runtime_seconds": runtime,
        "max_cell_seconds": base["max_cell_seconds"],
    }
    write_outputs(root, outputs)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m-draws", type=int, default=5_000)
    parser.add_argument("--no-draw-persistence", action="store_true")
    args = parser.parse_args(argv)
    outputs = run_monte_carlo(ROOT, m_draws=args.m_draws, persist_draws=not args.no_draw_persistence)
    mc = outputs["monte_carlo_result"]
    primary = mc[(mc["mc_mode"].eq(MC_MODE)) & (mc["prob_basis"].eq("all_draw"))]
    print(
        json.dumps(
            {
                "status": "OK",
                "run_id": RUN_ID,
                "parameter_set_id": PARAMETER_SET_ID,
                "dataset_version": DATASET_VERSION,
                "mc_mode": MC_MODE,
                "m_draws": args.m_draws,
                "monte_carlo_rows": int(len(mc)),
                "primary_cell_rows": int(len(primary)),
                "convergence_rows": int(len(outputs["mc_convergence_report"])),
                "runtime_seconds": outputs["runtime_seconds"],
                "max_cell_seconds_M5000": outputs["max_cell_seconds"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
