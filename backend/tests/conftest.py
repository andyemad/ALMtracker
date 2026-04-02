"""
ALM Inventory Tracker — pytest fixtures and test configuration.

Uses an in-memory SQLite database for full test isolation.
Tests run against the actual FastAPI application with a test-scoped database.

Provides two fixture families:
  1. Legacy function-style helpers (make_vehicle, make_watchlist_alert, etc.)
     used by the pre-existing test files (test_api_*.py).
  2. Pytest fixture factories (make_dealer, make_scrape_log, etc.)
     used by the new Sprint-1 test files (test_vehicles.py, test_dealers.py, etc.).
     These accept the db_session fixture and return a callable factory.

The db_session fixture wraps each test in a transaction that is rolled back
on teardown, giving full isolation without schema recreation overhead.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Optional

# Adjust sys.path so tests can import backend modules when run from project root
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, get_db
from main import app
import models

# ──────────────────────────────────────────────────────────────────────────────
# In-memory SQLite engine for test isolation
# ──────────────────────────────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Session-scoped schema creation (create once, not per-test)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create all tables once for the entire test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ──────────────────────────────────────────────────────────────────────────────
# Per-test DB isolation via transaction rollback (preferred, new tests)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session(_create_tables):
    """
    Yields a SQLAlchemy Session wrapped in a savepoint.
    All changes are rolled back after the test, giving full isolation
    without the cost of dropping/recreating the schema on each test.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ──────────────────────────────────────────────────────────────────────────────
