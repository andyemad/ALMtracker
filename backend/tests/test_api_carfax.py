from datetime import datetime
from unittest.mock import patch

from carfax import CarfaxResolution
from tests.conftest import make_vehicle


class TestCarfaxLookup:

    def test_requires_query_or_vehicle_id(self, client):
        r = client.get("/api/carfax")
        assert r.status_code == 400
        assert "stock number" in r.json()["detail"].lower()

    def test_returns_cached_carfax_for_stock(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        make_vehicle(
            db,
            stock_number="CACHE123",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            carfax_url="https://www.carfax.com/VehicleHistory/ar20/CACHED123",
            carfax_fetched_at=datetime.utcnow(),
        )

        r = client.get("/api/carfax", params={"query": "cache123"})
        assert r.status_code == 200

        data = r.json()
        assert data["status"] == "resolved"
        assert data["cached"] is True
        assert data["carfax_url"].endswith("CACHED123")
        assert data["vehicle"]["stock_number"] == "CACHE123"

    def test_returns_ambiguous_matches_for_duplicate_stock(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        make_dealer(id=324, name="ALM Marietta", city="Marietta")

        make_vehicle(
            db,
            stock_number="DUP100",
            vin="VIN00000000000001",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
        )
        make_vehicle(
            db,
            stock_number="DUP100",
            vin="VIN00000000000002",
            dealer_id=324,
            location_name="ALM Marietta",
        )

        r = client.get("/api/carfax", params={"query": "DUP100"})
        assert r.status_code == 200

        data = r.json()
        assert data["status"] == "ambiguous"
        assert len(data["matches"]) == 2
        assert {m["dealer_id"] for m in data["matches"]} == {323, 324}

    def test_dealer_filter_resolves_duplicate_stock(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        make_dealer(id=324, name="ALM Marietta", city="Marietta")

        make_vehicle(
            db,
            stock_number="DUP200",
            vin="VIN00000000000011",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            carfax_url="https://www.carfax.com/VehicleHistory/ar20/BUFORD",
            carfax_fetched_at=datetime.utcnow(),
        )
        make_vehicle(
            db,
            stock_number="DUP200",
            vin="VIN00000000000012",
            dealer_id=324,
            location_name="ALM Marietta",
            carfax_url="https://www.carfax.com/VehicleHistory/ar20/MARIETTA",
            carfax_fetched_at=datetime.utcnow(),
        )

        r = client.get("/api/carfax", params={"query": "DUP200", "dealer_id": 324})
        assert r.status_code == 200

        data = r.json()
        assert data["status"] == "resolved"
        assert data["cached"] is True
        assert data["vehicle"]["dealer_id"] == 324
        assert data["carfax_url"].endswith("MARIETTA")

    def test_uses_live_resolver_when_cache_is_missing(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        vehicle = make_vehicle(
            db,
            stock_number="LIVE123",
            vin="1HGCM82633A765432",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            listing_url="https://www.almcars.com/inventory/live123",
            carfax_url=None,
        )

        def fake_resolver(db_session, target_vehicle, *, force_refresh=False):
            assert target_vehicle.id == vehicle.id
            assert force_refresh is False
            target_vehicle.carfax_url = "https://www.carfax.com/VehicleHistory/ar20/LIVE123"
            target_vehicle.carfax_fetched_at = datetime.utcnow()
            db_session.add(target_vehicle)
            db_session.commit()
            db_session.refresh(target_vehicle)
            return CarfaxResolution(
                carfax_url=target_vehicle.carfax_url,
                listing_url=target_vehicle.listing_url,
                source_url=target_vehicle.listing_url,
            )

        with patch("main.resolve_vehicle_carfax", side_effect=fake_resolver) as resolver:
            r = client.get("/api/carfax", params={"query": "LIVE123"})

        assert r.status_code == 200
        resolver.assert_called_once()

        data = r.json()
        assert data["status"] == "resolved"
        assert data["cached"] is False
        assert data["carfax_url"].endswith("LIVE123")
        assert data["vehicle"]["carfax_url"].endswith("LIVE123")

    def test_falls_back_to_live_inventory_when_local_snapshot_misses(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        vehicle = make_vehicle(
            db,
            stock_number="FALLBACK123",
            vin="1HGCM82633A765499",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
            listing_url="https://www.almcars.com/inventory/fallback123",
            carfax_url=None,
        )

        def fake_resolver(db_session, target_vehicle, *, force_refresh=False):
            assert target_vehicle.id == vehicle.id
            target_vehicle.carfax_url = "https://www.carfax.com/VehicleHistory/ar20/FALLBACK123"
            target_vehicle.carfax_fetched_at = datetime.utcnow()
            db_session.add(target_vehicle)
            db_session.commit()
            db_session.refresh(target_vehicle)
            return CarfaxResolution(
                carfax_url=target_vehicle.carfax_url,
                listing_url=target_vehicle.listing_url,
                source_url=target_vehicle.listing_url,
            )

        with patch("main._find_carfax_matches", return_value=[]), \
             patch("main._find_live_carfax_matches", return_value=[vehicle]) as live_matches, \
             patch("main.resolve_vehicle_carfax", side_effect=fake_resolver) as resolver:
            r = client.get("/api/carfax", params={"query": "FALLBACK123"})

        assert r.status_code == 200
        live_matches.assert_called_once()
        resolver.assert_called_once()

        data = r.json()
        assert data["status"] == "resolved"
        assert data["cached"] is False
        assert data["carfax_url"].endswith("FALLBACK123")

    def test_returns_live_ambiguous_matches_when_snapshot_misses(self, client, db, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia", city="Buford")
        make_dealer(id=324, name="ALM Marietta", city="Marietta")

        first = make_vehicle(
            db,
            stock_number="LIVEAMB1",
            vin="VIN00000000000111",
            dealer_id=323,
            location_name="ALM Mall of Georgia",
        )
        second = make_vehicle(
            db,
            stock_number="LIVEAMB1",
            vin="VIN00000000000112",
            dealer_id=324,
            location_name="ALM Marietta",
        )

        with patch("main._find_carfax_matches", return_value=[]), \
             patch("main._find_live_carfax_matches", return_value=[first, second]) as live_matches:
            r = client.get("/api/carfax", params={"query": "LIVEAMB1"})

        assert r.status_code == 200
        live_matches.assert_called_once()

        data = r.json()
        assert data["status"] == "ambiguous"
        assert len(data["matches"]) == 2
