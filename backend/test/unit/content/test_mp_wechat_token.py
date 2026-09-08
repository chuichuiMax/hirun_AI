import pytest

from yuxi.services import mp_service


@pytest.mark.unit
def test_wechat_token_stale_detects_wechat_message():
    assert mp_service._wechat_token_stale(
        "invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken"
    )
    assert not mp_service._wechat_token_stale("ok")
    assert not mp_service._wechat_token_stale(None)
