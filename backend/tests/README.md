# ALM Inventory Tracker — Backend Test Suite

## Overview

Comprehensive test suite for the ALM Inventory Tracker FastAPI backend.
Tests run against an in-memory SQLite database with full transaction-level
isolation between tests — no test data persists between test functions.

## Running the Tests

From the backend directory:

```bash
cd /Users/emadsiddiqui/ALM/backend

# Run all tests
venv/bin/python -m pytest tests/

# Run with verbose output
venv/bin/python -m pytest tests/ -v

# Run a single test file
venv/bin/python -m pytest tests/test_vehicles.py

# Run a single test class
venv/bin/python -m pytest tests/test_vehicles.py::TestListVehicles

# Run a single test
venv/bin/python -m pytest tests/test_vehicles.py::TestListVehicles::test_returns_only_active_vehicles

# Run with short traceback for quick failure diagnosis
venv/bin/python -m pytest tests/ --tb=short -q

# Run with coverage report
venv/bin/python -m pytest tests/ --cov=. --cov-report=term-missing --ignore=venv
```

## Expected Output

```
357 passed, 54 xfailed, 14 xpassed in ~2.5s
```

- **passed** — tests that verify currently working API behavior
- **xfailed** — tests for Sprint 1 multi-location features not yet in main.py
- **xpassed** — xfail-marked tests that unexpectedly pass (benign, no action required)

## Test Files

### Pre-existing Files (legacy suite)

| File | What it covers | Tests |
|------|---------------|-------|
| `test_alerts.py` | `vehicle_matches_alert()` matching logic unit tests | 25 |
| `test_api_events.py` | `GET /api/events` — filtering, pagination | 10 |
| `test_api_integration.py` | Multi-endpoint integration scenarios | 18 |
| `test_api_leads.py` | Lead CRUD and inventory matching | 32 |
| `test_api_scrape.py` | `GET /api/scrape-logs` — listing and pagination | 10 |
| `test_api_stats.py` | `GET /api/stats` — all stat fields | 12 |
| `test_api_vehicles.py` | `GET /api/vehicles` — filters, sort, pagination | 33 |
| `test_api_watchlist.py` | Watchlist CRUD and match counts | 20 |
| `test_multi_location.py` | Multi-location expansion (mostly xfail) | 12 |

### Sprint 1 Files (24-location expansion)

| File | What it covers | Tests (passing + xfail) |
|------|---------------|-------------------------|
| `test_vehicles.py` | Full vehicle API including `dealer_id` filter | 56 (49 + 7 xfail) |
| `test_dealers.py` | `GET /api/dealers` and `GET /api/dealers/{id}/stats` | 22 (all xfail) |
| `test_stats.py` | `GET /api/stats` with `dealer_id` scoping | 28 (19 + 9 xfail) |
| `test_events.py` | `GET /api/events` with `dealer_id` filter | 24 (19 + 5 xfail) |
| `test_leads.py` | Lead CRUD + matches with `dealer_id` scoping | 54 (51 + 3 xfail) |
| `test_watchlist.py` | Watchlist CRUD + dealer-scoped alert matching | 58 (51 + 7 xfail) |

## Fixtures (conftest.py)

### Database Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `_create_tables` | session | Creates all SQLAlchemy tables once per test session |
| `db_session` | function | In-memory SQLite session; all changes rolled back after each test |
| `db` | function | Alias for `db_session` (backward compat with legacy tests) |
| `client` | function | FastAPI `TestClient` wired to `db_session`; APScheduler startup suppressed |

### Factory Fixtures (Sprint 1 tests)

| Fixture | Returns | Usage |
|---------|---------|-------|
| `make_dealer` | Callable | `make_dealer(id=323, name="ALM Mall of Georgia")` |
| `scrape_log_factory` | Callable | `scrape_log_factory(dealer_id=323, status="success")` |

### Plain Helper Functions (legacy tests)

These are imported directly by the legacy `test_api_*.py` files:

```python
from tests.conftest import make_vehicle, make_watchlist_alert, make_lead
from tests.conftest import make_scrape_log, make_vehicle_event

v     = make_vehicle(db, stock_number="TEST001", make="Toyota", price=25000.0)
alert = make_watchlist_alert(db, name="My Alert", make="Toyota", max_price=30000.0)
lead  = make_lead(db, customer_name="John Doe", interested_make="Honda")
log   = make_scrape_log(db, status="success", vehicles_found=276)
event = make_vehicle_event(db, stock_number="TEST001", event_type="added")
```

## Sprint 1 xfail Tests

Tests for features planned in ARCHITECTURE.md but not yet implemented in
`main.py` are decorated with `@pytest.mark.xfail(strict=False)`. When a
Sprint 1 feature is implemented, remove the corresponding `xfail` marker.

Features awaiting implementation before removing xfail markers:

1. `GET /api/dealers` — list all dealers with active vehicle counts
   - Remove xfail from `test_dealers.py::TestListDealers`
2. `GET /api/dealers/{id}/stats` — per-dealer stats and trend data
   - Remove xfail from `test_dealers.py::TestDealerStats`
3. `dealer_id` query param on `GET /api/vehicles`
   - Remove xfail from `test_vehicles.py::TestVehiclesDealerIdFilter`
   - Remove xfail from `test_vehicles.py::TestExportCSV` (dealer_id test)
4. `dealer_id` query param on `GET /api/events`
   - Remove xfail from `test_events.py::TestListEventsDealerIdFilter`
5. `dealer_id` query param on `GET /api/stats`
   - Remove xfail from `test_stats.py::TestGetStatsDealerIdFilter`
6. `dealer_id` field on `POST /api/watchlist` and dealer-scoped matching
   - Remove xfail from `test_watchlist.py::TestDealerScopedWatchlist`
7. `dealer_id` filter on `GET /api/leads/{id}/matches`
   - Remove xfail from `test_leads.py::TestLeadMatchesDealerIdFilter`

## Test Isolation

Each test function gets:
- A fresh empty SQLAlchemy session backed by a rolled-back transaction
- A fresh `TestClient` with the app's startup and shutdown events suppressed

The startup event suppression prevents the `AsyncIOScheduler` from binding
to the test event loop. Without this, the scheduler holds a stale loop
reference after the first test, causing `RuntimeError: Event loop is closed`
on all subsequent tests.

APScheduler startup and shutdown hooks are cleared before each `TestClient`
context and restored afterward, so the production app behavior is unaffected
when run outside of tests.

## Coverage Targets

| Module | Target |
|--------|--------|
| `main.py` | > 85% |
| `alerts.py` | > 95% |
| `models.py` | > 60% |
| `database.py` | > 50% |
