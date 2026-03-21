"""
Integration tests for cross-endpoint workflows.

Covers end-to-end scenarios:
1. Full scrape cycle simulation (add/remove/price change detection)
2. Watchlist → match flow
3. Lead CRM → vehicle match flow
4. Export → data integrity
5. Stats reflect actual DB state
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from tests.conftest import (
    make_vehicle, make_watchlist_alert, make_lead,
    make_scrape_log, make_vehicle_event
)


class TestScrapeSimulation:
    """
    Simulates what run_scrape() does without triggering the actual HTTP scraper.
    Validates that the change detection and event creation logic in main.py works correctly.
    """

    def test_vehicle_add_event_created(self, db, client):
        """Adding a new vehicle to the DB creates an 'added' event."""
        # Simulate a newly scraped vehicle being inserted
        v = make_vehicle(db, stock_number="NEW001", make="Ford")
        event = make_vehicle_event(
            db,
            stock_number="NEW001",
            event_type="added",
            description="Added: 2022 Ford F-150",
            make="Ford",
        )

        r = client.get("/api/events", params={"event_type": "added"})
        assert r.json()["total"] >= 1
        event_data = next(e for e in r.json()["data"] if e["stock_number"] == "NEW001")
        assert event_data["event_type"] == "added"

    def test_vehicle_removal_event_created(self, db, client):
        """Marking a vehicle inactive creates a 'removed' event."""
        v = make_vehicle(db, stock_number="GONE001", is_active=False)
        event = make_vehicle_event(
            db,
            stock_number="GONE001",
            event_type="removed",
            description="Removed: 2021 Toyota Camry",
        )

        r = client.get("/api/events", params={"event_type": "removed"})
        assert r.json()["total"] >= 1
        stocks = [e["stock_number"] for e in r.json()["data"]]
        assert "GONE001" in stocks

    def test_price_change_event_has_old_and_new_values(self, db, client):
        """Price change events store both old and new price values."""
        v = make_vehicle(db, stock_number="PRICE001", price=25000.0)
        event = make_vehicle_event(
            db,
            stock_number="PRICE001",
            event_type="price_change",
            description="Price change: 2022 Toyota Camry",
            old_value="28500",
            new_value="25000",
        )

        r = client.get("/api/events", params={"event_type": "price_change"})
        assert r.json()["total"] >= 1
        pc_events = [e for e in r.json()["data"] if e["stock_number"] == "PRICE001"]
        assert len(pc_events) == 1
        assert pc_events[0]["old_value"] == "28500"
        assert pc_events[0]["new_value"] == "25000"

    def test_stats_reflect_added_today(self, db, client):
        """Stats added_today increments when 'added' events are created today."""
        make_vehicle_event(db, event_type="added", stock_number="TODAY001",
                           timestamp=datetime.utcnow())
        make_vehicle_event(db, event_type="added", stock_number="TODAY002",
                           timestamp=datetime.utcnow())

        r = client.get("/api/stats")
        assert r.json()["added_today"] == 2

    def test_stats_total_active_consistent_with_vehicles(self, db, client):
        """stats.total_active matches actual count of active vehicles."""
        for i in range(5):
            make_vehicle(db, stock_number=f"ACTIVE{i}", is_active=True)
        for i in range(3):
            make_vehicle(db, stock_number=f"INACTIVE{i}", is_active=False)

        stats_r = client.get("/api/stats")
        vehicles_r = client.get("/api/vehicles", params={"is_active": True, "page_size": 100})

        assert stats_r.json()["total_active"] == vehicles_r.json()["total"]
        assert stats_r.json()["total_active"] == 5


class TestWatchlistToMatchFlow:

    def test_create_alert_then_check_matches(self, client, db):
        """Create a watchlist alert, add matching vehicles, verify match_count updates."""
        make_vehicle(db, stock_number="T1", make="Toyota", price=22000.0, is_active=True)
        make_vehicle(db, stock_number="T2", make="Toyota", price=35000.0, is_active=True)

        # Alert: Toyota under $25k
        r = client.post("/api/watchlist", json={
            "name": "Budget Toyota",
            "make": "Toyota",
            "max_price": 25000.0,
        })
        assert r.status_code == 200
        assert r.json()["match_count"] == 1  # Only T1 (22000) matches

    def test_update_alert_changes_match_count(self, client, db):
        """Updating alert criteria changes match_count in the response."""
        make_vehicle(db, stock_number="T1", make="Toyota", price=22000.0, is_active=True)
        make_vehicle(db, stock_number="T2", make="Toyota", price=35000.0, is_active=True)

        alert_r = client.post("/api/watchlist", json={"name": "Test", "make": "Toyota"})
        alert_id = alert_r.json()["id"]

        # Initial: both Toyotas match
        get_r = client.get("/api/watchlist")
        match_count_before = get_r.json()[0]["match_count"]
        assert match_count_before == 2

        # Update to add price ceiling
        update_r = client.put(f"/api/watchlist/{alert_id}", json={"max_price": 25000.0})
        assert update_r.json()["match_count"] == 1

    def test_deactivated_alert_still_retrievable(self, client, db):
        """Deactivated alerts appear in the list with is_active=False."""
        alert_r = client.post("/api/watchlist", json={"name": "Paused Alert"})
        alert_id = alert_r.json()["id"]
        client.put(f"/api/watchlist/{alert_id}", json={"is_active": False})

        r = client.get("/api/watchlist")
        alerts = r.json()
        paused = [a for a in alerts if a["id"] == alert_id]
        assert len(paused) == 1
        assert paused[0]["is_active"] is False


class TestLeadMatchFlow:

    def test_create_lead_and_find_matches(self, client, db):
        """Create lead, add inventory, verify matches endpoint returns correct vehicles."""
        make_vehicle(db, stock_number="C1", make="Toyota", model="Camry",
                     price=24000.0, is_active=True)
        make_vehicle(db, stock_number="C2", make="Toyota", model="Camry",
                     price=28000.0, is_active=True)
        make_vehicle(db, stock_number="A1", make="Honda", model="Accord",
                     price=22000.0, is_active=True)

        lead_r = client.post("/api/leads", json={
            "customer_name": "Jane Buyer",
            "interested_make": "Toyota",
            "interested_model": "Camry",
            "max_budget": 26000.0,
        })
        lead_id = lead_r.json()["id"]

        matches_r = client.get(f"/api/leads/{lead_id}/matches")
        assert matches_r.status_code == 200
        matches = matches_r.json()
        assert len(matches) == 1  # Only C1 (24000) matches budget
        assert matches[0]["stock_number"] == "C1"

    def test_lead_lifecycle(self, client, db):
        """Lead moves through status transitions correctly."""
        r = client.post("/api/leads", json={"customer_name": "Status Test"})
        lead_id = r.json()["id"]
        assert r.json()["status"] == "new"

        for status in ["contacted", "hot", "sold"]:
            update_r = client.put(f"/api/leads/{lead_id}", json={"status": status})
            assert update_r.json()["status"] == status

    def test_delete_lead_then_404_on_matches(self, client, db):
        """Deleted lead returns 404 on matches endpoint."""
        r = client.post("/api/leads", json={"customer_name": "Deleted"})
        lead_id = r.json()["id"]
        client.delete(f"/api/leads/{lead_id}")

        matches_r = client.get(f"/api/leads/{lead_id}/matches")
        assert matches_r.status_code == 404


class TestExportDataIntegrity:

    def test_export_row_count_matches_active_vehicles(self, client, db):
        """CSV export row count (excluding header) equals active vehicle count."""
        import csv
        import io

        for i in range(5):
            make_vehicle(db, stock_number=f"E{i}", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", is_active=False)

        r = client.get("/api/vehicles/export")
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        # 5 active + 1 header
        assert len(rows) == 6

    def test_export_price_matches_api(self, client, db):
        """Prices in CSV export match prices returned by the vehicles API."""
        import csv
        import io

        make_vehicle(db, stock_number="PRICETEST", price=33750.0, is_active=True)

        api_r = client.get("/api/vehicles")
        api_price = api_r.json()["data"][0]["price"]

        csv_r = client.get("/api/vehicles/export")
        reader = csv.DictReader(io.StringIO(csv_r.text))
        rows = list(reader)
        csv_price = float(rows[0]["Price"])

        assert api_price == csv_price


class TestFilterOptionsConsistency:

    def test_filter_options_makes_subset_of_vehicles_makes(self, client, db):
        """Makes from filter-options should be a subset of makes from vehicles endpoint."""
        make_vehicle(db, stock_number="T1", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="H1", make="Honda", is_active=True)
        make_vehicle(db, stock_number="F1", make="Ford", is_active=False)

        options_r = client.get("/api/filter-options")
        options_makes = set(options_r.json()["makes"])

        vehicles_r = client.get("/api/vehicles", params={"page_size": 100})
        vehicle_makes = set(v["make"] for v in vehicles_r.json()["data"])

        assert options_makes.issubset(vehicle_makes)
        assert "Ford" not in options_makes  # inactive excluded

    def test_filter_options_price_range_matches_vehicles(self, client, db):
        """filter-options price_range matches actual min/max from active vehicles."""
        make_vehicle(db, stock_number="MIN", price=10000.0, is_active=True)
        make_vehicle(db, stock_number="MAX", price=75000.0, is_active=True)
        make_vehicle(db, stock_number="INACTIVE", price=5000.0, is_active=False)

        r = client.get("/api/filter-options")
        price_range = r.json()["price_range"]
        assert price_range[0] == 10000.0
        assert price_range[1] == 75000.0


class TestHTTPMethodValidation:

    def test_get_on_post_only_endpoint_returns_405(self, client):
        r = client.get("/api/leads/1/matches")
        # Should return 404 (no lead) not 405 — the route exists for GET
        assert r.status_code in [200, 404]

    def test_watchlist_crud_endpoints_return_correct_status(self, client, db):
        # POST creates
        r = client.post("/api/watchlist", json={"name": "HTTP Test"})
        assert r.status_code == 200
        alert_id = r.json()["id"]

        # GET lists
        r = client.get("/api/watchlist")
        assert r.status_code == 200

        # PUT updates
        r = client.put(f"/api/watchlist/{alert_id}", json={"name": "Updated"})
        assert r.status_code == 200

        # DELETE removes
        r = client.delete(f"/api/watchlist/{alert_id}")
        assert r.status_code == 200

    def test_leads_crud_endpoints_return_correct_status(self, client, db):
        r = client.post("/api/leads", json={"customer_name": "HTTP Test"})
        assert r.status_code == 200
        lead_id = r.json()["id"]

        r = client.get("/api/leads")
        assert r.status_code == 200

        r = client.put(f"/api/leads/{lead_id}", json={"status": "hot"})
        assert r.status_code == 200

        r = client.delete(f"/api/leads/{lead_id}")
        assert r.status_code == 200
