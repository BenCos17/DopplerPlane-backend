from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str = "https://api.adsb.lol"
    cache_ttl_seconds: float = 120.0
    min_request_interval_seconds: float = 1.0
    upstream_timeout_seconds: float = 8.0
    max_radius_nm: float = 250.0


@dataclass
class CacheEntry:
    expires_at: float
    payload: Any


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="DopplerPlane self-hosted relay", version="1.0.0")
    cache: dict[tuple[float, float, float], CacheEntry] = {}
    last_request_at: dict[tuple[float, float, float], float] = {}
    locks: dict[tuple[float, float, float], asyncio.Lock] = {}

    def get_lock(key: tuple[float, float, float]) -> asyncio.Lock:
        lock = locks.get(key)
        if lock is None:
            lock = locks[key] = asyncio.Lock()
        return lock

    async def fetch_point(lat: float, lon: float, radius: float) -> Any:
        key = (lat, lon, radius)
        now = time.monotonic()
        cached = cache.get(key)
        if cached and cached.expires_at > now:
            return cached.payload

        async with get_lock(key):
            now = time.monotonic()
            cached = cache.get(key)
            if cached and cached.expires_at > now:
                return cached.payload

            previous = last_request_at.get(key)
            if previous is not None:
                wait_for = settings.min_request_interval_seconds - (now - previous)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

            url = f"{settings.upstream_base_url.rstrip('/')}/v2/point/{lat:g}/{lon:g}/{radius:g}"
            try:
                async with httpx.AsyncClient(
                    timeout=settings.upstream_timeout_seconds,
                    transport=transport,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.json()
            except httpx.HTTPStatusError as error:
                raise HTTPException(
                    status_code=502,
                    detail=f"ADS-B upstream returned HTTP {error.response.status_code}",
                ) from error
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(status_code=502, detail="ADS-B upstream unavailable") from error

            last_request_at[key] = time.monotonic()
            cache[key] = CacheEntry(
                expires_at=time.monotonic() + settings.cache_ttl_seconds,
                payload=payload,
            )
            return payload

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v2/point/{lat}/{lon}/{radius}")
    async def point(lat: float, lon: float, radius: float, request: Request) -> JSONResponse:
        if not -90 <= lat <= 90:
            raise HTTPException(status_code=422, detail="lat must be between -90 and 90")
        if not -180 <= lon <= 180:
            raise HTTPException(status_code=422, detail="lon must be between -180 and 180")
        if not 0 < radius <= settings.max_radius_nm:
            raise HTTPException(
                status_code=422,
                detail=f"radius must be greater than 0 and at most {settings.max_radius_nm:g} nm",
            )

        payload = await fetch_point(lat, lon, radius)
        return JSONResponse(content=payload, headers={"X-Cache-TTL": str(settings.cache_ttl_seconds)})

    return app


def settings_from_environment() -> Settings:
    return Settings(
        upstream_base_url=os.getenv("ADSB_UPSTREAM_BASE_URL", Settings.upstream_base_url),
        cache_ttl_seconds=float(os.getenv("CACHE_TTL_SECONDS", "120")),
        min_request_interval_seconds=float(os.getenv("MIN_REQUEST_INTERVAL_SECONDS", "1")),
        upstream_timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "8")),
        max_radius_nm=float(os.getenv("MAX_RADIUS_NM", "250")),
    )


app = create_app(settings_from_environment())