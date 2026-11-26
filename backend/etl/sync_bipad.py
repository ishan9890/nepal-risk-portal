"""
Sync real incidents from the BIPAD Portal.

Run:  python -m etl.sync_bipad
If BIPAD is unreachable, falls back to the bundled sample data (etl.seed).
"""
import json
import sys

import httpx
from sqlalchemy import text

from etl.seed import UPSERT_INCIDENT, get_engine

BIPAD_URL = "https://bipadportal.gov.np/api/v1/incident/"


def fetch_bipad(limit: int = 200) -> list[dict]:
    resp = httpx.get(
        BIPAD_URL,
        params={"limit": limit, "ordering": "-incident_on", "expand": "hazard"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def to_row(item: dict) -> dict | None:
    """Convert one BIPAD record into one of our rows. Skip if no location."""
    point = item.get("point") or {}
    coords = point.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    hazard = item.get("hazard")
    hazard_type = hazard.get("titleEn") if isinstance(hazard, dict) else None
    return {
        "external_id": f"BIPAD-{item['id']}",
        "hazard_type": (hazard_type or "other").lower().replace(" ", "_"),
        "title": item.get("title") or "BIPAD incident",
        "incident_date": item.get("incidentOn"),
        "lon": coords[0],
        "lat": coords[1],
        "deaths": item.get("peopleDeathCount") or 0,
        "injured": item.get("peopleInjuredCount") or 0,
        "families_affected": item.get("familyAffectedCount") or 0,
        "estimated_loss_npr": int(item.get("estimatedLoss") or 0),
        "raw_payload": json.dumps(item),
    }


def main() -> None:
    try:
        records = fetch_bipad()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"BIPAD unreachable ({exc}). Falling back to bundled sample data.")
        from etl.seed import main as seed_main
        seed_main()
        return

    rows = [r for r in (to_row(i) for i in records) if r and r["incident_date"]]
    print(f"Fetched {len(records)} records, {len(rows)} usable.")
    if not rows:
        print("Nothing usable. Keeping existing data.")
        return

    with get_engine().begin() as conn:
        conn.execute(UPSERT_INCIDENT, rows)
        n = conn.execute(text(
            "SELECT count(*) FROM disaster_incidents WHERE external_id LIKE 'BIPAD-%'"
        )).scalar()
        print(f"BIPAD incidents in database: {n}")


if __name__ == "__main__":
    sys.exit(main())