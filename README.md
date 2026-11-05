# DopplerPlane self-hosted backend

This service is a small self-hosted relay for the ADS-B point lookup used by DopplerPlane. It keeps the upstream response shape intact while coalescing concurrent requests and caching each coordinate/radius lookup.

## Run with Docker

```bash
docker compose up --build
```

The API is then available at `http://localhost:8000`.

```text
GET /v2/point/{lat}/{lon}/{radius}
GET /healthz
```

`radius` is in nautical miles and is limited to 250 by default. The default upstream is `https://api.airplanes.live`; set `ADSB_UPSTREAM_BASE_URL` to another compatible ADS-B provider if needed. `CACHE_TTL_SECONDS` defaults to 120 seconds, so upstream data is refreshed at most once every 2 minutes per exact lookup key. `MIN_REQUEST_INTERVAL_SECONDS` defaults to 1 second per exact lookup key.

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -e ".[test]"
uvicorn app.main:app --reload
```

This relay does not need Cloudflare Worker-specific code. Put it behind your own reverse proxy or tunnel, and point the app at that URL.