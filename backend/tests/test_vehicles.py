"""
test_vehicles.py — Tests for vehicle-related API endpoints.

Endpoints covered:
  GET  /api/vehicles           — list with filters, pagination, sorting
  GET  /api/vehicles/export    — CSV export
  GET  /api/filter-options     — distinct filter values

Multi-location tests (dealer_id param) are marked xfail because
GET /api/vehicles?dealer_id=N is a Sprint 1 feature not yet implemented
in main.py.  Remove the xfail marks once the dealer_id param ships.

Test isolation: every test receives a fresh empty DB via the db_session
fixture in conftest.py.  No test shares DB state with any other.
"""

import csv
import io
from datetime import datetime, timedelta

import pytest
import sys
import os

# Ensure backend package is importable when running from any directory
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import models

# ---------------------------------------------------------------------------
# Helpers — thin wrappers so tests read cleanly without importing conftest
# ---------------------------------------------------------------------------

def _v(db, **kwargs) -> models.Vehicle:
    """Create and persist a Vehicle with sensible defaults."""
    counter = getattr(_v, "_counter", 0) + 1
    _v._counter = counter
    defaults = dict(
        stock_number=f"STK{counter:05d}",
        vin=f"TEST{counter:017d}",
        year=2022,
        make="Toyota",
        model="Camry",
        trim="LE",
        price=25000.0,
        mileage=15000,
        exterior_color="White",
        body_style="Sedan",
        condition="Used",
        fuel_type="Gasoline",
        transmission="Automatic",
        is_active=True,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        days_on_lot=0,
    )
    defaults.update(kwargs)
    v = models.Vehicle(**defaults)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


# ===========================================================================
# GET /api/vehicles — functional tests (current behaviour)
# ===========================================================================

