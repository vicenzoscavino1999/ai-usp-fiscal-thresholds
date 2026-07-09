from reproducibility.verify import verify_reference


def test_official_reference_verifies_current_outputs():
    result = verify_reference()
    assert result.passed, result.messages
