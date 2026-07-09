import pytest

from ai_usp.shock import RawShockFiscalUseError, assert_no_phi_raw_direct_use


def test_phi_raw_direct_use_is_blocked():
    with pytest.raises(RawShockFiscalUseError):
        assert_no_phi_raw_direct_use(True, "test")
