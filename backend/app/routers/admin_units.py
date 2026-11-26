import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.session import get_session

router = APIRouter(prefix="/admin-units", tags=["admin-units"])

Level = Literal["province", "district", "municipality", "ward"]

# --- 1. All units of one level, as GeoJSON ---------------------------------
LIST_SQL = text("""
    SELECT a.unit_code, a.name_en, a.name_ne, a.admin_level, a.parent_code,
           a.population,
           ST_AsGeoJSON(a.geom, 6) AS geometry,
           r.flood_score, r.landslide_score, r.earthquake_score
    FROM admin_units a
    LEFT JOIN ward_risk_profiles r ON r.unit_code = a.unit_code
    WHERE a.admin_level = :level
      AND (CAST(:parent AS text) IS NULL OR a.parent_code = CAST(:parent AS text))
    ORDER BY a.unit_code
""")


@router.get("")
async def list_units(
    level: Level = Query(..., description="Administrative level"),
    parent_code: str | None = Query(None, description="Only children of this unit"),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(LIST_SQL, {"level": level, "parent": parent_code})).mappings().all()
    features = [
        {
            "type": "Feature",
            "id": r["unit_code"],
            "geometry": json.loads(r["geometry"]),
            "properties": {k: v for k, v in r.items() if k != "geometry"},
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}


# --- 2. Which area contains this point? ------------------------------------
# NOTE: this route must be declared BEFORE "/{unit_code}", or FastAPI would
# treat the word "locate" as a unit code.
LOCATE_SQL = text("""
    SELECT unit_code, name_en, name_ne, admin_level, parent_code
    FROM admin_units
    WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 0.00001)
    ORDER BY CASE admin_level
               WHEN 'ward' THEN 1 WHEN 'municipality' THEN 2
               WHEN 'district' THEN 3 ELSE 4 END,
             ST_Distance(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)),
             unit_code
    LIMIT 1
""")


@router.get("/locate")
async def locate(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(LOCATE_SQL, {"lat": lat, "lon": lon})).mappings().first()
    if row is None:
        raise HTTPException(404, "No administrative unit contains this point")
    return dict(row)


# --- 3. Details for one unit ----------------------------------------------
UNIT_SQL = text("""
    SELECT unit_code, name_en, name_ne, admin_level, parent_code, population
    FROM admin_units WHERE unit_code = :code
""")
RISK_SQL = text("""
    SELECT flood_score, landslide_score, earthquake_score, river_distance_m,
           mean_slope_deg, impervious_surface_pct, indicator_breakdown
    FROM ward_risk_profiles WHERE unit_code = :code
""")
# A unit's incidents = its own + those of its direct children
# (a municipality includes its wards).
INCIDENT_SCOPE = """
    unit_code = :code
    OR unit_code IN (SELECT unit_code FROM admin_units WHERE parent_code = :code)
"""
SUMMARY_SQL = text(f"""
    SELECT count(*) AS incidents,
           COALESCE(sum(deaths), 0)::bigint AS deaths,
           COALESCE(sum(injured), 0)::bigint AS injured,
           COALESCE(sum(families_affected), 0)::bigint AS families_affected,
           COALESCE(sum(estimated_loss_npr), 0)::bigint AS estimated_loss_npr
    FROM disaster_incidents WHERE {INCIDENT_SCOPE}
""")
RECENT_SQL = text(f"""
    SELECT external_id, hazard_type, title, incident_date, deaths, injured,
           families_affected, estimated_loss_npr
    FROM disaster_incidents WHERE {INCIDENT_SCOPE}
    ORDER BY incident_date DESC LIMIT 20
""")


@router.get("/{unit_code}")
async def unit_detail(unit_code: str, session: AsyncSession = Depends(get_session)):
    params = {"code": unit_code}
    unit = (await session.execute(UNIT_SQL, params)).mappings().first()
    if unit is None:
        raise HTTPException(404, f"Unknown unit_code: {unit_code}")
    risk = (await session.execute(RISK_SQL, params)).mappings().first()
    summary = (await session.execute(SUMMARY_SQL, params)).mappings().one()
    recent = (await session.execute(RECENT_SQL, params)).mappings().all()
    return {
        "unit": dict(unit),
        "risk": dict(risk) if risk else None,
        "incident_summary": dict(summary),
        "recent_incidents": [dict(r) for r in recent],
    }