class TestListVehicles:
    """Tests for GET /api/vehicles — all filters, pagination, sorting."""

    # ── Baseline ──────────────────────────────────────────────────────────

    def test_empty_db_returns_empty_paginated_response(self, client):
        r = client.get("/api/vehicles")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["data"] == []
        assert body["page"] == 1
        assert body["pages"] == 1
        assert body["page_size"] == 50

    def test_active_vehicle_appears_in_list(self, client, db_session):
        _v(db_session, stock_number="ACTIVE001", make="Honda", is_active=True)
        r = client.get("/api/vehicles")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "ACTIVE001"

    def test_response_includes_all_required_fields(self, client, db_session):
        _v(db_session)
        v = client.get("/api/vehicles").json()["data"][0]
        required = [
            "id", "vin", "stock_number", "year", "make", "model", "trim",
            "price", "mileage", "exterior_color", "interior_color", "body_style",
            "condition", "fuel_type", "transmission", "image_url", "listing_url",
            "is_active", "first_seen", "last_seen", "days_on_lot",
        ]
        for field in required:
            assert field in v, f"Response missing field: {field}"

    # ── is_active filter ──────────────────────────────────────────────────

    def test_default_is_active_true_excludes_inactive(self, client, db_session):
        _v(db_session, stock_number="ACT", is_active=True)
        _v(db_session, stock_number="INACT", is_active=False)
        r = client.get("/api/vehicles")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "ACT"

    def test_is_active_false_returns_only_inactive(self, client, db_session):
        _v(db_session, stock_number="ACT", is_active=True)
        _v(db_session, stock_number="INACT", is_active=False)
        r = client.get("/api/vehicles", params={"is_active": False})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "INACT"

    # ── Full-text search ──────────────────────────────────────────────────

    def test_search_matches_make(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        _v(db_session, stock_number="H1", make="Honda")
        r = client.get("/api/vehicles", params={"search": "toyota"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["make"] == "Toyota"

    def test_search_matches_model(self, client, db_session):
        _v(db_session, stock_number="C1", model="Camry")
        _v(db_session, stock_number="A1", model="Accord")
        r = client.get("/api/vehicles", params={"search": "camr"})
        assert r.json()["total"] == 1

    def test_search_matches_trim(self, client, db_session):
        _v(db_session, stock_number="XSE", trim="XSE V6")
        _v(db_session, stock_number="LE", trim="LE")
        r = client.get("/api/vehicles", params={"search": "V6"})
        assert r.json()["total"] == 1

    def test_search_matches_stock_number(self, client, db_session):
        _v(db_session, stock_number="P12345")
        _v(db_session, stock_number="U99999")
        r = client.get("/api/vehicles", params={"search": "P12345"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "P12345"

    def test_search_matches_vin(self, client, db_session):
        _v(db_session, stock_number="VIN1", vin="SPECIALVIN123XYZ")
        _v(db_session, stock_number="VIN2", vin="DIFFERENTVIN456")
        r = client.get("/api/vehicles", params={"search": "SPECIALVIN"})
        assert r.json()["total"] == 1

    def test_search_is_case_insensitive(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        r = client.get("/api/vehicles", params={"search": "TOYOTA"})
        assert r.json()["total"] == 1

    def test_search_no_results_returns_empty(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        r = client.get("/api/vehicles", params={"search": "Lamborghini"})
        assert r.json()["total"] == 0

    # ── Make / model filters ───────────────────────────────────────────────

    def test_filter_by_make_exact(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        _v(db_session, stock_number="T2", make="Toyota")
        _v(db_session, stock_number="H1", make="Honda")
        r = client.get("/api/vehicles", params={"make": "Toyota"})
        assert r.json()["total"] == 2
        assert all(v["make"] == "Toyota" for v in r.json()["data"])

    def test_filter_by_make_partial(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        _v(db_session, stock_number="T2", make="Toyota Certified")
        _v(db_session, stock_number="H1", make="Honda")
        r = client.get("/api/vehicles", params={"make": "Toyota"})
        # Both Toyota and Toyota Certified match (ilike %Toyota%)
        assert r.json()["total"] == 2

    def test_filter_by_model(self, client, db_session):
        _v(db_session, stock_number="C1", model="Camry")
        _v(db_session, stock_number="C2", model="Camry")
        _v(db_session, stock_number="A1", model="Accord")
        r = client.get("/api/vehicles", params={"model": "Camry"})
        assert r.json()["total"] == 2

    # ── Year range filters ─────────────────────────────────────────────────

    def test_filter_by_min_year(self, client, db_session):
        _v(db_session, stock_number="Y2020", year=2020)
        _v(db_session, stock_number="Y2022", year=2022)
        _v(db_session, stock_number="Y2024", year=2024)
        r = client.get("/api/vehicles", params={"min_year": 2022})
        assert r.json()["total"] == 2
        assert all(v["year"] >= 2022 for v in r.json()["data"])

    def test_filter_by_max_year(self, client, db_session):
        _v(db_session, stock_number="Y2020", year=2020)
        _v(db_session, stock_number="Y2022", year=2022)
        _v(db_session, stock_number="Y2024", year=2024)
        r = client.get("/api/vehicles", params={"max_year": 2022})
        assert r.json()["total"] == 2
        assert all(v["year"] <= 2022 for v in r.json()["data"])

    def test_filter_by_year_range(self, client, db_session):
        _v(db_session, stock_number="Y2019", year=2019)
        _v(db_session, stock_number="Y2021", year=2021)
        _v(db_session, stock_number="Y2023", year=2023)
        r = client.get("/api/vehicles", params={"min_year": 2020, "max_year": 2022})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["year"] == 2021

    # ── Price range filters ────────────────────────────────────────────────

    def test_filter_by_min_price(self, client, db_session):
        _v(db_session, stock_number="CHEAP", price=15000.0)
        _v(db_session, stock_number="MID", price=25000.0)
        _v(db_session, stock_number="EXP", price=45000.0)
        r = client.get("/api/vehicles", params={"min_price": 20000})
        assert r.json()["total"] == 2
        assert all(v["price"] >= 20000 for v in r.json()["data"])

    def test_filter_by_max_price(self, client, db_session):
        _v(db_session, stock_number="CHEAP", price=15000.0)
        _v(db_session, stock_number="MID", price=25000.0)
        _v(db_session, stock_number="EXP", price=45000.0)
        r = client.get("/api/vehicles", params={"max_price": 25000})
        assert r.json()["total"] == 2

    def test_filter_by_price_range(self, client, db_session):
        _v(db_session, stock_number="V10K", price=10000.0)
        _v(db_session, stock_number="V25K", price=25000.0)
        _v(db_session, stock_number="V50K", price=50000.0)
        r = client.get("/api/vehicles", params={"min_price": 15000, "max_price": 30000})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["price"] == 25000.0

    # ── Mileage filter ─────────────────────────────────────────────────────

    def test_filter_by_max_mileage(self, client, db_session):
        _v(db_session, stock_number="LOW", mileage=5000)
        _v(db_session, stock_number="HIGH", mileage=80000)
        r = client.get("/api/vehicles", params={"max_mileage": 50000})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "LOW"

    def test_max_mileage_boundary_included(self, client, db_session):
        _v(db_session, stock_number="EXACT", mileage=50000)
        r = client.get("/api/vehicles", params={"max_mileage": 50000})
        assert r.json()["total"] == 1

    # ── Days on lot filters ───────────────────────────────────────────────

    def test_filter_by_min_days_on_lot(self, client, db_session):
        _v(db_session, stock_number="FRESH", days_on_lot=2)
        _v(db_session, stock_number="AGED", days_on_lot=47)
        r = client.get("/api/vehicles", params={"min_days_on_lot": 30})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "AGED"

    def test_filter_by_max_days_on_lot(self, client, db_session):
        _v(db_session, stock_number="FRESH", days_on_lot=4)
        _v(db_session, stock_number="AGED", days_on_lot=61)
        r = client.get("/api/vehicles", params={"max_days_on_lot": 7})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "FRESH"

    # ── Condition / body style filters ────────────────────────────────────

    def test_filter_by_condition(self, client, db_session):
        _v(db_session, stock_number="USED1", condition="Used")
        _v(db_session, stock_number="NEW1", condition="New")
        r = client.get("/api/vehicles", params={"condition": "Used"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["condition"] == "Used"

    def test_filter_by_condition_case_insensitive(self, client, db_session):
        _v(db_session, stock_number="USED1", condition="Used")
        r = client.get("/api/vehicles", params={"condition": "used"})
        assert r.json()["total"] == 1

    def test_filter_by_body_style(self, client, db_session):
        _v(db_session, stock_number="S1", body_style="Sedan")
        _v(db_session, stock_number="S2", body_style="Sedan")
        _v(db_session, stock_number="T1", body_style="Truck")
        r = client.get("/api/vehicles", params={"body_style": "Sedan"})
        assert r.json()["total"] == 2

    # ── Combined filters ───────────────────────────────────────────────────

    def test_combined_make_price_year_condition_filter(self, client, db_session):
        _v(db_session, stock_number="MATCH",
           make="Toyota", price=25000.0, year=2022, condition="Used")
        _v(db_session, stock_number="WRONG_MAKE",
           make="Honda", price=25000.0, year=2022, condition="Used")
        _v(db_session, stock_number="WRONG_PRICE",
           make="Toyota", price=60000.0, year=2022, condition="Used")
        _v(db_session, stock_number="TOO_OLD",
           make="Toyota", price=25000.0, year=2015, condition="Used")

        r = client.get("/api/vehicles", params={
            "make": "Toyota", "max_price": 30000, "min_year": 2020, "condition": "Used"
        })
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "MATCH"

    # ── Sorting ────────────────────────────────────────────────────────────

    def test_sort_by_price_asc(self, client, db_session):
        _v(db_session, stock_number="EXPENSIVE", price=50000.0)
        _v(db_session, stock_number="CHEAP", price=10000.0)
        _v(db_session, stock_number="MID", price=25000.0)
        r = client.get("/api/vehicles", params={"sort_by": "price", "sort_order": "asc"})
        prices = [v["price"] for v in r.json()["data"]]
        assert prices == sorted(prices)

    def test_sort_by_price_desc(self, client, db_session):
        _v(db_session, stock_number="EXPENSIVE", price=50000.0)
        _v(db_session, stock_number="CHEAP", price=10000.0)
        r = client.get("/api/vehicles", params={"sort_by": "price", "sort_order": "desc"})
        prices = [v["price"] for v in r.json()["data"] if v["price"] is not None]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_year_asc(self, client, db_session):
        _v(db_session, stock_number="OLD", year=2018)
        _v(db_session, stock_number="NEW", year=2024)
        r = client.get("/api/vehicles", params={"sort_by": "year", "sort_order": "asc"})
        years = [v["year"] for v in r.json()["data"]]
        assert years == sorted(years)

    def test_sort_by_mileage_asc(self, client, db_session):
        _v(db_session, stock_number="HI", mileage=90000)
        _v(db_session, stock_number="LO", mileage=5000)
        r = client.get("/api/vehicles", params={"sort_by": "mileage", "sort_order": "asc"})
        miles = [v["mileage"] for v in r.json()["data"]]
        assert miles == sorted(miles)

    def test_invalid_sort_field_uses_default(self, client, db_session):
        _v(db_session)
        r = client.get("/api/vehicles", params={"sort_by": "injected_column; DROP TABLE vehicles; --"})
        assert r.status_code == 200  # should not crash or 500

    # ── Pagination ─────────────────────────────────────────────────────────

    def test_pagination_total_and_pages(self, client, db_session):
        for i in range(10):
            _v(db_session, stock_number=f"PAG{i:03d}")
        r = client.get("/api/vehicles", params={"page": 1, "page_size": 3})
        body = r.json()
        assert body["total"] == 10
        assert body["pages"] == 4
        assert len(body["data"]) == 3
        assert body["page"] == 1

    def test_pagination_page_2_offset_correct(self, client, db_session):
        for i in range(6):
            _v(db_session, stock_number=f"PAG{i:03d}")
        p1 = client.get("/api/vehicles", params={"page": 1, "page_size": 3}).json()["data"]
        p2 = client.get("/api/vehicles", params={"page": 2, "page_size": 3}).json()["data"]
        ids_p1 = {v["id"] for v in p1}
        ids_p2 = {v["id"] for v in p2}
        assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"

    def test_pagination_last_page_partial(self, client, db_session):
        for i in range(10):
            _v(db_session, stock_number=f"PAG{i:03d}")
        r = client.get("/api/vehicles", params={"page": 4, "page_size": 3})
        assert len(r.json()["data"]) == 1

    def test_pagination_beyond_last_page_returns_empty_data(self, client, db_session):
        _v(db_session)
        r = client.get("/api/vehicles", params={"page": 999, "page_size": 50})
        assert r.status_code == 200
        assert r.json()["data"] == []


# ===========================================================================
# GET /api/vehicles — multi-location dealer_id filter (Sprint 1 — xfail)
# ===========================================================================

class TestVehiclesDealerIdFilter:
    """
    Tests for the new `dealer_id` and `location_name` query parameters on
    GET /api/vehicles.  These are the highest-priority correctness tests
    for the 24-location expansion — stock number collision isolation depends
    entirely on scoping queries by dealer_id.
    """

    def test_dealer_id_filter_returns_only_that_dealers_vehicles(
        self, client, db_session, make_dealer
    ):
        d1 = make_dealer(id=323, name="ALM Mall of Georgia")
        d2 = make_dealer(id=401, name="ALM Roswell")

        _v(db_session, stock_number="MOG001", dealer_id=323,
           location_name="ALM Mall of Georgia", make="Toyota")
        _v(db_session, stock_number="RWL001", dealer_id=401,
           location_name="ALM Roswell", make="Honda")

        r = client.get("/api/vehicles", params={"dealer_id": 323})
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["dealer_id"] == 323
        assert data[0]["stock_number"] == "MOG001"

    def test_no_dealer_id_returns_vehicles_from_all_dealers(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _v(db_session, stock_number="MOG001", dealer_id=323)
        _v(db_session, stock_number="RWL001", dealer_id=401)

        r = client.get("/api/vehicles")
        assert r.json()["total"] == 2

    def test_unknown_dealer_id_returns_empty(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _v(db_session, stock_number="V1", dealer_id=323)

        r = client.get("/api/vehicles", params={"dealer_id": 9999})
        assert r.json()["total"] == 0
        assert r.json()["data"] == []

    def test_location_name_fuzzy_filter(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _v(db_session, stock_number="V1", dealer_id=323,
           location_name="ALM Mall of Georgia")
        _v(db_session, stock_number="V2", dealer_id=401,
           location_name="ALM Roswell")

        r = client.get("/api/vehicles", params={"location_name": "Mall"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["location_name"] == "ALM Mall of Georgia"

    def test_vehicle_dict_includes_dealer_id_and_location_name(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        _v(db_session, stock_number="V1", dealer_id=323,
           location_name="ALM Mall of Georgia")

        r = client.get("/api/vehicles", params={"dealer_id": 323})
        v = r.json()["data"][0]
        assert "dealer_id" in v, "dealer_id missing from _vehicle_dict response"
        assert "location_name" in v, "location_name missing from _vehicle_dict response"
        assert v["dealer_id"] == 323
        assert v["location_name"] == "ALM Mall of Georgia"

    def test_same_stock_number_different_dealers_both_returned_without_filter(
        self, client, db_session, make_dealer
    ):
        """Stock number collision: same stock# at two dealers must both exist."""
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        # Same stock number at two different dealers
        _v(db_session, stock_number="COLLISION", dealer_id=323, make="Toyota",
           location_name="ALM Mall of Georgia")
        _v(db_session, stock_number="COLLISION", dealer_id=401, make="Honda",
           location_name="ALM Roswell")

        r = client.get("/api/vehicles", params={"is_active": True})
        stocks = [v["stock_number"] for v in r.json()["data"]]
        assert stocks.count("COLLISION") == 2

    def test_dealer_id_filter_combined_with_make_filter(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        _v(db_session, stock_number="MOG_TOYOTA", dealer_id=323, make="Toyota")
        _v(db_session, stock_number="MOG_HONDA", dealer_id=323, make="Honda")
        _v(db_session, stock_number="RWL_TOYOTA", dealer_id=401, make="Toyota")

        r = client.get("/api/vehicles", params={"dealer_id": 323, "make": "Toyota"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "MOG_TOYOTA"


# ===========================================================================
# GET /api/vehicles/export — CSV export
# ===========================================================================

class TestExportCSV:
    """Tests for GET /api/vehicles/export."""

    def test_returns_csv_content_type(self, client, db_session):
        _v(db_session, stock_number="E1")
        r = client.get("/api/vehicles/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_returns_attachment_content_disposition(self, client, db_session):
        r = client.get("/api/vehicles/export")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd

    def test_empty_db_returns_header_row_only(self, client):
        r = client.get("/api/vehicles/export")
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 1  # header only

    def test_header_row_contains_expected_columns(self, client, db_session):
        _v(db_session)
        reader = csv.reader(io.StringIO(client.get("/api/vehicles/export").text))
        header = next(reader)
        for col in ["Stock#", "VIN", "Year", "Make", "Model", "Price"]:
            assert col in header, f"CSV header missing column: {col}"

    def test_active_vehicles_appear_in_export(self, client, db_session):
        _v(db_session, stock_number="ACTIVE", is_active=True)
        reader = csv.reader(io.StringIO(client.get("/api/vehicles/export").text))
        rows = list(reader)
        # header + 1 data row
        assert len(rows) == 2

    def test_inactive_vehicles_excluded_from_export(self, client, db_session):
        _v(db_session, stock_number="ACT", is_active=True)
        _v(db_session, stock_number="INACT", is_active=False)
        reader = csv.reader(io.StringIO(client.get("/api/vehicles/export").text))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 active row

    def test_vehicle_data_present_in_csv(self, client, db_session):
        _v(db_session, stock_number="CSVTEST", vin="TESTVIN001",
           make="Toyota", model="Camry", price=28500.0)
        content = client.get("/api/vehicles/export").text
        assert "CSVTEST" in content
        assert "TESTVIN001" in content
        assert "Toyota" in content
        assert "Camry" in content

    def test_multiple_vehicles_produce_multiple_rows(self, client, db_session):
        for i in range(5):
            _v(db_session, stock_number=f"EXP{i}", is_active=True)
        reader = csv.reader(io.StringIO(client.get("/api/vehicles/export").text))
        rows = list(reader)
        assert len(rows) == 6  # header + 5 data rows

    def test_export_scoped_to_dealer_id(self, client, db_session, make_dealer):
        """GET /api/vehicles/export?dealer_id=323 returns only that dealer's vehicles."""
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")
        _v(db_session, stock_number="MOG1", dealer_id=323, make="Toyota")
        _v(db_session, stock_number="RWL1", dealer_id=401, make="Honda")

        r = client.get("/api/vehicles/export", params={"dealer_id": 323})
        content = r.text
        assert "MOG1" in content
        assert "RWL1" not in content


# ===========================================================================
# GET /api/filter-options
# ===========================================================================

class TestFilterOptions:
    """Tests for GET /api/filter-options."""

    def test_empty_db_returns_nulls(self, client):
        r = client.get("/api/filter-options")
        assert r.status_code == 200
        body = r.json()
        assert body["makes"] == []
        assert body["body_styles"] == []
        assert body["price_range"] == [None, None]
        assert body["year_range"] == [None, None]

    def test_returns_distinct_makes_sorted(self, client, db_session):
        _v(db_session, stock_number="T1", make="Toyota")
        _v(db_session, stock_number="T2", make="Toyota")
        _v(db_session, stock_number="H1", make="Honda")
        r = client.get("/api/filter-options")
        makes = r.json()["makes"]
        assert sorted(makes) == makes  # alphabetically sorted
        assert len(makes) == 2
        assert "Toyota" in makes
        assert "Honda" in makes

    def test_excludes_makes_from_inactive_vehicles(self, client, db_session):
        _v(db_session, stock_number="ACT", make="Toyota", is_active=True)
        _v(db_session, stock_number="INACT", make="Ferrari", is_active=False)
        makes = client.get("/api/filter-options").json()["makes"]
        assert "Toyota" in makes
        assert "Ferrari" not in makes

    def test_excludes_empty_make_strings(self, client, db_session):
        _v(db_session, stock_number="EMPTY", make="", is_active=True)
        _v(db_session, stock_number="VALID", make="Toyota", is_active=True)
        makes = client.get("/api/filter-options").json()["makes"]
        assert "" not in makes

    def test_price_range_reflects_active_vehicles(self, client, db_session):
        _v(db_session, stock_number="MIN", price=10000.0, is_active=True)
        _v(db_session, stock_number="MAX", price=75000.0, is_active=True)
        _v(db_session, stock_number="INACT", price=1000.0, is_active=False)
        pr = client.get("/api/filter-options").json()["price_range"]
        assert pr[0] == 10000.0
        assert pr[1] == 75000.0

    def test_year_range_reflects_active_vehicles(self, client, db_session):
        _v(db_session, stock_number="OLD", year=2018, is_active=True)
        _v(db_session, stock_number="NEW", year=2024, is_active=True)
        yr = client.get("/api/filter-options").json()["year_range"]
        assert yr[0] == 2018
        assert yr[1] == 2024

    def test_body_styles_distinct_and_sorted(self, client, db_session):
        _v(db_session, stock_number="S1", body_style="Sedan")
        _v(db_session, stock_number="S2", body_style="Sedan")
        _v(db_session, stock_number="T1", body_style="Truck")
        styles = client.get("/api/filter-options").json()["body_styles"]
        assert len(styles) == 2
        assert styles == sorted(styles)

    def test_filter_options_scoped_to_dealer_id(self, client, db_session, make_dealer):
        """GET /api/filter-options?dealer_id=323 returns only MoG makes."""
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")
        _v(db_session, stock_number="V1", make="Toyota", dealer_id=323)
        _v(db_session, stock_number="V2", make="Ferrari", dealer_id=401)

        makes = client.get("/api/filter-options", params={"dealer_id": 323}).json()["makes"]
        assert "Toyota" in makes
        assert "Ferrari" not in makes
