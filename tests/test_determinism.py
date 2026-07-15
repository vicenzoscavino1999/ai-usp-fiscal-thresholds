from reproducibility.verify import DEFAULT_CURRENT, DEFAULT_REFERENCE, verify_reference


def test_official_reference_verifies_current_outputs():
    # A clean checkout intentionally has no ignored results/ directory. In
    # that environment validate the archived reference contract against
    # itself; after a reproduction, validate the generated official outputs.
    current = DEFAULT_CURRENT if (DEFAULT_CURRENT / "manifest.json").is_file() else DEFAULT_REFERENCE
    result = verify_reference(current_dir=current, reference_dir=DEFAULT_REFERENCE)
    assert result.passed, result.messages
