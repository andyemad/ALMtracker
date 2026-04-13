import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, distinct, func, not_, or_
from sqlalchemy.orm import Session, aliased

import models
from alerts import check_and_notify_watchlist, get_matching_vehicles
from carfax import resolve_vehicle_carfax
from database import Base, SessionLocal, engine, get_db
from migrations import run_migrations
from scraper import (
    DEALER_REGISTRY,
    DealerConfig,
    _extract,
    _fetch_dealer_filtered,
    _fetch_page,
    normalize_vehicle,
    scrape_all_dealers,
)

# NOTE: _extract, _fetch_page, _fetch_dealer_filtered, and normalize_vehicle
# are used by _find_live_carfax_matches() for real-time fallback lookups.

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

import os
import shutil

# ---------------------------------------------------------------------------
# Volume bootstrap: if DATABASE_URL points to a volume path and that file
# doesn't exist yet, seed it from the bundled alm.db baked into the image.
# This preserves weeks of historical event data on first volume mount instead
# of starting a blank DB.
# ---------------------------------------------------------------------------
_db_url = os.getenv("DATABASE_URL", "")
if _db_url.startswith("sqlite:////"):
    # Absolute path — strip the sqlite://// prefix to get the filesystem path
    _volume_db_path = _db_url[len("sqlite:////") - 1:]   # keep leading /
    _bundled_db_path = os.path.join(os.path.dirname(__file__), "alm.db")

    _force = os.getenv("FORCE_BOOTSTRAP", "").lower() in ("1", "true", "yes")
    _volume_missing = not os.path.exists(_volume_db_path)

    if (_volume_missing or _force) and os.path.exists(_bundled_db_path):
        os.makedirs(os.path.dirname(_volume_db_path), exist_ok=True)
        import sqlite3 as _sqlite3
        # Use SQLite's online backup API — safe even if a stale lock exists
        _src = _sqlite3.connect(_bundled_db_path)
        _dst = _sqlite3.connect(_volume_db_path)
        _src.backup(_dst)
        _dst.close()
        _src.close()
        action = "force-restored" if _force else "bootstrapped"
        logger.info(
            f"Volume {action}: copied bundled DB → {_volume_db_path} "
            f"({os.path.getsize(_volume_db_path):,} bytes)"
        )
    elif os.path.exists(_volume_db_path):
        logger.info(f"Volume DB already exists at {_volume_db_path} — skipping bootstrap")
    else:
        logger.warning(f"No bundled DB found at {_bundled_db_path} — starting fresh")

# Create tables first, then run migrations to seed data and add indexes
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created/verified successfully")
except Exception as e:
    logger.error(f"Table creation failed: {e}", exc_info=True)

try:
    run_migrations(engine)
    logger.info("Migrations completed successfully")
