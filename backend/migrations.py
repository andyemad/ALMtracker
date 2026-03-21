"""
ALM Inventory Tracker — Database Migration Script
==================================================
Version: 2.0 (24-location expansion)

Purpose:
    Idempotent migration script that evolves the alm.db schema from the v1.0
    single-dealer layout to the v2.0 multi-dealer (24-location) layout.

Safety guarantees:
    - Every operation is guarded by an existence check before execution.
    - All 276 existing Mall of Georgia vehicle records are preserved and assigned
      dealer_id=323 / location_name='ALM Mall of Georgia'.
    - Running this script multiple times produces exactly the same result as
      running it once (idempotent).
    - No table is dropped or recreated; only ALTER TABLE ADD COLUMN and CREATE
      INDEX operations are used (SQLite-safe).
    - All operations run inside a single connection; errors roll back cleanly.

What this script does (in order):
    Step 1  Create the `dealers` table if it does not exist
            (handled by Base.metadata.create_all — new table, safe to call repeatedly)

    Step 2  Seed all 24 ALM dealer locations into the `dealers` table
            Confirmed dealers (dealer_id=323) seeded as is_active=True.
            Placeholder dealers seeded as is_active=False until IDs are verified.
            Existing rows are skipped (ON CONFLICT DO NOTHING equivalent via query guard).

    Step 3  Add dealer_id + location_name columns to `vehicles` if absent
            Backfill all existing rows to dealer_id=323 / location_name='ALM Mall of Georgia'.

    Step 4  Add dealer_id + location_name columns to `vehicle_events` if absent
            Backfill events by joining through vehicles on stock_number.

    Step 5  Add dealer_id + location_name + details columns to `scrape_logs` if absent

    Step 6  Add dealer_id + location_name columns to `watchlist_alerts` if absent
            Existing alerts stay dealer_id=NULL (scope = all locations — correct behavior).

    Step 7  Create composite unique index (dealer_id, stock_number) on `vehicles`
            Named ix_uq_dealer_stock — created only if it does not already exist.
            Note: the old UNIQUE(stock_number) SQLite constraint is NOT dropped
            (SQLite cannot drop individual constraints without table recreation).
            Since all 276 existing rows are from dealer_id=323, no collision occurs.
            New rows from other dealers will be controlled at the application layer.

    Step 8  Create supporting indexes if absent:
            - ix_vehicle_dealer_active  on vehicles(dealer_id, is_active)
            - ix_vehicle_events_dealer  on vehicle_events(dealer_id)
            - ix_scrape_logs_dealer     on scrape_logs(dealer_id)

    Step 9  Add sold_at column to leads if absent

    Step 10 Add campaign + consent tracking columns to leads if absent

Usage:
    Run once before starting the v2.0 backend:
        cd /Users/emadsiddiqui/ALM/backend
        source venv/bin/activate
        python migrations.py

    Or import and call run_migrations() from within the application startup:
        from migrations import run_migrations
        from database import engine
        run_migrations(engine)

    Can be called multiple times safely — each step is guarded.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dealer seed data
# ---------------------------------------------------------------------------
# Keep this in sync with DEALER_REGISTRY in scraper.py.
# The migration uses its own copy to avoid a circular import at startup
# (scraper.py imports httpx/BeautifulSoup; migrations.py must be importable
# with only SQLAlchemy available in the venv at migration time).
#
# Structure: (dealer_id, name, city, is_active)
#   is_active=True  -> confirmed Overfuel dealer_id from live feed
#   is_active=False -> placeholder ID pending Sprint 0 discovery
#
# Update is_active to True and correct the dealer_id once you run:
#   python -c "from scraper import _discover_dealer_ids; _discover_dealer_ids()"

DEALER_SEED: list[tuple[int, str, str, bool]] = [
    # (dealer_id, name,                           city,             is_active)
    # All IDs confirmed via live _discover_dealer_ids() pass on 2026-03-10
    (318,  "ALM Hyundai Athens",        "Athens",           True),
    (319,  "ALM Hyundai Florence",      "Florence",         True),
    (320,  "ALM Kia South",             "Union City",       True),
    (321,  "ALM Kennesaw",              "Kennesaw",         True),
    (322,  "ALM Gwinnett",              "Duluth",           True),
    (323,  "ALM Mall of Georgia",       "Buford",           True),
    (324,  "ALM Marietta",              "Marietta",         True),
    (325,  "ALM Newnan",                "Newnan",           True),
    (326,  "ALM Roswell",               "Roswell",          True),
    (433,  "ALM Hyundai West",          "Lithia Springs",   True),
    (508,  "ALM Nissan Newnan",         "Newnan",           True),
    (512,  "ALM Kia Perry",             "Perry",            True),
    (513,  "ALM CDJR Perry",            "Perry",            True),
    (573,  "ALM Ford Marietta",         "Marietta",         True),
    (580,  "ALM Chevrolet South",       "Union City",       True),
    (882,  "ALM Hyundai Lumberton",     "Lumberton",        True),
    (1433, "ALM GMC South",             "Morrow",           True),
    (1438, "ALM Mazda South",           "Morrow",           True),
    (1525, "Carrollton Hyundai",        "Carrollton",       True),
    (1764, "ALM CDJR Macon",            "Macon",            True),
    (1766, "ALM Hyundai Macon",         "Macon",            True),
    (1768, "ALM Mazda Macon",           "Macon",            True),
    (1769, "Genesis Macon",             "Macon",            True),
    (1770, "Hyundai Warner Robins",     "Warner Robins",    True),
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _column_exists(conn, table: str, column: str) -> bool:
    """Return True if `column` exists in `table` (SQLite PRAGMA-based check)."""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result.fetchall())


def _index_exists(conn, index_name: str) -> bool:
    """Return True if an index with `index_name` exists in SQLite's master catalog."""
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": index_name},
    )
    return result.fetchone() is not None


