"""
Seed the database with sample Nepal data.

Run from the backend folder with:   python -m etl.seed
It is IDEMPOTENT: running it many times gives the same result (no duplicates).
"""
import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_DIR = BACKEND_DIR / "seed_data"
load_dotenv(BACKEND_DIR / ".env")


# ---------------------------------------------------------------------------
# 1. Database connection
# ---------------------------------------------------------------------------
def get_engine():
    url = os.environ["DATABASE_URL"]
    # Use the synchronous psycopg2 driver; a one-off script doesn't need async.
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url)


# ---------------------------------------------------------------------------
# 2. Helpers
# ---------------------------------------------------------------------------
_DEVANAGARI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def ne_number(n: int) -> str:
    """12 -> '१२' (Nepali numerals)."""
    return str(n).translate(_DEVANAGARI_DIGITS)


def box_wkt(min_lon, min_lat, max_lon, max_lat) -> str:
    """Turn a bounding box into WKT (Well-Known Text), a text format for shapes.
    A polygon's outer ring must be closed: first point == last point."""
    min_lon, min_lat, max_lon, max_lat = (round(v, 6) for v in (min_lon, min_lat, max_lon, max_lat))
    return (
        f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    )


# ---------------------------------------------------------------------------
# 3. Administrative units: provinces -> districts -> municipalities -> wards
# ---------------------------------------------------------------------------
def build_admin_units(hierarchy: dict) -> list[dict]:
    units: list[dict] = []

    for p in hierarchy["provinces"]:
        units.append(dict(
            unit_code=p["code"], name_en=p["name_en"], name_ne=p["name_ne"],
            admin_level="province", parent_code=None,
            population=p["population"], wkt=box_wkt(*p["bbox"]),
        ))

    for d in hierarchy["districts"]:
        units.append(dict(
            unit_code=d["code"], name_en=d["name_en"], name_ne=d["name_ne"],
            admin_level="district", parent_code=d["province"],
            population=d["population"], wkt=box_wkt(*d["bbox"]),
        ))

    for m in hierarchy["municipalities"]:
        units.append(dict(
            unit_code=m["code"], name_en=m["name_en"], name_ne=m["name_ne"],
            admin_level="municipality", parent_code=m["district"],
            population=m["population"], wkt=box_wkt(*m["bbox"]),
        ))

        # Generate placeholder wards by slicing the municipality into a grid.
        cols, rows = m["grid"]
        min_lon, min_lat, max_lon, max_lat = m["bbox"]
        dx = (max_lon - min_lon) / cols
        dy = (max_lat - min_lat) / rows
        ward_pop = m["population"] // m["wards"]

        for i in range(m["wards"]):
            row, col = divmod(i, cols)  # i=0 -> (row 0, col 0), i=1 -> (0, 1) ...
            number = i + 1
            units.append(dict(
                unit_code=f"{m['code']}-W{number:02d}",
                name_en=f"{m['short_en']} Ward {number}",
                name_ne=f"{m['short_ne']} वडा {ne_number(number)}",
                admin_level="ward", parent_code=m["code"],
                population=ward_pop,
                wkt=box_wkt(
                    min_lon + col * dx, min_lat + row * dy,
                    min_lon + (col + 1) * dx, min_lat + (row + 1) * dy,
                ),
            ))
    return units


UPSERT_UNIT = text("""
    INSERT INTO admin_units
        (unit_code, name_en, name_ne, admin_level, parent_code, population, geom)
    VALUES
        (:unit_code, :name_en, :name_ne, :admin_level, :parent_code, :population,
         ST_Multi(ST_GeomFromText(:wkt, 4326)))
    ON CONFLICT (unit_code) DO UPDATE SET
        name_en = EXCLUDED.name_en,
        name_ne = EXCLUDED.name_ne,
        admin_level = EXCLUDED.admin_level,
        parent_code = EXCLUDED.parent_code,
        population = EXCLUDED.population,
        geom = EXCLUDED.geom
""")


# ---------------------------------------------------------------------------
# 4. Synthetic ward risk profiles
# ---------------------------------------------------------------------------
# Every indicator is scaled 0..1 where 1 = MOST dangerous. Default weights sum to 1.
WEIGHTS = {
    "rainfall": 0.25,
    "river_proximity": 0.25,
    "slope": 0.15,
    "elevation": 0.10,
    "land_cover": 0.15,
    "soil": 0.10,
}


