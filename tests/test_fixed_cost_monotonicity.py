from ai_usp.policy_cost import fixed_policy_costs


def test_fixed_costs_are_monotone_in_admin_cost():
    low = fixed_policy_costs(
        admin_cost_new_gdp=0.001,
        admin_savings_existing_gdp=0.0,
        transition_oneoff_gdp=0.0,
        transition_recurring_gdp=0.0,
        transition_horizon_years=2,
        transition_discount_rate=0.03,
        leakage_fixed_gdp=0.0,
    )
    high = fixed_policy_costs(
        admin_cost_new_gdp=0.002,
        admin_savings_existing_gdp=0.0,
        transition_oneoff_gdp=0.0,
        transition_recurring_gdp=0.0,
        transition_horizon_years=2,
        transition_discount_rate=0.03,
        leakage_fixed_gdp=0.0,
    )
    assert high.f_fix > low.f_fix
