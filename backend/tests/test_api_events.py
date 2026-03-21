"""
Tests for GET /api/events

Covers:
- Default query (30-day window)
- Filtering by event_type
- Date window filtering (days parameter)
- Pagination
- Response shape validation
"""

import pytest
from datetime import datetime, timedelta
from tests.conftest import make_vehicle_event


class TestListEvents:

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/events")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["data"] == []

    def test_returns_events_within_default_30_day_window(self, client, db):
        # Within 30 days
        make_vehicle_event(db, stock_number="RECENT",
                           timestamp=datetime.utcnow() - timedelta(days=10))
        # Outside 30 days — should NOT appear
        make_vehicle_event(db, stock_number="OLD",
                           timestamp=datetime.utcnow() - timedelta(days=40))

        r = client.get("/api/events")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "RECENT"

    def test_filter_by_event_type_added(self, client, db):
        make_vehicle_event(db, stock_number="A1", event_type="added")
        make_vehicle_event(db, stock_number="R1", event_type="removed")
        make_vehicle_event(db, stock_number="P1", event_type="price_change")

        r = client.get("/api/events", params={"event_type": "added"})
        data = r.json()["data"]
        assert all(e["event_type"] == "added" for e in data)
        assert len(data) == 1

    def test_filter_by_event_type_removed(self, client, db):
        make_vehicle_event(db, stock_number="A1", event_type="added")
        make_vehicle_event(db, stock_number="R1", event_type="removed")

        r = client.get("/api/events", params={"event_type": "removed"})
        assert r.json()["total"] == 1

    def test_filter_by_event_type_price_change(self, client, db):
        make_vehicle_event(db, stock_number="P1", event_type="price_change",
                           old_value="25000", new_value="23000")

        r = client.get("/api/events", params={"event_type": "price_change"})
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["old_value"] == "25000"
        assert data[0]["new_value"] == "23000"

    def test_custom_days_window(self, client, db):
        make_vehicle_event(db, stock_number="E1",
                           timestamp=datetime.utcnow() - timedelta(days=3))
        make_vehicle_event(db, stock_number="E2",
                           timestamp=datetime.utcnow() - timedelta(days=10))

        r = client.get("/api/events", params={"days": 7})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "E1"

    def test_events_ordered_by_timestamp_desc(self, client, db):
        make_vehicle_event(db, stock_number="OLD",
                           timestamp=datetime.utcnow() - timedelta(hours=5))
        make_vehicle_event(db, stock_number="NEW",
                           timestamp=datetime.utcnow() - timedelta(hours=1))

        r = client.get("/api/events")
        data = r.json()["data"]
        assert data[0]["stock_number"] == "NEW"
        assert data[1]["stock_number"] == "OLD"

    def test_pagination(self, client, db):
        for i in range(10):
            make_vehicle_event(db, stock_number=f"E{i:03d}")

        r = client.get("/api/events", params={"page": 1, "page_size": 3})
        assert len(r.json()["data"]) == 3
        assert r.json()["total"] == 10

    def test_event_dict_has_required_fields(self, client, db):
        make_vehicle_event(db, stock_number="SHAPE_TEST",
                           event_type="added", description="Added: 2022 Toyota Camry")

        r = client.get("/api/events")
        e = r.json()["data"][0]
        required = ["id", "stock_number", "vin", "event_type", "description",
                    "old_value", "new_value", "timestamp", "year", "make", "model",
                    "trim", "price"]
        for field in required:
            assert field in e, f"Missing field: {field}"

    def test_price_change_event_has_old_and_new_values(self, client, db):
        make_vehicle_event(db, stock_number="PC1", event_type="price_change",
                           old_value="30000", new_value="27500",
                           description="Price change: 2022 Toyota Camry")

        r = client.get("/api/events", params={"event_type": "price_change"})
        event = r.json()["data"][0]
        assert event["old_value"] == "30000"
        assert event["new_value"] == "27500"
