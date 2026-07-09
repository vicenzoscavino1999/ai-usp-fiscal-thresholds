from ai_usp.policy_cost import endpoint_cost_scale


def test_demographic_endpoint_cost_is_monotone_in_eligible_share():
    base = endpoint_cost_scale(0.1, 0.2, 0.2)
    larger = endpoint_cost_scale(0.1, 0.2, 0.3)
    assert larger > base
