import pytest

from ai_usp.audit import AuditFailure, run_hard_gates


def test_mfc_mode_mixing_is_hard_fail():
    with pytest.raises(AuditFailure):
        run_hard_gates(
            uses_phi_raw_directly=False,
            mfc_mode_mixing=True,
            double_counting_failures=[],
            parameter_set_id="baseline-pilot-v2",
        )
