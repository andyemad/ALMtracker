"""
ALM Inventory Tracker — SQLAlchemy Models
==========================================
Version: 2.0 (24-location expansion)

Schema changes from v1.0 (single-dealer):
  - NEW:      Dealer table (authoritative registry of all 24 ALM locations)
  - MODIFIED: Vehicle — added dealer_id (FK), location_name, composite unique constraint
  - MODIFIED: VehicleEvent — added dealer_id, location_name
  - MODIFIED: ScrapeLog — added dealer_id, location_name, details (JSON)
  - MODIFIED: WatchlistAlert — added dealer_id, location_name (optional scope)
  - MODIFIED: Lead — sold timestamp, consent fields, and campaign attribution

Critical design decision — stock number uniqueness:
  Stock numbers are NOT globally unique across ALM locations. Two dealers can share the
  same stock number. The uniqueness constraint has been changed from UNIQUE(stock_number)
  to UNIQUE(dealer_id, stock_number). All change-detection logic in main.py must key on
  the composite (dealer_id, stock_number) tuple, not stock_number alone.

Migration note:
  Column additions to existing tables are handled by run_migrations() in database.py,
  not here. Base.metadata.create_all() handles only new tables (e.g., dealers).
"""

import json
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


# ─── Dealer ───────────────────────────────────────────────────────────────────

