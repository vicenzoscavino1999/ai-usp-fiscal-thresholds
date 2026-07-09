from ai_usp.policy_cost import endpoint_cost_scale


def test_endpoint_scaling_uses_endpoint_ratio_not_y0_endpoint_level():
    assert endpoint_cost_scale(0.10, 0.25, 0.50) == 0.20
    assert endpoint_cost_scale(0.10, 0.25, 0.50, fixed_policy=True) == 0.10
