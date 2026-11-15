"""Deterministic cell and preliminary country-policy classification."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, MutableMapping


def classify_cell(
    *,
    existence_condition_pass: bool,
    v_gross: float,
    crosses_v1: bool,
    debt_guardrail_pass: bool,
    stress_r4_only_crossing: bool,
) -> str:
    """Section 18.1 axis 1 with deterministic precedence."""

    if not existence_condition_pass:
        return "impossible_or_noncomputable"
    if v_gross < 1.0:
        return "not_feasible"
    if crosses_v1 and not debt_guardrail_pass:
        return "accounting_feasible_debt_failed"
    if stress_r4_only_crossing:
        return "extreme_conditional_crossing"
    return "feasible_cell"


def mark_stress_r4_only(rows: list[MutableMapping[str, object]]) -> None:
    """Flag cells whose country-policy crosses only in stress+r4."""

    grouped: dict[tuple[object, object], list[MutableMapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(row["country_id"], row["policy_id"])].append(row)
    for group_rows in grouped.values():
        crossing = [row for row in group_rows if bool(row.get("crosses_v1"))]
        only_stress_r4 = bool(crossing) and all(
            row["scenario_id"] == "stress" and row["regime_id"] == "r4" for row in crossing
        )
        for row in group_rows:
            row["stress_r4_only_crossing"] = (
                only_stress_r4
                and row["scenario_id"] == "stress"
                and row["regime_id"] == "r4"
                and bool(row.get("crosses_v1"))
            )


def classify_country_policy_preliminary(rows: Iterable[MutableMapping[str, object]]) -> dict[tuple[str, str], str]:
    """Section 18.2 deterministic preliminary label; MC leg is not evaluated."""

    grouped: dict[tuple[str, str], list[MutableMapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["country_id"]), str(row["policy_id"]))].append(row)

    result: dict[tuple[str, str], str] = {}
    for key, group_rows in grouped.items():
        _, policy_id = key
        crossings = [row for row in group_rows if bool(row.get("crosses_buffer"))]
        if policy_id == "UBI":
            result[key] = "stress_benchmark_only"
        elif not crossings:
            result[key] = "not_feasible"
        elif any(not bool(row.get("debt_guardrail_pass")) for row in crossings):
            result[key] = "fragile_feasibility"
        elif any(
            row.get("historical_plausibility_class")
            == "extreme_or_outside_historical_support"
            for row in crossings
        ):
            result[key] = "fragile_feasibility"
        else:
            result[key] = "conditional_feasibility_probabilistic_leg_not_evaluated"
    return result
