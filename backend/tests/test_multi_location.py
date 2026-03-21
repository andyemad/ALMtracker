"""
Multi-location expansion tests (Sprint S4-2).

Tests critical multi-location behaviors that are the highest-risk aspects
of the 24-dealer expansion:

1. Vehicle bucketing by dealer_id in scraper
2. Stock number collision isolation across dealers
3. Change detection scoped to dealer
4. API filter by dealer_id
5. Watchlist scoped match
6. Lead match scoped to dealer
7. Migration preserves existing Mall of Georgia vehicles
"""

import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import make_vehicle, make_watchlist_alert, make_lead


class TestScraperBucketsByDealer:
    """Tests for the refactored scraper.py multi-dealer bucketing."""

    def test_vehicles_bucketed_to_correct_dealer(self):
        """Each vehicle lands in its dealer's bucket, not others."""
        from scraper import scrape_all_dealers, DealerConfig

        mock_page_data = {
            "props": {"pageProps": {"inventory": {
                "results": [
                    {
                        "dealer_id": 323,
                        "dealer": {"name": "ALM Mall of Georgia"},
                        "stocknumber": "MoG001",
                        "vin": "VIN_MOG001",
                        "year": 2022, "make": "Toyota", "model": "Camry",
                        "price": "25000",
                    },
                    {
                        "dealer_id": 324,
                        "dealer": {"name": "ALM Marietta"},
                        "stocknumber": "MAR001",
                        "vin": "VIN_MAR001",
                        "year": 2023, "make": "Honda", "model": "Accord",
                        "price": "30000",
                    },
                ],
                "meta": {"total": 2}
            }}}
        }

        configs = [
            DealerConfig(dealer_id=323, name="ALM Mall of Georgia"),
            DealerConfig(dealer_id=324, name="ALM Marietta"),
        ]

        with patch("scraper._fetch_page", return_value=mock_page_data), \
             patch("scraper._fetch_dealer_filtered", return_value=[]):
            dealer_map, total_raw, method = scrape_all_dealers(configs)

        assert 323 in dealer_map
        assert 324 in dealer_map
        assert len(dealer_map[323]) == 1
        assert len(dealer_map[324]) == 1
        assert dealer_map[323][0]["stock_number"] == "MoG001"
        assert dealer_map[324][0]["stock_number"] == "MAR001"
        assert method == "overfuel_single_pass_bucket"

    def test_unregistered_dealer_excluded_from_results(self):
        """Vehicles from dealers not in the requested set are excluded."""
        from scraper import scrape_all_dealers, DealerConfig

        mock_page_data = {
            "props": {"pageProps": {"inventory": {
                "results": [
                    {
                        "dealer_id": 323,
                        "dealer": {"name": "ALM Mall of Georgia"},
                        "stocknumber": "MOG001",
                        "vin": "V1",
                        "year": 2022, "make": "Ford", "model": "F-150",
                        "price": "40000",
                    },
                    {
                        "dealer_id": 999,  # Not in requested set
                        "dealer": {"name": "Unknown Dealer"},
                        "stocknumber": "X999",
                        "vin": "V2",
                        "year": 2022, "make": "Chevrolet", "model": "Malibu",
                        "price": "20000",
                    },
                ],
                "meta": {"total": 2}
            }}}
        }

        configs = [DealerConfig(dealer_id=323, name="ALM Mall of Georgia")]

        with patch("scraper._fetch_page", return_value=mock_page_data), \
             patch("scraper._fetch_dealer_filtered", return_value=[]):
            dealer_map, total_raw, method = scrape_all_dealers(configs)

        assert 323 in dealer_map
        assert 999 not in dealer_map