except Exception as e:
    logger.error(f"Migration failed (non-fatal): {e}", exc_info=True)

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
)
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(title="ALM Inventory Tracker", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()


@app.get("/health")
def health():
    return {"status": "ok"}



# ─── Core Scrape Logic ────────────────────────────────────────────────────────

MUTABLE_VEHICLE_FIELDS = (
    "mileage", "exterior_color", "interior_color", "image_url",
    "listing_url", "condition", "fuel_type", "transmission", "body_style",
)


def _update_vehicle_fields(vehicle, vdata: dict):
    """Overwrite mutable fields on a Vehicle from fresh scrape data."""
    for fld in MUTABLE_VEHICLE_FIELDS:
        new_val = vdata.get(fld)
        if new_val:
            setattr(vehicle, fld, new_val)


def _load_dealer_configs(db: Session) -> list[DealerConfig]:
    """Load all active dealers from DB and convert to DealerConfig objects."""
    dealers = (
        db.query(models.Dealer)
        .filter(models.Dealer.is_active == True)
        .order_by(models.Dealer.scrape_priority, models.Dealer.name)
        .all()
    )
    return [
        DealerConfig(dealer_id=d.id, name=d.name, city=d.city or "", state=d.state or "GA")
        for d in dealers
    ]


def run_scrape(db: Session):
    start = datetime.utcnow()
    log = models.ScrapeLog(timestamp=start, status="running")
    db.add(log)
    db.commit()

    try:
        configs = _load_dealer_configs(db)
        if not configs:
            log.status = "error"
            log.error = "No active dealers found in database"
            db.commit()
            logger.error("Scrape aborted: no active dealers")
            return log

        logger.info(f"Starting scrape for {len(configs)} active dealer(s)")
        dealer_map, total_raw, method = scrape_all_dealers(configs)

        # Safety guard: if total vehicles found is suspiciously low it means the
        # pagination was cut short (transient HTTP error mid-run).  Writing those
        # partial results would mark thousands of live vehicles as "removed".
        # Abort early instead — the next scheduled run will retry the full pass.
        MIN_EXPECTED_VEHICLES = 5000
        if total_raw > 0 and total_raw < MIN_EXPECTED_VEHICLES:
            duration = (datetime.utcnow() - start).total_seconds()
            log.status = "partial"
            log.error = (
                f"Partial scrape: only {total_raw} vehicles found "
                f"(threshold {MIN_EXPECTED_VEHICLES}). No DB changes written."
            )
            log.vehicles_found = total_raw
            log.method = method
            log.duration_seconds = duration
            db.commit()
            logger.warning(
                f"Partial scrape aborted: {total_raw} vehicles < threshold {MIN_EXPECTED_VEHICLES}. "
                "Skipping DB write to prevent false removals."
            )
            return log

        total_added = total_removed = total_price_changes = 0
        dealer_details = []

        for config in configs:
            dealer_id = config.dealer_id
            scraped_vehicles = dealer_map.get(dealer_id, [])

            # Build active map keyed on (dealer_id, stock_number) for this dealer
            active_map = {
                (v.dealer_id, v.stock_number): v
                for v in db.query(models.Vehicle).filter(
                    models.Vehicle.dealer_id == dealer_id,
                    models.Vehicle.is_active == True,
                ).all()
            }
            scraped_map = {
                (dealer_id, v["stock_number"]): v
                for v in scraped_vehicles
                if v.get("stock_number")
            }

            added = removed = price_changes = dealer_error = 0

            try:
                # Additions + price changes
                for key, vdata in scraped_map.items():
                    stock = vdata["stock_number"]
                    if key in active_map:
                        # Vehicle is currently active — update fields + check for price change
                        existing = active_map[key]
                        existing.last_seen = datetime.utcnow()
                        existing.days_on_lot = (datetime.utcnow() - existing.first_seen).days

                        _update_vehicle_fields(existing, vdata)

                        new_price = vdata.get("price")
                        old_price = existing.price or 0
                        # Detect price change (both must be non-zero), OR backfill if existing is 0
                        if new_price and new_price > 0:
                            if old_price > 0 and abs(new_price - old_price) > 1:
                                db.add(models.VehicleEvent(
                                    stock_number=stock,
                                    vin=existing.vin,
                                    dealer_id=dealer_id,
                                    location_name=config.name,
                                    event_type="price_change",
                                    description=f"Price change: {existing.year} {existing.make} {existing.model}",
                                    old_value=str(old_price),
                                    new_value=str(new_price),
                                    year=existing.year,
                                    make=existing.make,
                                    model=existing.model,
                                    trim=existing.trim,
                                    price=new_price,
                                ))
                                existing.price = new_price
                                price_changes += 1
                            elif old_price == 0:
                                # Backfill: price was missing, now available
                                existing.price = new_price
                    else:
                        # Not in active_map — check if it exists as inactive (soft-deleted)
                        # to avoid UNIQUE constraint violation on (dealer_id, stock_number)
                        existing_inactive = (
                            db.query(models.Vehicle)
                            .filter(
                                models.Vehicle.dealer_id == dealer_id,
                                models.Vehicle.stock_number == stock,
                                models.Vehicle.is_active == False,
                            )
                            .first()
                        )
                        if existing_inactive:
                            # Reactivate the existing row
                            existing_inactive.is_active = True
                            existing_inactive.last_seen = datetime.utcnow()
                            existing_inactive.days_on_lot = 0
                            new_price = vdata.get("price")
                            if new_price and new_price > 0:
                                existing_inactive.price = new_price
                            _update_vehicle_fields(existing_inactive, vdata)
                        else:
                            # Genuinely new vehicle — insert
                            new_vehicle = models.Vehicle(
                                vin=vdata.get("vin", ""),
                                stock_number=stock,
                                dealer_id=dealer_id,
                                location_name=vdata.get("location_name") or config.name,
                                year=vdata.get("year"),
                                make=vdata.get("make", ""),
                                model=vdata.get("model", ""),
                                trim=vdata.get("trim", ""),
                                price=vdata.get("price"),
                                mileage=vdata.get("mileage"),
                                exterior_color=vdata.get("exterior_color", ""),
                                interior_color=vdata.get("interior_color", ""),
                                body_style=vdata.get("body_style", ""),
                                condition=vdata.get("condition", ""),
                                fuel_type=vdata.get("fuel_type", ""),
                                transmission=vdata.get("transmission", ""),
                                image_url=vdata.get("image_url", ""),
                                listing_url=vdata.get("listing_url", ""),
                                is_active=True,
                                first_seen=datetime.utcnow(),
                                last_seen=datetime.utcnow(),
                            )
                            db.add(new_vehicle)
                        db.add(models.VehicleEvent(
                            stock_number=stock,
                            vin=vdata.get("vin", ""),
                            dealer_id=dealer_id,
                            location_name=config.name,
                            event_type="added",
                            description=f"Added: {vdata.get('year')} {vdata.get('make')} {vdata.get('model')} {vdata.get('trim', '')}".strip(),
                            year=vdata.get("year"),
                            make=vdata.get("make", ""),
                            model=vdata.get("model", ""),
                            trim=vdata.get("trim", ""),
                            price=vdata.get("price"),
                        ))
                        added += 1

                # Removals
                for key, existing in active_map.items():
                    if key not in scraped_map:
                        existing.is_active = False
                        db.add(models.VehicleEvent(
                            stock_number=existing.stock_number,
                            vin=existing.vin,
                            dealer_id=dealer_id,
                            location_name=config.name,
                            event_type="removed",
                            description=f"Removed: {existing.year} {existing.make} {existing.model} {existing.trim or ''}".strip(),
                            year=existing.year,
                            make=existing.make,
                            model=existing.model,
                            trim=existing.trim,
                            price=existing.price,
                        ))
                        removed += 1

                # Update dealer.last_scraped
                dealer_row = db.query(models.Dealer).filter(models.Dealer.id == dealer_id).first()
                if dealer_row:
                    dealer_row.last_scraped = datetime.utcnow()

            except Exception as e:
                dealer_error = str(e)
                logger.error(f"Error processing dealer_id={dealer_id} ({config.name}): {e}")

            total_added += added
            total_removed += removed
            total_price_changes += price_changes
            dealer_details.append({
                "id": dealer_id,
                "name": config.name,
                "found": len(scraped_vehicles),
                "added": added,
                "removed": removed,
                "price_changes": price_changes,
                "status": "error" if dealer_error else "success",
                "error": dealer_error or None,
            })
            logger.info(
                f"  {config.name} (id={dealer_id}): "
                f"+{added} -{removed} ~{price_changes}, "
                f"{len(scraped_vehicles)} found"
            )

        duration = (datetime.utcnow() - start).total_seconds()
        log.vehicles_found = total_raw
        log.added_count = total_added
        log.removed_count = total_removed
        log.price_change_count = total_price_changes
        log.status = "success"
        log.method = method
        log.duration_seconds = duration
        log.set_details({"dealers": dealer_details})
        db.commit()

        check_and_notify_watchlist(db)
        logger.info(
            f"Scrape done: {len(configs)} dealers, "
            f"+{total_added} -{total_removed} ~{total_price_changes} "
            f"in {duration:.1f}s"
        )
        return log

    except Exception as e:
        log.status = "error"
        log.error = str(e)
        db.commit()
        logger.error(f"Scrape failed: {e}")
        raise


# ─── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    try:
        db = SessionLocal()
        count = db.query(models.Vehicle).count()
        db.close()
    except Exception as e:
        logger.warning(f"Could not query vehicles table (first run?): {e}")
        count = 0

    needs_scrape = count == 0
    if not needs_scrape:
        try:
            db = SessionLocal()
            last_log = (
                db.query(models.ScrapeLog)
                .filter(models.ScrapeLog.dealer_id.is_(None), models.ScrapeLog.status == "success")
                .order_by(desc(models.ScrapeLog.timestamp))
                .first()
            )
            db.close()
            if last_log is None or (datetime.utcnow() - last_log.timestamp).total_seconds() > 6 * 3600:
                needs_scrape = True
                logger.info("Stale data detected on startup — triggering scrape")
        except Exception as e:
            logger.warning(f"Could not check last scrape time: {e}")

    if needs_scrape:
        logger.info("Scheduling startup scrape in background...")

        async def _safe_initial_scrape():
            try:
                await asyncio.to_thread(run_scrape, SessionLocal())
                logger.info("Startup background scrape completed successfully")
            except Exception as e:
                logger.error(f"Startup background scrape failed (non-fatal): {e}")

        asyncio.create_task(_safe_initial_scrape())

    scheduler.add_job(
        lambda: run_scrape(SessionLocal()),
        IntervalTrigger(hours=6),
        id="scrape_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — scraping every 6 hours")


@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _vehicle_dict(v: models.Vehicle) -> dict:
    return {
        "id": v.id,
        "vin": v.vin,
        "stock_number": v.stock_number,
        "dealer_id": v.dealer_id,
        "location_name": v.location_name,
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
        "carfax_url": v.carfax_url,
        "carfax_fetched_at": v.carfax_fetched_at.isoformat() if v.carfax_fetched_at else None,
        "is_active": v.is_active,
        "first_seen": v.first_seen.isoformat() if v.first_seen else None,
        "last_seen": v.last_seen.isoformat() if v.last_seen else None,
        "days_on_lot": v.days_on_lot or 0,
    }


def _event_dict(e: models.VehicleEvent) -> dict:
    return {
        "id": e.id,
        "stock_number": e.stock_number,
        "vin": e.vin,
        "dealer_id": e.dealer_id,
        "location_name": e.location_name,
        "event_type": e.event_type,
        "description": e.description,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "year": e.year,
        "make": e.make,
        "model": e.model,
        "trim": e.trim,
        "price": e.price,
    }


def _exclude_currently_active_removals(q, db: Session):
    """
    Hide stale "removed" events for units that are currently active again.

    This covers both:
      - relists/reactivations at the same store
      - dealer transfers where the old store logged a removal and the new
        store logged an add for the same VIN
    """
    active_vehicle = aliased(models.Vehicle)

    active_by_vin = (
        db.query(active_vehicle.id)
        .filter(
            active_vehicle.is_active == True,
            active_vehicle.vin.isnot(None),
            active_vehicle.vin != "",
            models.VehicleEvent.vin.isnot(None),
            models.VehicleEvent.vin != "",
            active_vehicle.vin == models.VehicleEvent.vin,
        )
        .exists()
    )

    active_by_stock = (
        db.query(active_vehicle.id)
        .filter(
            active_vehicle.is_active == True,
            or_(models.VehicleEvent.vin.is_(None), models.VehicleEvent.vin == ""),
            active_vehicle.stock_number == models.VehicleEvent.stock_number,
        )
        .exists()
    )

    return q.filter(
        or_(
            models.VehicleEvent.event_type != "removed",
            not_(or_(active_by_vin, active_by_stock)),
        )
    )


def _find_carfax_matches(
    db: Session,
    query: str,
    dealer_id: Optional[int] = None,
) -> list[models.Vehicle]:
    normalized = query.strip().upper()
    if not normalized:
        return []

    q = db.query(models.Vehicle)
    if dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == dealer_id)

    q = q.filter(
        or_(
            func.upper(models.Vehicle.stock_number) == normalized,
            func.upper(models.Vehicle.vin) == normalized,
        )
    )

    # Prefer active vehicles, but fall back to inactive (e.g. recently sold)
    # so CARFAX links cached before the car sold are still retrievable.
    results = q.filter(models.Vehicle.is_active == True).order_by(desc(models.Vehicle.last_seen), desc(models.Vehicle.id)).all()
    if not results:
        results = q.order_by(desc(models.Vehicle.last_seen), desc(models.Vehicle.id)).all()
    return results


