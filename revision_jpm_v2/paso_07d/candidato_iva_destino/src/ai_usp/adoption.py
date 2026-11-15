"""Anchored AI adoption rules."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AdoptionState:
    q_bar: float
    q_use_target: float
    q_use_target_adj: float
    mu_t0: float
    q_prod_t0: float
    q_prod: float


def adoption_ceiling(informality: float, gap: float, omega_i: float, omega_g: float) -> float:
    """Plan 02 ceiling: q_bar = 1 - omega_I I - omega_G Gap."""

    return max(0.0, min(1.0, 1.0 - omega_i * informality - omega_g * gap))


def project_target_to_support(q_target: float, q_bar: float, epsilon_mu: float) -> float:
    """Project q_use_target to the interior of [0, q_bar]."""

    if q_bar <= 2.0 * epsilon_mu:
        raise ValueError("q_bar too small to host an interior q_use_target_adj.")
    return min(max(q_target, epsilon_mu), q_bar - epsilon_mu)


def invert_mu_logit(
    q_use_target_adj: float,
    q_bar: float,
    aipi: float,
    informality: float,
    gap: float,
    nu_a: float,
    nu_i: float,
    nu_g: float,
) -> float:
    """Derive the adoption intercept by logit inversion; mu is not free."""

    if q_use_target_adj <= 0.0 or q_use_target_adj >= q_bar:
        raise ValueError("q_use_target_adj must be inside (0, q_bar).")
    logit_term = math.log(q_use_target_adj / (q_bar - q_use_target_adj))
    return logit_term - nu_a * aipi + nu_i * informality + nu_g * gap


def build_adoption_state(
    *,
    q_use_target: float,
    aipi: float,
    informality: float,
    gap: float,
    omega_i: float,
    omega_g: float,
    nu_a: float,
    nu_i: float,
    nu_g: float,
    epsilon_mu: float,
    frozen: bool = True,
) -> AdoptionState:
    """Build the frozen-anchor adoption state used by the baseline pilot."""

    q_bar = adoption_ceiling(informality, gap, omega_i, omega_g)
    q_use_target_adj = project_target_to_support(q_use_target, q_bar, epsilon_mu)
    mu_t0 = invert_mu_logit(
        q_use_target_adj=q_use_target_adj,
        q_bar=q_bar,
        aipi=aipi,
        informality=informality,
        gap=gap,
        nu_a=nu_a,
        nu_i=nu_i,
        nu_g=nu_g,
    )
    q_prod_t0 = q_use_target_adj
    q_prod = q_prod_t0 if frozen else q_prod_t0
    return AdoptionState(
        q_bar=q_bar,
        q_use_target=float(q_use_target),
        q_use_target_adj=q_use_target_adj,
        mu_t0=mu_t0,
        q_prod_t0=q_prod_t0,
        q_prod=q_prod,
    )
