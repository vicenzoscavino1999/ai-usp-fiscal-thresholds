from ai_usp.fiscal_channels import RegimeSettings, compute_mfc
from ai_usp.labor_share import LaborCapitalWeights


def test_erosion_companion_reduces_mfc_for_reform_regime():
    weights = LaborCapitalWeights(0.5, 0.5, 0.5, 0.5, 0.5, 0.2, 0.5, 0.5, 0.2)
    regime = RegimeSettings("r1", 0.0, 0.0, 0.0, 0.1, 0.0, 1.0, 0.5, 0.5, 0.5, 0.5)
    result = compute_mfc(
        weights=weights,
        regime=regime,
        tau_l_eff=0.2,
        tau_k_eff=0.2,
        tau_c_eff=0.2,
        lambda_ai=0.1,
        lambda_ai_kbase=0.0,
        use_erosion_companion=True,
    )
    assert result.erosion_companion_applied
    assert result.mfc_gross < result.mfc_gross_mechanical
