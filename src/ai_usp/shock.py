"""AI shock conversion rules.

The deterministic engine never lets ``phi_raw`` enter fiscal equations.  Raw
scenario shocks must first be bridged to real GDP-equivalent terms and then to
nominal GDP-equivalent terms.
"""

from __future__ import annotations

from dataclasses import dataclass


class RawShockFiscalUseError(ValueError):
    """Raised when a fiscal equation attempts to consume ``phi_raw`` directly."""


@dataclass(frozen=True)
class ShockConversion:
    scenario_id: str
    phi_raw: float
    kappa_to_y: float
    pi_ai_y: float
    phi_y_real: float
    phi_y_nom: float


def convert_phi_raw(
    scenario_id: str,
    phi_raw: float,
    kappa_to_y: float,
    pi_ai_y: float = 0.0,
) -> ShockConversion:
    """Convert a raw AI productivity shock to nominal GDP-equivalent terms."""

    phi_y_real = phi_raw * kappa_to_y
    phi_y_nom = (1.0 + phi_y_real) * (1.0 + pi_ai_y) - 1.0
    return ShockConversion(
        scenario_id=scenario_id,
        phi_raw=float(phi_raw),
        kappa_to_y=float(kappa_to_y),
        pi_ai_y=float(pi_ai_y),
        phi_y_real=float(phi_y_real),
        phi_y_nom=float(phi_y_nom),
    )


def assert_no_phi_raw_direct_use(uses_phi_raw_directly: bool, context: str = "") -> None:
    """Hard gate for the plan 02 rule forbidding direct fiscal use of phi_raw."""

    if uses_phi_raw_directly:
        suffix = f" in {context}" if context else ""
        raise RawShockFiscalUseError(
            f"phi_raw cannot enter fiscal equations directly{suffix}; use phi_Y_nom."
        )
