from ai_usp.thresholds import debt_guardrail_pass


def test_debt_guardrail_uses_positive_primary_balance_gap():
    assert debt_guardrail_pass(fs_eff=0.03, cost_gross_gdp=0.02, xi=0.10, spb_plus_gdp=0.005)
    assert not debt_guardrail_pass(fs_eff=0.025, cost_gross_gdp=0.02, xi=0.10, spb_plus_gdp=0.005)
