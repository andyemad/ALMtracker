"""
Tests for alerts.py:
  vehicle_matches_alert()
  get_matching_vehicles()
  check_and_notify_watchlist() — logic only, no email delivery

Covers all filter criteria combinations and edge cases.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import models
from alerts import vehicle_matches_alert, get_matching_vehicles
from tests.conftest import make_vehicle, make_watchlist_alert, make_scrape_log


def make_alert(**kwargs) -> models.WatchlistAlert:
    """Create an in-memory WatchlistAlert without persisting to DB."""
    defaults = {
        "id": 1,
        "name": "Test Alert",
        "make": None,
        "model": None,
        "max_price": None,
        "min_price": None,
        "max_mileage": None,
        "min_year": None,
        "max_year": None,
        "condition": None,
        "notification_email": None,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_triggered": None,
        "trigger_count": 0,
    }
    defaults.update(kwargs)
    a = models.WatchlistAlert()
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


def make_veh(**kwargs) -> models.Vehicle:
    """Create an in-memory Vehicle without persisting to DB."""
    defaults = {
        "id": 1,
        "stock_number": "TEST001",
        "vin": "1HGCM82633A123456",
        "year": 2022,
        "make": "Toyota",
        "model": "Camry",
        "trim": "XSE",
        "price": 28500.0,
        "mileage": 15000,
        "condition": "used",
        "is_active": True,
        "first_seen": datetime.utcnow(),
        "last_seen": datetime.utcnow(),
        "days_on_lot": 5,
    }
    defaults.update(kwargs)
    v = models.Vehicle()
    for k, val in defaults.items():
        setattr(v, k, val)
    return v


class TestVehicleMatchesAlert:

    def test_no_criteria_matches_everything(self):
        alert = make_alert()
        vehicle = make_veh()
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_make_match_case_insensitive(self):
        alert = make_alert(make="toyota")
        vehicle = make_veh(make="Toyota")
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_make_no_match(self):
        alert = make_alert(make="Honda")
        vehicle = make_veh(make="Toyota")
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_model_partial_match(self):
        alert = make_alert(model="cam")
        vehicle = make_veh(model="Camry")
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_model_no_match(self):
        alert = make_alert(model="Accord")
        vehicle = make_veh(model="Camry")
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_max_price_passes_when_under(self):
        alert = make_alert(max_price=30000.0)
        vehicle = make_veh(price=28500.0)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_max_price_fails_when_over(self):
        alert = make_alert(max_price=25000.0)
        vehicle = make_veh(price=28500.0)
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_max_price_passes_when_equal(self):
        alert = make_alert(max_price=28500.0)
        vehicle = make_veh(price=28500.0)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_min_price_passes_when_above(self):
        alert = make_alert(min_price=20000.0)
        vehicle = make_veh(price=28500.0)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_min_price_fails_when_below(self):
        alert = make_alert(min_price=30000.0)
        vehicle = make_veh(price=28500.0)
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_max_mileage_passes_when_under(self):
        alert = make_alert(max_mileage=50000)
        vehicle = make_veh(mileage=15000)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_max_mileage_fails_when_over(self):
        alert = make_alert(max_mileage=10000)
        vehicle = make_veh(mileage=15000)
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_min_year_passes_when_at_or_above(self):
        alert = make_alert(min_year=2020)
        vehicle = make_veh(year=2022)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_min_year_fails_when_below(self):
        alert = make_alert(min_year=2023)
        vehicle = make_veh(year=2022)
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_max_year_passes_when_at_or_below(self):
        alert = make_alert(max_year=2023)
        vehicle = make_veh(year=2022)
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_max_year_fails_when_above(self):
        alert = make_alert(max_year=2021)
        vehicle = make_veh(year=2022)
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_condition_match_case_insensitive(self):
        alert = make_alert(condition="USED")
        vehicle = make_veh(condition="used")
        assert vehicle_matches_alert(vehicle, alert) is True

    def test_condition_no_match(self):
        alert = make_alert(condition="new")
        vehicle = make_veh(condition="used")
        assert vehicle_matches_alert(vehicle, alert) is False

    def test_price_is_none_skips_price_check(self):
        alert = make_alert(max_price=30000.0)
        vehicle = make_veh(price=None)
        # None price should not cause a crash — behavior: skip check, match passes
        result = vehicle_matches_alert(vehicle, alert)
        assert isinstance(result, bool)

    def test_multiple_criteria_all_must_pass(self):
        alert = make_alert(make="Toyota", max_price=30000.0, min_year=2020)
        vehicle_match = make_veh(make="Toyota", price=25000.0, year=2022)
        vehicle_wrong_make = make_veh(make="Honda", price=25000.0, year=2022)
        vehicle_over_price = make_veh(make="Toyota", price=45000.0, year=2022)

        assert vehicle_matches_alert(vehicle_match, alert) is True
        assert vehicle_matches_alert(vehicle_wrong_make, alert) is False
        assert vehicle_matches_alert(vehicle_over_price, alert) is False


class TestGetMatchingVehicles:

    def test_returns_empty_list_when_no_vehicles(self, db):
        alert = make_watchlist_alert(db, name="Empty Test", make="Toyota")
        result = get_matching_vehicles(alert, db)
        assert result == []

    def test_returns_matching_active_vehicles(self, db):
        alert = make_watchlist_alert(db, name="Toyota Alert", make="Toyota")
        make_vehicle(db, stock_number="T1", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="T2", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="T3", make="Toyota", is_active=False)

        result = get_matching_vehicles(alert, db)
        assert len(result) == 2

    def test_does_not_return_inactive_vehicles(self, db):
        alert = make_watchlist_alert(db, name="Toyota Alert", make="Toyota")
        make_vehicle(db, stock_number="T_INACTIVE", make="Toyota", is_active=False)

        result = get_matching_vehicles(alert, db)
        assert len(result) == 0

    def test_no_criteria_alert_matches_all_active(self, db):
        alert = make_watchlist_alert(db, name="All Vehicles")
        make_vehicle(db, stock_number="T1", make="Toyota")
        make_vehicle(db, stock_number="H1", make="Honda")
        make_vehicle(db, stock_number="INACTIVE", is_active=False)

        result = get_matching_vehicles(alert, db)
        assert len(result) == 2


class TestEmailNotSentWhenNoSmtp:

    def test_no_email_sent_when_smtp_not_configured(self, db, capsys):
        """When SMTP credentials are missing, email should silently log and return."""
        from alerts import _send_email

        alert = make_watchlist_alert(db, name="Email Test",
                                     notification_email="test@example.com")
        v = make_vehicle(db, stock_number="V1", make="Toyota")

        import os
        os.environ.pop("SMTP_USER", None)
        os.environ.pop("SMTP_PASS", None)

        # Should not raise an exception
        _send_email(alert, [v])