def _upsert_live_vehicle_match(db: Session, vdata: dict) -> models.Vehicle:
    dealer_id = vdata.get("dealer_id")
    stock_number = (vdata.get("stock_number") or "").strip()
    vin = (vdata.get("vin") or "").strip()

    vehicle: Optional[models.Vehicle] = None
    if dealer_id is not None and stock_number:
        vehicle = (
            db.query(models.Vehicle)
            .filter(
                models.Vehicle.dealer_id == dealer_id,
                models.Vehicle.stock_number == stock_number,
            )
            .order_by(desc(models.Vehicle.id))
            .first()
        )

    if vehicle is None and vin:
        q = db.query(models.Vehicle).filter(models.Vehicle.vin == vin)
        if dealer_id is not None:
            q = q.filter(models.Vehicle.dealer_id == dealer_id)
        vehicle = q.order_by(desc(models.Vehicle.last_seen), desc(models.Vehicle.id)).first()

    now = datetime.utcnow()
    location_name = (
        vdata.get("location_name")
        or DEALER_REGISTRY.get(dealer_id, {}).get("name")
        or None
    )

    if vehicle is None:
        vehicle = models.Vehicle(
            vin=vin or None,
            stock_number=stock_number,
            dealer_id=dealer_id,
            location_name=location_name,
            year=vdata.get("year") or None,
            make=vdata.get("make") or None,
            model=vdata.get("model") or None,
            trim=vdata.get("trim") or None,
            price=vdata.get("price"),
            mileage=vdata.get("mileage"),
            exterior_color=vdata.get("exterior_color") or None,
            interior_color=vdata.get("interior_color") or None,
            body_style=vdata.get("body_style") or None,
            condition=vdata.get("condition") or None,
            fuel_type=vdata.get("fuel_type") or None,
            transmission=vdata.get("transmission") or None,
            image_url=vdata.get("image_url") or None,
            listing_url=vdata.get("listing_url") or None,
            is_active=True,
            first_seen=now,
            last_seen=now,
            days_on_lot=0,
        )
        db.add(vehicle)
    else:
        vehicle.vin = vin or vehicle.vin
        vehicle.stock_number = stock_number or vehicle.stock_number
        vehicle.dealer_id = dealer_id if dealer_id is not None else vehicle.dealer_id
        vehicle.location_name = location_name or vehicle.location_name
        vehicle.year = vdata.get("year") or vehicle.year
        vehicle.make = vdata.get("make") or vehicle.make
        vehicle.model = vdata.get("model") or vehicle.model
        vehicle.trim = vdata.get("trim") or vehicle.trim
        vehicle.price = vdata.get("price") if vdata.get("price") is not None else vehicle.price
        vehicle.is_active = True
        vehicle.last_seen = now
        if vehicle.first_seen is None:
            vehicle.first_seen = now
        _update_vehicle_fields(vehicle, vdata)

    db.commit()
    db.refresh(vehicle)
    return vehicle


def _find_live_carfax_matches(
    db: Session,
    query: str,
    dealer_id: Optional[int] = None,
) -> list[models.Vehicle]:
    normalized = query.strip().upper()
    if not normalized:
        return []

    matches: list[models.Vehicle] = []
    seen_keys: set[tuple[Optional[int], str]] = set()

    def _collect(vdata: dict):
        stock_number = (vdata.get("stock_number") or "").strip().upper()
        vin = (vdata.get("vin") or "").strip().upper()
        if normalized not in {stock_number, vin}:
            return

        dedupe_key = (vdata.get("dealer_id"), stock_number or vin)
        if dedupe_key in seen_keys:
            return

        seen_keys.add(dedupe_key)
        matches.append(_upsert_live_vehicle_match(db, vdata))

    if dealer_id is not None:
        for vdata in _fetch_dealer_filtered(dealer_id):
            _collect(vdata)
        logger.info(
            "Live CARFAX fallback for %s at dealer_id=%s returned %s match(es)",
            normalized,
            dealer_id,
            len(matches),
        )
        return matches

    offset = 0
    total = None
    while True:
        page = _fetch_page(offset=offset)
        if page is None:
            break

        results, total = _extract(page)
        if not results:
            break

        for raw_vehicle in results:
            _collect(normalize_vehicle(raw_vehicle))

        offset += len(results)
        if total and offset >= total:
            break

    logger.info(
        "Live CARFAX fallback for %s returned %s match(es)",
        normalized,
        len(matches),
    )
    return matches


def _alert_dict(a: models.WatchlistAlert) -> dict:
    return {
        "id": a.id,
        "dealer_id": a.dealer_id,
        "location_name": a.location_name,
        "name": a.name,
        "make": a.make,
        "model": a.model,
        "max_price": a.max_price,
        "min_price": a.min_price,
        "max_mileage": a.max_mileage,
        "min_year": a.min_year,
        "max_year": a.max_year,
        "condition": a.condition,
        "notification_email": a.notification_email,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "last_triggered": a.last_triggered.isoformat() if a.last_triggered else None,
        "trigger_count": a.trigger_count or 0,
    }


def _lead_dict(l: models.Lead) -> dict:
    return {
        "id": l.id,
        "customer_name": l.customer_name,
        "customer_phone": l.customer_phone,
        "customer_email": l.customer_email,
        "interested_make": l.interested_make,
        "interested_model": l.interested_model,
        "max_budget": l.max_budget,
        "notes": l.notes,
        "status": l.status,
        "source": l.source,
        "campaign": getattr(l, "campaign", None),
        "sms_consent": bool(getattr(l, "sms_consent", False)),
        "sms_consent_at": l.sms_consent_at.isoformat() if getattr(l, "sms_consent_at", None) else None,
        "call_consent": bool(getattr(l, "call_consent", False)),
        "call_consent_at": l.call_consent_at.isoformat() if getattr(l, "call_consent_at", None) else None,
        "consent_text": getattr(l, "consent_text", None),
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "sold_at": l.sold_at.isoformat() if getattr(l, "sold_at", None) else None,
    }


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _log_dict(l: models.ScrapeLog) -> dict:
    return {
        "id": l.id,
        "dealer_id": l.dealer_id,
        "location_name": l.location_name,
        "timestamp": l.timestamp.isoformat() if l.timestamp else None,
        "vehicles_found": l.vehicles_found,
        "added_count": l.added_count,
        "removed_count": l.removed_count,
        "price_change_count": l.price_change_count,
        "status": l.status,
        "method": l.method,
        "error": l.error,
        "duration_seconds": l.duration_seconds,
        "details": l.get_details(),
    }


