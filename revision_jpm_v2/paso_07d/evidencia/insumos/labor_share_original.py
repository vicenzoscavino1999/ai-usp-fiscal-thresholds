"""Labor-share and capital-base transition equations."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LaborCapitalWeights:
    labor_share_prime: float
    delta_w_gdp0: float
    delta_nls_gdp0: float
    delta_capital_base_gdp0: float
    delta_capital_domestic_gdp0: float
    delta_consumption_taxable_gdp0: float
    omega_l: float
    omega_k: float
    omega_c: float


def _logit(x: float) -> float:
    x = min(max(x, 1e-12), 1.0 - 1e-12)
    return math.log(x / (1.0 - x))


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def compute_labor_capital_weights(
    *,
    labor_share: float,
    g_ai_level: float,
    q_prod: float,
    e_auto: float,
    e_aug: float,
    delta_s: float,
    psi_s: float,
    zeta_s: float,
    rst: float,
    lambda_ls: float,
    chi_kbase: float,
    chi_dom: float,
    psi_shift: float,
    tau_l_disp: float,
    tau_k_disp: float,
    tau_r_disp: float,
    mpc_w: float,
    mpc_pi: float,
    mpc_r: float,
    m_m: float,
    theta_r_dom: float,
    exempt_c: float,
) -> LaborCapitalWeights:
    """Compute endpoint weights using endpoint numerator and denominator."""

    if g_ai_level <= 0.0:
        return LaborCapitalWeights(
            labor_share_prime=labor_share,
            delta_w_gdp0=0.0,
            delta_nls_gdp0=0.0,
            delta_capital_base_gdp0=0.0,
            delta_capital_domestic_gdp0=0.0,
            delta_consumption_taxable_gdp0=0.0,
            omega_l=0.0,
            omega_k=0.0,
            omega_c=0.0,
        )

    pressure = (-(delta_s - zeta_s * rst) * e_auto + psi_s * e_aug) * q_prod
    labor_share_prime = _logistic(_logit(labor_share) + lambda_ls * pressure)
    delta_w_gdp0 = labor_share_prime * (1.0 + g_ai_level) - labor_share
    delta_nls_gdp0 = g_ai_level - delta_w_gdp0
    delta_capital_base_gdp0 = chi_kbase * delta_nls_gdp0
    delta_capital_domestic_gdp0 = chi_dom * (1.0 - psi_shift) * delta_capital_base_gdp0

    delta_residual_gdp0 = max(0.0, delta_nls_gdp0 - delta_capital_base_gdp0)
    delta_w_disp = (1.0 - tau_l_disp) * delta_w_gdp0
    delta_pi_disp = (1.0 - tau_k_disp) * delta_capital_domestic_gdp0
    delta_r_disp = theta_r_dom * (1.0 - tau_r_disp) * delta_residual_gdp0
    consumption_base = (
        mpc_w * delta_w_disp + mpc_pi * delta_pi_disp + mpc_r * delta_r_disp
    )
    delta_consumption_taxable_gdp0 = (
        (1.0 - exempt_c) * (1.0 - m_m) * max(0.0, consumption_base)
    )

    return LaborCapitalWeights(
        labor_share_prime=labor_share_prime,
        delta_w_gdp0=delta_w_gdp0,
        delta_nls_gdp0=delta_nls_gdp0,
        delta_capital_base_gdp0=delta_capital_base_gdp0,
        delta_capital_domestic_gdp0=delta_capital_domestic_gdp0,
        delta_consumption_taxable_gdp0=delta_consumption_taxable_gdp0,
        omega_l=delta_w_gdp0 / g_ai_level,
        omega_k=delta_capital_domestic_gdp0 / g_ai_level,
        omega_c=delta_consumption_taxable_gdp0 / g_ai_level,
    )
