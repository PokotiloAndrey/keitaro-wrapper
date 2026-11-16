import httpx
import pytest
from app.config import settings
from app.keitaro import Keitaro, UpstreamError


@pytest.mark.asyncio
async def test_error_does_not_echo_secret(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(settings, "keitaro_api_key", "secret-never-show")

    def handler(request):
        assert request.headers["Api-Key"] == "secret-never-show"
        return httpx.Response(403, text="secret-never-show")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamError) as err:
        await Keitaro().request("GET", "campaigns")
    assert "secret-never-show" not in err.value.message


def test_tracker_url_accepts_admin_link_and_rejects_credentials():
    from app.config import Settings
    from pydantic import ValidationError
    assert Settings(_env_file=None, keitaro_url='https://tracker.example/admin/').keitaro_url == 'https://tracker.example'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, keitaro_url='https://user:password@tracker.example')


def test_prefix_cannot_allow_all_campaigns():
    from app.config import Settings
    from pydantic import ValidationError
    for prefix in ['', 'test_', 'production']:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, campaign_prefix=prefix)