def _dealer_dict(d: models.Dealer, db: Session = None) -> dict:
    active_vehicle_count = 0
    if db is not None:
        active_vehicle_count = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.dealer_id == d.id, models.Vehicle.is_active == True)
            .count()
        )
    return {
        "id": d.id,
        "name": d.name,
        "city": d.city,
        "state": d.state,
        "is_active": d.is_active,
        "scrape_priority": d.scrape_priority,
        "active_vehicle_count": active_vehicle_count,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "last_scraped": d.last_scraped.isoformat() if d.last_scraped else None,
    }


# ─── Routes: Dealers ──────────────────────────────────────────────────────────

@app.get("/api/dealers/{dealer_id}/stats")
def get_dealer_stats(dealer_id: int, db: Session = Depends(get_db)):
    dealer = db.query(models.Dealer).filter(models.Dealer.id == dealer_id).first()
    if not dealer:
        raise HTTPException(404, "Dealer not found")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total_active = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.dealer_id == dealer_id, models.Vehicle.is_active == True)
        .count()
    )
    added_today = (
        db.query(models.VehicleEvent)
        .filter(
            models.VehicleEvent.dealer_id == dealer_id,
            models.VehicleEvent.event_type == "added",
            models.VehicleEvent.timestamp >= today,
        )
        .count()
    )
    removed_today = (
        _exclude_currently_active_removals(
            db.query(models.VehicleEvent).filter(
                models.VehicleEvent.dealer_id == dealer_id,
                models.VehicleEvent.timestamp >= today,
            ),
            db,
        )
        .filter(models.VehicleEvent.event_type == "removed")
        .count()
    )
    active_alerts = (
        db.query(models.WatchlistAlert)
        .filter(
            models.WatchlistAlert.is_active == True,
            or_(
                models.WatchlistAlert.dealer_id == dealer_id,
                models.WatchlistAlert.dealer_id.is_(None),
            ),
        )
        .count()
    )
    avg_price = (
        db.query(func.avg(models.Vehicle.price))
        .filter(
            models.Vehicle.dealer_id == dealer_id,
            models.Vehicle.is_active == True,
            models.Vehicle.price.isnot(None),
        )
        .scalar()
    )
    last_log = (
        db.query(models.ScrapeLog)
        .filter(models.ScrapeLog.dealer_id == dealer_id)
        .filter(models.ScrapeLog.status != "running")
        .order_by(desc(models.ScrapeLog.timestamp))
        .first()
    )
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    trend_logs = (
        db.query(models.ScrapeLog)
        .filter(
            models.ScrapeLog.dealer_id == dealer_id,
            models.ScrapeLog.timestamp >= two_weeks_ago,
            models.ScrapeLog.status == "success",
        )
        .order_by(asc(models.ScrapeLog.timestamp))
        .all()
    )

    return {
        "dealer_id": dealer_id,
        "location_name": dealer.name,
        "total_active": total_active,
        "added_today": added_today,
        "removed_today": removed_today,
        "active_alerts": active_alerts,
        "avg_price": round(float(avg_price or 0), 2),
        "last_scrape": last_log.timestamp.isoformat() if last_log else None,
        "last_scrape_status": last_log.status if last_log else None,
        "trend": [
            {
                "date": l.timestamp.strftime("%m/%d"),
                "count": l.vehicles_found,
                "added": l.added_count,
                "removed": l.removed_count,
            }
            for l in trend_logs
        ],
    }


