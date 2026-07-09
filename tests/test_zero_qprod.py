from ai_usp.thresholds import invert_threshold
from ai_usp.translation import s_ndc_score


def test_zero_qprod_zeroes_translation_and_blocks_q_side_inversion():
    assert s_ndc_score(0.2, 0.0, 1.0, 1.0, 1e-9) == 0.0
    result = invert_threshold(
        requirement_basis="baseline",
        xi=0.0,
        cost_gross_gdp=0.001,
        fixed_cost_gdp=0.0,
        spb_plus_gdp=0.0,
        mfc_tilde_gross=0.5,
        mfc_gross=0.5,
        mfc_base_without_ai_rent=0.5,
        g_ai_level=0.01,
        phi_y_nom=0.5,
        horizon_years=10,
        s_frontier=0.01,
        exposure_productive=0.1,
        q_prod=0.0,
        q_prod_t0=0.0,
        q_bar=0.8,
        lambda_q=0.3,
        lambda_ai=0.0,
        tau_ai_cap=1.0,
        beta=1.0,
        gamma=1.0,
        epsilon=1e-9,
    )
    assert "adoption_zero_impossible" in result.flags
