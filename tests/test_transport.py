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