class Dealer(Base):
    """
    Authoritative registry of ALM dealership locations.

    The primary key is the Overfuel dealer_id integer — the same value embedded
    in every vehicle object's `dealer_id` field in the Overfuel __NEXT_DATA__
    payload. Using the Overfuel ID directly as the PK avoids a surrogate-key
    translation layer and simplifies all foreign key joins.

    Seeded at application startup via seed_dealers() in main.py.
    Operator-editable: set is_active=False to exclude a dealer from scraping
    without any code change.
    """
    __tablename__ = "dealers"

    # Primary key is the Overfuel dealer_id (e.g. 323 for Mall of Georgia)
    id               = Column(Integer, primary_key=True)
    name             = Column(String, nullable=False)          # "ALM Mall of Georgia"
    city             = Column(String, nullable=True)           # "Buford"
    state            = Column(String, nullable=True, default="GA")
    is_active        = Column(Boolean, default=True)           # False = skip in scraper
    scrape_priority  = Column(Integer, default=1)              # lower = scrape first
    created_at       = Column(DateTime, default=datetime.utcnow)
    last_scraped     = Column(DateTime, nullable=True)

    # Relationships — back-references for ORM convenience (not used in hot paths)
    vehicles         = relationship("Vehicle", back_populates="dealer", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Dealer id={self.id} name={self.name!r} active={self.is_active}>"


# ─── Vehicle ──────────────────────────────────────────────────────────────────

class Vehicle(Base):
    """
    A single vehicle listing from the Overfuel inventory feed.

    Key changes from v1.0:
      - dealer_id FK links to Dealer.id
      - location_name is denormalized from Dealer.name for query performance
        (avoids a JOIN on every vehicle list query)
      - Composite unique constraint on (dealer_id, stock_number) replaces the
        former UNIQUE(stock_number) — stock numbers are dealer-scoped, not global

    Uniqueness key: (dealer_id, stock_number)
    Change detection in run_scrape() must use this composite key.
    """
    __tablename__ = "vehicles"

    id             = Column(Integer, primary_key=True, index=True)

    # ── Dealer attribution (NEW in v2.0) ──────────────────────────────────────
    dealer_id      = Column(
        Integer,
        ForeignKey("dealers.id"),
        nullable=True,   # nullable during migration; all rows backfilled to 323
        index=True,
    )
    location_name  = Column(String, nullable=True, index=True)   # denormalized

    # ── Vehicle identity ──────────────────────────────────────────────────────
    vin            = Column(String, index=True, nullable=True)
    stock_number   = Column(String, nullable=False)   # NOT globally unique — see __table_args__

    # ── Vehicle attributes ────────────────────────────────────────────────────
    year           = Column(Integer, nullable=True)
    make           = Column(String, index=True, nullable=True)
    model          = Column(String, index=True, nullable=True)
    trim           = Column(String, nullable=True)
    price          = Column(Float, nullable=True)
    mileage        = Column(Integer, nullable=True)
    exterior_color = Column(String, nullable=True)
    interior_color = Column(String, nullable=True)
    body_style     = Column(String, nullable=True)
    condition      = Column(String, nullable=True)
    fuel_type      = Column(String, nullable=True)
    transmission   = Column(String, nullable=True)
    image_url      = Column(String, nullable=True)
    listing_url    = Column(String, nullable=True)
    carfax_url     = Column(String, nullable=True)
    carfax_fetched_at = Column(DateTime, nullable=True)

    # ── Status and lifecycle ──────────────────────────────────────────────────
    is_active      = Column(Boolean, default=True)
    first_seen     = Column(DateTime, default=datetime.utcnow)
    last_seen      = Column(DateTime, default=datetime.utcnow)
    days_on_lot    = Column(Integer, default=0)

    # ── Relationship ──────────────────────────────────────────────────────────
    dealer         = relationship("Dealer", back_populates="vehicles")

    # ── Constraints and indexes ───────────────────────────────────────────────
    __table_args__ = (
        # Stock numbers are dealer-scoped — (dealer_id, stock_number) is the
        # correct uniqueness boundary. This replaces the old UNIQUE(stock_number).
        # For existing alm.db: the old index stays in place (SQLite cannot drop it
        # without table recreation) but causes no collision because all 276 existing
        # rows are from the same dealer. New table creation uses this constraint.
        UniqueConstraint("dealer_id", "stock_number", name="uq_dealer_stock"),

        # Composite index for the most common query pattern:
        # GET /api/vehicles?dealer_id=323&is_active=true
        Index("ix_vehicle_dealer_active", "dealer_id", "is_active"),

        # Supporting indexes for filter combinations
        Index("ix_vehicle_make_model",  "make", "model"),
        Index("ix_vehicle_price",       "price"),
        Index("ix_vehicle_days_on_lot", "days_on_lot"),
    )

    def __repr__(self) -> str:
        return (
            f"<Vehicle id={self.id} dealer_id={self.dealer_id} "
            f"stock={self.stock_number!r} {self.year} {self.make} {self.model}>"
        )


# ─── VehicleEvent ─────────────────────────────────────────────────────────────

class VehicleEvent(Base):
    """
    Immutable audit log of vehicle state changes (added, removed, price_change).

    dealer_id and location_name are denormalized here (no FK constraint) because:
      1. Events must be queryable by dealer without joining through vehicles
      2. Events for removed vehicles must still reference the correct dealer after
         the vehicle record is soft-deleted (is_active=False)
      3. Avoiding FK constraint prevents cascade issues on vehicle deactivation

    Change from v1.0: Added dealer_id and location_name columns.
    """
    __tablename__ = "vehicle_events"

    id            = Column(Integer, primary_key=True, index=True)

    # ── Dealer attribution (NEW in v2.0) ──────────────────────────────────────
    dealer_id     = Column(Integer, nullable=True, index=True)   # no FK — see docstring
    location_name = Column(String, nullable=True)

    # ── Event data ────────────────────────────────────────────────────────────
    stock_number  = Column(String, index=True)
    vin           = Column(String, nullable=True)
    event_type    = Column(String)           # "added" | "removed" | "price_change"
    description   = Column(String)
    old_value     = Column(String, nullable=True)
    new_value     = Column(String, nullable=True)

    # ── Vehicle snapshot at event time ────────────────────────────────────────
    year          = Column(Integer, nullable=True)
    make          = Column(String, nullable=True)
    model         = Column(String, nullable=True)
    trim          = Column(String, nullable=True)
    price         = Column(Float, nullable=True)

    timestamp     = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return (
            f"<VehicleEvent id={self.id} type={self.event_type!r} "
            f"dealer_id={self.dealer_id} stock={self.stock_number!r}>"
        )


# ─── WatchlistAlert ───────────────────────────────────────────────────────────

class WatchlistAlert(Base):
    """
    User-defined alert criteria for watchlist notifications.

    dealer_id is optional (nullable):
      - NULL: alert matches vehicles from ALL 24 locations (default behavior,
              backward-compatible with all existing alerts)
      - Integer: alert matches vehicles from that specific dealer only

    The matching logic in alerts.py enforces this scope before evaluating
    make/model/price/mileage criteria.

    Change from v1.0: Added dealer_id and location_name columns.
    Existing alerts are migrated with dealer_id=NULL (all locations) — no
    behavior change for any existing watchlist entries.
    """
    __tablename__ = "watchlist_alerts"

    id                 = Column(Integer, primary_key=True, index=True)

    # ── Location scope (NEW in v2.0) ──────────────────────────────────────────
    dealer_id          = Column(Integer, nullable=True)   # NULL = all locations
    location_name      = Column(String, nullable=True)

    # ── Alert criteria ────────────────────────────────────────────────────────
    name               = Column(String)
    make               = Column(String, nullable=True)
    model              = Column(String, nullable=True)
    max_price          = Column(Float, nullable=True)
    min_price          = Column(Float, nullable=True)
    max_mileage        = Column(Integer, nullable=True)
    min_year           = Column(Integer, nullable=True)
    max_year           = Column(Integer, nullable=True)
    condition          = Column(String, nullable=True)

    # ── Notification ──────────────────────────────────────────────────────────
    notification_email = Column(String, nullable=True)
    is_active          = Column(Boolean, default=True)

    # ── Tracking ──────────────────────────────────────────────────────────────
    created_at         = Column(DateTime, default=datetime.utcnow)
    last_triggered     = Column(DateTime, nullable=True)
    trigger_count      = Column(Integer, default=0)

    def __repr__(self) -> str:
        scope = f"dealer_id={self.dealer_id}" if self.dealer_id else "all_locations"
        return f"<WatchlistAlert id={self.id} name={self.name!r} scope={scope}>"


# ─── Lead ─────────────────────────────────────────────────────────────────────

class Lead(Base):
    """
    Customer lead / CRM record.

    Leads intentionally stay location-agnostic because a customer may match
    inventory across multiple ALM stores. Attribution and consent fields live on
    the lead so public funnels and paid media can run without separate CRM glue.
    """
    __tablename__ = "leads"

    id               = Column(Integer, primary_key=True, index=True)
    customer_name    = Column(String)
    customer_phone   = Column(String, nullable=True)
    customer_email   = Column(String, nullable=True)
    interested_make  = Column(String, nullable=True)
    interested_model = Column(String, nullable=True)
    max_budget       = Column(Float, nullable=True)
    notes            = Column(Text, nullable=True)
    status           = Column(String, default="new")   # new|contacted|hot|sold|lost
    source           = Column(String, nullable=True)   # walk-in|phone|referral|internet
    campaign         = Column(String, nullable=True)
    sms_consent      = Column(Boolean, default=False)
    sms_consent_at   = Column(DateTime, nullable=True)
    call_consent     = Column(Boolean, default=False)
    call_consent_at  = Column(DateTime, nullable=True)
    consent_text     = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow)
    sold_at          = Column(DateTime, nullable=True)  # set when status → 'sold'

    def __repr__(self) -> str:
        return f"<Lead id={self.id} name={self.customer_name!r} status={self.status!r}>"


