"""Policy endpoint-cost scaling rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixedPolicyCosts:
    ac_net_fix: float
    tr_ann: float
    leak_fix: float
    f_fix: float


def endpoint_cost_scale(
    cost_2024_gdp: float,
    eligible_share_2024: float,
    eligible_share_endpoint: float,
    fixed_policy: bool = False,
) -> float:
    """Plan 02 endpoint scaling: c_2034 = c_2024 * elig_share ratio."""

    if fixed_policy:
        return float(cost_2024_gdp)
    if eligible_share_2024 <= 0.0:
        raise ValueError("eligible_share_2024 must be positive.")
    return float(cost_2024_gdp) * (eligible_share_endpoint / eligible_share_2024)


def annuitize_oneoff(amount_gdp: float, discount_rate: float, horizon_years: int) -> float:
    if horizon_years <= 0:
        raise ValueError("transition horizon must be positive.")
    if amount_gdp == 0.0:
        return 0.0
    if discount_rate == 0.0:
        return amount_gdp / horizon_years
    r = discount_rate
    return amount_gdp * r / (1.0 - (1.0 + r) ** (-horizon_years))


def fixed_policy_costs(
    *,
    admin_cost_new_gdp: float,
    admin_savings_existing_gdp: float,
    transition_oneoff_gdp: float,
    transition_recurring_gdp: float,
    transition_horizon_years: int,
    transition_discount_rate: float,
    leakage_fixed_gdp: float,
    leakage_multiplier: float = 1.0,
) -> FixedPolicyCosts:
    ac_net_fix = admin_cost_new_gdp - admin_savings_existing_gdp
    tr_ann = transition_recurring_gdp + annuitize_oneoff(
        transition_oneoff_gdp,
        transition_discount_rate,
        transition_horizon_years,
    )
    leak_fix = leakage_fixed_gdp * leakage_multiplier
    return FixedPolicyCosts(
        ac_net_fix=ac_net_fix,
        tr_ann=tr_ann,
        leak_fix=leak_fix,
        f_fix=ac_net_fix + tr_ann + leak_fix,
    )
