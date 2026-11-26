def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "3." in r.json()["postgis"]


def test_list_wards_is_valid_geojson(client):
    r = client.get("/api/v1/admin-units", params={"level": "ward"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 71
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert feature["properties"]["flood_score"] is not None


def test_list_filtered_by_parent(client):
    r = client.get(
        "/api/v1/admin-units",
        params={"level": "ward", "parent_code": "NP-M-BHAKTAPUR"},
    )
    assert len(r.json()["features"]) == 10


def test_invalid_level_is_rejected(client):
    r = client.get("/api/v1/admin-units", params={"level": "banana"})
    assert r.status_code == 422


def test_locate_returns_a_ward(client):
    # A point well inside a ward, not on an edge.
    r = client.get("/api/v1/admin-units/locate", params={"lat": 27.6930, "lon": 85.3250})
    assert r.status_code == 200
    assert r.json()["admin_level"] == "ward"
    assert r.json()["parent_code"] == "NP-M-KATHMANDU-MC"


def test_locate_on_ward_edge_still_returns_a_ward(client):
    # Regression test for the boundary bug we hit in the seed script.
    r = client.get("/api/v1/admin-units/locate", params={"lat": 27.6930, "lon": 85.3200})
    assert r.status_code == 200
    assert r.json()["admin_level"] == "ward"


def test_locate_outside_nepal_is_404(client):
    r = client.get("/api/v1/admin-units/locate", params={"lat": 51.5, "lon": -0.12})
    assert r.status_code == 404


def test_unit_detail(client):
    r = client.get("/api/v1/admin-units/NP-M-KATHMANDU-MC")
    assert r.status_code == 200
    body = r.json()
    assert body["unit"]["name_ne"] == "काठमाडौं महानगरपालिका"
    assert body["incident_summary"]["incidents"] > 0


def test_unknown_unit_is_404(client):
    assert client.get("/api/v1/admin-units/DOES-NOT-EXIST").status_code == 404

def test_weather_unknown_unit_is_404(client):
    assert client.get("/api/v1/weather/DOES-NOT-EXIST").status_code == 404


def test_classify_rainfall():
    from app.services.weather import classify_rainfall
    assert classify_rainfall(10) == "low"
    assert classify_rainfall(60) == "moderate"
    assert classify_rainfall(150) == "high"
    assert classify_rainfall(250) == "extreme"