@app.get("/api/dealers")
def list_dealers(
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    q = db.query(models.Dealer)
    if active_only:
        q = q.filter(models.Dealer.is_active == True)
    q = q.order_by(models.Dealer.name)
    return [_dealer_dict(d, db) for d in q.all()]


# ─── Routes: Stats ────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    vq = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    if dealer_id is not None:
        vq = vq.filter(models.Vehicle.dealer_id == dealer_id)

    total_active = vq.count()

    eq = db.query(models.VehicleEvent)
    if dealer_id is not None:
        eq = eq.filter(models.VehicleEvent.dealer_id == dealer_id)

    added_today = (
        eq.filter(
            models.VehicleEvent.event_type == "added",
            models.VehicleEvent.timestamp >= today,
        )
        .count()
    )
    removed_today = (
        _exclude_currently_active_removals(
            eq.filter(models.VehicleEvent.timestamp >= today),
            db,
        )
        .filter(models.VehicleEvent.event_type == "removed")
        .count()
    )

    aq = db.query(models.WatchlistAlert).filter(models.WatchlistAlert.is_active == True)
    if dealer_id is not None:
        aq = aq.filter(
            or_(
                models.WatchlistAlert.dealer_id == dealer_id,
                models.WatchlistAlert.dealer_id.is_(None),
            )
        )
    active_alerts = aq.count()

    avg_price = (
        db.query(func.avg(models.Vehicle.price))
        .filter(
            models.Vehicle.is_active == True,
            models.Vehicle.price.isnot(None),
            *([models.Vehicle.dealer_id == dealer_id] if dealer_id is not None else []),
        )
        .scalar()
    )

    # Scrape logs are global (dealer_id=NULL) — always query the global logs
    last_log = (
        db.query(models.ScrapeLog)
        .filter(models.ScrapeLog.dealer_id.is_(None))
        .filter(models.ScrapeLog.status != "running")
        .order_by(desc(models.ScrapeLog.timestamp))
        .first()
    )

    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    trend_logs = (
        db.query(models.ScrapeLog)
        .filter(
            models.ScrapeLog.timestamp >= two_weeks_ago,
            models.ScrapeLog.status == "success",
            models.ScrapeLog.dealer_id.is_(None),
        )
        .order_by(asc(models.ScrapeLog.timestamp))
        .all()
    )

    scraping_now = (
        db.query(models.ScrapeLog)
        .filter(
            models.ScrapeLog.dealer_id.is_(None),
            models.ScrapeLog.status == "running",
            models.ScrapeLog.timestamp >= datetime.utcnow() - timedelta(minutes=10),
        )
        .first()
    ) is not None

    result = {
        "total_active": total_active,
        "added_today": added_today,
        "removed_today": removed_today,
        "active_alerts": active_alerts,
        "avg_price": round(float(avg_price or 0), 2),
        "scraping_now": scraping_now,
        "last_scrape": last_log.timestamp.isoformat() if last_log else None,
        "last_scrape_status": last_log.status if last_log else None,
        "trend": [
            {
                "date": l.timestamp.strftime("%m/%d"),
                "count": l.vehicles_found,
                "added": l.added_count,
                "removed": l.removed_count,
            }
            for l in trend_logs
        ],
    }
    if dealer_id is not None:
        dealer_row = db.query(models.Dealer).filter(models.Dealer.id == dealer_id).first()
        result["dealer_id"] = dealer_id
        result["location_name"] = dealer_row.name if dealer_row else None
    else:
        result["dealer_id"] = None
        result["location_name"] = "All Locations"
    return result


@app.get("/api/my-stats")
def get_my_stats(db: Session = Depends(get_db)):
    """
    Personal sales coach endpoint.
    Tracks progress toward the 20.5 cars/month goal using leads marked 'sold'
    this calendar month (keyed on sold_at, which is set the moment status → 'sold').
    """
    import calendar as cal

    GOAL = 20.5
    today = datetime.utcnow()
    first_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = cal.monthrange(today.year, today.month)[1]
    days_elapsed = max(today.day, 1)
    days_remaining = max(days_in_month - today.day, 0)

    # Sold this month — use sold_at if available, fall back to updated_at for
    # legacy rows that were marked sold before the sold_at column existed
    sold_this_month = (
        db.query(func.count(models.Lead.id))
        .filter(
            models.Lead.status == "sold",
            func.coalesce(models.Lead.sold_at, models.Lead.updated_at) >= first_of_month,
        )
        .scalar()
        or 0
    )

    pace_per_day = sold_this_month / days_elapsed
    projected_eom = round(pace_per_day * days_in_month, 1)
    remaining_needed = max(0.0, GOAL - sold_this_month)
    needed_per_day = round(remaining_needed / days_remaining, 2) if days_remaining > 0 else 0.0
    on_track = projected_eom >= GOAL
    deficit = round(GOAL - projected_eom, 1) if not on_track else 0.0

    # Hot leads — most recently updated first, up to 5
    hot_leads = (
        db.query(models.Lead)
        .filter(models.Lead.status == "hot")
        .order_by(desc(models.Lead.updated_at))
        .limit(5)
        .all()
    )

    return {
        "goal": GOAL,
        "sold_this_month": sold_this_month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "pace_per_day": round(pace_per_day, 2),
        "projected_eom": projected_eom,
        "needed_per_day": needed_per_day,
        "on_track": on_track,
        "deficit": deficit,
        "hot_leads": [_lead_dict(l) for l in hot_leads],
    }


# ─── Routes: Vehicles ─────────────────────────────────────────────────────────

@app.get("/api/vehicles")
def list_vehicles(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
    location_name: Optional[str] = None,
    search: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    max_mileage: Optional[int] = None,
    min_days_on_lot: Optional[int] = None,
    max_days_on_lot: Optional[int] = None,
    condition: Optional[str] = None,
    body_style: Optional[str] = None,
    is_trade_in: Optional[bool] = None,
    is_active: Optional[bool] = True,
    sort_by: str = "first_seen",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
    q = db.query(models.Vehicle)

    if is_active is not None:
        q = q.filter(models.Vehicle.is_active == is_active)
    if dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == dealer_id)
    if location_name:
        q = q.filter(models.Vehicle.location_name.ilike(f"%{location_name}%"))
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Vehicle.make.ilike(term),
                models.Vehicle.model.ilike(term),
                models.Vehicle.trim.ilike(term),
                models.Vehicle.stock_number.ilike(term),
                models.Vehicle.vin.ilike(term),
                models.Vehicle.location_name.ilike(term),
            )
        )
    if make:
        q = q.filter(models.Vehicle.make.ilike(f"%{make}%"))
    if model:
        q = q.filter(models.Vehicle.model.ilike(f"%{model}%"))
    if min_year:
        q = q.filter(models.Vehicle.year >= min_year)
    if max_year:
        q = q.filter(models.Vehicle.year <= max_year)
    if min_price:
        q = q.filter(models.Vehicle.price >= min_price)
    if max_price:
        q = q.filter(models.Vehicle.price <= max_price)
    if max_mileage:
        q = q.filter(models.Vehicle.mileage <= max_mileage)
    if min_days_on_lot is not None:
        q = q.filter(models.Vehicle.days_on_lot >= min_days_on_lot)
    if max_days_on_lot is not None:
        q = q.filter(models.Vehicle.days_on_lot <= max_days_on_lot)
    if condition:
        q = q.filter(models.Vehicle.condition.ilike(f"%{condition}%"))
    if body_style:
        q = q.filter(models.Vehicle.body_style.ilike(f"%{body_style}%"))
    if is_trade_in is True:
        q = q.filter(or_(
            models.Vehicle.stock_number.ilike('%A'),
            models.Vehicle.stock_number.ilike('%B'),
            models.Vehicle.stock_number.ilike('%C'),
            models.Vehicle.stock_number.ilike('%D'),
            models.Vehicle.stock_number.ilike('%E'),
        ))
    elif is_trade_in is False:
        q = q.filter(~or_(
            models.Vehicle.stock_number.ilike('%A'),
            models.Vehicle.stock_number.ilike('%B'),
            models.Vehicle.stock_number.ilike('%C'),
            models.Vehicle.stock_number.ilike('%D'),
            models.Vehicle.stock_number.ilike('%E'),
        ))

    valid_sort = {"year", "make", "model", "price", "mileage", "first_seen", "days_on_lot"}
    col = getattr(models.Vehicle, sort_by if sort_by in valid_sort else "first_seen")
    q = q.order_by(asc(col) if sort_order == "asc" else desc(col))

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "data": [_vehicle_dict(v) for v in items],
    }


@app.get("/api/carfax")
def lookup_carfax(
    db: Session = Depends(get_db),
    query: Optional[str] = None,
    vehicle_id: Optional[int] = None,
    dealer_id: Optional[int] = None,
    refresh: bool = False,
):
    if vehicle_id is None and not (query or "").strip():
        raise HTTPException(400, "Provide a stock number, VIN, or vehicle_id")

    vehicle: Optional[models.Vehicle] = None
    normalized_query = (query or "").strip()

    if vehicle_id is not None:
        q = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id)
        if dealer_id is not None:
            q = q.filter(models.Vehicle.dealer_id == dealer_id)
        vehicle = q.first()
        if vehicle is None:
            raise HTTPException(404, "Vehicle not found")
    else:
        matches = _find_carfax_matches(db, normalized_query, dealer_id)
        if not matches:
            matches = _find_live_carfax_matches(db, normalized_query, dealer_id)
        if not matches:
            raise HTTPException(404, "No active vehicle found for that stock number or VIN")
        if len(matches) > 1:
            return {
                "status": "ambiguous",
                "query": normalized_query,
                "matches": [_vehicle_dict(v) for v in matches],
            }
        vehicle = matches[0]

    if vehicle.carfax_url and not refresh:
        return {
            "status": "resolved",
            "query": normalized_query or vehicle.stock_number,
            "cached": True,
            "carfax_url": vehicle.carfax_url,
            "listing_url": vehicle.listing_url,
            "vehicle": _vehicle_dict(vehicle),
        }

    try:
        resolution = resolve_vehicle_carfax(db, vehicle, force_refresh=refresh)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        logger.error("CARFAX lookup failed for vehicle_id=%s: %s", vehicle.id, exc, exc_info=True)
        raise HTTPException(502, "Could not retrieve the CARFAX link from ALM right now") from exc

    db.refresh(vehicle)
    return {
        "status": "resolved",
        "query": normalized_query or vehicle.stock_number,
        "cached": False,
        "carfax_url": resolution.carfax_url,
        "listing_url": resolution.listing_url,
        "vehicle": _vehicle_dict(vehicle),
    }