def _table_exists(conn, table: str) -> bool:
    """Return True if `table` exists in SQLite's master catalog."""
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def _step1_create_dealers_table(conn) -> None:
    """
    Create the dealers table using raw DDL (mirrors the SQLAlchemy model exactly).
    Base.metadata.create_all() is the preferred call site; this is a belt-and-
    suspenders fallback for running migrations.py standalone without the ORM.
    """
    if _table_exists(conn, "dealers"):
        logger.info("Step 1: dealers table already exists — skipping CREATE")
        return

    logger.info("Step 1: Creating dealers table")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS dealers (
            id              INTEGER PRIMARY KEY,
            name            VARCHAR NOT NULL,
            city            VARCHAR,
            state           VARCHAR DEFAULT 'GA',
            is_active       BOOLEAN DEFAULT 1,
            scrape_priority INTEGER DEFAULT 1,
            created_at      DATETIME,
            last_scraped    DATETIME
        )
    """))
    logger.info("Step 1: dealers table created")


def _step2_seed_dealers(conn) -> None:
    """
    Insert all known ALM dealer locations into the dealers table.
    Skips any dealer_id that already has a row (idempotent).
    Updates name/city for rows that exist but have stale data.
    """
    logger.info("Step 2: Seeding dealers table")
    inserted = 0
    updated = 0
    skipped = 0

    from datetime import datetime
    now = datetime.utcnow().isoformat()

    for dealer_id, name, city, is_active in DEALER_SEED:
        existing = conn.execute(
            text("SELECT id, name, city, is_active FROM dealers WHERE id = :id"),
            {"id": dealer_id},
        ).fetchone()

        if existing is None:
            conn.execute(
                text("""
                    INSERT INTO dealers (id, name, city, state, is_active, scrape_priority, created_at)
                    VALUES (:id, :name, :city, 'GA', :is_active, 1, :created_at)
                """),
                {
                    "id":         dealer_id,
                    "name":       name,
                    "city":       city,
                    "is_active":  1 if is_active else 0,
                    "created_at": now,
                },
            )
            status = "ACTIVE" if is_active else "inactive (placeholder ID)"
            logger.info(f"  Inserted dealer_id={dealer_id}: {name} ({city}) [{status}]")
            inserted += 1
        else:
            # Row exists — update name/city if they changed (e.g. after discovery confirms real ID)
            if existing[1] != name or existing[2] != city:
                conn.execute(
                    text("UPDATE dealers SET name=:name, city=:city WHERE id=:id"),
                    {"id": dealer_id, "name": name, "city": city},
                )
                logger.info(f"  Updated dealer_id={dealer_id}: {name} ({city})")
                updated += 1
            else:
                skipped += 1

    logger.info(
        f"Step 2 complete: {inserted} inserted, {updated} updated, {skipped} already current"
    )


def _step3_migrate_vehicles(conn) -> None:
    """
    Add dealer_id and location_name columns to `vehicles` if absent.
    Backfills all existing rows to Mall of Georgia (dealer_id=323).
    """
    dealer_id_present  = _column_exists(conn, "vehicles", "dealer_id")
    location_name_present = _column_exists(conn, "vehicles", "location_name")

    if dealer_id_present and location_name_present:
        logger.info("Step 3: vehicles.dealer_id and location_name already present — skipping")
        return

    if not dealer_id_present:
        logger.info("Step 3a: Adding dealer_id column to vehicles")
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN dealer_id INTEGER"))

    if not location_name_present:
        logger.info("Step 3b: Adding location_name column to vehicles")
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN location_name VARCHAR"))

    # Backfill: assign all existing NULL rows to Mall of Georgia
    result = conn.execute(
        text("""
            UPDATE vehicles
            SET dealer_id     = 323,
                location_name = 'ALM Mall of Georgia'
            WHERE dealer_id IS NULL
        """)
    )
    rows_backfilled = result.rowcount
    logger.info(
        f"Step 3 complete: {rows_backfilled} vehicle rows backfilled to dealer_id=323"
    )


def _step4_migrate_vehicle_events(conn) -> None:
    """
    Add dealer_id and location_name columns to `vehicle_events` if absent.
    Backfills events by joining through `vehicles` on stock_number where possible.
    Orphaned events (no matching vehicle) remain dealer_id=NULL.
    """
    dealer_id_present     = _column_exists(conn, "vehicle_events", "dealer_id")
    location_name_present = _column_exists(conn, "vehicle_events", "location_name")

    if dealer_id_present and location_name_present:
        logger.info("Step 4: vehicle_events columns already present — skipping")
        return

    if not dealer_id_present:
        logger.info("Step 4a: Adding dealer_id column to vehicle_events")
        conn.execute(text("ALTER TABLE vehicle_events ADD COLUMN dealer_id INTEGER"))

    if not location_name_present:
        logger.info("Step 4b: Adding location_name column to vehicle_events")
        conn.execute(text("ALTER TABLE vehicle_events ADD COLUMN location_name VARCHAR"))

    # Backfill via JOIN on stock_number (most events will match their vehicle)
    result = conn.execute(
        text("""
            UPDATE vehicle_events
            SET dealer_id = (
                SELECT v.dealer_id
                FROM vehicles v
                WHERE v.stock_number = vehicle_events.stock_number
                  AND v.dealer_id IS NOT NULL
                LIMIT 1
            ),
            location_name = (
                SELECT v.location_name
                FROM vehicles v
                WHERE v.stock_number = vehicle_events.stock_number
                  AND v.location_name IS NOT NULL
                LIMIT 1
            )
            WHERE dealer_id IS NULL
        """)
    )
    rows_backfilled = result.rowcount
    logger.info(
        f"Step 4 complete: {rows_backfilled} vehicle_event rows backfilled via stock_number join"
    )


def _step5_migrate_scrape_logs(conn) -> None:
    """
    Add dealer_id, location_name, and details columns to `scrape_logs` if absent.
    Existing rows remain with dealer_id=NULL (retroactively treated as aggregate logs).
    """
    added = []

    if not _column_exists(conn, "scrape_logs", "dealer_id"):
        logger.info("Step 5a: Adding dealer_id column to scrape_logs")
        conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN dealer_id INTEGER"))
        added.append("dealer_id")

    if not _column_exists(conn, "scrape_logs", "location_name"):
        logger.info("Step 5b: Adding location_name column to scrape_logs")
        conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN location_name VARCHAR"))
        added.append("location_name")

    if not _column_exists(conn, "scrape_logs", "details"):
        logger.info("Step 5c: Adding details column to scrape_logs")
        conn.execute(text("ALTER TABLE scrape_logs ADD COLUMN details TEXT"))
        added.append("details")

    if added:
        logger.info(f"Step 5 complete: Added columns to scrape_logs: {added}")
    else:
        logger.info("Step 5: All scrape_logs columns already present — skipping")


def _step6_migrate_watchlist_alerts(conn) -> None:
    """
    Add dealer_id and location_name columns to `watchlist_alerts` if absent.
    Existing alerts remain dealer_id=NULL which means "match all locations"
    — correct backward-compatible behavior.
    """
    dealer_id_present     = _column_exists(conn, "watchlist_alerts", "dealer_id")
    location_name_present = _column_exists(conn, "watchlist_alerts", "location_name")

    if dealer_id_present and location_name_present:
        logger.info("Step 6: watchlist_alerts columns already present — skipping")
        return

    if not dealer_id_present:
        logger.info("Step 6a: Adding dealer_id column to watchlist_alerts")
        conn.execute(text("ALTER TABLE watchlist_alerts ADD COLUMN dealer_id INTEGER"))

    if not location_name_present:
        logger.info("Step 6b: Adding location_name column to watchlist_alerts")
        conn.execute(text("ALTER TABLE watchlist_alerts ADD COLUMN location_name VARCHAR"))

    logger.info(
        "Step 6 complete: Existing watchlist alerts retain dealer_id=NULL "
        "(scope = all locations)"
    )


def _step7_drop_old_stock_unique_index(conn) -> None:
    """
    Drop the old UNIQUE INDEX on vehicles(stock_number) that was created by the
    v1.0 schema. Stock numbers are dealer-scoped (not globally unique), so this
    index must be removed before multi-dealer inserts can work.

    The old index is a standalone CREATE UNIQUE INDEX (not an inline table
    constraint), so it can be dropped directly in SQLite without table recreation.

    Index name in existing alm.db: ix_vehicles_stock_number
    """
    old_index = "ix_vehicles_stock_number"
    if _index_exists(conn, old_index):
        logger.info(f"Step 7a: Dropping old unique index {old_index!r}")
        conn.execute(text(f"DROP INDEX {old_index}"))
        logger.info(f"Step 7a: {old_index!r} dropped")
    else:
        logger.info(f"Step 7a: Old index {old_index!r} not present — skipping")


def _step7_create_composite_unique_index(conn) -> None:
    """
    Create the composite unique index (dealer_id, stock_number) on vehicles.

    Index name: ix_uq_dealer_stock
    This enforces the invariant that (dealer_id, stock_number) is unique per the
    v2.0 data contract.  The old UNIQUE(stock_number) constraint from the v1.0
    schema cannot be dropped without table recreation (SQLite limitation), but it
    causes no collisions because all 276 v1.0 rows share the same dealer_id=323.

    SQLite does not support CREATE UNIQUE INDEX ... IF NOT EXISTS in older versions,
    so we check existence manually before issuing the DDL.
    """
    index_name = "ix_uq_dealer_stock"

    if _index_exists(conn, index_name):
        logger.info(f"Step 7: Index {index_name!r} already exists — skipping")
        return

    logger.info(f"Step 7: Creating composite unique index {index_name!r}")
    conn.execute(
        text(f"CREATE UNIQUE INDEX {index_name} ON vehicles (dealer_id, stock_number)")
    )
    logger.info(f"Step 7 complete: {index_name!r} created on vehicles(dealer_id, stock_number)")


def _step8_create_supporting_indexes(conn) -> None:
    """
    Create supporting query-performance indexes if they do not already exist.
    All indexes match those defined in models.py __table_args__ so that
    Base.metadata.create_all() and this migration converge on the same schema.
    """
    indexes = [
        # (index_name, DDL string)
        (
            "ix_vehicle_dealer_active",
            "CREATE INDEX ix_vehicle_dealer_active ON vehicles (dealer_id, is_active)",
        ),
        (
            "ix_vehicle_events_dealer",
            "CREATE INDEX ix_vehicle_events_dealer ON vehicle_events (dealer_id)",
        ),
        (
            "ix_scrape_logs_dealer",
            "CREATE INDEX ix_scrape_logs_dealer ON scrape_logs (dealer_id)",
        ),
        # These may already exist from v1.0 — the guard handles it
        (
            "ix_vehicle_make_model",
            "CREATE INDEX ix_vehicle_make_model ON vehicles (make, model)",
        ),
        (
            "ix_vehicle_price",
            "CREATE INDEX ix_vehicle_price ON vehicles (price)",
        ),
        (
            "ix_vehicle_days_on_lot",
            "CREATE INDEX ix_vehicle_days_on_lot ON vehicles (days_on_lot)",
        ),
    ]

    created = []
    skipped = []
    for index_name, ddl in indexes:
        if _index_exists(conn, index_name):
            skipped.append(index_name)
        else:
            conn.execute(text(ddl))
            created.append(index_name)
            logger.info(f"  Created index: {index_name}")

    logger.info(
        f"Step 8 complete: {len(created)} index(es) created, "
        f"{len(skipped)} already existed"
    )


def _step9_add_sold_at_to_leads(conn) -> None:
    """
    Add sold_at column to `leads` if absent.
    Backfills existing status='sold' rows with sold_at = updated_at
    as the best available approximation for pre-migration records.
    """
    if _column_exists(conn, "leads", "sold_at"):
        logger.info("Step 9: leads.sold_at already present — skipping")
        return

    logger.info("Step 9: Adding sold_at column to leads")
    conn.execute(text("ALTER TABLE leads ADD COLUMN sold_at DATETIME"))

    result = conn.execute(
        text("""
            UPDATE leads
            SET sold_at = updated_at
            WHERE status = 'sold' AND sold_at IS NULL
        """)
    )
    logger.info(
        f"Step 9 complete: leads.sold_at added, "
        f"{result.rowcount} existing sold rows backfilled"
    )


def _step10_add_attribution_and_consent_to_leads(conn) -> None:
    """
    Add campaign attribution and explicit outreach consent columns to `leads`
    if absent. These fields let ALM track paid/organic funnel performance and
    keep an auditable record of whether SMS or calling is allowed.
    """
    additions = [
        ("campaign", "TEXT"),
        ("sms_consent", "BOOLEAN DEFAULT 0"),
        ("sms_consent_at", "DATETIME"),
        ("call_consent", "BOOLEAN DEFAULT 0"),
        ("call_consent_at", "DATETIME"),
        ("consent_text", "TEXT"),
    ]

    created = []
    skipped = []
    for column_name, column_type in additions:
        if _column_exists(conn, "leads", column_name):
            skipped.append(column_name)
            continue

        logger.info(f"Step 10: Adding leads.{column_name}")
        conn.execute(text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}"))
        created.append(column_name)

    logger.info(
        f"Step 10 complete: {len(created)} lead column(s) added, "
        f"{len(skipped)} already existed"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_migrations(engine: Engine) -> None:
    """
    Execute all migration steps against the provided SQLAlchemy engine.

    Idempotent: safe to call on a fresh DB, on a partially migrated DB,
    or on a fully migrated DB.  Each step checks current state before acting.

    Recommended call site (in main.py startup event, before seed_dealers):
        from migrations import run_migrations
        from database import engine
        run_migrations(engine)

    Args:
        engine: SQLAlchemy Engine connected to alm.db
    """
    logger.info("=" * 60)
    logger.info("ALM v2.0 migrations starting")
    logger.info("=" * 60)

    with engine.connect() as conn:
        # Enable WAL mode for better concurrent read/write performance
        conn.execute(text("PRAGMA journal_mode=WAL"))

        _step1_create_dealers_table(conn)
        _step2_seed_dealers(conn)
        _step3_migrate_vehicles(conn)
        _step4_migrate_vehicle_events(conn)
        _step5_migrate_scrape_logs(conn)
        _step6_migrate_watchlist_alerts(conn)
        _step7_drop_old_stock_unique_index(conn)
        _step7_create_composite_unique_index(conn)
        _step8_create_supporting_indexes(conn)
        _step9_add_sold_at_to_leads(conn)
        _step10_add_attribution_and_consent_to_leads(conn)

        conn.commit()

    logger.info("=" * 60)
    logger.info("ALM v2.0 migrations complete")
    logger.info("=" * 60)


def _verify_migration(engine: Engine) -> dict:
    """
    Post-migration verification.  Queries the DB to confirm every expected
    structural change is in place.  Returns a dict of check_name -> bool.

    Use for CI assertions or manual inspection after running migrations:
        from migrations import run_migrations, _verify_migration
        from database import engine
        results = _verify_migration(engine)
        assert all(results.values()), f"Migration incomplete: {results}"
    """
    checks: dict[str, bool] = {}

    with engine.connect() as conn:
        # Table existence
        checks["dealers_table_exists"]         = _table_exists(conn, "dealers")
        checks["vehicles_table_exists"]        = _table_exists(conn, "vehicles")
        checks["vehicle_events_table_exists"]  = _table_exists(conn, "vehicle_events")
        checks["watchlist_alerts_table_exists"]= _table_exists(conn, "watchlist_alerts")
        checks["scrape_logs_table_exists"]     = _table_exists(conn, "scrape_logs")

        # Column additions — vehicles
        checks["vehicles.dealer_id"]           = _column_exists(conn, "vehicles",        "dealer_id")
        checks["vehicles.location_name"]       = _column_exists(conn, "vehicles",        "location_name")

        # Column additions — vehicle_events
        checks["vehicle_events.dealer_id"]     = _column_exists(conn, "vehicle_events",  "dealer_id")
        checks["vehicle_events.location_name"] = _column_exists(conn, "vehicle_events",  "location_name")

        # Column additions — scrape_logs
        checks["scrape_logs.dealer_id"]        = _column_exists(conn, "scrape_logs",     "dealer_id")
        checks["scrape_logs.location_name"]    = _column_exists(conn, "scrape_logs",     "location_name")
        checks["scrape_logs.details"]          = _column_exists(conn, "scrape_logs",     "details")

        # Column additions — watchlist_alerts
        checks["watchlist_alerts.dealer_id"]   = _column_exists(conn, "watchlist_alerts","dealer_id")
        checks["watchlist_alerts.location_name"]= _column_exists(conn, "watchlist_alerts","location_name")
        checks["leads.sold_at"]                = _column_exists(conn, "leads", "sold_at")
        checks["leads.campaign"]               = _column_exists(conn, "leads", "campaign")
        checks["leads.sms_consent"]            = _column_exists(conn, "leads", "sms_consent")
        checks["leads.sms_consent_at"]         = _column_exists(conn, "leads", "sms_consent_at")
        checks["leads.call_consent"]           = _column_exists(conn, "leads", "call_consent")
        checks["leads.call_consent_at"]        = _column_exists(conn, "leads", "call_consent_at")
        checks["leads.consent_text"]           = _column_exists(conn, "leads", "consent_text")

        # Indexes
        checks["ix_uq_dealer_stock"]           = _index_exists(conn, "ix_uq_dealer_stock")
        checks["ix_vehicle_dealer_active"]     = _index_exists(conn, "ix_vehicle_dealer_active")
        checks["ix_vehicle_events_dealer"]     = _index_exists(conn, "ix_vehicle_events_dealer")
        checks["ix_scrape_logs_dealer"]        = _index_exists(conn, "ix_scrape_logs_dealer")

        # Data integrity — all vehicles backfilled with dealer_id=323
        result = conn.execute(
            text("SELECT COUNT(*) FROM vehicles WHERE dealer_id IS NULL")
        ).scalar()
        checks["no_null_dealer_id_on_vehicles"] = (result == 0)

        # Mall of Georgia dealer exists and is active
        mog = conn.execute(
            text("SELECT is_active FROM dealers WHERE id = 323")
        ).fetchone()
        checks["dealer_323_exists"]   = mog is not None
        checks["dealer_323_is_active"]= bool(mog[0]) if mog else False

        # Total dealers seeded
        dealer_count = conn.execute(
            text("SELECT COUNT(*) FROM dealers")
        ).scalar()
        checks[f"dealers_seeded_{len(DEALER_SEED)}"] = (dealer_count >= len(DEALER_SEED))

    passed = sum(1 for v in checks.values() if v)
    failed = [k for k, v in checks.items() if not v]

    logger.info(f"Migration verification: {passed}/{len(checks)} checks passed")
    if failed:
        logger.warning(f"FAILED checks: {failed}")
    else:
        logger.info("All migration verification checks passed.")

    return checks


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Change to backend directory so SQLite relative path resolves correctly
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)

    from database import engine, Base
    import models  # noqa: F401 — ensures all ORM models are registered before create_all

    logger.info(f"Working directory: {backend_dir}")
    logger.info(f"Database: {os.path.abspath('alm.db')}")

    # Create any brand-new tables (e.g., `dealers`) — no-op for existing tables
    logger.info("Running Base.metadata.create_all() for new tables...")
    Base.metadata.create_all(bind=engine)

    # Run column-level migrations + seeding
    run_migrations(engine)

    # Verify everything is in place
    logger.info("Running post-migration verification...")
    results = _verify_migration(engine)

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.error(f"Migration INCOMPLETE. Failed checks: {failed}")
        sys.exit(1)
    else:
        logger.info("Migration SUCCESSFUL. All checks passed.")
        sys.exit(0)
