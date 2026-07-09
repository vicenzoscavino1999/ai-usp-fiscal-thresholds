from ai_usp.thresholds import invert_threshold


def test_me_addback_round_trip_and_nonpositive_tilde_guard():
    mfc_gross = 0.20
    ac_me = 0.02
    tr_me = 0.01
    leak_me = 0.02
    me = ac_me + tr_me + leak_me
    mfc_tilde = mfc_gross - me
    g_ai_level = 0.10
    r_req = 0.03

    result = invert_threshold(
        requirement_basis="baseline",
        xi=0.0,
        cost_gross_gdp=r_req,
        fixed_cost_gdp=0.0,
        spb_plus_gdp=0.0,
        mfc_tilde_gross=mfc_tilde,
        mfc_gross=mfc_gross,
        mfc_base_without_ai_rent=mfc_gross,
        g_ai_level=g_ai_level,
        phi_y_nom=1.0,
        horizon_years=10,
        s_frontier=1.0,
        exposure_productive=0.5,
        q_prod=0.5,
        q_prod_t0=0.5,
        q_bar=1.0,
        lambda_q=0.3,
        lambda_ai=0.0,
        tau_ai_cap=1.0,
        beta=1.0,
        gamma=1.0,
        epsilon=1e-9,
        me_addback=me,
    )

    assert result.mfc_required_gross == r_req / g_ai_level + me
    assert ((result.mfc_required_gross - me) * g_ai_level) == r_req

    dangerous = invert_threshold(
        requirement_basis="baseline",
        xi=0.0,
        cost_gross_gdp=0.01,
        fixed_cost_gdp=0.0,
        spb_plus_gdp=0.0,
        mfc_tilde_gross=-0.01,
        mfc_gross=0.05,
        mfc_base_without_ai_rent=0.05,
        g_ai_level=0.10,
        phi_y_nom=1.0,
        horizon_years=10,
        s_frontier=1.0,
        exposure_productive=0.5,
        q_prod=0.5,
        q_prod_t0=0.5,
        q_bar=1.0,
        lambda_q=0.3,
        lambda_ai=0.0,
        tau_ai_cap=1.0,
        beta=1.0,
        gamma=1.0,
        epsilon=1e-9,
        me_addback=0.06,
    )

    assert not dangerous.existence_condition_pass
    assert "noncomputable_mfc_zero_or_negative" in dangerous.flags