@app.get("/api/vehicles/export")
def export_csv(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
    is_trade_in: Optional[bool] = None,
):
    q = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    if dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == dealer_id)
    if is_trade_in is True:
        q = q.filter(or_(
            models.Vehicle.stock_number.ilike('%A'),
            models.Vehicle.stock_number.ilike('%B'),
            models.Vehicle.stock_number.ilike('%C'),
            models.Vehicle.stock_number.ilike('%D'),
            models.Vehicle.stock_number.ilike('%E'),
        ))
    vehicles = q.order_by(models.Vehicle.make, models.Vehicle.model).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["Stock#", "VIN", "Year", "Make", "Model", "Trim", "Price", "Mileage",
         "Color", "Body Style", "Condition", "Days on Lot", "Location", "URL"]
    )
    for v in vehicles:
        w.writerow([
            v.stock_number, v.vin, v.year, v.make, v.model, v.trim,
            v.price, v.mileage, v.exterior_color, v.body_style,
            v.condition, v.days_on_lot or 0, v.location_name or "", v.listing_url,
        ])
    buf.seek(0)
    suffix = "_trade_ins" if is_trade_in else ""
    filename = f"alm_inventory{suffix}{'_' + str(dealer_id) if dealer_id else ''}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/filter-options")
def filter_options(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
):
    base = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    if dealer_id is not None:
        base = base.filter(models.Vehicle.dealer_id == dealer_id)

    makes = [
        r[0]
        for r in base.with_entities(distinct(models.Vehicle.make))
        .filter(models.Vehicle.make != "")
        .order_by(models.Vehicle.make)
        .all()
    ]
    body_styles = [
        r[0]
        for r in base.with_entities(distinct(models.Vehicle.body_style))
        .filter(
            models.Vehicle.body_style.isnot(None),
            models.Vehicle.body_style != "",
        )
        .order_by(models.Vehicle.body_style)
        .all()
    ]
    min_price = base.with_entities(func.min(models.Vehicle.price)).scalar()
    max_price = base.with_entities(func.max(models.Vehicle.price)).scalar()
    min_year = base.with_entities(func.min(models.Vehicle.year)).scalar()
    max_year = base.with_entities(func.max(models.Vehicle.year)).scalar()

    return {
        "makes": makes,
        "body_styles": body_styles,
        "price_range": [min_price, max_price],
        "year_range": [min_year, max_year],
    }


# ─── Routes: Events ───────────────────────────────────────────────────────────

@app.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    days: int = 30,
    page: int = 1,
    page_size: int = 50,
):
    since = datetime.utcnow() - timedelta(days=days)

    # Base query scoped by time + dealer + search (NO event_type filter)
    base = db.query(models.VehicleEvent).filter(models.VehicleEvent.timestamp >= since)
    base = _exclude_currently_active_removals(base, db)
    if dealer_id is not None:
        base = base.filter(models.VehicleEvent.dealer_id == dealer_id)
    if search:
        pat = f"%{search}%"
        base = base.filter(or_(
            models.VehicleEvent.stock_number.ilike(pat),
            models.VehicleEvent.vin.ilike(pat),
            models.VehicleEvent.make.ilike(pat),
            models.VehicleEvent.model.ilike(pat),
        ))

    # Counts per event type (always computed from unfiltered base)
    type_counts = dict(
        base.with_entities(models.VehicleEvent.event_type, func.count())
        .group_by(models.VehicleEvent.event_type)
        .all()
    )
    counts = {
        "added": type_counts.get("added", 0),
        "removed": type_counts.get("removed", 0),
        "price_change": type_counts.get("price_change", 0),
    }

    # Now apply event_type filter for pagination
    q = base
    if event_type:
        q = q.filter(models.VehicleEvent.event_type == event_type)
    q = q.order_by(desc(models.VehicleEvent.timestamp))

    total = q.count()
    pages = max(1, (total + page_size - 1) // page_size)
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "pages": pages, "page": page, "counts": counts, "data": [_event_dict(e) for e in items]}


# ─── Routes: Watchlist ────────────────────────────────────────────────────────

@app.get("/api/watchlist")
def list_watchlist(db: Session = Depends(get_db), dealer_id: Optional[int] = None):
    q = db.query(models.WatchlistAlert)
    if dealer_id is not None:
        q = q.filter(
            or_(
                models.WatchlistAlert.dealer_id == dealer_id,
                models.WatchlistAlert.dealer_id.is_(None),
            )
        )
    alerts = q.order_by(desc(models.WatchlistAlert.created_at)).all()
    result = []
    for a in alerts:
        d = _alert_dict(a)
        d["match_count"] = len(get_matching_vehicles(a, db))
        result.append(d)
    return result