# Legacy per-test fixtures (used by test_api_*.py files)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db(db_session):
    """
    Alias for db_session — provided for backward compatibility with legacy
    test files (test_api_*.py) that use the parameter name 'db'.
    Both 'db' and 'db_session' refer to the same isolated test session.
    """
    return db_session


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient with DB override.

    Wires the FastAPI app to use the same isolated db_session that the test
    uses, so HTTP calls and direct ORM operations share one transaction that
    is rolled back after the test.

    The startup lifecycle handler (APScheduler) is suppressed during tests:
    - We save and clear app.router.on_startup before entering the TestClient
      context so the AsyncIOScheduler never binds to the test event loop.
    - This prevents "Event loop is closed" errors on the second and subsequent
      tests, which occur because the scheduler holds a reference to the loop
      opened by the first TestClient and tries to reuse it after it is closed.
    - Any previously running scheduler instance is shut down before each test
      so its internal loop reference is also cleared.
    """
    import main as _main

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass  # rollback handled by db_session fixture

    app.dependency_overrides[get_db] = _override_get_db

    # Suppress startup AND shutdown events so APScheduler never touches the
    # test event loop and never tries to call shutdown on a loop that is
    # already closed or was never started.
    saved_startup = list(app.router.on_startup)
    saved_shutdown = list(app.router.on_shutdown)
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()

    # If a scheduler from a previous test is still running, shut it down so
    # it releases its stale event-loop reference.
    if _main.scheduler.running:
        try:
            _main.scheduler.shutdown(wait=False)
        except Exception:
            pass

    with TestClient(app) as c:
        yield c

    # Restore lifecycle handlers for any non-test usage of the app object.
    app.router.on_startup[:] = saved_startup
    app.router.on_shutdown[:] = saved_shutdown
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_vehicle(
    db,
    stock_number: str = "TEST001",
    vin: str = "1HGCM82633A123456",
    dealer_id: Optional[int] = None,
    location_name: Optional[str] = None,
    year: int = 2022,
    make: str = "Toyota",
    model: str = "Camry",
    trim: str = "XSE",
    price: float = 28500.0,
    mileage: int = 15000,
    exterior_color: str = "Silver",
    interior_color: str = "Black",
    body_style: str = "Sedan",
    condition: str = "used",
    fuel_type: str = "Gasoline",
    transmission: str = "Automatic",
    image_url: str = "https://cdn.example.com/car.jpg",
    listing_url: str = "https://www.almcars.com/inventory/test001",
    carfax_url: Optional[str] = None,
    carfax_fetched_at: datetime = None,
    is_active: bool = True,
    days_on_lot: int = 5,
    first_seen: datetime = None,
    last_seen: datetime = None,
) -> models.Vehicle:
    v = models.Vehicle(
        stock_number=stock_number,
        vin=vin,
        dealer_id=dealer_id,
        location_name=location_name,
        year=year,
        make=make,
        model=model,
        trim=trim,
        price=price,
        mileage=mileage,
        exterior_color=exterior_color,
        interior_color=interior_color,
        body_style=body_style,
        condition=condition,
        fuel_type=fuel_type,
        transmission=transmission,
        image_url=image_url,
        listing_url=listing_url,
        carfax_url=carfax_url,
        carfax_fetched_at=carfax_fetched_at,
        is_active=is_active,
        days_on_lot=days_on_lot,
        first_seen=first_seen or datetime.utcnow(),
        last_seen=last_seen or datetime.utcnow(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def make_watchlist_alert(
    db,
    name: str = "Test Alert",
    make: str = None,
    model: str = None,
    max_price: float = None,
    min_price: float = None,
    max_mileage: int = None,
    min_year: int = None,
    max_year: int = None,
    condition: str = None,
    notification_email: str = None,
    is_active: bool = True,
) -> models.WatchlistAlert:
    alert = models.WatchlistAlert(
        name=name,
        make=make,
        model=model,
        max_price=max_price,
        min_price=min_price,
        max_mileage=max_mileage,
        min_year=min_year,
        max_year=max_year,
        condition=condition,
        notification_email=notification_email,
        is_active=is_active,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def make_lead(
    db,
    customer_name: str = "John Doe",
    customer_phone: str = "555-0100",
    customer_email: str = "john@example.com",
    interested_make: str = "Toyota",
    interested_model: str = "Camry",
    max_budget: float = 35000.0,
    notes: str = "Test note",
    status: str = "new",
    source: str = "internet",
    campaign: Optional[str] = None,
    sms_consent: bool = False,
    call_consent: bool = False,
    consent_text: Optional[str] = None,
) -> models.Lead:
    now = datetime.utcnow()
    lead = models.Lead(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        interested_make=interested_make,
        interested_model=interested_model,
        max_budget=max_budget,
        notes=notes,
        status=status,
        source=source,
        campaign=campaign,
        sms_consent=sms_consent,
        sms_consent_at=now if sms_consent else None,
        call_consent=call_consent,
        call_consent_at=now if call_consent else None,
        consent_text=consent_text,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def make_scrape_log(
    db,
    status: str = "success",
    vehicles_found: int = 276,
    added_count: int = 5,
    removed_count: int = 2,
    price_change_count: int = 3,
    method: str = "httpx_dealer_filter",
    duration_seconds: float = 42.5,
    timestamp: datetime = None,
) -> models.ScrapeLog:
    log = models.ScrapeLog(
        timestamp=timestamp or datetime.utcnow(),
        status=status,
        vehicles_found=vehicles_found,
        added_count=added_count,
        removed_count=removed_count,
        price_change_count=price_change_count,
        method=method,
        duration_seconds=duration_seconds,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def make_vehicle_event(
    db,
    stock_number: str = "TEST001",
    vin: str = "1HGCM82633A123456",
    event_type: str = "added",
    description: str = "Added: 2022 Toyota Camry XSE",
    old_value: str = None,
    new_value: str = None,
    year: int = 2022,
    make: str = "Toyota",
    model: str = "Camry",
    trim: str = "XSE",
    price: float = 28500.0,
    timestamp: datetime = None,
) -> models.VehicleEvent:
    event = models.VehicleEvent(
        stock_number=stock_number,
        vin=vin,
        event_type=event_type,
        description=description,
        old_value=old_value,
        new_value=new_value,
        year=year,
        make=make,
        model=model,
        trim=trim,
        price=price,
        timestamp=timestamp or datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ──────────────────────────────────────────────────────────────────────────────
# Pytest fixture factories — used by new test files (test_vehicles.py, etc.)
# These fixtures receive db_session and return a callable factory function.
# New-style tests that use db_session directly should use these fixtures
# instead of the plain helper functions above.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def make_dealer(db_session):
    """
    Pytest fixture factory for Dealer rows.

    Usage in tests:
        def test_something(client, db_session, make_dealer):
            d = make_dealer(id=323, name="ALM Mall of Georgia")
    """
    _counter = [0]

    def _factory(
        id: Optional[int] = None,
        name: Optional[str] = None,
        city: str = "Atlanta",
        state: str = "GA",
        is_active: bool = True,
        scrape_priority: int = 1,
        last_scraped: Optional[datetime] = None,
    ) -> models.Dealer:
        _counter[0] += 1
        dealer = models.Dealer(
            id=id if id is not None else (9000 + _counter[0]),
            name=name if name is not None else f"ALM Test Dealer {_counter[0]}",
            city=city,
            state=state,
            is_active=is_active,
            scrape_priority=scrape_priority,
            last_scraped=last_scraped,
            created_at=datetime.utcnow(),
        )
        db_session.add(dealer)
        db_session.commit()
        db_session.refresh(dealer)
        return dealer

    return _factory


@pytest.fixture()
def scrape_log_factory(db_session):
    """
    Pytest fixture factory for ScrapeLog rows (new-style Sprint-1 tests).

    Named scrape_log_factory to avoid shadowing the legacy make_scrape_log
    plain helper function imported directly by test_api_scrape.py and others.

    Usage in tests:
        def test_something(client, db_session, scrape_log_factory):
            log = scrape_log_factory(status="success", vehicles_found=276)
            dealer_log = scrape_log_factory(dealer_id=323, status="success")
    """
    def _factory(
        dealer_id: Optional[int] = None,
        location_name: Optional[str] = None,
        status: str = "success",
        method: str = "httpx",
        vehicles_found: int = 0,
        added_count: int = 0,
        removed_count: int = 0,
        price_change_count: int = 0,
        duration_seconds: float = 30.0,
        error: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        details: Optional[str] = None,
    ) -> models.ScrapeLog:
        log = models.ScrapeLog(
            dealer_id=dealer_id,
            location_name=location_name,
            status=status,
            method=method,
            vehicles_found=vehicles_found,
            added_count=added_count,
            removed_count=removed_count,
            price_change_count=price_change_count,
            duration_seconds=duration_seconds,
            error=error,
            timestamp=timestamp or datetime.utcnow(),
            details=details,
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        return log

    return _factory
