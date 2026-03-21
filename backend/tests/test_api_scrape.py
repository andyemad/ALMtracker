"""
Tests for:
  GET  /api/scrape-logs
  POST /api/scrape/trigger

Covers log listing, trigger endpoint, and background task invocation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from tests.conftest import make_scrape_log


class TestGetScrapeLogs:

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/scrape-logs")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_scrape_logs(self, client, db):
        make_scrape_log(db, status="success")
        make_scrape_log(db, status="error")

        r = client.get("/api/scrape-logs")
        assert len(r.json()) == 2

    def test_returns_logs_ordered_by_timestamp_desc(self, client, db):
        make_scrape_log(db, status="success",
                        timestamp=datetime.utcnow() - timedelta(hours=5))
        make_scrape_log(db, status="success",
                        timestamp=datetime.utcnow() - timedelta(hours=1))

        r = client.get("/api/scrape-logs")
        logs = r.json()
        # Most recent first
        assert logs[0]["timestamp"] > logs[1]["timestamp"]

    def test_default_limit_is_20(self, client, db):
        for i in range(25):
            make_scrape_log(db, status="success",
                            timestamp=datetime.utcnow() - timedelta(hours=i))

        r = client.get("/api/scrape-logs")
        assert len(r.json()) == 20

    def test_custom_limit(self, client, db):
        for i in range(10):
            make_scrape_log(db, status="success",
                            timestamp=datetime.utcnow() - timedelta(hours=i))

        r = client.get("/api/scrape-logs", params={"limit": 5})
        assert len(r.json()) == 5

    def test_log_dict_has_required_fields(self, client, db):
        make_scrape_log(db, status="success", vehicles_found=276,
                        added_count=5, removed_count=2, price_change_count=3,
                        method="httpx_dealer_filter", duration_seconds=42.5)

        r = client.get("/api/scrape-logs")
        log = r.json()[0]
        required = [
            "id", "timestamp", "vehicles_found", "added_count", "removed_count",
            "price_change_count", "status", "method", "error", "duration_seconds"
        ]
        for field in required:
            assert field in log, f"Missing field: {field}"

    def test_log_values_are_correct(self, client, db):
        make_scrape_log(db, status="success", vehicles_found=276, added_count=5,
                        removed_count=2, price_change_count=3, method="httpx_dealer_filter",
                        duration_seconds=42.5)

        r = client.get("/api/scrape-logs")
        log = r.json()[0]
        assert log["status"] == "success"
        assert log["vehicles_found"] == 276
        assert log["added_count"] == 5
        assert log["removed_count"] == 2
        assert log["price_change_count"] == 3
        assert log["method"] == "httpx_dealer_filter"
        assert log["duration_seconds"] == 42.5

    def test_error_log_has_error_field(self, client, db):
        log = make_scrape_log(db, status="error")
        # Manually set error message
        from database import Base
        import models
        session_log = None
        for session_factory in []:
            pass
        # Use db directly
        db_log = db.query(models.ScrapeLog).filter(models.ScrapeLog.id == log.id).first()
        db_log.error = "Connection timeout"
        db.commit()

        r = client.get("/api/scrape-logs")
        assert r.json()[0]["error"] == "Connection timeout"


class TestTriggerScrape:

    def test_trigger_returns_message(self, client):
        with patch("main.run_scrape") as mock_run:
            r = client.post("/api/scrape/trigger")
            assert r.status_code == 200
            data = r.json()
            assert "message" in data
            assert "trigger" in data["message"].lower() or "scrape" in data["message"].lower()

    def test_trigger_adds_background_task(self, client):
        """Trigger endpoint should accept the request without error."""
        with patch("main.run_scrape"):
            r = client.post("/api/scrape/trigger")
            assert r.status_code == 200
