"""Pre-run and run-time hard gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .shock import assert_no_phi_raw_direct_use


class AuditFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditItem:
    gate_id: str
    status: str
    severity: str
    notes: str


def run_hard_gates(
    *,
    uses_phi_raw_directly: bool,
    mfc_mode_mixing: bool,
    double_counting_failures: Iterable[str],
    parameter_set_id: str,
    expected_parameter_set_id: str = "baseline-pilot-v2",
) -> list[AuditItem]:
    """Return hard-gate audit rows or raise before result export."""

    items: list[AuditItem] = []
    try:
        assert_no_phi_raw_direct_use(uses_phi_raw_directly, context="deterministic engine")
        items.append(AuditItem("phi_raw_direct_fiscal_use", "pass", "hard", "phi_raw blocked from fiscal equations."))
    except Exception as exc:  # pragma: no cover - raised below with full audit
        items.append(AuditItem("phi_raw_direct_fiscal_use", "fail", "hard", str(exc)))

    items.append(
        AuditItem(
            "mfc_mode_exclusion",
            "fail" if mfc_mode_mixing else "pass",
            "hard",
            "No rate-side/base-side mixing on the same margin." if not mfc_mode_mixing else "MFC mode mixing detected.",
        )
    )

    failures = list(double_counting_failures)
    items.append(
        AuditItem(
            "double_counting_audit",
            "fail" if failures else "pass",
            "hard",
            "; ".join(failures) if failures else "No hard double-counting failures in the pilot subset.",
        )
    )

    items.append(
        AuditItem(
            "parameter_set_lock",
            "pass" if parameter_set_id == expected_parameter_set_id else "fail",
            "hard",
            f"parameter_set_id={parameter_set_id}; expected {expected_parameter_set_id}.",
        )
    )

    failed = [item for item in items if item.severity == "hard" and item.status != "pass"]
    if failed:
        raise AuditFailure("; ".join(f"{item.gate_id}: {item.notes}" for item in failed))
    return items


def assert_no_result_without_audit(audit_items: Iterable[AuditItem]) -> None:
    items = list(audit_items)
    if not items or any(item.status != "pass" for item in items if item.severity == "hard"):
        raise AuditFailure("Results cannot be exported without passing hard audit gates.")
