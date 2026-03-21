"""
Tests for:
  GET    /api/watchlist
  POST   /api/watchlist
  PUT    /api/watchlist/{alert_id}
  DELETE /api/watchlist/{alert_id}

Covers CRUD operations, match_count calculation, and validation edge cases.
"""

import pytest
from tests.conftest import make_vehicle, make_watchlist_alert


class TestGetWatchlist:

    def test_empty_returns_empty_list(self, client):
        r = client.get("/api/watchlist")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all_alerts(self, client, db):
        make_watchlist_alert(db, name="Alert 1")
        make_watchlist_alert(db, name="Alert 2")

        r = client.get("/api/watchlist")
        assert len(r.json()) == 2

    def test_alert_dict_has_required_fields(self, client, db):
        make_watchlist_alert(db, name="Shape Test")

        r = client.get("/api/watchlist")
        alert = r.json()[0]
        required = [
            "id", "name", "make", "model", "max_price", "min_price", "max_mileage",
            "min_year", "max_year", "condition", "notification_email", "is_active",
            "created_at", "last_triggered", "trigger_count", "match_count"
        ]
        for field in required:
            assert field in alert, f"Missing field: {field}"

    def test_match_count_is_zero_when_no_matching_vehicles(self, client, db):
        make_watchlist_alert(db, name="No Match", make="Lamborghini")
        make_vehicle(db, stock_number="V1", make="Toyota")

        r = client.get("/api/watchlist")
        assert r.json()[0]["match_count"] == 0

    def test_match_count_counts_matching_active_vehicles(self, client, db):
        make_watchlist_alert(db, name="Toyota Alert", make="Toyota")
        make_vehicle(db, stock_number="T1", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="T2", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="T3", make="Toyota", is_active=False)  # excluded

        r = client.get("/api/watchlist")
        assert r.json()[0]["match_count"] == 2

    def test_match_count_with_price_filter(self, client, db):
        make_watchlist_alert(db, name="Budget Toyota", make="Toyota", max_price=25000.0)
        make_vehicle(db, stock_number="CHEAP", make="Toyota", price=20000.0)
        make_vehicle(db, stock_number="EXPENSIVE", make="Toyota", price=40000.0)

        r = client.get("/api/watchlist")
        assert r.json()[0]["match_count"] == 1

    def test_match_count_with_condition_filter(self, client, db):
        make_watchlist_alert(db, name="New Cars Only", condition="new")
        make_vehicle(db, stock_number="NEW1", condition="new")
        make_vehicle(db, stock_number="USED1", condition="used")

        r = client.get("/api/watchlist")
        assert r.json()[0]["match_count"] == 1


class TestCreateWatchlist:

    def test_create_minimal_alert(self, client):
        payload = {"name": "My Alert"}
        r = client.post("/api/watchlist", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Alert"
        assert data["is_active"] is True
        assert data["trigger_count"] == 0
        assert data["match_count"] == 0

    def test_create_full_alert(self, client):
        payload = {
            "name": "Full Alert",
            "make": "Toyota",
            "model": "Camry",
            "max_price": 35000.0,
            "min_price": 15000.0,
            "max_mileage": 50000,
            "min_year": 2020,
            "max_year": 2024,
            "condition": "used",
            "notification_email": "test@example.com",
        }
        r = client.post("/api/watchlist", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["make"] == "Toyota"
        assert data["model"] == "Camry"
        assert data["max_price"] == 35000.0
        assert data["min_price"] == 15000.0
        assert data["max_mileage"] == 50000
        assert data["min_year"] == 2020
        assert data["max_year"] == 2024
        assert data["condition"] == "used"
        assert data["notification_email"] == "test@example.com"

    def test_create_alert_empty_string_make_stored_as_null(self, client):
        payload = {"name": "Test", "make": ""}
        r = client.post("/api/watchlist", json=payload)
        assert r.status_code == 200
        assert r.json()["make"] is None

    def test_created_alert_appears_in_list(self, client):
        client.post("/api/watchlist", json={"name": "Test Alert"})
        r = client.get("/api/watchlist")
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Test Alert"

    def test_create_returns_match_count(self, client, db):
        make_vehicle(db, stock_number="T1", make="Toyota", is_active=True)
        r = client.post("/api/watchlist", json={"name": "Toyota", "make": "Toyota"})
        assert r.json()["match_count"] == 1


class TestUpdateWatchlist:

    def test_update_name(self, client, db):
        alert = make_watchlist_alert(db, name="Original Name")
        r = client.put(f"/api/watchlist/{alert.id}", json={"name": "Updated Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_update_is_active_false(self, client, db):
        alert = make_watchlist_alert(db, name="Active", is_active=True)
        r = client.put(f"/api/watchlist/{alert.id}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_update_price_filters(self, client, db):
        alert = make_watchlist_alert(db, name="Test")
        r = client.put(f"/api/watchlist/{alert.id}",
                       json={"max_price": 30000.0, "min_price": 10000.0})
        assert r.status_code == 200
        assert r.json()["max_price"] == 30000.0
        assert r.json()["min_price"] == 10000.0

    def test_update_nonexistent_alert_returns_404(self, client):
        r = client.put("/api/watchlist/99999", json={"name": "Ghost"})
        assert r.status_code == 404

    def test_update_preserves_unmodified_fields(self, client, db):
        alert = make_watchlist_alert(db, name="Preserve Test", make="Toyota", max_price=30000.0)
        r = client.put(f"/api/watchlist/{alert.id}", json={"name": "Updated"})
        data = r.json()
        assert data["make"] == "Toyota"
        assert data["max_price"] == 30000.0


class TestDeleteWatchlist:

    def test_delete_existing_alert(self, client, db):
        alert = make_watchlist_alert(db, name="To Delete")
        r = client.delete(f"/api/watchlist/{alert.id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_deleted_alert_no_longer_appears_in_list(self, client, db):
        alert = make_watchlist_alert(db, name="Gone")
        client.delete(f"/api/watchlist/{alert.id}")
        r = client.get("/api/watchlist")
        assert len(r.json()) == 0

    def test_delete_nonexistent_alert_returns_404(self, client):
        r = client.delete("/api/watchlist/99999")
        assert r.status_code == 404
