"""
test_stats.py — Tests for GET /api/stats

Covers:
  - All fields in the response with an empty database
  - total_active, added_today, removed_today, active_alerts, avg_price
  - last_scrape / last_scrape_status from ScrapeLog
  - 14-day trend data filtering (success-only, window boundary)
  - dealer_id filter — Sprint 1 feature (xfail until implemented)

Test isolation: every test gets a fresh empty in-memory DB via db_session.
"""

from datetime import datetime, timedelta

import pytest
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import models


# ---------------------------------------------------------------------------
# Helpers — create test data directly via db_session
# ---------------------------------------------------------------------------

def _add_vehicle(db, stock_number, is_active=True, price=None, dealer_id=None):
    v = models.Vehicle(
        stock_number=stock_number,
        vin=f"VIN{stock_number}",
        make="Toyota", model="Camry",
        price=price,
        is_active=is_active,
        dealer_id=dealer_id,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db.add(v)
    db.commit()
    return v


def _add_event(db, event_type, stock_number, timestamp=None, dealer_id=None):
    e = models.VehicleEvent(
        stock_number=stock_number,
        event_type=event_type,
        description=f"Test {event_type}",
        make="Toyota", model="Camry",
        dealer_id=dealer_id,
        timestamp=timestamp or datetime.utcnow(),
    )
    db.add(e)
    db.commit()
    return e


def _add_alert(db, name, is_active=True):
    a = models.WatchlistAlert(
        name=name,
        is_active=is_active,
        created_at=datetime.utcnow(),
    )
    db.add(a)
    db.commit()
    return a


def _add_scrape_log(db, status, timestamp=None, vehicles_found=0,
                   added_count=0, removed_count=0, dealer_id=None):
    log = models.ScrapeLog(
        status=status,
        timestamp=timestamp or datetime.utcnow(),
        vehicles_found=vehicles_found,
        added_count=added_count,
        removed_count=removed_count,
        dealer_id=dealer_id,
        method="httpx",
        duration_seconds=30.0,
    )
    db.add(log)
    db.commit()
    return log


# ===========================================================================
# GET /api/stats — current behaviour (no dealer_id filter)
# ===========================================================================

class TestGetStats:
    """Core tests for GET /api/stats without dealer_id filter."""

    # ── Empty database ─────────────────────────────────────────────────────

    def test_empty_db_returns_zeroed_response(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total_active"] == 0
        assert body["added_today"] == 0
        assert body["removed_today"] == 0
        assert body["active_alerts"] == 0
        assert body["avg_price"] == 0.0
        assert body["last_scrape"] is None
        assert body["last_scrape_status"] is None
        assert body["trend"] == []

    def test_response_has_all_required_keys(self, client):
        r = client.get("/api/stats")
        required = [
            "total_active", "added_today", "removed_today", "active_alerts",
            "avg_price", "last_scrape", "last_scrape_status", "trend",
        ]
        for key in required:
            assert key in r.json(), f"Stats response missing key: {key}"

    # ── total_active ───────────────────────────────────────────────────────

    def test_total_active_counts_active_vehicles_only(self, client, db_session):
        _add_vehicle(db_session, "ACT1", is_active=True)
        _add_vehicle(db_session, "ACT2", is_active=True)
        _add_vehicle(db_session, "INACT", is_active=False)
        assert client.get("/api/stats").json()["total_active"] == 2

    def test_total_active_zero_when_all_inactive(self, client, db_session):
        _add_vehicle(db_session, "INACT1", is_active=False)
        _add_vehicle(db_session, "INACT2", is_active=False)
        assert client.get("/api/stats").json()["total_active"] == 0

    # ── added_today ────────────────────────────────────────────────────────

    def test_added_today_counts_only_todays_added_events(self, client, db_session):
        _add_event(db_session, "added", "TODAY001", timestamp=datetime.utcnow())
        _add_event(db_session, "added", "TODAY002", timestamp=datetime.utcnow())
        # Yesterday — must NOT count
        _add_event(db_session, "added", "YEST001",
                   timestamp=datetime.utcnow() - timedelta(days=2))
        assert client.get("/api/stats").json()["added_today"] == 2

    def test_added_today_does_not_count_other_event_types(self, client, db_session):
        _add_event(db_session, "removed", "R001")
        _add_event(db_session, "price_change", "P001")
        assert client.get("/api/stats").json()["added_today"] == 0

    # ── removed_today ──────────────────────────────────────────────────────

    def test_removed_today_counts_only_todays_removed_events(self, client, db_session):
        _add_event(db_session, "removed", "REM001", timestamp=datetime.utcnow())
        _add_event(db_session, "removed", "REM002",
                   timestamp=datetime.utcnow() - timedelta(days=2))
        assert client.get("/api/stats").json()["removed_today"] == 1

    # ── active_alerts ──────────────────────────────────────────────────────

    def test_active_alerts_counts_only_is_active_true_alerts(self, client, db_session):
        _add_alert(db_session, "Active 1", is_active=True)
        _add_alert(db_session, "Active 2", is_active=True)
        _add_alert(db_session, "Inactive", is_active=False)
        assert client.get("/api/stats").json()["active_alerts"] == 2

    def test_active_alerts_zero_when_no_alerts(self, client):
        assert client.get("/api/stats").json()["active_alerts"] == 0

    # ── avg_price ──────────────────────────────────────────────────────────

    def test_avg_price_calculated_from_active_vehicles(self, client, db_session):
        _add_vehicle(db_session, "V1", price=20000.0, is_active=True)
        _add_vehicle(db_session, "V2", price=30000.0, is_active=True)
        _add_vehicle(db_session, "V_INACTIVE", price=40000.0, is_active=False)
        assert client.get("/api/stats").json()["avg_price"] == 25000.0

    def test_avg_price_ignores_null_prices(self, client, db_session):
        _add_vehicle(db_session, "V1", price=20000.0, is_active=True)
        _add_vehicle(db_session, "V_NULL", price=None, is_active=True)
        assert client.get("/api/stats").json()["avg_price"] == 20000.0

    def test_avg_price_zero_when_no_active_vehicles(self, client):
        assert client.get("/api/stats").json()["avg_price"] == 0.0

    def test_avg_price_rounded_to_two_decimal_places(self, client, db_session):
        # 10000 + 20000 + 30001 = 60001 / 3 = 20000.333...
        _add_vehicle(db_session, "V1", price=10000.0)
        _add_vehicle(db_session, "V2", price=20000.0)
        _add_vehicle(db_session, "V3", price=30001.0)
        avg = client.get("/api/stats").json()["avg_price"]
        assert isinstance(avg, float)
        # Should be rounded; verify it's a reasonable float (not raw fraction)
        assert abs(avg - 20000.33) < 0.01

    # ── last_scrape ────────────────────────────────────────────────────────

    def test_last_scrape_is_most_recent_log(self, client, db_session):
        _add_scrape_log(db_session, "success",
                        timestamp=datetime.utcnow() - timedelta(hours=5))
        _add_scrape_log(db_session, "success",
                        timestamp=datetime.utcnow() - timedelta(minutes=30))
        body = client.get("/api/stats").json()
        assert body["last_scrape"] is not None
        assert body["last_scrape_status"] == "success"

    def test_last_scrape_includes_error_status(self, client, db_session):
        _add_scrape_log(db_session, "error",
                        timestamp=datetime.utcnow() - timedelta(hours=1))
        body = client.get("/api/stats").json()
        assert body["last_scrape_status"] == "error"

    def test_last_scrape_picks_most_recent_of_any_status(self, client, db_session):
        _add_scrape_log(db_session, "success",
                        timestamp=datetime.utcnow() - timedelta(hours=4))
        _add_scrape_log(db_session, "error",
                        timestamp=datetime.utcnow() - timedelta(hours=1))
        body = client.get("/api/stats").json()
        # Most recent is the error log
        assert body["last_scrape_status"] == "error"

    # ── trend ──────────────────────────────────────────────────────────────

    def test_trend_contains_only_last_14_days(self, client, db_session):
        # 7 days ago — should appear
        _add_scrape_log(db_session, "success", vehicles_found=276,
                        timestamp=datetime.utcnow() - timedelta(days=7))
        # 20 days ago — should NOT appear
        _add_scrape_log(db_session, "success", vehicles_found=280,
                        timestamp=datetime.utcnow() - timedelta(days=20))
        trend = client.get("/api/stats").json()["trend"]
        assert len(trend) == 1

    def test_trend_excludes_error_status_logs(self, client, db_session):
        _add_scrape_log(db_session, "success",
                        timestamp=datetime.utcnow() - timedelta(hours=1))
        _add_scrape_log(db_session, "error",
                        timestamp=datetime.utcnow() - timedelta(hours=2))
        trend = client.get("/api/stats").json()["trend"]
        assert len(trend) == 1

    def test_trend_entry_has_date_count_added_removed(self, client, db_session):
        _add_scrape_log(db_session, "success", vehicles_found=276,
                        added_count=5, removed_count=2,
                        timestamp=datetime.utcnow() - timedelta(hours=1))
        entry = client.get("/api/stats").json()["trend"][0]
        assert "date" in entry
        assert "count" in entry
        assert "added" in entry
        assert "removed" in entry
        assert entry["count"] == 276
        assert entry["added"] == 5
        assert entry["removed"] == 2

    def test_trend_is_ordered_oldest_first(self, client, db_session):
        _add_scrape_log(db_session, "success", vehicles_found=100,
                        timestamp=datetime.utcnow() - timedelta(hours=10))
        _add_scrape_log(db_session, "success", vehicles_found=200,
                        timestamp=datetime.utcnow() - timedelta(hours=2))
        trend = client.get("/api/stats").json()["trend"]
        assert trend[0]["count"] == 100
        assert trend[1]["count"] == 200

    def test_trend_date_format_is_mm_dd(self, client, db_session):
        _add_scrape_log(db_session, "success",
                        timestamp=datetime.utcnow() - timedelta(hours=1))
        entry = client.get("/api/stats").json()["trend"][0]
        # Format should be MM/DD, e.g. "03/10"
        date_str = entry["date"]
        assert "/" in date_str
        parts = date_str.split("/")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)


# ===========================================================================
# GET /api/stats?dealer_id=N — Sprint 1 feature (xfail)
# ===========================================================================

class TestGetStatsDealerIdFilter:
    """
    Tests for GET /api/stats?dealer_id=N.

    When dealer_id is provided:
      - All counts filter to that dealer's vehicles/events
      - Response includes dealer_id and location_name fields
    When omitted:
      - Aggregates across all dealers (backward-compatible)
    """

    def test_total_active_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _add_vehicle(db_session, "MOG1", dealer_id=323, is_active=True)
        _add_vehicle(db_session, "MOG2", dealer_id=323, is_active=True)
        _add_vehicle(db_session, "RWL1", dealer_id=401, is_active=True)
        _add_vehicle(db_session, "RWL2", dealer_id=401, is_active=True)
        _add_vehicle(db_session, "RWL3", dealer_id=401, is_active=True)

        assert client.get("/api/stats", params={"dealer_id": 323}).json()["total_active"] == 2
        assert client.get("/api/stats", params={"dealer_id": 401}).json()["total_active"] == 3

    def test_added_today_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _add_event(db_session, "added", "MOG1", dealer_id=323)
        _add_event(db_session, "added", "MOG2", dealer_id=323)
        _add_event(db_session, "added", "RWL1", dealer_id=401)

        assert client.get("/api/stats", params={"dealer_id": 323}).json()["added_today"] == 2
        assert client.get("/api/stats", params={"dealer_id": 401}).json()["added_today"] == 1

    def test_removed_today_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _add_event(db_session, "removed", "MOG1", dealer_id=323)
        _add_event(db_session, "removed", "RWL1", dealer_id=401)

        assert client.get("/api/stats", params={"dealer_id": 323}).json()["removed_today"] == 1

    def test_avg_price_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _add_vehicle(db_session, "MOG1", dealer_id=323, price=20000.0)
        _add_vehicle(db_session, "MOG2", dealer_id=323, price=30000.0)
        _add_vehicle(db_session, "RWL1", dealer_id=401, price=100000.0)

        avg = client.get("/api/stats", params={"dealer_id": 323}).json()["avg_price"]
        assert avg == 25000.0

    def test_response_includes_dealer_id_field(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        body = client.get("/api/stats", params={"dealer_id": 323}).json()
        assert "dealer_id" in body
        assert body["dealer_id"] == 323

    def test_response_includes_location_name_field(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        body = client.get("/api/stats", params={"dealer_id": 323}).json()
        assert "location_name" in body
        assert body["location_name"] == "ALM Mall of Georgia"

    def test_no_dealer_id_aggregates_all_dealers(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _add_vehicle(db_session, "MOG1", dealer_id=323, is_active=True)
        _add_vehicle(db_session, "RWL1", dealer_id=401, is_active=True)

        body = client.get("/api/stats").json()
        # Without dealer_id, should count both dealers
        assert body["total_active"] == 2

    def test_no_dealer_id_response_has_null_dealer_id(self, client):
        body = client.get("/api/stats").json()
        # When no dealer_id filter, response should indicate null/all-locations
        assert body.get("dealer_id") is None

    def test_no_dealer_id_location_name_is_all_locations(self, client):
        body = client.get("/api/stats").json()
        assert body.get("location_name") == "All Locations"

    def test_unknown_dealer_id_returns_zeroed_stats(self, client, db_session, make_dealer):
        # dealer_id=9999 exists as a filter value but no vehicles/events for it
        make_dealer(id=323, name="ALM Mall of Georgia")
        _add_vehicle(db_session, "V1", dealer_id=323, is_active=True)

        body = client.get("/api/stats", params={"dealer_id": 9999}).json()
        assert body["total_active"] == 0
        assert body["added_today"] == 0