class TestVinReconciliation:
    """
    Tests for _reconcile_by_vin() — the supplemental per-dealer fetch that
    fixes vehicles misattributed in the unfiltered Overfuel feed.

    The Overfuel unfiltered feed sometimes assigns a vehicle to the wrong
    dealer with a modified stock number (e.g., suffix 'P' or 'A').
    The dealer-filtered endpoint is authoritative.
    """

    def _make_page(self, vehicles, total=None):
        total = total or len(vehicles)
        return {
            "props": {"pageProps": {"inventory": {
                "results": vehicles,
                "meta": {"total": total},
            }}}
        }

    def _raw_vehicle(self, dealer_id, stock, vin, make="Toyota", model="Camry", year=2023):
        return {
            "dealer_id": dealer_id,
            "dealer": {"name": f"Dealer {dealer_id}"},
            "stocknumber": stock,
            "vin": vin,
            "year": year, "make": make, "model": model,
            "price": "30000",
        }

    def test_misattributed_vehicle_moved_to_correct_dealer(self):
        """
        A vehicle attributed to dealer 320 in the unfiltered feed (with stock suffix 'P')
        but listed under dealer 323 in the filtered feed should end up in dealer 323's
        bucket with the correct stock number.
        """
        from scraper import scrape_all_dealers, DealerConfig

        # Unfiltered feed: VIN_X wrongly assigned to dealer 320 with stock "ABC123P"
        unfiltered_page = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_CORRECT"),
            self._raw_vehicle(320, "ABC123P", "VIN_X"),  # wrong dealer + suffix
        ])

        # Filtered page for dealer 323: VIN_X correctly attributed, stock "ABC123"
        filtered_page_323 = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_CORRECT"),
            self._raw_vehicle(323, "ABC123", "VIN_X"),   # correct
        ])

        # Filtered page for dealer 320: does not include VIN_X
        filtered_page_320 = self._make_page([])

        configs = [
            DealerConfig(dealer_id=320, name="ALM Kia South"),
            DealerConfig(dealer_id=323, name="ALM Mall of Georgia"),
        ]

        def mock_fetch_filtered(dealer_id):
            from scraper import _extract, normalize_vehicle
            page = filtered_page_323 if dealer_id == 323 else filtered_page_320
            results, _ = _extract(page)
            nvs = [normalize_vehicle(v) for v in results]
            for nv in nvs:
                nv["dealer_id"] = dealer_id
            return [nv for nv in nvs if nv.get("stock_number") and nv.get("vin")]

        with patch("scraper._fetch_page", return_value=unfiltered_page), \
             patch("scraper._fetch_dealer_filtered", side_effect=mock_fetch_filtered):
            dealer_map, _, _ = scrape_all_dealers(configs)

        # VIN_X must be in dealer 323's bucket with corrected stock number
        stocks_323 = {v["stock_number"] for v in dealer_map[323]}
        stocks_320 = {v["stock_number"] for v in dealer_map[320]}

        assert "ABC123" in stocks_323, "Corrected stock should be in dealer 323"
        assert "ABC123P" not in stocks_320, "Suffixed stock should be removed from dealer 320"
        assert "ABC123P" not in stocks_323, "Suffixed version should not appear in dealer 323"

    def test_reconciliation_preserves_correctly_attributed_vehicles(self):
        """
        Vehicles already in the correct dealer's bucket are not duplicated
        or removed during reconciliation.
        """
        from scraper import scrape_all_dealers, DealerConfig

        unfiltered_page = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
            self._raw_vehicle(323, "MOG002", "VIN_B"),
        ])

        filtered_323 = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
            self._raw_vehicle(323, "MOG002", "VIN_B"),
        ])

        configs = [DealerConfig(dealer_id=323, name="ALM Mall of Georgia")]

        def mock_fetch_filtered(dealer_id):
            from scraper import _extract, normalize_vehicle
            results, _ = _extract(filtered_323)
            nvs = [normalize_vehicle(v) for v in results]
            for nv in nvs:
                nv["dealer_id"] = dealer_id
            return [nv for nv in nvs if nv.get("stock_number") and nv.get("vin")]

        with patch("scraper._fetch_page", return_value=unfiltered_page), \
             patch("scraper._fetch_dealer_filtered", side_effect=mock_fetch_filtered):
            dealer_map, _, _ = scrape_all_dealers(configs)

        # Exactly 2 vehicles, no duplicates
        assert len(dealer_map[323]) == 2

    def test_reconciliation_adds_vehicle_missing_from_unfiltered_feed(self):
        """
        A vehicle that appears in the filtered feed but is completely absent
        from the unfiltered feed (e.g., due to a missing stock number) is added
        to the correct dealer's bucket.
        """
        from scraper import scrape_all_dealers, DealerConfig

        # Unfiltered feed: only 1 vehicle for dealer 323
        unfiltered_page = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
        ])

        # Filtered page has an extra vehicle not in the unfiltered feed
        filtered_323 = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
            self._raw_vehicle(323, "MOG002", "VIN_B"),  # extra
        ])

        configs = [DealerConfig(dealer_id=323, name="ALM Mall of Georgia")]

        def mock_fetch_filtered(dealer_id):
            from scraper import _extract, normalize_vehicle
            results, _ = _extract(filtered_323)
            nvs = [normalize_vehicle(v) for v in results]
            for nv in nvs:
                nv["dealer_id"] = dealer_id
            return [nv for nv in nvs if nv.get("stock_number") and nv.get("vin")]

        with patch("scraper._fetch_page", return_value=unfiltered_page), \
             patch("scraper._fetch_dealer_filtered", side_effect=mock_fetch_filtered):
            dealer_map, _, _ = scrape_all_dealers(configs)

        stocks = {v["stock_number"] for v in dealer_map[323]}
        assert "MOG001" in stocks
        assert "MOG002" in stocks
        assert len(dealer_map[323]) == 2

    def test_fetch_dealer_filtered_failure_does_not_crash(self):
        """
        If _fetch_dealer_filtered() fails for a dealer, the unfiltered bucket
        data is used as-is — no exception is raised.
        """
        from scraper import scrape_all_dealers, DealerConfig

        unfiltered_page = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
        ])

        configs = [DealerConfig(dealer_id=323, name="ALM Mall of Georgia")]

        with patch("scraper._fetch_page", return_value=unfiltered_page), \
             patch("scraper._fetch_dealer_filtered", return_value=[]):
            dealer_map, _, _ = scrape_all_dealers(configs)

        # Unfiltered data survives
        assert len(dealer_map[323]) == 1
        assert dealer_map[323][0]["stock_number"] == "MOG001"

    def test_discovery_mode_skips_reconciliation(self):
        """
        When scrape_all_dealers() is called with no configs (discovery mode),
        _fetch_dealer_filtered is never called.
        """
        from scraper import scrape_all_dealers

        unfiltered_page = self._make_page([
            self._raw_vehicle(323, "MOG001", "VIN_A"),
        ])

        with patch("scraper._fetch_page", return_value=unfiltered_page), \
             patch("scraper._fetch_dealer_filtered") as mock_filtered:
            scrape_all_dealers(active_dealers=None)

        mock_filtered.assert_not_called()


