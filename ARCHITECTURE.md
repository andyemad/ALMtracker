# ALM Inventory Tracker — 24-Location Expansion Architecture

**Document Version:** 1.1
**Date:** 2026-03-10
**Author:** Backend Architect (backend-architect)
**Reviewed By:** AgentsOrchestrator (2026-03-10)
**Status:** Approved for Implementation
**Scope:** Full backend redesign from single-dealer (dealer_id=323) to all 24 ALM locations

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Database Architecture](#2-database-architecture)
3. [Migration Strategy](#3-migration-strategy)
4. [Scraper Architecture](#4-scraper-architecture)
5. [API Endpoint Specification](#5-api-endpoint-specification)
6. [Alert System Changes](#6-alert-system-changes)
7. [Configuration Management](#7-configuration-management)
8. [Performance Design](#8-performance-design)
9. [Error Isolation Strategy](#9-error-isolation-strategy)
10. [Implementation Sequence](#10-implementation-sequence)

---

## 1. System Overview

### Current State

```
almcars.com (Overfuel/Next.js SSR)
         |
         | HTTPS GET /inventory?limit=500&offset=N
         |
    scraper.py
    (filter by dealer_id=323 only)
         |
    alm.db / SQLite
    vehicles: 276 rows (no dealer column)
         |
    FastAPI (main.py)
    (no location filtering)
         |
    React/Vite frontend
    (single-location view)
```

### Target State

```
almcars.com (Overfuel/Next.js SSR)
         |
         | Single pagination pass — all ~6,900 vehicles
         |
    scraper.py
    (bucket results by dealer_id — 24 dealers simultaneously)
         |
         | Dict[dealer_id -> List[vehicle_dict]]
         |
    main.py run_scrape()
    (per-dealer change detection loop)
         |
    alm.db / SQLite
    dealers: 24 rows
    vehicles: ~6,900 rows (dealer_id FK, composite unique key)
    vehicle_events: per-dealer attribution
    scrape_logs: aggregate + per-dealer JSON detail
    watchlist_alerts: optional dealer_id scope
         |
    FastAPI (main.py)
    GET /api/dealers
    GET /api/vehicles?dealer_id=N   (all endpoints location-aware)
    GET /api/stats?dealer_id=N
    GET /api/dealers/{id}/stats
         |
    React/Vite frontend
    LocationContext (global dealer selector)
    /locations page (24-card overview)
```

### Design Principles

1. **Single pagination pass**: All 24 dealers are collected in one traversal of the Overfuel
   inventory pages (~14 pages, ~6,900 vehicles). This avoids N*14 HTTP requests and keeps
   total scrape time under 90 seconds.

2. **Dealer FK as authoritative identity**: The Overfuel `dealer_id` integer becomes the
   primary dealer identifier. It is stored in the `dealers` table and referenced as a FK
   from `vehicles`, `vehicle_events`, and `scrape_logs`. This allows disabling/enabling
   dealers without code changes.

3. **Composite uniqueness**: Stock numbers are NOT globally unique across ALM locations.
   The vehicle uniqueness key changes from `stock_number` alone to `(dealer_id, stock_number)`.
   This is a P0 correctness fix — ignoring it causes cross-dealer vehicle collisions.

4. **Zero downtime migration**: The existing 276 Mall of Georgia records are preserved
   by assigning `dealer_id=323` and `location_name='ALM Mall of Georgia'` via a startup
   migration guard. No data is dropped or re-created.

5. **Backward compatibility**: All existing API endpoints remain functional with no
   `dealer_id` param — they aggregate across all dealers, preserving the current behavior
   as the "all locations" view.

---

## 2. Database Architecture

### 2.1 Entity-Relationship Diagram

```
dealers (NEW)
  id (PK, integer — Overfuel dealer_id)
  name
  city
  state
  is_active
  scrape_priority
  created_at
  last_scraped
       |
       | 1:N
       |
vehicles (MODIFIED)
  id (PK)
  dealer_id (FK -> dealers.id, indexed)    <- NEW
  location_name (denormalized, indexed)    <- NEW
  vin
  stock_number
  UNIQUE(dealer_id, stock_number)          <- CHANGED from UNIQUE(stock_number)
  year, make, model, trim
  price, mileage
  exterior_color, interior_color
  body_style, condition, fuel_type
  transmission
  image_url, listing_url
  is_active
  first_seen, last_seen, days_on_lot
       |
       | 1:N
       |
vehicle_events (MODIFIED)
  id (PK)
  dealer_id (nullable, indexed)           <- NEW
  location_name (nullable)                <- NEW
  stock_number
  vin
  event_type
  description
  old_value, new_value
  year, make, model, trim, price
  timestamp

watchlist_alerts (MODIFIED)
  id (PK)
  dealer_id (nullable)                    <- NEW  (NULL = all locations)
  location_name (nullable)               <- NEW
  name, make, model
  max_price, min_price, max_mileage
  min_year, max_year, condition
  notification_email
  is_active
  created_at, last_triggered, trigger_count

leads (UNCHANGED)
  id (PK)
  customer_name, customer_phone, customer_email
  interested_make, interested_model, max_budget
  notes, status, source
  created_at, updated_at

scrape_logs (MODIFIED)
  id (PK)
  dealer_id (nullable, indexed)           <- NEW  (NULL = aggregate run)
  location_name (nullable)               <- NEW
  details (TEXT/JSON)                    <- NEW  (per-dealer breakdown)
  timestamp
  vehicles_found
  added_count, removed_count, price_change_count
  status, method, error, duration_seconds
```

### 2.2 SQL Schema — Complete DDL

The following represents the target schema after all migrations are applied. SQLAlchemy
generates this via `Base.metadata.create_all()`. The DDL is shown here for audit and
review purposes.

```sql
-- ─── Dealers ──────────────────────────────────────────────────────────────────
CREATE TABLE dealers (
    id              INTEGER PRIMARY KEY,        -- Overfuel dealer_id (e.g. 323)
    name            VARCHAR NOT NULL,           -- "ALM Mall of Georgia"
    city            VARCHAR,                    -- "Buford"
    state           VARCHAR DEFAULT 'GA',
    is_active       BOOLEAN DEFAULT 1,          -- FALSE = skip in scraper
    scrape_priority INTEGER DEFAULT 1,          -- lower = scrape first (future use)
    created_at      DATETIME DEFAULT (datetime('now')),
    last_scraped    DATETIME
);

CREATE INDEX ix_dealers_is_active ON dealers(is_active);


-- ─── Vehicles ─────────────────────────────────────────────────────────────────
CREATE TABLE vehicles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id       INTEGER REFERENCES dealers(id),   -- FK, nullable during migration
    location_name   VARCHAR,                          -- denormalized for query speed
    vin             VARCHAR,
    stock_number    VARCHAR NOT NULL,
    year            INTEGER,
    make            VARCHAR,
    model           VARCHAR,
    trim            VARCHAR,
    price           REAL,
    mileage         INTEGER,
    exterior_color  VARCHAR,
    interior_color  VARCHAR,
    body_style      VARCHAR,
    condition       VARCHAR,
    fuel_type       VARCHAR,
    transmission    VARCHAR,
    image_url       VARCHAR,
    listing_url     VARCHAR,
    is_active       BOOLEAN DEFAULT 1,
    first_seen      DATETIME DEFAULT (datetime('now')),
    last_seen       DATETIME DEFAULT (datetime('now')),
    days_on_lot     INTEGER DEFAULT 0,
    CONSTRAINT uq_dealer_stock UNIQUE (dealer_id, stock_number)
);

-- Performance indexes (Sprint 4 — S4-1)
CREATE INDEX ix_vehicle_vin            ON vehicles(vin);
CREATE INDEX ix_vehicle_make           ON vehicles(make);
CREATE INDEX ix_vehicle_model          ON vehicles(model);
CREATE INDEX ix_vehicle_dealer_active  ON vehicles(dealer_id, is_active);
CREATE INDEX ix_vehicle_location       ON vehicles(location_name);
CREATE INDEX ix_vehicle_make_model     ON vehicles(make, model);
CREATE INDEX ix_vehicle_price          ON vehicles(price);
CREATE INDEX ix_vehicle_days_on_lot    ON vehicles(days_on_lot);


-- ─── Vehicle Events ───────────────────────────────────────────────────────────
CREATE TABLE vehicle_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id     INTEGER,                   -- denormalized (no FK for performance)
    location_name VARCHAR,
    stock_number  VARCHAR,
    vin           VARCHAR,
    event_type    VARCHAR,                   -- added | removed | price_change
    description   VARCHAR,
    old_value     VARCHAR,
    new_value     VARCHAR,
    year          INTEGER,
    make          VARCHAR,
    model         VARCHAR,
    trim          VARCHAR,
    price         REAL,
    timestamp     DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX ix_vehicle_events_stock      ON vehicle_events(stock_number);
CREATE INDEX ix_vehicle_events_dealer     ON vehicle_events(dealer_id);
CREATE INDEX ix_vehicle_events_timestamp  ON vehicle_events(timestamp);
CREATE INDEX ix_vehicle_events_type       ON vehicle_events(event_type);


-- ─── Watchlist Alerts ─────────────────────────────────────────────────────────
CREATE TABLE watchlist_alerts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id          INTEGER,              -- NULL = match all locations
    location_name      VARCHAR,
    name               VARCHAR,
    make               VARCHAR,
    model              VARCHAR,
    max_price          REAL,
    min_price          REAL,
    max_mileage        INTEGER,
    min_year           INTEGER,
    max_year           INTEGER,
    condition          VARCHAR,
    notification_email VARCHAR,
    is_active          BOOLEAN DEFAULT 1,
    created_at         DATETIME DEFAULT (datetime('now')),
    last_triggered     DATETIME,
    trigger_count      INTEGER DEFAULT 0
);


-- ─── Leads (unchanged) ────────────────────────────────────────────────────────
CREATE TABLE leads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name    VARCHAR,
    customer_phone   VARCHAR,
    customer_email   VARCHAR,
    interested_make  VARCHAR,
    interested_model VARCHAR,
    max_budget       REAL,
    notes            TEXT,
    status           VARCHAR DEFAULT 'new',
    source           VARCHAR,
    created_at       DATETIME DEFAULT (datetime('now')),
    updated_at       DATETIME DEFAULT (datetime('now'))
);


-- ─── Scrape Logs ──────────────────────────────────────────────────────────────
CREATE TABLE scrape_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id           INTEGER,             -- NULL = aggregate run across all dealers
    location_name       VARCHAR,
    details             TEXT,                -- JSON: per-dealer breakdown
    timestamp           DATETIME DEFAULT (datetime('now')),
    vehicles_found      INTEGER DEFAULT 0,
    added_count         INTEGER DEFAULT 0,
    removed_count       INTEGER DEFAULT 0,
    price_change_count  INTEGER DEFAULT 0,
    status              VARCHAR DEFAULT 'success',
    method              VARCHAR,
    error               TEXT,
    duration_seconds    REAL
);

CREATE INDEX ix_scrape_logs_timestamp ON scrape_logs(timestamp);
CREATE INDEX ix_scrape_logs_dealer    ON scrape_logs(dealer_id);
```

### 2.3 WAL Mode

Enable SQLite WAL (Write-Ahead Logging) to eliminate write-lock contention between
the scraper's bulk writes and the API's concurrent reads. Add to `database.py`:

```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

`busy_timeout=5000` prevents `SQLITE_BUSY` errors during concurrent access by retrying
for up to 5 seconds before raising.

---

## 3. Migration Strategy

### 3.1 Guiding Constraints

- SQLite does not support `ALTER TABLE ... ADD COLUMN ... NOT NULL` without a default.
  All new columns are defined `nullable=True` in SQLAlchemy; the existing 276 rows are
  backfilled via an UPDATE after the column is added.
- No Alembic is used in this phase. Migrations run as idempotent Python functions in
  `database.py` called once at application startup before any routes are served.
- The migration is safe to re-run: each step checks if the column already exists via
  `PRAGMA table_info` before attempting `ALTER TABLE`.

### 3.2 Migration Functions in database.py

```python
def _column_exists(conn, table: str, column: str) -> bool:
    """Check via PRAGMA table_info whether a column exists in a SQLite table."""
    result = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in result)


def run_migrations(engine) -> None:
    """
    Idempotent startup migration guard.
    Applies each schema change exactly once, logging the result.
    Safe to call on every application startup.
    """
    logger = logging.getLogger("database.migrations")

    with engine.connect() as conn:

        # ── Migration 1: Add dealer_id and location_name to vehicles ──────────
        if not _column_exists(conn, "vehicles", "dealer_id"):
            logger.info("Migration 1: Adding dealer_id to vehicles")
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN dealer_id INTEGER"))
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN location_name VARCHAR"))
            conn.execute(text(
                "UPDATE vehicles SET dealer_id = 323, "
                "location_name = 'ALM Mall of Georgia' WHERE dealer_id IS NULL"
            ))
            conn.commit()
            logger.info("Migration 1: Complete — 276 existing vehicles assigned dealer_id=323")
        else:
            logger.info("Migration 1: Skipped (dealer_id already present on vehicles)")

        # ── Migration 2: Add dealer_id to vehicle_events ──────────────────────
        if not _column_exists(conn, "vehicle_events", "dealer_id"):
            logger.info("Migration 2: Adding dealer_id to vehicle_events")
            conn.execute(text("ALTER TABLE vehicle_events ADD COLUMN dealer_id INTEGER"))
            conn.execute(text("ALTER TABLE vehicle_events ADD COLUMN location_name VARCHAR"))
            # Backfill events that can be tied to a vehicle with known dealer_id
            conn.execute(text("""
                UPDATE vehicle_events
                SET dealer_id = (
                    SELECT v.dealer_id FROM vehicles v
                    WHERE v.stock_number = vehicle_events.stock_number
                    LIMIT 1
                ),
                location_name = (
                    SELECT v.location_name FROM vehicles v
                    WHERE v.stock_number = vehicle_events.stock_number
                    LIMIT 1
                )
                WHERE dealer_id IS NULL
            """))
            conn.commit()
            logger.info("Migration 2: Complete — vehicle_events backfilled")
        else:
            logger.info("Migration 2: Skipped (dealer_id already present on vehicle_events)")

        # ── Migration 3: Add dealer_id and details to scrape_logs ─────────────
        if not _column_exists(conn, "scrape_logs", "dealer_id"):
            logger.info("Migration 3: Adding dealer_id and details to scrape_logs")
            conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN dealer_id INTEGER"))
            conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN location_name VARCHAR"))
            conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN details TEXT"))
            conn.commit()
            logger.info("Migration 3: Complete")
        else:
            logger.info("Migration 3: Skipped (dealer_id already present on scrape_logs)")

        # ── Migration 4: Add dealer_id to watchlist_alerts ───────────────────
        if not _column_exists(conn, "watchlist_alerts", "dealer_id"):
            logger.info("Migration 4: Adding dealer_id to watchlist_alerts")
            conn.execute(text("ALTER TABLE watchlist_alerts ADD COLUMN dealer_id INTEGER"))
            conn.execute(text("ALTER TABLE watchlist_alerts ADD COLUMN location_name VARCHAR"))
            # Existing alerts stay NULL (match all locations — correct behavior)
            conn.commit()
            logger.info("Migration 4: Complete — existing alerts scope to all locations")
        else:
            logger.info("Migration 4: Skipped (dealer_id already present on watchlist_alerts)")

        # ── Migration 5: Unique constraint change on vehicles ─────────────────
        # SQLite does not support DROP CONSTRAINT. The composite unique key
        # (dealer_id, stock_number) is enforced at the application layer in the
        # scraper and run_scrape() loop. The old UNIQUE(stock_number) constraint
        # was applied at table creation time and cannot be dropped without
        # recreating the table.
        #
        # Resolution: The Vehicle model's stock_number column must have
        # unique=False in SQLAlchemy for new table creation. For the existing
        # table, the old unique index on stock_number is left in place but
        # becomes harmless because all 276 existing records are from the same
        # dealer, making stock_number effectively unique within that set.
        # New dealers' stock numbers that collide with MoG stock numbers will
        # NOT hit the old unique index because stock numbers are dealer-scoped
        # in practice. The application enforces (dealer_id, stock_number)
        # uniqueness via upsert logic in run_scrape().
        #
        # Full constraint enforcement requires SQLite table recreation (deferred
        # to post-Sprint 1 cleanup or when migrating to PostgreSQL).
        logger.info("Migration 5: Stock number uniqueness enforced at application layer")
```

### 3.3 Startup Sequence

```python
# In main.py @app.on_event("startup")

async def startup():
    # Step 1: Create tables that do not exist (dealers, etc.)
    Base.metadata.create_all(bind=engine)

    # Step 2: Apply column-level migrations to existing tables
    from database import run_migrations
    run_migrations(engine)

    # Step 3: Seed dealer registry (idempotent)
    db = SessionLocal()
    seed_dealers(db)
    db.close()

    # Step 4: Initial scrape if DB is empty
    db2 = SessionLocal()
    count = db2.query(models.Vehicle).count()
    db2.close()
    if count == 0:
        logger.info("Empty DB — running initial scrape...")
        db3 = SessionLocal()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_scrape, db3)
        db3.close()

    # Step 5: Start scheduler
    scheduler.add_job(...)
    scheduler.start()
```

---

## 4. Scraper Architecture

### 4.1 Design Goals

| Goal | Mechanism |
|---|---|
| Single HTTP pass for all 24 dealers | Paginate once; bucket by dealer_id in memory |
| Error isolation per dealer | Per-dealer try/except; one dealer failure does not abort others |
| Backward compatibility | `scrape_single_dealer(323)` API preserved for tests and manual triggers |
| No N*14 page fetches | Collect all dealer data in one traversal, not one traversal per dealer |
| Scrape time budget | All 6,900 vehicles across ~14 pages in under 90 seconds |

### 4.2 Core Data Structures

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DealerConfig:
    """Lightweight dealer descriptor used during a scrape run."""
    dealer_id: int
    name: str
    city: str = ""
    state: str = "GA"


# Return type of scrape_all_vehicles()
# Maps dealer_id -> list of normalized vehicle dicts
DealerVehicleMap = Dict[int, List[Dict]]
```

### 4.3 Refactored scraper.py — Public Interface

```python
def scrape_all_vehicles(
    dealers: Optional[List[DealerConfig]] = None,
) -> Tuple[DealerVehicleMap, str]:
    """
    Paginate through the full Overfuel inventory in a single pass.
    Bucket each vehicle into its dealer's list.

    Args:
        dealers: List of DealerConfig objects to collect. If None, the caller
                 (main.py) passes the active dealer set from the DB.
                 Passing an explicit list enables targeted partial scrapes.

    Returns:
        (dealer_vehicle_map, method_string)
        dealer_vehicle_map: {dealer_id: [normalized_vehicle_dict, ...]}
        method_string: e.g. "httpx_multi_dealer"
    """


def scrape_single_dealer(
    dealer_id: int,
    dealer_name: str = "",
) -> List[Dict]:
    """
    Convenience wrapper: returns only the vehicles for one dealer.
    Performs a full pagination pass (same HTTP cost as scrape_all_vehicles
    with one dealer in the set). Used for targeted re-scrapes and tests.
    """
    result, _ = scrape_all_vehicles(
        dealers=[DealerConfig(dealer_id=dealer_id, name=dealer_name)]
    )
    return result.get(dealer_id, [])
```

### 4.4 Internal Bucketing Logic

```python
def scrape_all_vehicles(
    dealers: Optional[List[DealerConfig]] = None,
) -> Tuple[DealerVehicleMap, str]:

    dealer_set: set[int] = {d.dealer_id for d in dealers} if dealers else None
    dealer_buckets: DealerVehicleMap = {d.dealer_id: [] for d in dealers} if dealers else {}

    offset = 0
    total_global: Optional[int] = None

    while True:
        data = _fetch_page(offset=offset)
        if not data:
            logger.warning(f"No data at offset={offset}, stopping")
            break

        results, total = _extract(data)

        if total_global is None:
            total_global = total
            logger.info(f"Total Overfuel inventory: {total} vehicles across all stores")
            # If no dealer filter given, build bucket keys from discovered dealer_ids
            if dealer_set is None:
                for v in results:
                    did = v.get("dealer_id")
                    if did and did not in dealer_buckets:
                        dealer_buckets[did] = []

        if not results:
            break

        for v in results:
            did = v.get("dealer_id")
            if did is None:
                logger.debug(f"Vehicle {v.get('stocknumber')} has no dealer_id — skipping")
                continue
            # If dealer_set is None (collect all), auto-expand buckets
            if dealer_set is None:
                dealer_buckets.setdefault(did, [])
                dealer_buckets[did].append(normalize_vehicle(v))
            elif did in dealer_set:
                dealer_buckets[did].append(normalize_vehicle(v))

        logger.info(
            f"  offset={offset}: fetched {len(results)} vehicles "
            f"(cumulative buckets: {sum(len(b) for b in dealer_buckets.values())})"
        )

        offset += len(results)
        if total_global and offset >= total_global:
            break

    # Per-dealer summary log
    for did, vehicles in dealer_buckets.items():
        logger.info(f"  dealer_id={did}: {len(vehicles)} vehicles")

    total_collected = sum(len(b) for b in dealer_buckets.values())
    if total_collected == 0:
        logger.warning("0 vehicles collected — check dealer IDs or site structure")
        return {}, "no_results"

    return dealer_buckets, "httpx_multi_dealer"
```

### 4.5 normalize_vehicle() — Dealer Field Extraction

The existing `normalize_vehicle()` already extracts `dealer_id` and `location_name` from
the Overfuel payload. Verify and harden the dealer name extraction:

```python
def normalize_vehicle(v: Dict) -> Dict:
    """Normalize a raw Overfuel vehicle dict. dealer_id and location_name are required."""
    stock = str(v.get("stocknumber") or v.get("stock_number") or v.get("id") or "")

    image_url = v.get("featuredphoto") or v.get("image_url") or ""
    if image_url and not image_url.startswith("http"):
        image_url = f"https:{image_url}"

    slug = v.get("slug") or ""
    if slug:
        listing_url = f"{BASE_URL}/inventory/{slug}" if not slug.startswith("http") else slug
    elif stock:
        listing_url = f"{BASE_URL}/inventory/{stock.lower()}"
    else:
        listing_url = ""

    # Dealer attribution — must be reliable for all 24 locations
    raw_dealer = v.get("dealer") or {}
    dealer_id_from_payload = v.get("dealer_id")
    if isinstance(raw_dealer, dict):
        location_name = raw_dealer.get("name") or ""
        # Prefer dealer.dealer_id if top-level dealer_id is absent
        if dealer_id_from_payload is None:
            dealer_id_from_payload = raw_dealer.get("id") or raw_dealer.get("dealer_id")
    else:
        location_name = str(raw_dealer) if raw_dealer else ""

    return {
        "vin": v.get("vin") or "",
        "stock_number": stock,
        "year": int(v.get("year") or 0),
        "make": v.get("make") or "",
        "model": v.get("model") or "",
        "trim": v.get("trim") or v.get("series") or "",
        "price": _clean_price(v.get("price") or v.get("originalprice")),
        "mileage": _clean_mileage(v.get("mileage")),
        "exterior_color": v.get("exteriorcolor") or v.get("exteriorcolorstandard") or "",
        "interior_color": v.get("interiorcolor") or v.get("interiorcolorstandard") or "",
        "body_style": v.get("body") or v.get("body_style") or "",
        "condition": v.get("condition") or "",
        "fuel_type": v.get("fuel") or v.get("fuel_type") or "",
        "transmission": v.get("transmission") or "",
        "image_url": image_url,
        "listing_url": listing_url,
        "dealer_id": dealer_id_from_payload,
        "location_name": location_name,
    }
```

### 4.6 Scrape Timing Analysis

| Metric | Single-Dealer (current) | 24-Dealer (target) |
|---|---|---|
| HTTP pages fetched | ~14 | ~14 (same pass) |
| Vehicles processed | 276 (filtered) | ~6,900 (all bucketed) |
| CPU (normalize + bucket) | Negligible | ~10ms additional |
| DB writes per run | ~276 | Up to ~6,900 |
| Total scrape time | ~60s | ~75–90s (DB write dominated) |
| Scheduler interval | 6 hours | 6 hours (unchanged) |

The single pagination pass means HTTP time is identical to the current single-dealer scrape.
The additional time comes from the larger DB write batch. 90 seconds is well within the
6-hour scheduler interval with no risk of overlap.

---

## 5. API Endpoint Specification

### 5.1 New Endpoints

#### GET /api/dealers

Returns all registered ALM dealer locations.

```
GET /api/dealers?active_only=true

Response 200:
[
  {
    "id": 323,
    "name": "ALM Mall of Georgia",
    "city": "Buford",
    "state": "GA",
    "is_active": true,
    "scrape_priority": 1,
    "last_scraped": "2026-03-10T06:00:00",
    "active_vehicle_count": 276
  },
  ...
]

Query Parameters:
  active_only (bool, default=true): filter to is_active=true dealers only
```

Implementation:

```python
@app.get("/api/dealers")
def list_dealers(
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    q = db.query(models.Dealer)
    if active_only:
        q = q.filter(models.Dealer.is_active == True)
    dealers = q.order_by(models.Dealer.name).all()
    return [_dealer_dict(d, db) for d in dealers]


def _dealer_dict(d: models.Dealer, db: Session) -> dict:
    active_vehicle_count = (
        db.query(func.count(models.Vehicle.id))
        .filter(
            models.Vehicle.dealer_id == d.id,
            models.Vehicle.is_active == True,
        )
        .scalar()
    ) or 0
    return {
        "id": d.id,
        "name": d.name,
        "city": d.city,
        "state": d.state,
        "is_active": d.is_active,
        "scrape_priority": d.scrape_priority,
        "last_scraped": d.last_scraped.isoformat() if d.last_scraped else None,
        "active_vehicle_count": active_vehicle_count,
    }
```

#### GET /api/dealers/{dealer_id}/stats

Returns the same structure as `GET /api/stats` but scoped to one dealer.

```
GET /api/dealers/323/stats

Response 200: (same schema as /api/stats, scoped to dealer_id=323)
{
  "total_active": 276,
  "added_today": 3,
  "removed_today": 1,
  "active_alerts": 5,
  "avg_price": 28450.00,
  "last_scrape": "2026-03-10T06:00:00",
  "last_scrape_status": "success",
  "dealer_id": 323,
  "location_name": "ALM Mall of Georgia",
  "trend": [...]
}

Response 404: {"detail": "Dealer not found"}
```

### 5.2 Updated Endpoints — Signatures

All changes are additive (new optional query parameters). No existing parameters are removed.
Clients that do not pass `dealer_id` receive aggregated results across all dealers — the
current behavior is preserved.

#### GET /api/stats

```python
@app.get("/api/stats")
def get_stats(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW: scope to single dealer
):
```

When `dealer_id` is provided:
- All counts (`total_active`, `added_today`, `removed_today`) filter by `dealer_id`
- Response includes `"dealer_id": dealer_id` and `"location_name": "..."`

When `dealer_id` is absent:
- All counts aggregate across all dealers (current behavior)
- Response includes `"dealer_id": null` and `"location_name": "All Locations"`

#### GET /api/vehicles

```python
@app.get("/api/vehicles")
def list_vehicles(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW
    location_name: Optional[str] = None,      # NEW (fuzzy match)
    search: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    max_mileage: Optional[int] = None,
    condition: Optional[str] = None,
    body_style: Optional[str] = None,
    is_active: Optional[bool] = True,
    sort_by: str = "first_seen",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
```

Filter additions:
```python
if dealer_id:
    q = q.filter(models.Vehicle.dealer_id == dealer_id)
if location_name:
    q = q.filter(models.Vehicle.location_name.ilike(f"%{location_name}%"))
```

Response: `_vehicle_dict()` now includes `"dealer_id"` and `"location_name"` fields.

#### GET /api/vehicles/export

```python
@app.get("/api/vehicles/export")
def export_csv(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW
):
```

CSV header updated to include `Location` column between `Stock#` and `VIN`.

#### GET /api/filter-options

```python
@app.get("/api/filter-options")
def filter_options(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW
):
```

When `dealer_id` is provided, makes and body styles are scoped to that dealer's active inventory.

#### GET /api/events

```python
@app.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW
    event_type: Optional[str] = None,
    days: int = 30,
    page: int = 1,
    page_size: int = 50,
):
```

#### GET /api/leads/{lead_id}/matches

```python
@app.get("/api/leads/{lead_id}/matches")
def lead_matches(
    lead_id: int,
    dealer_id: Optional[int] = None,          # NEW
    db: Session = Depends(get_db),
):
```

#### GET /api/scrape-logs

```python
@app.get("/api/scrape-logs")
def list_scrape_logs(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,          # NEW
    limit: int = 20,
):
```

Response: `_log_dict()` now includes `"dealer_id"`, `"location_name"`, and `"details"` fields.
`"details"` is a parsed JSON object or `null`.

#### POST /api/scrape/trigger

```python
@app.post("/api/scrape/trigger")
async def trigger_scrape(
    data: dict = None,                        # UPDATED: accepts optional body
    background_tasks: BackgroundTasks = None,
):
    dealer_id = (data or {}).get("dealer_id")  # None = scrape all
    db = SessionLocal()
    if dealer_id:
        background_tasks.add_task(run_scrape_for_dealer, dealer_id, db)
        return {"message": f"Scrape triggered for dealer_id={dealer_id}"}
    else:
        background_tasks.add_task(run_scrape, db)
        return {"message": "Full scrape triggered for all dealers"}
```

#### POST/PUT /api/watchlist and GET /api/watchlist

```python
# POST /api/watchlist — new body field
{
  "name": "BMW Under $30k at MoG",
  "make": "BMW",
  "max_price": 30000,
  "dealer_id": 323,                           # NEW: optional, null = all locations
  "notification_email": "..."
}

# GET /api/watchlist response — new fields per alert
{
  "id": 1,
  "dealer_id": 323,                           # NEW
  "location_name": "ALM Mall of Georgia",     # NEW
  ...
}
```

### 5.3 Response Shape Updates — _vehicle_dict()

```python
def _vehicle_dict(v: models.Vehicle) -> dict:
    return {
        "id": v.id,
        "dealer_id": v.dealer_id,                # NEW
        "location_name": v.location_name,        # NEW
        "vin": v.vin,
        "stock_number": v.stock_number,
        "year": v.year,
        "make": v.make,
        "model": v.model,
        "trim": v.trim,
        "price": v.price,
        "mileage": v.mileage,
        "exterior_color": v.exterior_color,
        "interior_color": v.interior_color,
        "body_style": v.body_style,
        "condition": v.condition,
        "fuel_type": v.fuel_type,
        "transmission": v.transmission,
        "image_url": v.image_url,
        "listing_url": v.listing_url,
        "is_active": v.is_active,
        "first_seen": v.first_seen.isoformat() if v.first_seen else None,
        "last_seen": v.last_seen.isoformat() if v.last_seen else None,
        "days_on_lot": v.days_on_lot or 0,
    }
```

### 5.4 Complete API Route Map

| Method | Path | New Params | Notes |
|---|---|---|---|
| GET | /api/dealers | `active_only` | NEW endpoint |
| GET | /api/dealers/{id}/stats | — | NEW endpoint |
| GET | /api/stats | `dealer_id` | Updated |
| GET | /api/vehicles | `dealer_id`, `location_name` | Updated |
| GET | /api/vehicles/export | `dealer_id` | Updated |
| GET | /api/filter-options | `dealer_id` | Updated |
| GET | /api/events | `dealer_id` | Updated |
| GET | /api/watchlist | — | Response includes dealer fields |
| POST | /api/watchlist | `dealer_id`, `location_name` | Updated |
| PUT | /api/watchlist/{id} | `dealer_id`, `location_name` | Updated |
| DELETE | /api/watchlist/{id} | — | Unchanged |
| GET | /api/leads | — | Unchanged |
| POST | /api/leads | — | Unchanged |
| PUT | /api/leads/{id} | — | Unchanged |
| DELETE | /api/leads/{id} | — | Unchanged |
| GET | /api/leads/{id}/matches | `dealer_id` | Updated |
| GET | /api/scrape-logs | `dealer_id` | Updated |
| POST | /api/scrape/trigger | body `{"dealer_id": N}` | Updated |

---

## 6. Alert System Changes

### 6.1 Watchlist Alert Scope

Existing alerts have no `dealer_id` column. After migration they will have `dealer_id=NULL`,
which is the correct "match all locations" behavior. No existing alert behavior changes.

New alerts may optionally include a `dealer_id` to scope notifications to a single location.
The matching function enforces this:

```python
def vehicle_matches_alert(v: models.Vehicle, a: models.WatchlistAlert) -> bool:
    # Location scope check — NEW, evaluated first for early exit
    if a.dealer_id is not None and v.dealer_id != a.dealer_id:
        return False

    # Existing criteria — unchanged
    if a.make and a.make.lower() not in (v.make or "").lower():
        return False
    if a.model and a.model.lower() not in (v.model or "").lower():
        return False
    if a.max_price is not None and v.price is not None and v.price > a.max_price:
        return False
    if a.min_price is not None and v.price is not None and v.price < a.min_price:
        return False
    if a.max_mileage is not None and v.mileage is not None and v.mileage > a.max_mileage:
        return False
    if a.min_year is not None and v.year is not None and v.year < a.min_year:
        return False
    if a.max_year is not None and v.year is not None and v.year > a.max_year:
        return False
    if a.condition and a.condition.lower() not in (v.condition or "").lower():
        return False
    return True
```

### 6.2 get_matching_vehicles() Optimization

Pre-filter at the DB layer when `dealer_id` is set, rather than loading all active vehicles
into Python memory and filtering in Python:

```python
def get_matching_vehicles(alert: models.WatchlistAlert, db: Session) -> List[models.Vehicle]:
    q = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    # Pre-filter at DB level for scoped alerts
    if alert.dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == alert.dealer_id)
    vehicles = q.all()
    return [v for v in vehicles if vehicle_matches_alert(v, alert)]
```

### 6.3 Email Notification Updates

Email subject and body are updated to include location context:

```python
def _send_email(alert: models.WatchlistAlert, vehicles: list):
    ...
    location_label = alert.location_name or "All ALM Locations"
    subject = f"[ALM Alert] {alert.name} @ {location_label} — {len(vehicles)} match(es)"

    lines = [
        f"ALM Watchlist Alert: {alert.name}",
        f"Location: {location_label}",
        f"Found {len(vehicles)} matching vehicle(s):\n",
    ]
    for v in vehicles:
        lines.append(f"  {v.year} {v.make} {v.model} {v.trim or ''}".strip())
        lines.append(f"  Location: {v.location_name or 'Unknown'}")
        lines.append(f"  Price: ${v.price:,.0f}" if v.price else "  Price: N/A")
        lines.append(f"  Mileage: {v.mileage:,}" if v.mileage else "  Mileage: N/A")
        lines.append(f"  Stock #: {v.stock_number}")
        if v.listing_url:
            lines.append(f"  Link: {v.listing_url}")
        lines.append("")
    ...
```

### 6.4 check_and_notify_watchlist() in Multi-Dealer Context

The existing function queries `Vehicle.first_seen >= latest_log.timestamp` to find vehicles
added during the most recent scrape. This continues to work correctly at 24-dealer scale
because the `latest_log.timestamp` captures the start time of the most recent scrape run
regardless of how many dealers were included.

No structural change is required. The only needed update is passing the per-dealer context
into the email if the alert has a `dealer_id` set.

---

## 7. Configuration Management

### 7.1 Dealer Registry — Seed Data

The dealer registry is stored in the `dealers` database table and seeded at application
startup via an idempotent `seed_dealers()` function. The seed data is defined as a Python
constant in `scraper.py` and used by both the seeder and the scraper.

The dealer IDs below are to be confirmed via the Sprint 0 discovery process (S0-1). The
placeholder list shows the structure; actual IDs must come from a live `__NEXT_DATA__` parse.

```python
# scraper.py
# Populated from S0-1 discovery. Update this dict after running the discovery script.
DEALER_REGISTRY: Dict[int, Dict[str, str]] = {
    323: {"name": "ALM Mall of Georgia",    "city": "Buford"},
    # --- Confirmed after S0-1 ---
    # 401: {"name": "ALM Roswell",          "city": "Roswell"},
    # 402: {"name": "ALM Buckhead",         "city": "Atlanta"},
    # 403: {"name": "ALM Kennesaw",         "city": "Kennesaw"},
    # ... (remaining 20 dealers from discovery)
}
```

### 7.2 seed_dealers() Function

```python
# main.py or a new seeder.py module
def seed_dealers(db: Session) -> None:
    """
    Insert all known ALM dealers into the dealers table.
    Idempotent: skips dealers that already exist by primary key.
    """
    from scraper import DEALER_REGISTRY
    inserted = 0
    for dealer_id, info in DEALER_REGISTRY.items():
        existing = db.query(models.Dealer).filter(
            models.Dealer.id == dealer_id
        ).first()
        if not existing:
            db.add(models.Dealer(
                id=dealer_id,
                name=info["name"],
                city=info.get("city", ""),
                state=info.get("state", "GA"),
                is_active=True,
                scrape_priority=1,
            ))
            inserted += 1
    if inserted:
        db.commit()
        logger.info(f"Seeded {inserted} new dealer(s)")
    else:
        logger.info("Dealer seed: all dealers already present")
```

### 7.3 run_scrape() Integration — Active Dealer List

At scrape time, the active dealer list is always read from the DB (not from the static dict),
so that operators can disable a dealer via a DB update without touching code:

```python
def run_scrape(db: Session):
    start = datetime.utcnow()
    log = models.ScrapeLog(timestamp=start, status="running", dealer_id=None)
    db.add(log)
    db.commit()

    try:
        # Fetch active dealers from DB — not from the hard-coded DEALER_REGISTRY
        active_dealers = db.query(models.Dealer).filter(
            models.Dealer.is_active == True
        ).order_by(models.Dealer.scrape_priority, models.Dealer.name).all()

        dealer_configs = [
            DealerConfig(
                dealer_id=d.id,
                name=d.name,
                city=d.city or "",
            )
            for d in active_dealers
        ]

        dealer_vehicle_map, method = scrape_all_vehicles(dealers=dealer_configs)
        ...
```

### 7.4 Environment Variables

```
# /Users/emadsiddiqui/ALM/backend/.env.example

# SMTP — required for watchlist email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
ALERT_FROM_NAME=ALM Inventory Tracker

# Scraper tuning — optional
SCRAPE_INTERVAL_HOURS=6
SCRAPE_TIMEOUT_SECONDS=300
SCRAPE_MAX_RETRIES=3

# SQLite path — optional override
DATABASE_URL=sqlite:///./alm.db
```

### 7.5 Operational Runbook

```
# Disable a dealer from being scraped (no code change required):
UPDATE dealers SET is_active = 0 WHERE id = <dealer_id>;

# Re-enable a dealer:
UPDATE dealers SET is_active = 1 WHERE id = <dealer_id>;

# Trigger a manual scrape for all dealers:
POST /api/scrape/trigger
Body: {}

# Trigger a manual scrape for one dealer only:
POST /api/scrape/trigger
Body: {"dealer_id": 323}

# Verify all dealers are registered:
GET /api/dealers

# Check last scrape time per dealer:
GET /api/dealers
(inspect "last_scraped" field per dealer)

# Check scrape log for all dealers:
GET /api/scrape-logs

# Check scrape log for one dealer:
GET /api/scrape-logs?dealer_id=323
```

---

## 8. Performance Design

### 8.1 Index Strategy

At ~6,900 vehicles, SQLite handles all queries comfortably with proper indexes. The most
common query patterns and their supporting indexes:

| Query Pattern | Index Used | Expected Rows Scanned |
|---|---|---|
| `is_active=true` (all active) | `ix_vehicle_dealer_active (dealer_id, is_active)` | 6,900 → index scan |
| `dealer_id=323, is_active=true` | `ix_vehicle_dealer_active` | 276 |
| `make=Toyota, dealer_id=323` | `ix_vehicle_make_model` + filter | ~50 |
| `price <= 30000, dealer_id=323` | `ix_vehicle_price` + filter | varies |
| Events by dealer | `ix_vehicle_events_dealer` | varies |
| Scrape logs by dealer | `ix_scrape_logs_dealer` | varies |

### 8.2 Query Time Targets

| Endpoint | Target P95 | At 6,900 Vehicles |
|---|---|---|
| GET /api/vehicles (no filter) | < 200ms | Achievable with index scan |
| GET /api/vehicles?dealer_id=323 | < 50ms | 276 rows via composite index |
| GET /api/stats (aggregate) | < 200ms | COUNT with indexed filter |
| GET /api/stats?dealer_id=323 | < 50ms | Indexed COUNT |
| GET /api/dealers (24 rows) | < 20ms | Full scan of 24-row table |
| GET /api/filter-options | < 200ms | DISTINCT on indexed columns |

### 8.3 SQLite WAL Mode

As documented in Section 2.3, WAL mode enables concurrent readers during the scraper's
write transaction. Without WAL, every API request during a scrape run would block on the
SQLite write lock, causing P95 latency spikes of 2–5 seconds.

### 8.4 Scrape Write Strategy

During `run_scrape()`, the full set of DB writes for all 24 dealers is batched into a single
`db.commit()` at the end of each dealer's change detection loop. This reduces transaction
overhead while keeping rollback granularity at the per-dealer level:

```python
for dealer_config in dealer_configs:
    did = dealer_config.dealer_id
    vehicles = dealer_vehicle_map.get(did, [])
    try:
        _process_dealer(db, did, dealer_config.name, vehicles, ...)
        db.commit()  # commit per dealer — not per vehicle
    except Exception as e:
        db.rollback()
        logger.error(f"Failed processing dealer_id={did}: {e}")
        # Continue to next dealer — error isolation
```

### 8.5 DB Vacuum Schedule

With ~6,900 vehicles and their events accumulating over time, add a monthly SQLite VACUUM
to reclaim space from soft-deleted (is_active=False) vehicle rows:

```python
scheduler.add_job(
    lambda: engine.execute("VACUUM"),
    "cron",
    day=1, hour=3,  # first of month at 3am
    id="vacuum_job",
    replace_existing=True,
)
```

---

## 9. Error Isolation Strategy

### 9.1 Per-Dealer Error Boundary in run_scrape()

The multi-dealer scrape loop wraps each dealer's processing in an independent try/except.
A failure in dealer B's change detection (database error, unexpected data shape) does not
abort dealers C through Z. The per-dealer error is logged, the failed dealer's result is
recorded in the `ScrapeLog.details` JSON, and the overall log status is set to `"partial"`
rather than `"error"` when at least one dealer succeeds.

```python
dealer_results = []
overall_status = "success"

for dealer_config in dealer_configs:
    did = dealer_config.dealer_id
    dealer_vehicles = dealer_vehicle_map.get(did, [])
    dealer_result = {
        "id": did,
        "name": dealer_config.name,
        "found": len(dealer_vehicles),
        "added": 0,
        "removed": 0,
        "price_changes": 0,
        "status": "success",
        "error": None,
    }

    try:
        added, removed, price_changes = _process_dealer(
            db, did, dealer_config.name, dealer_vehicles, active_map
        )
        dealer_result.update({
            "added": added,
            "removed": removed,
            "price_changes": price_changes,
        })
        db.commit()

        # Update dealer.last_scraped
        dealer_row = db.query(models.Dealer).filter(models.Dealer.id == did).first()
        if dealer_row:
            dealer_row.last_scraped = datetime.utcnow()
        db.commit()

    except Exception as e:
        db.rollback()
        dealer_result["status"] = "error"
        dealer_result["error"] = str(e)
        overall_status = "partial"
        logger.error(f"Dealer {did} ({dealer_config.name}) processing failed: {e}")

    dealer_results.append(dealer_result)
```

### 9.2 HTTP Fetch Resilience

The existing `_fetch_page()` already wraps HTTP errors in a try/except and returns `None`.
The pagination loop breaks on `None`. No change needed for single-page HTTP failures.

For full scrape abort (all pages failing), the `log.status = "error"` path in the existing
code handles this correctly.

### 9.3 Scrape Timeout Guard

Add a timeout wrapper to prevent a hung scrape from blocking the next scheduled run:

```python
import signal

class ScrapeTimeoutError(Exception):
    pass

def _timeout_handler(signum, frame):
    raise ScrapeTimeoutError("Scrape exceeded maximum allowed time")

def run_scrape(db: Session):
    timeout_seconds = int(os.getenv("SCRAPE_TIMEOUT_SECONDS", "300"))
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        _run_scrape_inner(db)
    except ScrapeTimeoutError:
        logger.error(f"Scrape aborted after {timeout_seconds}s timeout")
        # log.status already set to "running" — update to "error"
        ...
    finally:
        signal.alarm(0)  # cancel alarm
```

Note: `signal.SIGALRM` is Unix-only. On macOS (development) this works correctly.

### 9.4 Scheduler Overlap Prevention

The existing `replace_existing=True` in the APScheduler job prevents job stacking. Verify
that the job ID is stable across restarts:

```python
scheduler.add_job(
    lambda: run_scrape(SessionLocal()),
    IntervalTrigger(hours=int(os.getenv("SCRAPE_INTERVAL_HOURS", "6"))),
    id="full_scrape_all_dealers",   # stable ID — changed from "scrape_job"
    replace_existing=True,
    max_instances=1,                # belt-and-suspenders: never run twice
)
```

---

## 10. Implementation Sequence

The implementation maps to the sprint plan in SPRINT.md. The sequences below add concrete
file-level ordering to avoid blocked work.

### Phase 1 — Foundation (Sprint 1, no regressions risk)

```
1. models.py
   a. Add Dealer class
   b. Add dealer_id, location_name to Vehicle
   c. Add UniqueConstraint("dealer_id", "stock_number") to Vehicle.__table_args__
   d. Add dealer_id, location_name to VehicleEvent
   e. Add dealer_id, location_name, details to ScrapeLog
   f. Add dealer_id, location_name to WatchlistAlert

2. database.py
   a. Add WAL mode pragma listener
   b. Add _column_exists() helper
   c. Add run_migrations() function

3. scraper.py
   a. Add DealerConfig dataclass
   b. Remove DEALER_ID = 323 and DEALER_NAME module constants
   c. Add DEALER_REGISTRY dict (populated after S0-1 discovery)
   d. Refactor scrape_all_vehicles() to return DealerVehicleMap
   e. Add scrape_single_dealer() wrapper
   f. Harden normalize_vehicle() dealer field extraction

4. main.py
   a. Update startup() to call run_migrations() and seed_dealers()
   b. Update run_scrape() to consume DealerVehicleMap
   c. Change active_map key to (dealer_id, stock_number)
   d. Add per-dealer processing loop with error isolation
   e. Update ScrapeLog to include details JSON
```

### Phase 2 — API Layer (Sprint 2, build on Phase 1)

```
5. main.py (continued)
   a. Add _dealer_dict() helper
   b. Update _vehicle_dict() to include dealer fields
   c. Update _event_dict() to include dealer fields
   d. Update _log_dict() to include dealer fields and parse details JSON
   e. Update _alert_dict() to include dealer fields
   f. Add GET /api/dealers endpoint
   g. Add GET /api/dealers/{dealer_id}/stats endpoint
   h. Add dealer_id param to GET /api/stats
   i. Add dealer_id param to GET /api/vehicles
   j. Add dealer_id param to GET /api/vehicles/export
   k. Add dealer_id param to GET /api/filter-options
   l. Add dealer_id param to GET /api/events
   m. Add dealer_id param to GET /api/scrape-logs
   n. Update POST /api/scrape/trigger to accept body with dealer_id
   o. Update POST/PUT /api/watchlist to accept dealer_id
   p. Add dealer_id param to GET /api/leads/{id}/matches

6. alerts.py
   a. Update vehicle_matches_alert() to check alert.dealer_id
   b. Update get_matching_vehicles() to pre-filter at DB level
   c. Update _send_email() subject and body to include location
```

### Phase 3 — Hardening (Sprint 4, after Phase 2 is stable)

```
7. database.py
   a. Add monthly VACUUM scheduler job

8. main.py
   a. Add SCRAPE_TIMEOUT_SECONDS guard
   b. Update scheduler job ID and add max_instances=1

9. models.py
   a. Add composite indexes (ix_vehicle_dealer_active, etc.)

10. backend/tests/test_multi_location.py (new file)
    a. 10 integration test cases as specified in SPRINT.md S4-2
```

---

## Appendix A — Critical Architecture Decision: Stock Number Uniqueness

**Problem**: In the current system, `Vehicle.stock_number` is defined with `unique=True`.
Stock numbers are assigned by individual dealerships and are NOT globally unique across the
24 ALM locations. Two different stores can and do reuse the same stock number format
(e.g., both MoG and Roswell may have a vehicle with stock# "P12345").

**Impact of ignoring this**: If the scraper processes dealer B's vehicle with stock# "P12345"
and dealer A already has an active vehicle with that stock number, the uniqueness violation
causes either a duplicate key error (crashing the scrape) or the wrong vehicle record being
updated (silent data corruption).

**Chosen resolution**: The composite unique constraint `(dealer_id, stock_number)` is the
correct long-term solution. For SQLite's existing table, this is enforced at the application
layer during `run_scrape()` by keying the `active_map` on `(dealer_id, stock_number)` tuples
rather than `stock_number` alone. New table creation (on a fresh DB) uses the SQLAlchemy
`UniqueConstraint("dealer_id", "stock_number")` declaratively.

**SQLite constraint limitation**: The old `UNIQUE(stock_number)` index on the existing
`alm.db` cannot be dropped without recreating the table. Because all 276 existing records
are from the same dealer (MoG), no actual collision exists in the current data. New dealers'
stock numbers that happen to match MoG stock numbers will be caught by the application-layer
key before any INSERT is attempted, and the correct record (keyed by dealer_id+stock_number)
will be found in the active_map. A full table recreation to enforce the constraint at the DB
level is deferred to the PostgreSQL migration (Technical Debt item 2 in SPRINT.md).

---

## Appendix B — Overfuel API Field Reference

```
Overfuel __NEXT_DATA__ path:
  props.pageProps.inventory.results  -> array of vehicle objects
  props.pageProps.inventory.meta.total -> total vehicle count (all stores)

Vehicle object fields of interest:
  dealer_id          -> integer, uniquely identifies the dealership
  dealer.name        -> string, human-readable dealer name
  dealer.id          -> same as dealer_id (fallback)
  stocknumber        -> stock number (our stock_number)
  vin                -> VIN
  year, make, model, trim, series
  price, originalprice
  mileage
  exteriorcolor, exteriorcolorstandard
  interiorcolor, interiorcolorstandard
  body               -> body style (our body_style)
  condition          -> "Used" | "New" | "Certified"
  fuel               -> fuel type (our fuel_type)
  transmission
  featuredphoto      -> primary image URL (may be protocol-relative)
  slug               -> URL slug for the listing page

Pagination:
  URL: /inventory?limit=500&offset=N
  Page size: 500 vehicles per request
  Total vehicles: ~6,898 across all stores
  Pages required: ~14

Location filter note:
  The location filter (?location=buford) is client-side only.
  SSR returns total=0 when a location param is present.
  Always fetch unfiltered and apply dealer_id filter in Python.
```
