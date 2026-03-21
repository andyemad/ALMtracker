"""
test_events.py — Tests for GET /api/events

Covers:
  - Default 30-day window filtering
  - event_type filter (added, removed, price_change)
  - Custom days window
  - Pagination (page, page_size)
  - Response shape and field values
  - Ordering (newest first)
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
# Helper
# ---------------------------------------------------------------------------

def _event(db, stock_number="EVT001", event_type="added",
           description="Test event", old_value=None, new_value=None,
           make="Toyota", model="Camry", year=2022, price=25000.0,
           timestamp=None, dealer_id=None, location_name=None):
    e = models.VehicleEvent(
        stock_number=stock_number,
        vin="",
        event_type=event_type,
        description=description,
        old_value=old_value,
        new_value=new_value,
        make=make,
        model=model,
        year=year,
        price=price,
        timestamp=timestamp or datetime.utcnow(),
        dealer_id=dealer_id,
        location_name=location_name,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# ===========================================================================
# GET /api/events — current behaviour
# ===========================================================================

class TestListEvents:
    """Tests for GET /api/events — filtering, pagination, response shape."""

    # ── Empty state ────────────────────────────────────────────────────────

    def test_empty_db_returns_empty_paginated_response(self, client):
        r = client.get("/api/events")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["data"] == []

    # ── Response shape ─────────────────────────────────────────────────────

    def test_event_dict_has_all_required_fields(self, client, db_session):
        _event(db_session, stock_number="SHAPE",
               event_type="added", description="Added 2022 Toyota Camry",
               old_value=None, new_value=None, price=28500.0)
        r = client.get("/api/events")
        e = r.json()["data"][0]
        required = [
            "id", "stock_number", "vin", "event_type", "description",
            "old_value", "new_value", "timestamp", "year", "make",
            "model", "trim", "price",
        ]
        for field in required:
            assert field in e, f"Event response missing field: {field}"

    # ── Date window filter ─────────────────────────────────────────────────

    def test_default_30_day_window_excludes_old_events(self, client, db_session):
        _event(db_session, stock_number="RECENT",
               timestamp=datetime.utcnow() - timedelta(days=10))
        _event(db_session, stock_number="OLD",
               timestamp=datetime.utcnow() - timedelta(days=40))
        r = client.get("/api/events")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "RECENT"

    def test_events_exactly_30_days_old_are_excluded(self, client, db_session):
        # Exactly 30 days ago — the window is "since = now - 30 days",
        # so events at the exact boundary may be excluded depending on
        # microsecond precision.  We test 31 days to confirm exclusion.
        _event(db_session, stock_number="BORDER",
               timestamp=datetime.utcnow() - timedelta(days=31))
        assert client.get("/api/events").json()["total"] == 0

    def test_custom_days_window_7_days(self, client, db_session):
        _event(db_session, stock_number="IN",
               timestamp=datetime.utcnow() - timedelta(days=3))
        _event(db_session, stock_number="OUT",
               timestamp=datetime.utcnow() - timedelta(days=10))
        r = client.get("/api/events", params={"days": 7})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "IN"

    def test_custom_days_window_1_day(self, client, db_session):
        _event(db_session, stock_number="HOURS_AGO",
               timestamp=datetime.utcnow() - timedelta(hours=2))
        _event(db_session, stock_number="DAYS_AGO",
               timestamp=datetime.utcnow() - timedelta(days=2))
        r = client.get("/api/events", params={"days": 1})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "HOURS_AGO"

    def test_large_days_window_includes_old_events(self, client, db_session):
        _event(db_session, stock_number="VERY_OLD",
               timestamp=datetime.utcnow() - timedelta(days=200))
        r = client.get("/api/events", params={"days": 365})
        assert r.json()["total"] == 1

    # ── event_type filter ──────────────────────────────────────────────────

    def test_filter_by_event_type_added(self, client, db_session):
        _event(db_session, stock_number="A1", event_type="added")
        _event(db_session, stock_number="R1", event_type="removed")
        _event(db_session, stock_number="P1", event_type="price_change")
        r = client.get("/api/events", params={"event_type": "added"})
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["event_type"] == "added"

    def test_filter_by_event_type_removed(self, client, db_session):
        _event(db_session, stock_number="A1", event_type="added")
        _event(db_session, stock_number="R1", event_type="removed")
        r = client.get("/api/events", params={"event_type": "removed"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["event_type"] == "removed"

    def test_removed_event_hidden_if_same_vin_is_currently_active(self, client, db_session):
        db_session.add(models.Vehicle(
            stock_number="ACTIVE1",
            vin="VIN-TRANSFER-1",
            dealer_id=324,
            location_name="ALM Marietta",
            year=2024,
            make="BMW",
            model="7 Series",
            trim="740i",
            price=57164.0,
            mileage=12000,
            exterior_color="Black",
            interior_color="Black",
            body_style="Sedan",
            condition="used",
            fuel_type="Gasoline",
            transmission="Automatic",
            image_url="",
            listing_url="",
            is_active=True,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
        ))
        db_session.commit()

        _event(
            db_session,
            stock_number="OLD1",
            vin="VIN-TRANSFER-1",
            event_type="removed",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            description="Removed: 2024 BMW 7 Series 740i",
        )

        r = client.get("/api/events", params={"event_type": "removed"})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_removed_event_visible_if_unit_is_not_active_anywhere(self, client, db_session):
        _event(
            db_session,
            stock_number="GONE1",
            vin="VIN-GONE-1",
            event_type="removed",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            description="Removed: 2024 Nissan Rogue SV",
        )

        r = client.get("/api/events", params={"event_type": "removed"})
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "GONE1"

    def test_filter_by_event_type_price_change(self, client, db_session):
        _event(db_session, stock_number="P1", event_type="price_change",
               old_value="30000", new_value="27500")
        r = client.get("/api/events", params={"event_type": "price_change"})
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["old_value"] == "30000"
        assert data[0]["new_value"] == "27500"

    def test_no_event_type_filter_returns_all_types(self, client, db_session):
        _event(db_session, stock_number="A1", event_type="added")
        _event(db_session, stock_number="R1", event_type="removed")
        _event(db_session, stock_number="P1", event_type="price_change")
        assert client.get("/api/events").json()["total"] == 3

    def test_unknown_event_type_returns_empty(self, client, db_session):
        _event(db_session, stock_number="A1", event_type="added")
        r = client.get("/api/events", params={"event_type": "unknown_type"})
        assert r.json()["total"] == 0

    # ── Ordering ───────────────────────────────────────────────────────────

    def test_events_ordered_newest_first(self, client, db_session):
        _event(db_session, stock_number="OLD",
               timestamp=datetime.utcnow() - timedelta(hours=5))
        _event(db_session, stock_number="NEW",
               timestamp=datetime.utcnow() - timedelta(hours=1))
        data = client.get("/api/events").json()["data"]
        assert data[0]["stock_number"] == "NEW"
        assert data[1]["stock_number"] == "OLD"

    # ── Pagination ─────────────────────────────────────────────────────────

    def test_pagination_total_and_items_per_page(self, client, db_session):
        for i in range(10):
            _event(db_session, stock_number=f"EVT{i:03d}")
        r = client.get("/api/events", params={"page": 1, "page_size": 3})
        body = r.json()
        assert body["total"] == 10
        assert len(body["data"]) == 3

    def test_pagination_page_2_different_items(self, client, db_session):
        for i in range(6):
            _event(db_session, stock_number=f"EVT{i:03d}",
                   timestamp=datetime.utcnow() - timedelta(seconds=i))
        p1 = client.get("/api/events", params={"page": 1, "page_size": 3}).json()["data"]
        p2 = client.get("/api/events", params={"page": 2, "page_size": 3}).json()["data"]
        ids_p1 = {e["id"] for e in p1}
        ids_p2 = {e["id"] for e in p2}
        assert ids_p1.isdisjoint(ids_p2)

    def test_pagination_beyond_last_page_returns_empty(self, client, db_session):
        _event(db_session)
        r = client.get("/api/events", params={"page": 999, "page_size": 50})
        assert r.status_code == 200
        assert r.json()["data"] == []

    # ── Price change event values ──────────────────────────────────────────

    def test_price_change_stores_old_and_new_values(self, client, db_session):
        _event(db_session, stock_number="PC1", event_type="price_change",
               old_value="35000", new_value="29999",
               description="Price change: 2022 Toyota Camry")
        r = client.get("/api/events", params={"event_type": "price_change"})
        e = r.json()["data"][0]
        assert e["old_value"] == "35000"
        assert e["new_value"] == "29999"
        assert e["description"] == "Price change: 2022 Toyota Camry"

    def test_added_event_old_and_new_values_are_null(self, client, db_session):
        _event(db_session, stock_number="A1", event_type="added",
               old_value=None, new_value=None)
        e = client.get("/api/events").json()["data"][0]
        assert e["old_value"] is None
        assert e["new_value"] is None

    # ── Vehicle snapshot fields ────────────────────────────────────────────

    def test_event_contains_vehicle_snapshot_fields(self, client, db_session):
        _event(db_session, stock_number="SNAP1",
               year=2023, make="Honda", model="Accord",
               price=32000.0)
        e = client.get("/api/events").json()["data"][0]
        assert e["year"] == 2023
        assert e["make"] == "Honda"
        assert e["model"] == "Accord"
        assert e["price"] == 32000.0


# ===========================================================================
# GET /api/events?dealer_id=N — Sprint 1 feature (xfail)
# ===========================================================================

class TestListEventsDealerIdFilter:
    """Tests for the dealer_id filter on GET /api/events."""

    def test_dealer_id_filter_returns_only_that_dealers_events(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _event(db_session, stock_number="MOG1", dealer_id=323, event_type="added")
        _event(db_session, stock_number="MOG2", dealer_id=323, event_type="removed")
        _event(db_session, stock_number="RWL1", dealer_id=401, event_type="added")

        r = client.get("/api/events", params={"dealer_id": 323})
        assert r.status_code == 200
        data = r.json()["data"]
        assert r.json()["total"] == 2
        assert all(e["dealer_id"] == 323 for e in data)

    def test_no_dealer_id_returns_events_from_all_dealers(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _event(db_session, stock_number="MOG1", dealer_id=323)
        _event(db_session, stock_number="RWL1", dealer_id=401)

        assert client.get("/api/events").json()["total"] == 2

    def test_dealer_id_filter_combined_with_event_type(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _event(db_session, stock_number="MOG_ADD", dealer_id=323, event_type="added")
        _event(db_session, stock_number="MOG_REM", dealer_id=323, event_type="removed")
        _event(db_session, stock_number="RWL_ADD", dealer_id=401, event_type="added")

        r = client.get("/api/events", params={"dealer_id": 323, "event_type": "added"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "MOG_ADD"

    def test_unknown_dealer_id_returns_empty_events(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _event(db_session, stock_number="MOG1", dealer_id=323)

        r = client.get("/api/events", params={"dealer_id": 9999})
        assert r.json()["total"] == 0

    def test_event_dict_includes_dealer_id_field(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _event(db_session, stock_number="V1", dealer_id=323,
               location_name="ALM Mall of Georgia")

        r = client.get("/api/events")
        e = r.json()["data"][0]
        assert "dealer_id" in e
        assert e["dealer_id"] == 323
