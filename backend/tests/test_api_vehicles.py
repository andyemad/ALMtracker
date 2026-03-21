"""
Tests for:
  GET  /api/vehicles
  GET  /api/vehicles/export
  GET  /api/filter-options

Covers all filter parameters, pagination, sorting, and CSV export.
"""

import pytest
import csv
import io
from datetime import datetime, timedelta
from tests.conftest import make_vehicle


class TestListVehicles:

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/vehicles")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["data"] == []
        assert data["page"] == 1
        assert data["pages"] == 1

    def test_returns_only_active_by_default(self, client, db):
        make_vehicle(db, stock_number="ACTIVE", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", is_active=False)

        r = client.get("/api/vehicles")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "ACTIVE"

    def test_is_active_false_returns_inactive(self, client, db):
        make_vehicle(db, stock_number="ACTIVE", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", is_active=False)

        r = client.get("/api/vehicles", params={"is_active": False})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "INACTIVE"

    def test_search_by_make(self, client, db):
        make_vehicle(db, stock_number="T1", make="Toyota")
        make_vehicle(db, stock_number="H1", make="Honda")

        r = client.get("/api/vehicles", params={"search": "toyota"})
        data = r.json()["data"]
        assert all("Toyota" in v["make"] for v in data)
        assert len(data) == 1

    def test_search_by_stock_number(self, client, db):
        make_vehicle(db, stock_number="P12345", make="Toyota")
        make_vehicle(db, stock_number="U99999", make="Honda")

        r = client.get("/api/vehicles", params={"search": "P12345"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "P12345"

    def test_search_by_vin(self, client, db):
        make_vehicle(db, stock_number="V1", vin="SPECIALVIN123")
        make_vehicle(db, stock_number="V2", vin="DIFFERENTVIN456")

        r = client.get("/api/vehicles", params={"search": "SPECIALVIN"})
        assert r.json()["total"] == 1

    def test_filter_by_make(self, client, db):
        make_vehicle(db, stock_number="T1", make="Toyota")
        make_vehicle(db, stock_number="H1", make="Honda")
        make_vehicle(db, stock_number="T2", make="Toyota")

        r = client.get("/api/vehicles", params={"make": "Toyota"})
        assert r.json()["total"] == 2

    def test_filter_by_model(self, client, db):
        make_vehicle(db, stock_number="C1", model="Camry")
        make_vehicle(db, stock_number="C2", model="Camry")
        make_vehicle(db, stock_number="A1", model="Accord")

        r = client.get("/api/vehicles", params={"model": "Camry"})
        assert r.json()["total"] == 2

    def test_filter_by_min_year(self, client, db):
        make_vehicle(db, stock_number="Y2020", year=2020)
        make_vehicle(db, stock_number="Y2022", year=2022)
        make_vehicle(db, stock_number="Y2024", year=2024)

        r = client.get("/api/vehicles", params={"min_year": 2022})
        assert r.json()["total"] == 2

    def test_filter_by_max_year(self, client, db):
        make_vehicle(db, stock_number="Y2020", year=2020)
        make_vehicle(db, stock_number="Y2022", year=2022)
        make_vehicle(db, stock_number="Y2024", year=2024)

        r = client.get("/api/vehicles", params={"max_year": 2022})
        assert r.json()["total"] == 2

    def test_filter_by_min_price(self, client, db):
        make_vehicle(db, stock_number="CHEAP", price=15000.0)
        make_vehicle(db, stock_number="MID", price=25000.0)
        make_vehicle(db, stock_number="EXP", price=45000.0)

        r = client.get("/api/vehicles", params={"min_price": 20000})
        assert r.json()["total"] == 2

    def test_filter_by_max_price(self, client, db):
        make_vehicle(db, stock_number="CHEAP", price=15000.0)
        make_vehicle(db, stock_number="MID", price=25000.0)
        make_vehicle(db, stock_number="EXP", price=45000.0)

        r = client.get("/api/vehicles", params={"max_price": 25000})
        assert r.json()["total"] == 2

    def test_filter_by_max_mileage(self, client, db):
        make_vehicle(db, stock_number="LOW", mileage=5000)
        make_vehicle(db, stock_number="HIGH", mileage=80000)

        r = client.get("/api/vehicles", params={"max_mileage": 50000})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "LOW"

    def test_filter_by_condition(self, client, db):
        make_vehicle(db, stock_number="USED1", condition="used")
        make_vehicle(db, stock_number="NEW1", condition="new")

        r = client.get("/api/vehicles", params={"condition": "used"})
        assert r.json()["total"] == 1

    def test_filter_by_body_style(self, client, db):
        make_vehicle(db, stock_number="S1", body_style="Sedan")
        make_vehicle(db, stock_number="S2", body_style="Sedan")
        make_vehicle(db, stock_number="T1", body_style="Truck")

        r = client.get("/api/vehicles", params={"body_style": "Sedan"})
        assert r.json()["total"] == 2

    def test_pagination_page_1(self, client, db):
        for i in range(10):
            make_vehicle(db, stock_number=f"V{i:03d}")

        r = client.get("/api/vehicles", params={"page": 1, "page_size": 3})
        data = r.json()
        assert len(data["data"]) == 3
        assert data["total"] == 10
        assert data["pages"] == 4
        assert data["page"] == 1

    def test_pagination_last_page(self, client, db):
        for i in range(10):
            make_vehicle(db, stock_number=f"V{i:03d}")

        r = client.get("/api/vehicles", params={"page": 4, "page_size": 3})
        assert len(r.json()["data"]) == 1  # 10 items, 3 per page, page 4 has 1

    def test_sort_by_price_asc(self, client, db):
        make_vehicle(db, stock_number="EXPENSIVE", price=50000.0)
        make_vehicle(db, stock_number="CHEAP", price=10000.0)
        make_vehicle(db, stock_number="MID", price=25000.0)

        r = client.get("/api/vehicles", params={"sort_by": "price", "sort_order": "asc"})
        prices = [v["price"] for v in r.json()["data"]]
        assert prices == sorted(prices)

    def test_sort_by_price_desc(self, client, db):
        make_vehicle(db, stock_number="EXPENSIVE", price=50000.0)
        make_vehicle(db, stock_number="CHEAP", price=10000.0)

        r = client.get("/api/vehicles", params={"sort_by": "price", "sort_order": "desc"})
        prices = [v["price"] for v in r.json()["data"] if v["price"] is not None]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_year_asc(self, client, db):
        make_vehicle(db, stock_number="OLD", year=2018)
        make_vehicle(db, stock_number="NEW", year=2024)

        r = client.get("/api/vehicles", params={"sort_by": "year", "sort_order": "asc"})
        years = [v["year"] for v in r.json()["data"]]
        assert years == sorted(years)

    def test_invalid_sort_field_falls_back_to_default(self, client, db):
        make_vehicle(db, stock_number="V1")
        r = client.get("/api/vehicles", params={"sort_by": "malicious_field"})
        assert r.status_code == 200  # Should not crash

    def test_vehicle_dict_has_all_required_fields(self, client, db):
        make_vehicle(db, stock_number="FULLTEST")
        r = client.get("/api/vehicles")
        v = r.json()["data"][0]
        required_fields = [
            "id", "vin", "stock_number", "year", "make", "model", "trim",
            "price", "mileage", "exterior_color", "interior_color", "body_style",
            "condition", "fuel_type", "transmission", "image_url", "listing_url",
            "is_active", "first_seen", "last_seen", "days_on_lot"
        ]
        for field in required_fields:
            assert field in v, f"Missing field: {field}"

    def test_combined_filters(self, client, db):
        make_vehicle(db, stock_number="MATCH", make="Toyota", price=25000.0, year=2022, condition="used")
        make_vehicle(db, stock_number="WRONG_MAKE", make="Honda", price=25000.0, year=2022, condition="used")
        make_vehicle(db, stock_number="WRONG_PRICE", make="Toyota", price=60000.0, year=2022, condition="used")

        r = client.get("/api/vehicles", params={
            "make": "Toyota", "max_price": 30000, "min_year": 2020, "condition": "used"
        })
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["stock_number"] == "MATCH"


class TestExportCSV:

    def test_export_returns_csv_content_type(self, client, db):
        make_vehicle(db, stock_number="EXPORT1")
        r = client.get("/api/vehicles/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_export_content_disposition_header(self, client, db):
        r = client.get("/api/vehicles/export")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".csv" in r.headers.get("content-disposition", "")

    def test_export_has_header_row(self, client, db):
        make_vehicle(db, stock_number="V1")
        r = client.get("/api/vehicles/export")
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader)
        assert "Stock#" in header
        assert "VIN" in header
        assert "Year" in header
        assert "Make" in header
        assert "Model" in header
        assert "Price" in header

    def test_export_includes_only_active_vehicles(self, client, db):
        make_vehicle(db, stock_number="ACTIVE", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", is_active=False)

        r = client.get("/api/vehicles/export")
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        # header + 1 data row
        assert len(rows) == 2

    def test_export_empty_db(self, client):
        r = client.get("/api/vehicles/export")
        assert r.status_code == 200
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == 1  # header only

    def test_export_vehicle_data_in_row(self, client, db):
        make_vehicle(db, stock_number="MYSTOCK", vin="TESTVIN123",
                     year=2022, make="Toyota", model="Camry", price=28500.0)
        r = client.get("/api/vehicles/export")
        content = r.text
        assert "MYSTOCK" in content
        assert "TESTVIN123" in content
        assert "Toyota" in content
        assert "Camry" in content


class TestFilterOptions:

    def test_empty_db_returns_empty_options(self, client):
        r = client.get("/api/filter-options")
        assert r.status_code == 200
        data = r.json()
        assert data["makes"] == []
        assert data["body_styles"] == []
        assert data["price_range"] == [None, None]
        assert data["year_range"] == [None, None]

    def test_returns_distinct_makes(self, client, db):
        make_vehicle(db, stock_number="T1", make="Toyota")
        make_vehicle(db, stock_number="T2", make="Toyota")
        make_vehicle(db, stock_number="H1", make="Honda")

        r = client.get("/api/filter-options")
        makes = r.json()["makes"]
        assert len(makes) == 2
        assert "Toyota" in makes
        assert "Honda" in makes

    def test_makes_are_sorted_alphabetically(self, client, db):
        make_vehicle(db, stock_number="Z1", make="Toyota")
        make_vehicle(db, stock_number="A1", make="Honda")

        r = client.get("/api/filter-options")
        makes = r.json()["makes"]
        assert makes == sorted(makes)

    def test_returns_correct_price_range(self, client, db):
        make_vehicle(db, stock_number="V1", price=10000.0)
        make_vehicle(db, stock_number="V2", price=50000.0)
        make_vehicle(db, stock_number="V3", price=25000.0)

        r = client.get("/api/filter-options")
        price_range = r.json()["price_range"]
        assert price_range[0] == 10000.0
        assert price_range[1] == 50000.0

    def test_returns_correct_year_range(self, client, db):
        make_vehicle(db, stock_number="V1", year=2018)
        make_vehicle(db, stock_number="V2", year=2024)

        r = client.get("/api/filter-options")
        year_range = r.json()["year_range"]
        assert year_range[0] == 2018
        assert year_range[1] == 2024

    def test_filters_active_vehicles_only(self, client, db):
        make_vehicle(db, stock_number="ACTIVE", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", make="Ferrari", is_active=False)

        r = client.get("/api/filter-options")
        makes = r.json()["makes"]
        assert "Toyota" in makes
        assert "Ferrari" not in makes

    def test_excludes_empty_makes(self, client, db):
        make_vehicle(db, stock_number="EMPTY", make="", is_active=True)
        make_vehicle(db, stock_number="VALID", make="Toyota", is_active=True)

        r = client.get("/api/filter-options")
        makes = r.json()["makes"]
        assert "" not in makes
        assert "Toyota" in makes

    def test_body_styles_distinct_and_sorted(self, client, db):
        make_vehicle(db, stock_number="S1", body_style="Sedan")
        make_vehicle(db, stock_number="S2", body_style="Sedan")
        make_vehicle(db, stock_number="T1", body_style="Truck")

        r = client.get("/api/filter-options")
        styles = r.json()["body_styles"]
        assert len(styles) == 2
        assert styles == sorted(styles)
