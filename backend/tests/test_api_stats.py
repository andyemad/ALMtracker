"""
Tests for GET /api/stats

Covers:
- Empty database returns zeroed stats
- Active vehicle count
- Added/removed today counts
- Average price calculation
- Last scrape info
- Trend data (14-day rolling)
- active_alerts count
"""

import pytest
from datetime import datetime, timedelta
from tests.conftest import make_vehicle, make_vehicle_event, make_watchlist_alert, make_scrape_log


class TestGetStats:

    def test_empty_db_returns_zeroed_stats(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_active"] == 0
        assert data["added_today"] == 0
        assert data["removed_today"] == 0
        assert data["active_alerts"] == 0
        assert data["avg_price"] == 0.0
        assert data["last_scrape"] is None
        assert data["last_scrape_status"] is None
        assert data["trend"] == []

    def test_total_active_counts_only_active_vehicles(self, client, db):
        make_vehicle(db, stock_number="ACTIVE001", is_active=True)
        make_vehicle(db, stock_number="ACTIVE002", is_active=True)
        make_vehicle(db, stock_number="INACTIVE001", is_active=False)

        r = client.get("/api/stats")
        assert r.status_code == 200
        assert r.json()["total_active"] == 2

    def test_added_today_counts_only_today_events(self, client, db):
        # Added today
        make_vehicle_event(db, stock_number="NEW001", event_type="added",
                           timestamp=datetime.utcnow())
        # Added yesterday — should NOT count
        make_vehicle_event(db, stock_number="OLD001", event_type="added",
                           timestamp=datetime.utcnow() - timedelta(days=2))

        r = client.get("/api/stats")
        assert r.json()["added_today"] == 1

    def test_removed_today_counts_only_today_events(self, client, db):
        make_vehicle_event(db, stock_number="REM001", event_type="removed",
                           timestamp=datetime.utcnow())
        make_vehicle_event(db, stock_number="REM002", event_type="removed",
                           timestamp=datetime.utcnow() - timedelta(days=2))

        r = client.get("/api/stats")
        assert r.json()["removed_today"] == 1

    def test_active_alerts_count(self, client, db):
        make_watchlist_alert(db, name="Alert 1", is_active=True)
        make_watchlist_alert(db, name="Alert 2", is_active=True)
        make_watchlist_alert(db, name="Alert 3", is_active=False)

        r = client.get("/api/stats")
        assert r.json()["active_alerts"] == 2

    def test_avg_price_calculated_from_active_vehicles(self, client, db):
        make_vehicle(db, stock_number="V1", price=20000.0, is_active=True)
        make_vehicle(db, stock_number="V2", price=30000.0, is_active=True)
        make_vehicle(db, stock_number="V3", price=40000.0, is_active=False)  # excluded

        r = client.get("/api/stats")
        assert r.json()["avg_price"] == 25000.0

    def test_avg_price_ignores_null_prices(self, client, db):
        make_vehicle(db, stock_number="V1", price=20000.0, is_active=True)
        make_vehicle(db, stock_number="V2", price=None, is_active=True)

        r = client.get("/api/stats")
        assert r.json()["avg_price"] == 20000.0

    def test_last_scrape_from_most_recent_log(self, client, db):
        make_scrape_log(db, status="success",
                        timestamp=datetime.utcnow() - timedelta(hours=2))
        most_recent = make_scrape_log(db, status="success",
                                      timestamp=datetime.utcnow() - timedelta(minutes=10))

        r = client.get("/api/stats")
        data = r.json()
        assert data["last_scrape_status"] == "success"
        assert data["last_scrape"] is not None

    def test_trend_includes_only_last_14_days(self, client, db):
        # Within 14 days
        make_scrape_log(db, status="success",
                        timestamp=datetime.utcnow() - timedelta(days=7))
        # Outside 14 days — should not appear
        make_scrape_log(db, status="success",
                        timestamp=datetime.utcnow() - timedelta(days=20))

        r = client.get("/api/stats")
        trend = r.json()["trend"]
        assert len(trend) == 1

    def test_trend_only_includes_successful_scrapes(self, client, db):
        make_scrape_log(db, status="success", timestamp=datetime.utcnow() - timedelta(hours=1))
        make_scrape_log(db, status="error", timestamp=datetime.utcnow() - timedelta(hours=2))

        r = client.get("/api/stats")
        trend = r.json()["trend"]
        assert len(trend) == 1

    def test_trend_entry_has_required_fields(self, client, db):
        make_scrape_log(db, status="success", vehicles_found=276, added_count=5, removed_count=2,
                        timestamp=datetime.utcnow() - timedelta(hours=1))

        r = client.get("/api/stats")
        trend = r.json()["trend"]
        assert len(trend) == 1
        entry = trend[0]
        assert "date" in entry
        assert "count" in entry
        assert "added" in entry
        assert "removed" in entry
        assert entry["count"] == 276
        assert entry["added"] == 5
        assert entry["removed"] == 2

    def test_stats_response_shape(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        required_keys = [
            "total_active", "added_today", "removed_today", "active_alerts",
            "avg_price", "last_scrape", "last_scrape_status", "trend"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
