"""Fiscal-space arithmetic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FiscalSpace:
    fs_gross: float
    fs_eff: float
    v_gross: float
    v_net: float


def compute_fiscal_space(
    *,
    mfc_gross: float,
    mfc_tilde_gross: float,
    g_ai_level: float,
    ac_net_fix: float,
    tr_ann: float,
    leak_fix: float,
    cost_gross_gdp: float,
    cost_net_gdp: float,
) -> FiscalSpace:
    fs_gross = mfc_gross * g_ai_level
    fs_eff = mfc_tilde_gross * g_ai_level - ac_net_fix - tr_ann - leak_fix
    v_gross = fs_eff / cost_gross_gdp if cost_gross_gdp > 0.0 else float("nan")
    v_net = fs_eff / cost_net_gdp if cost_net_gdp > 0.0 else float("nan")
    return FiscalSpace(fs_gross=fs_gross, fs_eff=fs_eff, v_gross=v_gross, v_net=v_net)
