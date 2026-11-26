import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.weather import fetch_rainfall
from app.session import get_session

router = APIRouter(prefix="/weather", tags=["weather"])

CENTROID_SQL = text("""
    SELECT ST_Y(ST_PointOnSurface(geom)) AS lat,
           ST_X(ST_PointOnSurface(geom)) AS lon
    FROM admin_units WHERE unit_code = :code
""")


@router.get("/{unit_code}")
async def unit_weather(unit_code: str, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(CENTROID_SQL, {"code": unit_code})).mappings().first()
    if row is None:
        raise HTTPException(404, f"Unknown unit_code: {unit_code}")
    try:
        data = await fetch_rainfall(row["lat"], row["lon"])
    except httpx.HTTPError:
        raise HTTPException(503, "Weather service temporarily unavailable")
    return {"unit_code": unit_code, "lat": row["lat"], "lon": row["lon"], **data}