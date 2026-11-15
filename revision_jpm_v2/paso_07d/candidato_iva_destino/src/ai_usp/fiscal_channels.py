"""Fiscal-channel capture equations."""

from __future__ import annotations

from dataclasses import dataclass

from .labor_share import LaborCapitalWeights


@dataclass(frozen=True)
class RegimeSettings:
    regime_code: str
    tau_l_delta: float
    tau_k_delta: float
    tau_c_delta: float
    tau_ai_eff: float
    base_broadening_delta: float
    leakage_multiplier: float
    epsilon_ero_l: float
    epsilon_ero_k: float
    epsilon_ero_c: float
    epsilon_ero_ai: float


@dataclass(frozen=True)
class FiscalChannelResult:
    tau_l: float
    tau_k: float
    tau_c: float
    tau_ai: float
    omega_l: float
    omega_k: float
    omega_k_net: float
    omega_c: float
    mfc_gross_mechanical: float
    mfc_gross: float
    mfc_tilde_gross: float
    ac_me: float
    tr_me: float
    leak_me: float
    erosion_companion_applied: bool


def _rate(base: float, relative_delta: float) -> float:
    return min(1.0, max(0.0, base * (1.0 + relative_delta)))


def apply_base_broadening_to_structure(
    psi_shift: float,
    exempt_c: float,
    base_broadening_delta: float,
) -> tuple[float, float]:
    """Base-side broadening changes bases, not tax rates."""

    delta = min(max(base_broadening_delta, 0.0), 1.0)
    return max(0.0, psi_shift * (1.0 - delta)), max(0.0, exempt_c * (1.0 - delta))


def compute_mfc(
    *,
    weights: LaborCapitalWeights,
    regime: RegimeSettings,
    tau_l_eff: float,
    tau_k_eff: float,
    tau_c_eff: float,
    lambda_ai: float,
    lambda_ai_kbase: float,
    ac_me: float = 0.0,
    tr_me: float = 0.0,
    leak_me: float = 0.0,
    use_erosion_companion: bool = True,
) -> FiscalChannelResult:
    """Compute gross and margin-net fiscal capture for a scenario-regime cell."""

    tau_l = _rate(tau_l_eff, regime.tau_l_delta)
    tau_k = _rate(tau_k_eff, regime.tau_k_delta)
    tau_c = _rate(tau_c_eff, regime.tau_c_delta)
    tau_ai = min(1.0, max(0.0, regime.tau_ai_eff))
    omega_k_net = weights.omega_k - lambda_ai_kbase

    mfc_mechanical = (
        weights.omega_l * tau_l
        + omega_k_net * tau_k
        + weights.omega_c * tau_c
        + lambda_ai * tau_ai
    )

    erosion_applied = use_erosion_companion and regime.regime_code != "r0"
    if erosion_applied:
        mfc_gross = (
            weights.omega_l * max(0.0, 1.0 - regime.epsilon_ero_l * tau_l) * tau_l
            + omega_k_net * max(0.0, 1.0 - regime.epsilon_ero_k * tau_k) * tau_k
            + weights.omega_c * max(0.0, 1.0 - regime.epsilon_ero_c * tau_c) * tau_c
            + lambda_ai * max(0.0, 1.0 - regime.epsilon_ero_ai * tau_ai) * tau_ai
        )
    else:
        mfc_gross = mfc_mechanical

    return FiscalChannelResult(
        tau_l=tau_l,
        tau_k=tau_k,
        tau_c=tau_c,
        tau_ai=tau_ai,
        omega_l=weights.omega_l,
        omega_k=weights.omega_k,
        omega_k_net=omega_k_net,
        omega_c=weights.omega_c,
        mfc_gross_mechanical=mfc_mechanical,
        mfc_gross=mfc_gross,
        mfc_tilde_gross=mfc_gross - ac_me - tr_me - leak_me,
        ac_me=ac_me,
        tr_me=tr_me,
        leak_me=leak_me,
        erosion_companion_applied=erosion_applied,
    )
