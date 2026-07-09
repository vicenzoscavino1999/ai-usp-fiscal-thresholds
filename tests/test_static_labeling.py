from ai_usp.classify import classify_cell


def test_cell_classification_precedence():
    assert (
        classify_cell(
            existence_condition_pass=False,
            v_gross=2.0,
            crosses_v1=True,
            debt_guardrail_pass=True,
            stress_r4_only_crossing=False,
        )
        == "impossible_or_noncomputable"
    )
    assert (
        classify_cell(
            existence_condition_pass=True,
            v_gross=0.9,
            crosses_v1=False,
            debt_guardrail_pass=True,
            stress_r4_only_crossing=False,
        )
        == "not_feasible"
    )
    assert (
        classify_cell(
            existence_condition_pass=True,
            v_gross=1.1,
            crosses_v1=True,
            debt_guardrail_pass=False,
            stress_r4_only_crossing=True,
        )
        == "accounting_feasible_debt_failed"
    )
