from ai_usp.thresholds import invert_threshold


def test_zero_phi_blocks_t_inversion():
    result = invert_threshold(
        requirement_basis="baseline",
        xi=0.0,
        cost_gross_gdp=0.01,
        fixed_cost_gdp=0.0,
        spb_plus_gdp=0.0,
        mfc_tilde_gross=0.2,
        mfc_gross=0.2,
        mfc_base_without_ai_rent=0.2,
        g_ai_level=0.01,
        phi_y_nom=0.0,
        horizon_years=10,
        s_frontier=1.0,
        exposure_productive=0.1,
        q_prod=0.1,
        q_prod_t0=0.1,
        q_bar=0.8,
        lambda_q=0.3,
        lambda_ai=0.0,
        tau_ai_cap=1.0,
        beta=1.0,
        gamma=1.0,
        epsilon=1e-9,
    )
    assert "noncomputable_phi_zero_or_negative" in result.flags