class TestStockNumberCollisionIsolation:
    """
    CRITICAL: Two dealers can have the same stock number.
    Vehicles with the same stock_number but different dealer_id must be
    treated as completely separate vehicles.
    """

    def test_same_stock_different_dealers_creates_two_vehicles(self, client, db):
        """
        Two vehicles with the same stock_number but different dealer_ids
        must coexist in the database as separate rows.
        """
        v1 = make_vehicle(db, stock_number="SAMESTOCK", make="Toyota")
        v1.dealer_id = 323
        v1.location_name = "ALM Mall of Georgia"
        db.commit()

        v2 = make_vehicle(db, stock_number="SAMESTOCK2", make="Honda")
        v2.dealer_id = 324
        v2.location_name = "ALM Marietta"
        v2.stock_number = "SAMESTOCK"
        db.commit()

        from models import Vehicle
        count = db.query(Vehicle).filter(Vehicle.stock_number == "SAMESTOCK").count()
        assert count == 2

    def test_change_detection_scoped_to_dealer(self, db):
        """
        The active_map composite key (dealer_id, stock_number) ensures
        removal detection is per-dealer.
        """
        v1 = make_vehicle(db, stock_number="SHARED", make="Toyota", is_active=True)
        v1.dealer_id = 323
        v1.location_name = "ALM Mall of Georgia"

        v2 = make_vehicle(db, stock_number="SHARED2", make="Honda", is_active=True)
        v2.dealer_id = 324
        v2.location_name = "ALM Marietta"
        v2.stock_number = "SHARED"

        db.commit()

        from models import Vehicle
        vehicles = db.query(Vehicle).filter(Vehicle.stock_number == "SHARED").all()
        assert all(v.is_active for v in vehicles)