@app.post("/api/watchlist")
def create_watchlist(data: dict, db: Session = Depends(get_db)):
    dealer_id = data.get("dealer_id")
    location_name = None
    if dealer_id:
        dealer = db.query(models.Dealer).filter(models.Dealer.id == dealer_id).first()
        if dealer:
            location_name = dealer.name

    alert = models.WatchlistAlert(
        dealer_id=dealer_id or None,
        location_name=location_name,
        name=data.get("name", ""),
        make=data.get("make") or None,
        model=data.get("model") or None,
        max_price=data.get("max_price"),
        min_price=data.get("min_price"),
        max_mileage=data.get("max_mileage"),
        min_year=data.get("min_year"),
        max_year=data.get("max_year"),
        condition=data.get("condition") or None,
        notification_email=data.get("notification_email") or None,
        is_active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    d = _alert_dict(alert)
    d["match_count"] = len(get_matching_vehicles(alert, db))
    return d


@app.put("/api/watchlist/{alert_id}")
def update_watchlist(alert_id: int, data: dict, db: Session = Depends(get_db)):
    alert = db.query(models.WatchlistAlert).filter(models.WatchlistAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    allowed = {"name", "make", "model", "max_price", "min_price", "max_mileage",
               "min_year", "max_year", "condition", "notification_email", "is_active",
               "dealer_id", "location_name"}
    for k, v in data.items():
        if k in allowed:
            setattr(alert, k, v)
    db.commit()
    db.refresh(alert)
    d = _alert_dict(alert)
    d["match_count"] = len(get_matching_vehicles(alert, db))
    return d


@app.delete("/api/watchlist/{alert_id}")
def delete_watchlist(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(models.WatchlistAlert).filter(models.WatchlistAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    db.delete(alert)
    db.commit()
    return {"ok": True}


# ─── Routes: Leads ────────────────────────────────────────────────────────────

@app.get("/api/leads")
def list_leads(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    q = db.query(models.Lead)
    if status:
        q = q.filter(models.Lead.status == status)
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Lead.customer_name.ilike(term),
                models.Lead.customer_email.ilike(term),
                models.Lead.customer_phone.ilike(term),
            )
        )
    q = q.order_by(desc(models.Lead.updated_at))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "data": [_lead_dict(l) for l in items]}


@app.post("/api/leads")
def create_lead(data: dict, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    sms_consent = _coerce_bool(data.get("sms_consent"))
    call_consent = _coerce_bool(data.get("call_consent"))
    lead = models.Lead(
        customer_name=data.get("customer_name", ""),
        customer_phone=data.get("customer_phone"),
        customer_email=data.get("customer_email"),
        interested_make=data.get("interested_make"),
        interested_model=data.get("interested_model"),
        max_budget=data.get("max_budget"),
        notes=data.get("notes"),
        status=data.get("status", "new"),
        source=data.get("source"),
        campaign=data.get("campaign"),
        sms_consent=sms_consent,
        sms_consent_at=now if sms_consent else None,
        call_consent=call_consent,
        call_consent_at=now if call_consent else None,
        consent_text=data.get("consent_text"),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


@app.put("/api/leads/{lead_id}")
def update_lead(lead_id: int, data: dict, db: Session = Depends(get_db)):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    allowed = {"customer_name", "customer_phone", "customer_email", "interested_make",
               "interested_model", "max_budget", "notes", "status", "source",
               "campaign", "consent_text"}
    for k, v in data.items():
        if k in allowed:
            setattr(lead, k, v)

    if "sms_consent" in data:
        lead.sms_consent = _coerce_bool(data.get("sms_consent"))
        lead.sms_consent_at = (
            lead.sms_consent_at or datetime.utcnow()
            if lead.sms_consent
            else None
        )

    if "call_consent" in data:
        lead.call_consent = _coerce_bool(data.get("call_consent"))
        lead.call_consent_at = (
            lead.call_consent_at or datetime.utcnow()
            if lead.call_consent
            else None
        )

    lead.updated_at = datetime.utcnow()
    # Stamp sold_at the first time a lead is marked sold
    if data.get("status") == "sold" and not getattr(lead, "sold_at", None):
        lead.sold_at = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    db.delete(lead)
    db.commit()
    return {"ok": True}


@app.get("/api/leads/{lead_id}/matches")
def lead_matches(
    lead_id: int,
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
    condition: Optional[str] = None,
):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    q = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    if dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == dealer_id)
    if lead.interested_make:
        q = q.filter(models.Vehicle.make.ilike(f"%{lead.interested_make}%"))
    if lead.interested_model:
        q = q.filter(models.Vehicle.model.ilike(f"%{lead.interested_model}%"))
    if lead.max_budget:
        q = q.filter(models.Vehicle.price <= lead.max_budget)
    if condition:
        # "new" → match "New"; "pre-owned" → match "Pre-owned" / "Used" / etc.
        if condition.lower() == "new":
            q = q.filter(models.Vehicle.condition.ilike("new"))
        else:
            q = q.filter(models.Vehicle.condition.notilike("new"))
    matches = q.order_by(asc(models.Vehicle.price)).limit(20).all()
    return [_vehicle_dict(v) for v in matches]


# ─── Routes: Scrape Logs ──────────────────────────────────────────────────────

@app.get("/api/scrape-logs")
def list_scrape_logs(
    db: Session = Depends(get_db),
    dealer_id: Optional[int] = None,
    limit: int = 20,
):
    q = db.query(models.ScrapeLog)
    if dealer_id is not None:
        q = q.filter(models.ScrapeLog.dealer_id == dealer_id)
    logs = q.order_by(desc(models.ScrapeLog.timestamp)).limit(limit).all()
    return [_log_dict(l) for l in logs]


@app.post("/api/scrape/trigger")
async def trigger_scrape(background_tasks: BackgroundTasks):
    def _safe_scrape():
        db = SessionLocal()
        try:
            run_scrape(db)
        except Exception as e:
            logger.error(f"Background scrape failed: {e}", exc_info=True)
        finally:
            db.close()
    background_tasks.add_task(_safe_scrape)
    return {"message": "Scrape triggered in background"}


# ─── Analytics ────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
def get_analytics(dealer_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Comprehensive sales analytics derived from vehicles where is_active=False.
    These are the true sold/off-lot units — much cleaner than raw removed events
    which include scraping noise from partial scrapes and VIN reconciliation.

    When dealer_id is provided, scopes all stats to that location.
    When absent, returns aggregate + per-location breakdown.
    """
    from sqlalchemy import case as sa_case

    # ── Base query: sold vehicles (is_active=False) ──────────────────────────
    base = db.query(models.Vehicle).filter(models.Vehicle.is_active == False)
    if dealer_id:
        base = base.filter(models.Vehicle.dealer_id == dealer_id)

    sold = base.all()
    total_sold = len(sold)

    if total_sold == 0:
        return {
            "total_sold": 0, "summary": {}, "top_makes": [], "top_models": [],
            "top_colors": [], "body_styles": [], "condition_split": {},
            "price_buckets": [], "velocity_by_make": [], "weekly_trend": [],
            "location_performance": [], "cars_to_move": [],
        }

    # ── Summary stats ────────────────────────────────────────────────────────
    prices   = [v.price    for v in sold if v.price    and v.price > 0]
    mileages = [v.mileage  for v in sold if v.mileage  and v.mileage > 0]
    days     = [v.days_on_lot for v in sold if v.days_on_lot and v.days_on_lot > 0]
    dates    = [v.last_seen   for v in sold if v.last_seen]

    summary = {
        "total_sold":      total_sold,
        "avg_price":       round(sum(prices) / len(prices), 0)   if prices   else 0,
        "avg_mileage":     round(sum(mileages) / len(mileages), 0) if mileages else 0,
        "avg_days_on_lot": round(sum(days) / len(days), 1)        if days     else 0,
        "date_from":       min(dates).strftime("%Y-%m-%d") if dates else None,
        "date_to":         max(dates).strftime("%Y-%m-%d") if dates else None,
    }

    # ── Top makes ────────────────────────────────────────────────────────────
    make_counts: dict[str, int] = {}
    for v in sold:
        if v.make:
            make_counts[v.make] = make_counts.get(v.make, 0) + 1
    top_makes = [
        {"make": m, "count": c, "pct": round(c / total_sold * 100, 1)}
        for m, c in sorted(make_counts.items(), key=lambda x: -x[1])[:12]
    ]

    # ── Top models (year + make + model) ─────────────────────────────────────
    model_counts: dict[tuple, int] = {}
    model_prices: dict[tuple, list] = {}
    for v in sold:
        if v.make and v.model:
            key = (v.year or 0, v.make, v.model)
            model_counts[key] = model_counts.get(key, 0) + 1
            if v.price and v.price > 0:
                model_prices.setdefault(key, []).append(v.price)
    top_models = [
        {
            "year": k[0], "make": k[1], "model": k[2],
            "count": c,
            "avg_price": round(sum(model_prices.get(k, [])) / len(model_prices[k]), 0)
                         if model_prices.get(k) else 0,
        }
        for k, c in sorted(model_counts.items(), key=lambda x: -x[1])[:15]
    ]

    # ── Top colors ───────────────────────────────────────────────────────────
    color_counts: dict[str, int] = {}
    for v in sold:
        c_raw = (v.exterior_color or "").strip()
        if c_raw:
            color_counts[c_raw] = color_counts.get(c_raw, 0) + 1
    top_colors = [
        {"color": col, "count": cnt, "pct": round(cnt / total_sold * 100, 1)}
        for col, cnt in sorted(color_counts.items(), key=lambda x: -x[1])[:12]
    ]

    # ── Body styles ──────────────────────────────────────────────────────────
    body_counts: dict[str, int] = {}
    for v in sold:
        b = (v.body_style or "").strip() or "Unknown"
        body_counts[b] = body_counts.get(b, 0) + 1
    body_styles = [
        {"body_style": b, "count": c, "pct": round(c / total_sold * 100, 1)}
        for b, c in sorted(body_counts.items(), key=lambda x: -x[1])
        if b != "Unknown"
    ]

    # ── Condition split ──────────────────────────────────────────────────────
    new_count      = sum(1 for v in sold if (v.condition or "").lower() == "new")
    preowned_count = total_sold - new_count
    condition_split = {
        "new":      new_count,
        "preowned": preowned_count,
        "new_pct":      round(new_count / total_sold * 100, 1),
        "preowned_pct": round(preowned_count / total_sold * 100, 1),
    }

    # ── Price buckets ────────────────────────────────────────────────────────
    buckets = [
        ("Under $15k",   0,      15000),
        ("$15k–$25k",    15000,  25000),
        ("$25k–$35k",    25000,  35000),
        ("$35k–$50k",    35000,  50000),
        ("$50k–$75k",    50000,  75000),
        ("$75k+",        75000,  None),
    ]
    price_buckets = []
    for label, lo, hi in buckets:
        cnt = sum(
            1 for v in sold
            if v.price and v.price >= lo and (hi is None or v.price < hi)
        )
        if cnt > 0:
            price_buckets.append({
                "range": label, "count": cnt,
                "pct": round(cnt / total_sold * 100, 1),
            })

    # ── Velocity by make (avg days_on_lot per make) ──────────────────────────
    make_days: dict[str, list] = {}
    for v in sold:
        if v.make and v.days_on_lot and v.days_on_lot > 0:
            make_days.setdefault(v.make, []).append(v.days_on_lot)
    velocity_by_make = sorted(
        [
            {"make": m, "avg_days": round(sum(d) / len(d), 1), "sample": len(d)}
            for m, d in make_days.items() if len(d) >= 3
        ],
        key=lambda x: x["avg_days"],
    )[:12]

    # ── Weekly trend (sold per week using last_seen date) ────────────────────
    week_counts: dict[str, int] = {}
    for v in sold:
        if v.last_seen:
            # ISO week label: "Apr 07"
            week_start = v.last_seen - timedelta(days=v.last_seen.weekday())
            label = week_start.strftime("%b %d")
            week_counts[label] = week_counts.get(label, 0) + 1
    weekly_trend = [
        {"week": w, "sold": c}
        for w, c in sorted(week_counts.items(), key=lambda x: x[0])
    ]

    # ── Top model years ──────────────────────────────────────────────────────
    year_counts: dict[int, int] = {}
    for v in sold:
        if v.year:
            year_counts[v.year] = year_counts.get(v.year, 0) + 1
    top_years = [
        {"year": y, "count": c, "pct": round(c / total_sold * 100, 1)}
        for y, c in sorted(year_counts.items(), key=lambda x: -x[1])[:12]
    ]

    # ── New vs Used split per franchise (branded) location ───────────────────
    # A "branded" location is one that has at least 1 new-condition vehicle sold.
    # These are the OEM franchise stores (Hyundai, Kia, Ford, etc.). Used-only
    # independents (Mall of Georgia, etc.) are excluded because they have 0 new.
    branded_agg: dict[str, dict] = {}
    for v in sold:
        loc = v.location_name or "Unknown"
        if loc not in branded_agg:
            branded_agg[loc] = {"dealer_id": v.dealer_id, "new": 0, "used": 0,
                                 "new_prices": [], "used_prices": []}
        s = branded_agg[loc]
        if (v.condition or "").lower() == "new":
            s["new"] += 1
            if v.price and v.price > 0: s["new_prices"].append(v.price)
        else:
            s["used"] += 1
            if v.price and v.price > 0: s["used_prices"].append(v.price)

    branded_location_split = sorted(
        [
            {
                "dealer_id": s["dealer_id"],
                "name": loc,
                "new":  s["new"],
                "used": s["used"],
                "total": s["new"] + s["used"],
                "new_pct":  round(s["new"]  / (s["new"] + s["used"]) * 100, 1),
                "used_pct": round(s["used"] / (s["new"] + s["used"]) * 100, 1),
                "avg_new_price":  round(sum(s["new_prices"])  / len(s["new_prices"]),  0) if s["new_prices"]  else 0,
                "avg_used_price": round(sum(s["used_prices"]) / len(s["used_prices"]), 0) if s["used_prices"] else 0,
            }
            for loc, s in branded_agg.items()
            if s["new"] > 0  # only franchise locations with new-car sales
        ],
        key=lambda x: -x["total"],
    )

    # ── Location performance (all-locations query only) ───────────────────────
    location_performance = []
    if not dealer_id:
        loc_stats: dict[str, dict] = {}
        for v in sold:
            loc = v.location_name or "Unknown"
            did = v.dealer_id
            if loc not in loc_stats:
                loc_stats[loc] = {"dealer_id": did, "name": loc, "sold": 0,
                                  "prices": [], "days": [], "makes": {}}
            s = loc_stats[loc]
            s["sold"] += 1
            if v.price and v.price > 0: s["prices"].append(v.price)
            if v.days_on_lot and v.days_on_lot > 0: s["days"].append(v.days_on_lot)
            if v.make: s["makes"][v.make] = s["makes"].get(v.make, 0) + 1

        for loc, s in sorted(loc_stats.items(), key=lambda x: -x[1]["sold"]):
            top_make = max(s["makes"], key=s["makes"].get) if s["makes"] else ""
            location_performance.append({
                "dealer_id":   s["dealer_id"],
                "name":        s["name"],
                "sold":        s["sold"],
                "pct":         round(s["sold"] / total_sold * 100, 1),
                "avg_price":   round(sum(s["prices"]) / len(s["prices"]), 0) if s["prices"] else 0,
                "avg_days":    round(sum(s["days"]) / len(s["days"]), 1)     if s["days"]   else 0,
                "top_make":    top_make,
            })

    # ── Cars to move (current active inventory, flagged by urgency) ───────────
    # Category avg: mean days_on_lot per make from sold vehicles
    make_avg_days = {
        m: round(sum(d) / len(d), 1)
        for m, d in make_days.items() if d
    }
    overall_avg = summary["avg_days_on_lot"] or 14.0

    active_q = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    if dealer_id:
        active_q = active_q.filter(models.Vehicle.dealer_id == dealer_id)
    active_vehicles = (
        active_q.order_by(models.Vehicle.days_on_lot.desc()).limit(200).all()
    )

    cars_to_move = []
    for v in active_vehicles:
        cat_avg = make_avg_days.get(v.make, overall_avg)
        dol = v.days_on_lot or 0
        ratio = dol / cat_avg if cat_avg > 0 else 0
        if ratio >= 1.2 or dol >= 20:
            urgency = "critical" if ratio >= 2.0 or dol >= 30 else \
                      "high"     if ratio >= 1.5 or dol >= 25 else "medium"
            cars_to_move.append({
                "id":            v.id,
                "stock_number":  v.stock_number,
                "year":          v.year,
                "make":          v.make,
                "model":         v.model,
                "trim":          v.trim,
                "price":         v.price,
                "mileage":       v.mileage,
                "exterior_color":v.exterior_color,
                "days_on_lot":   dol,
                "category_avg":  cat_avg,
                "urgency":       urgency,
                "location_name": v.location_name,
                "dealer_id":     v.dealer_id,
                "listing_url":   v.listing_url,
                "condition":     v.condition,
            })

    cars_to_move.sort(key=lambda x: -x["days_on_lot"])

    return {
        "summary":                 summary,
        "top_makes":               top_makes,
        "top_models":              top_models,
        "top_years":               top_years,
        "top_colors":              top_colors,
        "body_styles":             body_styles,
        "condition_split":         condition_split,
        "price_buckets":           price_buckets,
        "velocity_by_make":        velocity_by_make,
        "weekly_trend":            weekly_trend,
        "location_performance":    location_performance,
        "branded_location_split":  branded_location_split,
        "cars_to_move":            cars_to_move[:50],
    }