# ─── ScrapeLog ────────────────────────────────────────────────────────────────

class ScrapeLog(Base):
    """
    Audit record for each scrape run.

    Two usage modes:
      1. Aggregate log (dealer_id=None): One record per full 24-dealer scrape run.
         Totals reflect the sum across all dealers. The `details` field contains
         a JSON-serialized per-dealer breakdown.

      2. Per-dealer log (dealer_id=N): One record per single-dealer re-scrape
         (triggered via POST /api/scrape/trigger with a dealer_id body param).

    `details` JSON structure (aggregate log):
      {
        "dealers": [
          {
            "id": 323,
            "name": "ALM Mall of Georgia",
            "found": 276,
            "added": 2,
            "removed": 1,
            "price_changes": 0,
            "status": "success",
            "error": null
          },
          ...
        ]
      }

    Changes from v1.0: Added dealer_id, location_name, details columns.
    """
    __tablename__ = "scrape_logs"

    id                  = Column(Integer, primary_key=True, index=True)

    # ── Dealer attribution (NEW in v2.0) ──────────────────────────────────────
    dealer_id           = Column(Integer, nullable=True, index=True)   # None = aggregate
    location_name       = Column(String, nullable=True)
    details             = Column(Text, nullable=True)   # JSON string — see docstring

    # ── Run metadata ──────────────────────────────────────────────────────────
    timestamp           = Column(DateTime, default=datetime.utcnow)
    status              = Column(String, default="success")   # running|success|partial|error
    method              = Column(String, nullable=True)
    error               = Column(Text, nullable=True)
    duration_seconds    = Column(Float, nullable=True)

    # ── Totals (aggregate across all dealers for aggregate log) ───────────────
    vehicles_found      = Column(Integer, default=0)
    added_count         = Column(Integer, default=0)
    removed_count       = Column(Integer, default=0)
    price_change_count  = Column(Integer, default=0)

    def get_details(self) -> dict:
        """Parse the details JSON string into a Python dict. Returns {} on error."""
        if not self.details:
            return {}
        try:
            return json.loads(self.details)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_details(self, data: dict) -> None:
        """Serialize a Python dict into the details JSON string."""
        self.details = json.dumps(data)

    def __repr__(self) -> str:
        scope = f"dealer_id={self.dealer_id}" if self.dealer_id else "all_dealers"
        return (
            f"<ScrapeLog id={self.id} status={self.status!r} "
            f"scope={scope} found={self.vehicles_found}>"
        )
