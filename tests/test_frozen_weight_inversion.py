from ai_usp.adoption import build_adoption_state
from ai_usp.thresholds import invert_threshold


def test_frozen_qprod_anchor_and_use_inversion():
    state = build_adoption_state(
        q_use_target=0.1,
        aipi=0.5,
        informality=0.2,
        gap=0.0,
        omega_i=0.5,
        omega_g=0.5,
        nu_a=1.0,
        nu_i=0.5,
        nu_g=0.5,
        epsilon_mu=1e-6,
    )
    assert state.q_prod == state.q_prod_t0 == state.q_use_target_adj
    result = invert_threshold(
        requirement_basis="baseline",
        xi=0.0,
        cost_gross_gdp=0.001,
        fixed_cost_gdp=0.0,
        spb_plus_gdp=0.0,
        mfc_tilde_gross=1.0,
        mfc_gross=1.0,
        mfc_base_without_ai_rent=1.0,
        g_ai_level=0.1,
        phi_y_nom=0.5,
        horizon_years=10,
        s_frontier=0.1,
        exposure_productive=0.5,
        q_prod=state.q_prod,
        q_prod_t0=state.q_prod_t0,
        q_bar=state.q_bar,
        lambda_q=0.3,
        lambda_ai=0.0,
        tau_ai_cap=1.0,
        beta=1.0,
        gamma=1.0,
        epsilon=1e-9,
    )
    assert result.q_use_required is not None
