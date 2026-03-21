"""
test_dealers.py — Tests for the dealer registry endpoints.

Endpoints covered:
  GET /api/dealers             — list dealers, filter by is_active
  GET /api/dealers/{id}/stats  — per-dealer stats (same shape as /api/stats)

Both endpoints are NEW in the 24-location expansion (Sprint 1) and do not yet
exist in main.py.  All tests are marked xfail.  Remove the marks once
GET /api/dealers and GET /api/dealers/{id}/stats are implemented per
ARCHITECTURE.md §5.1.

Test isolation: every test receives a fresh empty DB via db_session fixture.
"""

from datetime import datetime, timedelta

import pytest
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import models


# ===========================================================================
# GET /api/dealers
# ===========================================================================

class TestListDealers:
    """Tests for GET /api/dealers."""

    # ── Empty state ────────────────────────────────────────────────────────

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/dealers")
        assert r.status_code == 200
        assert r.json() == []

    # ── Basic listing ──────────────────────────────────────────────────────

    def test_returns_all_active_dealers_by_default(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", is_active=True)
        make_dealer(id=401, name="ALM Roswell", is_active=True)
        make_dealer(id=402, name="ALM Buckhead", is_active=False)

        r = client.get("/api/dealers")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2  # default: active_only=true
        names = {d["name"] for d in data}
        assert "ALM Mall of Georgia" in names
        assert "ALM Roswell" in names
        assert "ALM Buckhead" not in names

    def test_active_only_false_returns_all_dealers(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", is_active=True)
        make_dealer(id=402, name="ALM Buckhead", is_active=False)

        r = client.get("/api/dealers", params={"active_only": False})
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_active_only_true_explicit_excludes_inactive(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Active", is_active=True)
        make_dealer(id=999, name="ALM Inactive", is_active=False)

        r = client.get("/api/dealers", params={"active_only": True})
        names = [d["name"] for d in r.json()]
        assert "ALM Active" in names
        assert "ALM Inactive" not in names

    # ── Response shape ─────────────────────────────────────────────────────

    def test_dealer_response_has_required_fields(self, client, db_session, make_dealer):
        make_dealer(
            id=323,
            name="ALM Mall of Georgia",
            city="Buford",
            state="GA",
            is_active=True,
            scrape_priority=1,
        )
        r = client.get("/api/dealers")
        assert r.status_code == 200
        d = r.json()[0]
        required = [
            "id", "name", "city", "state", "is_active",
            "scrape_priority", "last_scraped", "active_vehicle_count",
        ]
        for field in required:
            assert field in d, f"Dealer response missing field: {field}"

    def test_dealer_id_matches_overfuel_dealer_id(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        r = client.get("/api/dealers")
        assert r.json()[0]["id"] == 323

    def test_dealer_city_and_state_returned(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford", state="GA")
        d = client.get("/api/dealers").json()[0]
        assert d["city"] == "Buford"
        assert d["state"] == "GA"

    # ── active_vehicle_count ────────────────────────────────────────────────

    def test_active_vehicle_count_zero_when_no_vehicles(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        d = client.get("/api/dealers").json()[0]
        assert d["active_vehicle_count"] == 0

    def test_active_vehicle_count_counts_only_active_vehicles(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        # 3 active, 1 inactive
        for i in range(3):
            v = models.Vehicle(
                dealer_id=323, stock_number=f"ACT{i}", vin=f"VIN{i}",
                make="Toyota", model="Camry", is_active=True,
                first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
            )
            db_session.add(v)
        v_inactive = models.Vehicle(
            dealer_id=323, stock_number="INACT", vin="VININACT",
            make="Toyota", model="Camry", is_active=False,
            first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
        )
        db_session.add(v_inactive)
        db_session.commit()

        d = client.get("/api/dealers").json()[0]
        assert d["active_vehicle_count"] == 3

    def test_active_vehicle_count_is_dealer_scoped(
        self, client, db_session, make_dealer
    ):
        """Each dealer's active_vehicle_count reflects only their own vehicles."""
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        # 2 vehicles at dealer 323
        for i in range(2):
            db_session.add(models.Vehicle(
                dealer_id=323, stock_number=f"MOG{i}", vin=f"VINMOG{i}",
                make="Toyota", model="Camry", is_active=True,
                first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
            ))
        # 5 vehicles at dealer 401
        for i in range(5):
            db_session.add(models.Vehicle(
                dealer_id=401, stock_number=f"RWL{i}", vin=f"VINRWL{i}",
                make="Honda", model="Accord", is_active=True,
                first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
            ))
        db_session.commit()

        dealers = client.get("/api/dealers", params={"active_only": False}).json()
        counts = {d["id"]: d["active_vehicle_count"] for d in dealers}
        assert counts[323] == 2
        assert counts[401] == 5

    # ── Ordering ───────────────────────────────────────────────────────────

    def test_dealers_returned_in_alphabetical_order(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=401, name="ALM Roswell")
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=402, name="ALM Buckhead")

        names = [d["name"] for d in client.get("/api/dealers", params={"active_only": False}).json()]
        assert names == sorted(names)

    # ── last_scraped field ─────────────────────────────────────────────────

    def test_last_scraped_null_when_never_scraped(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", last_scraped=None)
        d = client.get("/api/dealers").json()[0]
        assert d["last_scraped"] is None

    def test_last_scraped_iso_string_when_scraped(self, client, db_session, make_dealer):
        ts = datetime.utcnow() - timedelta(hours=6)
        make_dealer(id=323, name="ALM Mall of Georgia", last_scraped=ts)
        d = client.get("/api/dealers").json()[0]
        assert d["last_scraped"] is not None
        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(d["last_scraped"])
        assert isinstance(parsed, datetime)

    # ── Single dealer with no vehicles vs with vehicles ───────────────────

    def test_single_dealer_with_vehicles(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        db_session.add(models.Vehicle(
            dealer_id=323, stock_number="V1", vin="VIN1",
            make="Toyota", model="Camry", is_active=True,
            first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
        ))
        db_session.commit()

        r = client.get("/api/dealers")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["active_vehicle_count"] == 1


# ===========================================================================
# GET /api/dealers/{dealer_id}/stats
# ===========================================================================

class TestDealerStats:
    """
    Tests for GET /api/dealers/{dealer_id}/stats.

    Response shape must match GET /api/stats but scoped to one dealer,
    with two additional fields: dealer_id and location_name.
    """

    # ── 404 for unknown dealer ─────────────────────────────────────────────

    def test_unknown_dealer_returns_404(self, client):
        r = client.get("/api/dealers/9999/stats")
        assert r.status_code == 404

    # ── Basic response shape ───────────────────────────────────────────────

    def test_response_has_all_required_fields(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        r = client.get("/api/dealers/323/stats")
        assert r.status_code == 200
        body = r.json()
        required_keys = [
            "total_active", "added_today", "removed_today", "active_alerts",
            "avg_price", "last_scrape", "last_scrape_status", "trend",
            "dealer_id", "location_name",
        ]
        for key in required_keys:
            assert key in body, f"Dealer stats missing key: {key}"

    def test_dealer_id_and_location_name_in_response(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        body = client.get("/api/dealers/323/stats").json()
        assert body["dealer_id"] == 323
        assert body["location_name"] == "ALM Mall of Georgia"

    # ── Counts are dealer-scoped ───────────────────────────────────────────

    def test_total_active_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        # 3 vehicles at dealer 323
        for i in range(3):
            db_session.add(models.Vehicle(
                dealer_id=323, stock_number=f"MOG{i}", vin=f"VINMOG{i}",
                make="Toyota", model="Camry", is_active=True,
                first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
            ))
        # 7 vehicles at dealer 401
        for i in range(7):
            db_session.add(models.Vehicle(
                dealer_id=401, stock_number=f"RWL{i}", vin=f"VINRWL{i}",
                make="Honda", model="Accord", is_active=True,
                first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
            ))
        db_session.commit()

        assert client.get("/api/dealers/323/stats").json()["total_active"] == 3
        assert client.get("/api/dealers/401/stats").json()["total_active"] == 7

    def test_added_today_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        # 2 "added" events today for dealer 323
        for i in range(2):
            e = models.VehicleEvent(
                dealer_id=323, stock_number=f"NEW{i}",
                event_type="added", description="Added",
                make="Toyota", model="Camry", timestamp=datetime.utcnow(),
            )
            db_session.add(e)
        # 5 "added" events today for dealer 401
        for i in range(5):
            e = models.VehicleEvent(
                dealer_id=401, stock_number=f"RNEW{i}",
                event_type="added", description="Added",
                make="Honda", model="Accord", timestamp=datetime.utcnow(),
            )
            db_session.add(e)
        db_session.commit()

        assert client.get("/api/dealers/323/stats").json()["added_today"] == 2
        assert client.get("/api/dealers/401/stats").json()["added_today"] == 5

    def test_avg_price_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        db_session.add(models.Vehicle(
            dealer_id=323, stock_number="V1", vin="VIN1",
            make="Toyota", model="Camry", price=20000.0, is_active=True,
            first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
        ))
        db_session.add(models.Vehicle(
            dealer_id=323, stock_number="V2", vin="VIN2",
            make="Toyota", model="Camry", price=30000.0, is_active=True,
            first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
        ))
        # Different dealer — should not affect dealer 323's avg
        db_session.add(models.Vehicle(
            dealer_id=401, stock_number="V3", vin="VIN3",
            make="Honda", model="Accord", price=100000.0, is_active=True,
            first_seen=datetime.utcnow(), last_seen=datetime.utcnow(),
        ))
        db_session.commit()

        stats = client.get("/api/dealers/323/stats").json()
        assert stats["avg_price"] == 25000.0

    # ── Zero state for brand new dealer ────────────────────────────────────

    def test_brand_new_dealer_returns_zeroed_stats(self, client, db_session, make_dealer):
        make_dealer(id=9001, name="ALM Brand New Location")
        body = client.get("/api/dealers/9001/stats").json()
        assert body["total_active"] == 0
        assert body["added_today"] == 0
        assert body["removed_today"] == 0
        assert body["avg_price"] == 0.0
        assert body["last_scrape"] is None
        assert body["trend"] == []

    # ── Trend data ─────────────────────────────────────────────────────────

    def test_trend_only_includes_dealer_scrape_logs(
        self, client, db_session, make_dealer, scrape_log_factory
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        scrape_log_factory(
            dealer_id=323, status="success", vehicles_found=276,
            timestamp=datetime.utcnow() - timedelta(hours=1),
        )
        scrape_log_factory(
            dealer_id=401, status="success", vehicles_found=150,
            timestamp=datetime.utcnow() - timedelta(hours=2),
        )

        trend = client.get("/api/dealers/323/stats").json()["trend"]
        # Only the dealer 323 log should appear in the trend
        assert len(trend) == 1
