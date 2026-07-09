"""Domestic translation from adoption/exposure to ten-year AI growth."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class TranslationResult:
    s_ndc: float
    s_frontier: float
    translation_factor: float
    g_ai_level: float
    frontier_exposure_fallback_used: bool


def tilde(value: float, epsilon: float) -> float:
    return epsilon + (1.0 - epsilon) * value


def s_ndc_score(
    exposure_productive: float,
    q_prod: float,
    beta: float,
    gamma: float,
    epsilon: float,
) -> float:
    """Bilinear/productive score with a zero corner before epsilon smoothing."""

    if exposure_productive <= 0.0 or q_prod <= 0.0:
        return 0.0
    return tilde(exposure_productive, epsilon) ** beta * tilde(q_prod, epsilon) ** gamma


def frontier_score(
    benchmark_rows: Iterable[Mapping[str, float]],
    beta: float,
    gamma: float,
    epsilon: float,
    missing_exposure_fallback: float = 1.0,
) -> tuple[float, bool]:
    """Mean benchmark score; missing exposure uses the declared fallback."""

    scores: list[float] = []
    fallback_used = False
    for row in benchmark_rows:
        q = float(row["adoption_proxy"])
        raw_e = row.get("exposure_productive")
        if raw_e is None or (isinstance(raw_e, float) and math.isnan(raw_e)):
            exposure = missing_exposure_fallback
            fallback_used = True
        else:
            exposure = float(raw_e)
        scores.append(s_ndc_score(exposure, q, beta, gamma, epsilon))
    if not scores:
        raise ValueError("Frontier benchmark set is empty.")
    return sum(scores) / len(scores), fallback_used


def translate_to_growth(
    *,
    exposure_productive: float,
    q_prod: float,
    phi_y_nom: float,
    beta: float,
    gamma: float,
    epsilon: float,
    horizon_years: int,
    benchmark_rows: Iterable[Mapping[str, float]],
    missing_frontier_exposure_fallback: float = 1.0,
) -> TranslationResult:
    """Compute S_NDC, frontier-normalized T, and endpoint AI GDP gain."""

    s_domestic = s_ndc_score(exposure_productive, q_prod, beta, gamma, epsilon)
    s_frontier, fallback_used = frontier_score(
        benchmark_rows,
        beta=beta,
        gamma=gamma,
        epsilon=epsilon,
        missing_exposure_fallback=missing_frontier_exposure_fallback,
    )
    translation_factor = 0.0 if s_frontier <= 0.0 else min(1.0, s_domestic / s_frontier)
    g_ai_level = (1.0 + phi_y_nom * translation_factor) ** horizon_years - 1.0
    return TranslationResult(
        s_ndc=s_domestic,
        s_frontier=s_frontier,
        translation_factor=translation_factor,
        g_ai_level=g_ai_level,
        frontier_exposure_fallback_used=fallback_used,
    )
