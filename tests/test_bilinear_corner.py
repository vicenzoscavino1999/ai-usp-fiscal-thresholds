from ai_usp.translation import s_ndc_score


def test_bilinear_corner_is_zero_before_epsilon_smoothing():
    assert s_ndc_score(0.0, 0.5, 1.0, 1.0, 1e-9) == 0.0
    assert s_ndc_score(0.5, 0.0, 1.0, 1.0, 1e-9) == 0.0
    assert s_ndc_score(0.5, 0.5, 1.0, 1.0, 1e-9) > 0.0
