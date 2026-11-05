import httpx
import pytest

from app.main import Settings, create_app


@pytest.mark.anyio
async def test_point_is_cached_for_polling_clients() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url).endswith("/v2/point/51.5/-0.1/25")
        return httpx.Response(200, json={"ac": [{"hex": "abc123"}]})

    app = create_app(
        Settings(cache_ttl_seconds=30, min_request_interval_seconds=0),
        transport=httpx.MockTransport(handler),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/v2/point/51.5/-0.1/25")
        second = await client.get("/v2/point/51.5/-0.1/25")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert calls == 1


@pytest.mark.anyio
async def test_radius_is_limited() -> None:
    app = create_app(Settings(max_radius_nm=250))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v2/point/51.5/-0.1/251")

    assert response.status_code == 422