def make_risk_profile(unit_code: str) -> dict:
    # Seeding the random generator with the unit_code makes results repeatable:
    # the same ward always gets the same numbers, on every run and every machine.
    rng = random.Random(unit_code)
    ind = {name: round(rng.random(), 3) for name in WEIGHTS}

    flood = sum(ind[k] * w for k, w in WEIGHTS.items()) * 100
    landslide = (0.5 * ind["slope"] + 0.3 * ind["rainfall"] + 0.2 * ind["soil"]) * 100
    earthquake = (0.6 * ind["soil"] + 0.4 * rng.random()) * 100

    return dict(
        unit_code=unit_code,
        flood_score=round(flood, 1),
        landslide_score=round(landslide, 1),
        earthquake_score=round(earthquake, 1),
        river_distance_m=round(50 + (1 - ind["river_proximity"]) * 3000, 0),
        mean_slope_deg=round(ind["slope"] * 35, 1),
        impervious_surface_pct=round(ind["land_cover"] * 100, 1),
        indicator_breakdown=json.dumps(ind),
    )


UPSERT_RISK = text("""
    INSERT INTO ward_risk_profiles
        (unit_code, flood_score, landslide_score, earthquake_score,
         river_distance_m, mean_slope_deg, impervious_surface_pct,
         indicator_breakdown, updated_at)
    VALUES
        (:unit_code, :flood_score, :landslide_score, :earthquake_score,
         :river_distance_m, :mean_slope_deg, :impervious_surface_pct,
         CAST(:indicator_breakdown AS jsonb), now())
    ON CONFLICT (unit_code) DO UPDATE SET
        flood_score = EXCLUDED.flood_score,
        landslide_score = EXCLUDED.landslide_score,
        earthquake_score = EXCLUDED.earthquake_score,
        river_distance_m = EXCLUDED.river_distance_m,
        mean_slope_deg = EXCLUDED.mean_slope_deg,
        impervious_surface_pct = EXCLUDED.impervious_surface_pct,
        indicator_breakdown = EXCLUDED.indicator_breakdown,
        updated_at = now()
""")


# ---------------------------------------------------------------------------
# 5. Incidents, with a SPATIAL JOIN to find each incident's administrative unit
# ---------------------------------------------------------------------------
UPSERT_INCIDENT = text("""
    INSERT INTO disaster_incidents
        (external_id, hazard_type, title, incident_date, unit_code,
         deaths, injured, families_affected, estimated_loss_npr,
         location, raw_payload)
    VALUES
        (:external_id, :hazard_type, :title, :incident_date,
         (SELECT unit_code FROM admin_units
           WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
           ORDER BY CASE admin_level
                      WHEN 'ward' THEN 1
                      WHEN 'municipality' THEN 2
                      WHEN 'district' THEN 3
                      ELSE 4 END
           LIMIT 1),
         :deaths, :injured, :families_affected, :estimated_loss_npr,
         ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
         CAST(:raw_payload AS jsonb))
    ON CONFLICT (external_id) DO UPDATE SET
        hazard_type = EXCLUDED.hazard_type,
        title = EXCLUDED.title,
        incident_date = EXCLUDED.incident_date,
        unit_code = EXCLUDED.unit_code,
        deaths = EXCLUDED.deaths,
        injured = EXCLUDED.injured,
        families_affected = EXCLUDED.families_affected,
        estimated_loss_npr = EXCLUDED.estimated_loss_npr,
        location = EXCLUDED.location,
        raw_payload = EXCLUDED.raw_payload
""")


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
def main() -> None:
    hierarchy = json.loads((SEED_DIR / "admin_hierarchy.json").read_text(encoding="utf-8"))
    incidents = json.loads((SEED_DIR / "incidents.json").read_text(encoding="utf-8"))

    units = build_admin_units(hierarchy)
    ward_codes = [u["unit_code"] for u in units if u["admin_level"] == "ward"]
    risk_rows = [make_risk_profile(code) for code in ward_codes]
    incident_rows = [{**i, "raw_payload": json.dumps(i)} for i in incidents]

    engine = get_engine()
    # engine.begin() = ONE transaction: everything succeeds together, or nothing is saved.
    with engine.begin() as conn:
        conn.execute(UPSERT_UNIT, units)
        conn.execute(UPSERT_RISK, risk_rows)
        conn.execute(UPSERT_INCIDENT, incident_rows)

        print("Rows now in the database:")
        for level, n in conn.execute(text(
            "SELECT admin_level, count(*) FROM admin_units GROUP BY admin_level ORDER BY 2"
        )):
            print(f"  admin_units [{level}]: {n}")
        for table in ("ward_risk_profiles", "disaster_incidents"):
            n = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"  {table}: {n}")

        unmatched = conn.execute(text(
            "SELECT count(*) FROM disaster_incidents WHERE unit_code IS NULL"
        )).scalar()
        print(f"Incidents that matched no area: {unmatched}")


if __name__ == "__main__":
    main()