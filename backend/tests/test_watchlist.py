"""
test_watchlist.py — Tests for watchlist alert endpoints and alert matching logic.

Endpoints covered:
  GET    /api/watchlist               — list all alerts with match_count
  POST   /api/watchlist               — create alert
  PUT    /api/watchlist/{alert_id}    — update alert
  DELETE /api/watchlist/{alert_id}    — delete alert

Also covers:
  - vehicle_matches_alert() logic directly (unit tests)
  - dealer-scoped alert matching (Sprint 1 xfail — new dealer_id field)
  - Watchlist alert with dealer_id=None matches all locations

Test isolation: every test gets a fresh empty in-memory DB via db_session.
"""

from datetime import datetime

import pytest
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import models
from alerts import vehicle_matches_alert, get_matching_vehicles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vehicle(db, stock_number, make="Toyota", model="Camry",
             price=25000.0, mileage=15000, year=2022, condition="Used",
             is_active=True, dealer_id=None, location_name=None):
    v = models.Vehicle(
        stock_number=stock_number,
        vin=f"VIN{stock_number}",
        make=make,
        model=model,
        price=price,
        mileage=mileage,
        year=year,
        condition=condition,
        is_active=is_active,
        dealer_id=dealer_id,
        location_name=location_name,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _alert(db, name="Test Alert", make=None, model=None, max_price=None,
           min_price=None, max_mileage=None, min_year=None, max_year=None,
           condition=None, notification_email=None, is_active=True,
           dealer_id=None, location_name=None):
    a = models.WatchlistAlert(
        name=name, make=make, model=model, max_price=max_price,
        min_price=min_price, max_mileage=max_mileage, min_year=min_year,
        max_year=max_year, condition=condition,
        notification_email=notification_email, is_active=is_active,
        dealer_id=dealer_id, location_name=location_name,
        created_at=datetime.utcnow(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _mem_vehicle(**kwargs) -> models.Vehicle:
    """Create an in-memory Vehicle (not persisted) for unit testing."""
    defaults = dict(
        stock_number="TEST001", vin="VIN001",
        year=2022, make="Toyota", model="Camry", trim="XSE",
        price=28500.0, mileage=15000, condition="Used", is_active=True,
        dealer_id=None, location_name=None,
    )
    defaults.update(kwargs)
    v = models.Vehicle()
    for k, val in defaults.items():
        setattr(v, k, val)
    return v


def _mem_alert(**kwargs) -> models.WatchlistAlert:
    """Create an in-memory WatchlistAlert (not persisted) for unit testing."""
    defaults = dict(
        name="Test Alert", make=None, model=None, max_price=None,
        min_price=None, max_mileage=None, min_year=None, max_year=None,
        condition=None, notification_email=None, is_active=True,
        dealer_id=None, location_name=None, trigger_count=0,
        created_at=datetime.utcnow(), last_triggered=None,
    )
    defaults.update(kwargs)
    a = models.WatchlistAlert()
    for k, val in defaults.items():
        setattr(a, k, val)
    return a


# ===========================================================================
# GET /api/watchlist
# ===========================================================================

class TestGetWatchlist:

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/watchlist")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all_alerts(self, client, db_session):
        _alert(db_session, name="Alert 1")
        _alert(db_session, name="Alert 2")
        assert len(client.get("/api/watchlist").json()) == 2

    def test_alert_dict_has_all_required_fields(self, client, db_session):
        _alert(db_session, name="Shape Test")
        alert = client.get("/api/watchlist").json()[0]
        required = [
            "id", "name", "make", "model", "max_price", "min_price",
            "max_mileage", "min_year", "max_year", "condition",
            "notification_email", "is_active", "created_at",
            "last_triggered", "trigger_count", "match_count",
        ]
        for field in required:
            assert field in alert, f"Watchlist response missing field: {field}"

    def test_match_count_zero_when_no_matching_vehicles(self, client, db_session):
        _alert(db_session, name="No Match", make="Lamborghini")
        _vehicle(db_session, "V1", make="Toyota")
        assert client.get("/api/watchlist").json()[0]["match_count"] == 0

    def test_match_count_counts_matching_active_vehicles(self, client, db_session):
        _alert(db_session, name="Toyota", make="Toyota")
        _vehicle(db_session, "T1", make="Toyota", is_active=True)
        _vehicle(db_session, "T2", make="Toyota", is_active=True)
        _vehicle(db_session, "T3", make="Toyota", is_active=False)  # excluded
        assert client.get("/api/watchlist").json()[0]["match_count"] == 2

    def test_match_count_with_price_ceiling(self, client, db_session):
        _alert(db_session, name="Budget Toyota", make="Toyota", max_price=25000.0)
        _vehicle(db_session, "CHEAP", make="Toyota", price=20000.0)
        _vehicle(db_session, "EXPENSIVE", make="Toyota", price=40000.0)
        assert client.get("/api/watchlist").json()[0]["match_count"] == 1

    def test_match_count_with_price_floor(self, client, db_session):
        _alert(db_session, name="Premium", min_price=30000.0)
        _vehicle(db_session, "CHEAP", price=20000.0)
        _vehicle(db_session, "PREMIUM", price=45000.0)
        assert client.get("/api/watchlist").json()[0]["match_count"] == 1

    def test_match_count_with_mileage_filter(self, client, db_session):
        _alert(db_session, name="Low Miles", max_mileage=30000)
        _vehicle(db_session, "LOW", mileage=20000)
        _vehicle(db_session, "HIGH", mileage=80000)
        assert client.get("/api/watchlist").json()[0]["match_count"] == 1

    def test_match_count_with_year_range(self, client, db_session):
        _alert(db_session, name="2020+", min_year=2020, max_year=2023)
        _vehicle(db_session, "V2019", year=2019)
        _vehicle(db_session, "V2021", year=2021)
        _vehicle(db_session, "V2024", year=2024)
        assert client.get("/api/watchlist").json()[0]["match_count"] == 1

    def test_match_count_with_condition_filter(self, client, db_session):
        _alert(db_session, name="New Only", condition="New")
        _vehicle(db_session, "NEW1", condition="New")
        _vehicle(db_session, "USED1", condition="Used")
        assert client.get("/api/watchlist").json()[0]["match_count"] == 1

    def test_no_criteria_alert_matches_all_active(self, client, db_session):
        _alert(db_session, name="All Vehicles")
        _vehicle(db_session, "T1", make="Toyota")
        _vehicle(db_session, "H1", make="Honda")
        _vehicle(db_session, "INACT", is_active=False)
        assert client.get("/api/watchlist").json()[0]["match_count"] == 2


# ===========================================================================
# POST /api/watchlist
# ===========================================================================

class TestCreateWatchlist:

    def test_create_minimal_alert(self, client):
        r = client.post("/api/watchlist", json={"name": "My Alert"})
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Alert"
        assert data["is_active"] is True
        assert data["trigger_count"] == 0
        assert data["match_count"] == 0
        assert data["id"] is not None

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
            "condition": "Used",
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
        assert data["condition"] == "Used"
        assert data["notification_email"] == "test@example.com"

    def test_empty_string_make_stored_as_null(self, client):
        r = client.post("/api/watchlist", json={"name": "Test", "make": ""})
        assert r.status_code == 200
        assert r.json()["make"] is None

    def test_empty_string_model_stored_as_null(self, client):
        r = client.post("/api/watchlist", json={"name": "Test", "model": ""})
        assert r.json()["model"] is None

    def test_created_alert_appears_in_list(self, client):
        client.post("/api/watchlist", json={"name": "Persisted Alert"})
        r = client.get("/api/watchlist")
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Persisted Alert"

    def test_create_returns_match_count(self, client, db_session):
        _vehicle(db_session, "T1", make="Toyota")
        r = client.post("/api/watchlist", json={"name": "Toyota Watch", "make": "Toyota"})
        assert r.json()["match_count"] == 1

    def test_create_alert_timestamps(self, client):
        r = client.post("/api/watchlist", json={"name": "Time Test"})
        data = r.json()
        assert data["created_at"] is not None
        assert data["last_triggered"] is None
        assert data["trigger_count"] == 0


# ===========================================================================
# PUT /api/watchlist/{alert_id}
# ===========================================================================

class TestUpdateWatchlist:

    def test_update_name(self, client, db_session):
        alert = _alert(db_session, name="Original")
        r = client.put(f"/api/watchlist/{alert.id}", json={"name": "Updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated"

    def test_update_is_active_false(self, client, db_session):
        alert = _alert(db_session, is_active=True)
        r = client.put(f"/api/watchlist/{alert.id}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_update_is_active_true(self, client, db_session):
        alert = _alert(db_session, is_active=False)
        r = client.put(f"/api/watchlist/{alert.id}", json={"is_active": True})
        assert r.json()["is_active"] is True

    def test_update_price_filters(self, client, db_session):
        alert = _alert(db_session, name="Price Test")
        r = client.put(f"/api/watchlist/{alert.id}",
                       json={"max_price": 30000.0, "min_price": 10000.0})
        assert r.json()["max_price"] == 30000.0
        assert r.json()["min_price"] == 10000.0

    def test_update_make_filter(self, client, db_session):
        alert = _alert(db_session, make=None)
        r = client.put(f"/api/watchlist/{alert.id}", json={"make": "Honda"})
        assert r.json()["make"] == "Honda"

    def test_update_notification_email(self, client, db_session):
        alert = _alert(db_session)
        r = client.put(f"/api/watchlist/{alert.id}",
                       json={"notification_email": "new@example.com"})
        assert r.json()["notification_email"] == "new@example.com"

    def test_update_preserves_unmodified_fields(self, client, db_session):
        alert = _alert(db_session, name="Keep Name", make="Toyota", max_price=30000.0)
        r = client.put(f"/api/watchlist/{alert.id}", json={"is_active": False})
        data = r.json()
        assert data["name"] == "Keep Name"
        assert data["make"] == "Toyota"
        assert data["max_price"] == 30000.0

    def test_update_returns_updated_match_count(self, client, db_session):
        alert = _alert(db_session, make="Toyota")
        _vehicle(db_session, "T1", make="Toyota", price=22000.0)
        _vehicle(db_session, "T2", make="Toyota", price=35000.0)

        # Before: both match
        assert client.get("/api/watchlist").json()[0]["match_count"] == 2

        # After adding price ceiling: only T1 matches
        r = client.put(f"/api/watchlist/{alert.id}", json={"max_price": 25000.0})
        assert r.json()["match_count"] == 1

    def test_update_nonexistent_alert_returns_404(self, client):
        r = client.put("/api/watchlist/99999", json={"name": "Ghost"})
        assert r.status_code == 404


# ===========================================================================
# DELETE /api/watchlist/{alert_id}
# ===========================================================================

class TestDeleteWatchlist:

    def test_delete_existing_alert_returns_ok(self, client, db_session):
        alert = _alert(db_session, name="To Delete")
        r = client.delete(f"/api/watchlist/{alert.id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_deleted_alert_not_in_list(self, client, db_session):
        alert = _alert(db_session, name="Gone")
        client.delete(f"/api/watchlist/{alert.id}")
        assert client.get("/api/watchlist").json() == []

    def test_delete_one_of_many_leaves_others(self, client, db_session):
        a1 = _alert(db_session, name="Keep")
        a2 = _alert(db_session, name="Delete")
        client.delete(f"/api/watchlist/{a2.id}")
        alerts = client.get("/api/watchlist").json()
        assert len(alerts) == 1
        assert alerts[0]["name"] == "Keep"

    def test_delete_nonexistent_alert_returns_404(self, client):
        r = client.delete("/api/watchlist/99999")
        assert r.status_code == 404


# ===========================================================================
# vehicle_matches_alert() — unit tests (no HTTP, no DB)
# ===========================================================================

class TestVehicleMatchesAlertLogic:
    """Direct unit tests for the alerts.vehicle_matches_alert() function."""

    def test_no_criteria_matches_any_vehicle(self):
        assert vehicle_matches_alert(_mem_vehicle(), _mem_alert()) is True

    def test_make_match_case_insensitive(self):
        assert vehicle_matches_alert(
            _mem_vehicle(make="Toyota"), _mem_alert(make="toyota")
        ) is True

    def test_make_no_match(self):
        assert vehicle_matches_alert(
            _mem_vehicle(make="Toyota"), _mem_alert(make="Honda")
        ) is False

    def test_model_partial_match(self):
        assert vehicle_matches_alert(
            _mem_vehicle(model="Camry"), _mem_alert(model="cam")
        ) is True

    def test_model_no_match(self):
        assert vehicle_matches_alert(
            _mem_vehicle(model="Camry"), _mem_alert(model="Accord")
        ) is False

    def test_max_price_passes_when_at_limit(self):
        assert vehicle_matches_alert(
            _mem_vehicle(price=28500.0), _mem_alert(max_price=28500.0)
        ) is True

    def test_max_price_fails_when_over(self):
        assert vehicle_matches_alert(
            _mem_vehicle(price=30000.0), _mem_alert(max_price=25000.0)
        ) is False

    def test_min_price_fails_when_under(self):
        assert vehicle_matches_alert(
            _mem_vehicle(price=20000.0), _mem_alert(min_price=25000.0)
        ) is False

    def test_min_price_passes_when_at_or_above(self):
        assert vehicle_matches_alert(
            _mem_vehicle(price=25000.0), _mem_alert(min_price=25000.0)
        ) is True

    def test_max_mileage_fails_when_over(self):
        assert vehicle_matches_alert(
            _mem_vehicle(mileage=80000), _mem_alert(max_mileage=50000)
        ) is False

    def test_max_mileage_passes_at_boundary(self):
        assert vehicle_matches_alert(
            _mem_vehicle(mileage=50000), _mem_alert(max_mileage=50000)
        ) is True

    def test_min_year_fails_when_below(self):
        assert vehicle_matches_alert(
            _mem_vehicle(year=2019), _mem_alert(min_year=2020)
        ) is False

    def test_max_year_fails_when_above(self):
        assert vehicle_matches_alert(
            _mem_vehicle(year=2025), _mem_alert(max_year=2023)
        ) is False

    def test_condition_case_insensitive(self):
        assert vehicle_matches_alert(
            _mem_vehicle(condition="used"), _mem_alert(condition="USED")
        ) is True

    def test_condition_no_match(self):
        assert vehicle_matches_alert(
            _mem_vehicle(condition="Used"), _mem_alert(condition="New")
        ) is False

    def test_null_price_skips_price_check(self):
        """Vehicle with no price should not crash the matcher."""
        result = vehicle_matches_alert(
            _mem_vehicle(price=None), _mem_alert(max_price=30000.0)
        )
        assert isinstance(result, bool)

    def test_multiple_criteria_all_must_pass(self):
        alert = _mem_alert(make="Toyota", max_price=30000.0, min_year=2020)
        assert vehicle_matches_alert(
            _mem_vehicle(make="Toyota", price=25000.0, year=2022), alert
        ) is True
        assert vehicle_matches_alert(
            _mem_vehicle(make="Honda", price=25000.0, year=2022), alert
        ) is False
        assert vehicle_matches_alert(
            _mem_vehicle(make="Toyota", price=45000.0, year=2022), alert
        ) is False
        assert vehicle_matches_alert(
            _mem_vehicle(make="Toyota", price=25000.0, year=2018), alert
        ) is False


# ===========================================================================
# get_matching_vehicles() — unit tests against real DB session
# ===========================================================================

class TestGetMatchingVehicles:

    def test_empty_db_returns_empty_list(self, db_session):
        alert = _alert(db_session, make="Toyota")
        assert get_matching_vehicles(alert, db_session) == []

    def test_returns_only_active_matching_vehicles(self, db_session):
        alert = _alert(db_session, make="Toyota")
        _vehicle(db_session, "T1", make="Toyota", is_active=True)
        _vehicle(db_session, "T2", make="Toyota", is_active=True)
        _vehicle(db_session, "T3", make="Toyota", is_active=False)
        result = get_matching_vehicles(alert, db_session)
        assert len(result) == 2

    def test_no_criteria_matches_all_active(self, db_session):
        alert = _alert(db_session, name="All Vehicles")
        _vehicle(db_session, "T1")
        _vehicle(db_session, "H1", make="Honda")
        _vehicle(db_session, "INACT", is_active=False)
        result = get_matching_vehicles(alert, db_session)
        assert len(result) == 2

    def test_price_ceiling_filter(self, db_session):
        alert = _alert(db_session, max_price=25000.0)
        _vehicle(db_session, "CHEAP", price=20000.0)
        _vehicle(db_session, "EXPENSIVE", price=40000.0)
        result = get_matching_vehicles(alert, db_session)
        assert len(result) == 1
        assert result[0].stock_number == "CHEAP"


# ===========================================================================
# Dealer-scoped watchlist alerts — Sprint 1 (xfail)
# ===========================================================================

class TestDealerScopedWatchlist:
    """
    Tests for dealer-scoped watchlist alerts.

    When alert.dealer_id is set:
      - Only vehicles from that dealer trigger the alert
    When alert.dealer_id is None:
      - Vehicles from any dealer match (existing behaviour preserved)
    """

    def test_api_post_accepts_dealer_id_field(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        r = client.post("/api/watchlist", json={
            "name": "MoG BMW Watch",
            "make": "BMW",
            "dealer_id": 323,
        })
        assert r.status_code == 200
        assert r.json()["dealer_id"] == 323

    def test_api_response_includes_dealer_id(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _alert(db_session, name="Scoped Alert", dealer_id=323,
               location_name="ALM Mall of Georgia")
        alerts = client.get("/api/watchlist").json()
        assert "dealer_id" in alerts[0]
        assert alerts[0]["dealer_id"] == 323

    def test_scoped_alert_match_count_excludes_other_dealers(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _vehicle(db_session, "MOG_TOYOTA", make="Toyota", dealer_id=323,
                 location_name="ALM Mall of Georgia")
        _vehicle(db_session, "RWL_TOYOTA", make="Toyota", dealer_id=401,
                 location_name="ALM Roswell")

        # Alert scoped to dealer 323 only
        _alert(db_session, name="MoG Toyota Alert", make="Toyota", dealer_id=323)

        alerts = client.get("/api/watchlist").json()
        # Only the MOG vehicle should be counted
        assert alerts[0]["match_count"] == 1

    def test_unscoped_alert_matches_all_dealers(self, db_session):
        """alert.dealer_id=None should match vehicles from all dealers."""
        alert = _alert(db_session, make="Toyota", dealer_id=None)
        _vehicle(db_session, "MOG_T", make="Toyota", dealer_id=323)
        _vehicle(db_session, "RWL_T", make="Toyota", dealer_id=401)

        result = get_matching_vehicles(alert, db_session)
        assert len(result) == 2

    def test_dealer_scoped_alert_does_not_match_other_dealer(self, db_session):
        """alert.dealer_id=323 must not match dealer 401 vehicles."""
        alert = _alert(db_session, make="Toyota", dealer_id=323)
        _vehicle(db_session, "MOG_T", make="Toyota", dealer_id=323)
        _vehicle(db_session, "RWL_T", make="Toyota", dealer_id=401)

        result = get_matching_vehicles(alert, db_session)
        assert len(result) == 1
        assert result[0].dealer_id == 323

    def test_update_alert_can_set_dealer_id(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        alert = _alert(db_session, name="Previously Unscoped")

        r = client.put(f"/api/watchlist/{alert.id}", json={"dealer_id": 323})
        assert r.status_code == 200
        assert r.json()["dealer_id"] == 323

    def test_update_alert_can_clear_dealer_id(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        alert = _alert(db_session, dealer_id=323)

        r = client.put(f"/api/watchlist/{alert.id}", json={"dealer_id": None})
        assert r.status_code == 200
        assert r.json()["dealer_id"] is None