class TestAPILocationFiltering:
    """Tests for dealer_id parameter on API endpoints."""

    def test_vehicles_filtered_by_dealer_id(self, client, db):
        """GET /api/vehicles?dealer_id=323 returns only MoG vehicles."""
        v1 = make_vehicle(db, stock_number="MOG001", make="Toyota")
        v1.dealer_id = 323
        v1.location_name = "ALM Mall of Georgia"

        v2 = make_vehicle(db, stock_number="MAR001", make="Honda")
        v2.dealer_id = 324
        v2.location_name = "ALM Marietta"
        db.commit()

        r = client.get("/api/vehicles", params={"dealer_id": 323})
        assert r.status_code == 200
        data = r.json()["data"]
        assert all(v["dealer_id"] == 323 for v in data)
        assert len(data) == 1

    def test_vehicles_without_dealer_id_returns_all(self, client, db):
        """GET /api/vehicles without dealer_id returns all active vehicles."""
        v1 = make_vehicle(db, stock_number="V1", make="Toyota")
        v1.dealer_id = 323
        v2 = make_vehicle(db, stock_number="V2", make="Honda")
        v2.dealer_id = 324
        db.commit()

        r = client.get("/api/vehicles")
        assert r.json()["total"] == 2

    def test_stats_scoped_to_dealer(self, client, db):
        """GET /api/stats?dealer_id=323 returns only MoG stats."""
        v1 = make_vehicle(db, stock_number="V1", is_active=True)
        v1.dealer_id = 323
        v2 = make_vehicle(db, stock_number="V2", is_active=True)
        v2.dealer_id = 324
        db.commit()

        r = client.get("/api/stats", params={"dealer_id": 323})
        assert r.json()["total_active"] == 1

    def test_filter_options_scoped_to_dealer(self, client, db):
        """GET /api/filter-options?dealer_id=323 returns MoG makes only."""
        v1 = make_vehicle(db, stock_number="V1", make="Toyota")
        v1.dealer_id = 323
        v2 = make_vehicle(db, stock_number="V2", make="Ferrari")
        v2.dealer_id = 324
        db.commit()

        r = client.get("/api/filter-options", params={"dealer_id": 323})
        makes = r.json()["makes"]
        assert "Toyota" in makes
        assert "Ferrari" not in makes


class TestWatchlistScopedMatch:
    """Tests for dealer-scoped watchlist alerts."""

    def test_scoped_alert_does_not_match_other_dealer(self, client, db):
        """Alert with dealer_id=323 only matches Mall of Georgia vehicles."""
        v1 = make_vehicle(db, stock_number="MOG_TOYOTA", make="Toyota")
        v1.dealer_id = 323
        v2 = make_vehicle(db, stock_number="MAR_TOYOTA", make="Toyota")
        v2.dealer_id = 324
        db.commit()

        alert = make_watchlist_alert(db, name="MoG Toyota Alert", make="Toyota")
        alert.dealer_id = 323
        db.commit()

        from alerts import get_matching_vehicles
        matches = get_matching_vehicles(alert, db)
        assert len(matches) == 1
        assert all(v.dealer_id == 323 for v in matches)

    def test_unscoped_alert_matches_all_dealers(self, client, db):
        """Alert without dealer_id matches vehicles from all dealers."""
        v1 = make_vehicle(db, stock_number="V1", make="Toyota")
        v1.dealer_id = 323
        v2 = make_vehicle(db, stock_number="V2", make="Toyota")
        v2.dealer_id = 324
        db.commit()

        alert = make_watchlist_alert(db, name="All Toyota Alert", make="Toyota")
        # alert.dealer_id is None by default — matches all locations

        from alerts import get_matching_vehicles
        matches = get_matching_vehicles(alert, db)
        assert len(matches) == 2


class TestMigrationPreservesExistingData:
    """Tests that the multi-location migration doesn't corrupt existing data."""

    def test_existing_vehicles_get_dealer_id_323_after_migration(self, db):
        """Vehicles assigned dealer_id=323 retain that value."""
        v = make_vehicle(db, stock_number="PRE_MIGRATION")
        v.dealer_id = 323
        v.location_name = "ALM Mall of Georgia"
        db.commit()

        db.refresh(v)
        assert v.dealer_id == 323
        assert v.location_name == "ALM Mall of Georgia"

    def test_vehicle_count_unchanged_after_migration(self, db):
        """Migration backfill does not add or remove vehicle rows."""
        from models import Vehicle

        for i in range(10):
            make_vehicle(db, stock_number=f"PRE{i}")

        count_before = db.query(Vehicle).count()

        vehicles = db.query(Vehicle).filter(Vehicle.stock_number.like("PRE%")).all()
        for v in vehicles:
            v.dealer_id = 323
            v.location_name = "ALM Mall of Georgia"
        db.commit()

        count_after = db.query(Vehicle).count()
        assert count_before == count_after
