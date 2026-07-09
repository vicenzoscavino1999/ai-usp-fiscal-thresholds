"""Threshold inversion and buffer/debt guardrail logic."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .translation import tilde


XI_GRID = (0.0, 0.05, 0.10, 0.25, 0.50)


@dataclass(frozen=True)
class ThresholdResult:
    requirement_basis: str
    xi: float
    required_revenue_gdp: float
    g_ai_required: float | None
    mfc_required_gross: float | None
    t_required_h: float | None
    tau_ai_required: float | None
    q_prod_required: float | None
    q_use_required: float | None
    aipi_required: float | None
    exposure_required: float | None
    existence_condition_pass: bool
    impossibility_reason: str | None
    floor_driven_flag: bool
    epsilon_used: float
    flags: tuple[str, ...]


def debt_guardrail_pass(
    *,
    fs_eff: float,
    cost_gross_gdp: float,
    xi: float,
    spb_plus_gdp: float,
) -> bool:
    return fs_eff >= (1.0 + xi) * cost_gross_gdp + spb_plus_gdp


def invert_threshold(
    *,
    requirement_basis: str,
    xi: float,
    cost_gross_gdp: float,
    fixed_cost_gdp: float,
    spb_plus_gdp: float,
    mfc_tilde_gross: float,
    mfc_gross: float,
    mfc_base_without_ai_rent: float,
    g_ai_level: float,
    phi_y_nom: float,
    horizon_years: int,
    s_frontier: float,
    exposure_productive: float,
    q_prod: float,
    q_prod_t0: float,
    q_bar: float,
    lambda_q: float,
    lambda_ai: float,
    tau_ai_cap: float,
    beta: float,
    gamma: float,
    epsilon: float,
    currently_covers_buffer: bool = False,
    me_addback: float = 0.0,
) -> ThresholdResult:
    """Closed-form inversions from plan 02 section 7.7."""

    flags: list[str] = []
    if currently_covers_buffer:
        flags.append("requirement_already_covered")

    required_revenue = (1.0 + xi) * cost_gross_gdp + fixed_cost_gdp
    if requirement_basis in {"debt_guardrail", "debt_consistent"}:
        required_revenue += spb_plus_gdp
    elif requirement_basis != "baseline":
        raise ValueError(f"Unknown requirement_basis: {requirement_basis}")

    g_required: float | None = None
    mfc_required: float | None = None
    t_required_h: float | None = None
    q_required: float | None = None
    q_use_required: float | None = None
    exposure_required: float | None = None
    tau_ai_required: float | None = None
    floor_driven = False

    if mfc_tilde_gross <= 0.0:
        flags.append("noncomputable_mfc_zero_or_negative")
    else:
        g_required = required_revenue / mfc_tilde_gross
        if phi_y_nom <= 0.0:
            flags.append("noncomputable_phi_zero_or_negative")
        else:
            t_required_h = ((1.0 + g_required) ** (1.0 / horizon_years) - 1.0) / phi_y_nom
            if t_required_h > 1.0:
                flags.append("frontier_exceeds_one")

    if g_ai_level <= 0.0:
        flags.append("noncomputable_g_ai_zero_or_negative")
    else:
        mfc_required = required_revenue / g_ai_level + me_addback

    if t_required_h is not None and t_required_h <= 1.0:
        s_required = t_required_h * s_frontier
        if exposure_productive <= 0.0:
            flags.append("exposure_zero_impossible")
        else:
            tilde_e = tilde(exposure_productive, epsilon)
            tilde_q_req = (s_required / (tilde_e**beta)) ** (1.0 / gamma)
            q_required = max(0.0, (tilde_q_req - epsilon) / (1.0 - epsilon))
            floor_driven = q_required == 0.0 and s_required > 0.0
            if q_required > q_bar:
                flags.append("adoption_ceiling")
            if lambda_q <= 0.0:
                flags.append("use_undefined_lambda_q_zero")
            else:
                q_use_required = max(
                    0.0,
                    (q_required - (1.0 - lambda_q) * q_prod_t0) / lambda_q,
                )
                if q_use_required > q_bar:
                    flags.append("use_ceiling")

        if q_prod <= 0.0:
            flags.append("adoption_zero_impossible")
        else:
            tilde_q = tilde(q_prod, epsilon)
            tilde_e_req = (s_required / (tilde_q**gamma)) ** (1.0 / beta)
            exposure_required = max(0.0, (tilde_e_req - epsilon) / (1.0 - epsilon))
            if exposure_required > 1.0:
                flags.append("exposure_ceiling_impossible")

    if g_ai_level > 0.0:
        if lambda_ai <= 0.0:
            if required_revenue / g_ai_level > mfc_base_without_ai_rent:
                flags.append("ai_rent_capture_impossible")
        else:
            tau_ai_required = max(
                0.0,
                (required_revenue / g_ai_level - mfc_base_without_ai_rent) / lambda_ai,
            )
            if tau_ai_required > tau_ai_cap:
                flags.append("ai_rent_capture_impossible")

    hard_prefixes = (
        "noncomputable",
        "frontier_exceeds_one",
        "adoption_ceiling",
        "use_ceiling",
        "exposure_ceiling_impossible",
        "exposure_zero_impossible",
        "adoption_zero_impossible",
        "ai_rent_capture_impossible",
    )
    hard_flags = [flag for flag in flags if flag.startswith(hard_prefixes)]
    existence_pass = len(hard_flags) == 0
    reason = ";".join(flags) if flags else None

    return ThresholdResult(
        requirement_basis=requirement_basis,
        xi=float(xi),
        required_revenue_gdp=required_revenue,
        g_ai_required=g_required,
        mfc_required_gross=mfc_required,
        t_required_h=t_required_h,
        tau_ai_required=tau_ai_required,
        q_prod_required=q_required,
        q_use_required=q_use_required,
        aipi_required=None,
        exposure_required=exposure_required,
        existence_condition_pass=existence_pass,
        impossibility_reason=reason,
        floor_driven_flag=floor_driven,
        epsilon_used=epsilon,
        flags=tuple(flags),
    )
