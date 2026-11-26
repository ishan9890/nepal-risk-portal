import time
from typing import Any

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 30 * 60  # reuse a result for 30 minutes

# in-memory cache: {(lat, lon): (timestamp, data)}
_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def classify_rainfall(mm_48h: float) -> str:
    """Turn cumulative rainfall into a simple alert level."""
    if mm_48h >= 200:
        return "extreme"
    if mm_48h >= 100:
        return "high"
    if mm_48h >= 50:
        return "moderate"
    return "low"


async def fetch_rainfall(lat: float, lon: float) -> dict[str, Any]:
    # Round the coordinates so nearby wards share one cached result.
    key = (round(lat, 2), round(lon, 2))
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        return {**hit[1], "cached": True}

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "forecast_days": 3,
        "timezone": "Asia/Kathmandu",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
    hourly = resp.json()["hourly"]["precipitation"]
    values = [v or 0.0 for v in hourly]  # None -> 0

    data = {
        "rain_24h_mm": round(sum(values[:24]), 1),
        "rain_48h_mm": round(sum(values[:48]), 1),
        "rain_72h_mm": round(sum(values[:72]), 1),
    }
    data["alert_level"] = classify_rainfall(data["rain_48h_mm"])
    _cache[key] = (now, data)
    return {**data, "cached": False}