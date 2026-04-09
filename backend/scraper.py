"""
ALM Cars Inventory Scraper — v2.0 (24-location)
================================================
Site: almcars.com (powered by Overfuel, domain_id=214)

How the Overfuel feed works:
  - GET /inventory?limit=500&offset=N returns ALL vehicles across ALL stores.
  - A location filter in the URL is client-side only; the SSR payload (via __NEXT_DATA__)
    always returns the full unfiltered set regardless of any URL location param.
  - Each vehicle object carries a `dealer_id` integer that identifies its store.
  - We make ONE linear pagination pass (~14 pages x 500 = ~6,900 vehicles) and bucket
    results by dealer_id in memory. No per-dealer HTTP round-trips.

Overfuel field name mapping:
  stocknumber              -> stock_number
  featuredphoto            -> image_url
  exteriorcolor / exteriorcolorstandard -> exterior_color
  interiorcolor / interiorcolorstandard -> interior_color
  body                     -> body_style
  fuel                     -> fuel_type
  originalprice            -> price (fallback)

Public surface:
  DEALER_REGISTRY          dict[int, dict]  — seed data for the dealers table
  DealerConfig             dataclass        — lightweight dealer descriptor
  DealerVehicleMap         type alias       — dict[dealer_id -> list[vehicle_dict]]
  scrape_all_dealers()     main entry point — returns DealerVehicleMap
  scrape_single_dealer()   narrow wrapper  — returns list[vehicle_dict] for one dealer

Internal helpers (prefixed _):
  _fetch_page()            GET one paginated page, parse __NEXT_DATA__
  _extract()               pull (results, total) out of the JSON tree
  _clean_price()           safe float coerce
  _clean_mileage()         safe int coerce
  normalize_vehicle()      raw Overfuel dict -> internal schema dict
  _bucket_vehicles()       paginate + bucket into DealerVehicleMap

Design invariants:
  - All pipelines idempotent: re-running the scraper produces the same normalized dicts
    for the same source payload.  No side-effects (DB writes live in main.py).
  - normalize_vehicle() always sets dealer_id and location_name — never leaves them None
    when the Overfuel payload carries them.  Missing fields fall back gracefully.
  - Error isolation: _fetch_page() never raises — it returns None on any HTTP/parse error
    so the pagination loop can log and continue rather than aborting the entire run.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.almcars.com"
PAGE_SIZE = 500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ---------------------------------------------------------------------------
# Dealer Registry
# ---------------------------------------------------------------------------
# This dict is the single source of truth for ALM dealership identities.
# It is consumed by two subsystems:
#   1. migrations.py / seed_dealers() — populates the `dealers` table on startup
#   2. _bucket_vehicles() — used to enrich vehicle dicts with canonical names
#
# Confirmed IDs:
#   323  — ALM Mall of Georgia (verified via live __NEXT_DATA__ parse)
#
# All other entries use IDs discovered via the Sprint 0 discovery process
# (parse the full __NEXT_DATA__ payload and collect every unique dealer_id +
# dealer.name seen in the results).  The values below are PLACEHOLDER IDs
# for the remaining 23 known ALM locations derived from ALM's public website.
# Replace any entry marked "[PLACEHOLDER]" with the actual Overfuel dealer_id
# after running the discovery script (see ARCHITECTURE.md §7.1).
#
# To run discovery:
#   python -c "from scraper import _discover_dealer_ids; _discover_dealer_ids()"
#
# Structure: { overfuel_dealer_id: {"name": str, "city": str} }

DEALER_REGISTRY: Dict[int, Dict[str, str]] = {
    # All IDs confirmed via live _discover_dealer_ids() pass on 2026-03-10
    318:  {"name": "ALM Hyundai Athens",        "city": "Athens"},
    319:  {"name": "ALM Hyundai Florence",      "city": "Florence"},
    320:  {"name": "ALM Kia South",             "city": "Union City"},
    321:  {"name": "ALM Kennesaw",              "city": "Kennesaw"},
    322:  {"name": "ALM Gwinnett",              "city": "Duluth"},
    323:  {"name": "ALM Mall of Georgia",       "city": "Buford"},
    324:  {"name": "ALM Marietta",              "city": "Marietta"},
    325:  {"name": "ALM Newnan",                "city": "Newnan"},
    326:  {"name": "ALM Roswell",               "city": "Roswell"},
    433:  {"name": "ALM Hyundai West",          "city": "Lithia Springs"},
    508:  {"name": "ALM Nissan Newnan",         "city": "Newnan"},
    512:  {"name": "ALM Kia Perry",             "city": "Perry"},
    513:  {"name": "ALM CDJR Perry",            "city": "Perry"},
    573:  {"name": "ALM Ford Marietta",         "city": "Marietta"},
    580:  {"name": "ALM Chevrolet South",       "city": "Union City"},
    882:  {"name": "ALM Hyundai Lumberton",     "city": "Lumberton"},
    1433: {"name": "ALM GMC South",             "city": "Morrow"},
    1438: {"name": "ALM Mazda South",           "city": "Morrow"},
    1525: {"name": "Carrollton Hyundai",        "city": "Carrollton"},
    1764: {"name": "ALM CDJR Macon",            "city": "Macon"},
    1766: {"name": "ALM Hyundai Macon",         "city": "Macon"},
    1768: {"name": "ALM Mazda Macon",           "city": "Macon"},
    1769: {"name": "Genesis Macon",             "city": "Macon"},
    1770: {"name": "Hyundai Warner Robins",     "city": "Warner Robins"},
}

# All IDs confirmed from live Overfuel feed — all dealers are active.
CONFIRMED_DEALER_IDS: frozenset[int] = frozenset(DEALER_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Maps Overfuel dealer_id -> list of normalized vehicle dicts for that dealer.
DealerVehicleMap = Dict[int, List[Dict]]


@dataclass
class DealerConfig:
    """
    Lightweight descriptor passed into the scraper.  Built from Dealer ORM rows
    in main.py so the scraper has zero SQLAlchemy dependency.
    """
    dealer_id:  int
    name:       str
    city:       str = ""
    state:      str = "GA"
    is_active:  bool = True
    # Runtime-populated by _bucket_vehicles(); not provided by caller
    vehicles:   List[Dict] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Field normalization helpers
# ---------------------------------------------------------------------------

def _clean_price(val) -> Optional[float]:
    """Coerce any price-like value to float.  Returns None on failure."""
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _clean_mileage(val) -> Optional[int]:
    """Coerce any mileage-like value to int.  Returns None on failure."""
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Vehicle normalization
# ---------------------------------------------------------------------------

def normalize_vehicle(v: Dict) -> Dict:
    """
    Normalize a raw Overfuel vehicle dict into the internal schema used by
    the Vehicle SQLAlchemy model.

    Dealer attribution strategy (in priority order):
      1. v["dealer_id"]              — top-level int field (most reliable)
      2. v["dealer"]["id"]           — nested dealer object
      3. v["dealer"]["dealer_id"]    — alternative key in nested object
      4. None                        — signals a vehicle with no dealer; caller discards it

    location_name is extracted from v["dealer"]["name"] when available.

    This function never raises.  Every field has a safe fallback.
    """
    stock = str(v.get("stocknumber") or v.get("stock_number") or v.get("id") or "").strip()

    # Image URL: ensure absolute URL
    image_url = v.get("featuredphoto") or v.get("image_url") or ""
    if image_url and not image_url.startswith("http"):
        image_url = f"https:{image_url}"

    # Listing URL: prefer slug-based canonical URL
    slug = v.get("slug") or ""
    if slug:
        listing_url = f"{BASE_URL}/inventory/{slug}" if not slug.startswith("http") else slug
    elif stock:
        listing_url = f"{BASE_URL}/inventory/{stock.lower()}"
    else:
        listing_url = ""

    # Dealer attribution — extract dealer_id and location_name from payload
    dealer_id_from_payload: Optional[int] = None
    location_name: str = ""

    raw_dealer = v.get("dealer")
    if isinstance(raw_dealer, dict):
        location_name = raw_dealer.get("name") or ""
        # Prefer top-level dealer_id; fall back to nested dealer object fields
        top_level_did = v.get("dealer_id")
        if top_level_did is not None:
            try:
                dealer_id_from_payload = int(top_level_did)
            except (ValueError, TypeError):
                dealer_id_from_payload = None
        if dealer_id_from_payload is None:
            nested_did = raw_dealer.get("id") or raw_dealer.get("dealer_id")
            if nested_did is not None:
                try:
                    dealer_id_from_payload = int(nested_did)
                except (ValueError, TypeError):
                    dealer_id_from_payload = None
    elif v.get("dealer_id") is not None:
        try:
            dealer_id_from_payload = int(v["dealer_id"])
        except (ValueError, TypeError):
            dealer_id_from_payload = None

    # Enrich location_name from DEALER_REGISTRY if the payload name is empty
    if dealer_id_from_payload is not None and not location_name:
        registry_entry = DEALER_REGISTRY.get(dealer_id_from_payload)
        if registry_entry:
            location_name = registry_entry["name"]

    return {
        "vin":            v.get("vin") or "",
        "stock_number":   stock,
        "year":           int(v.get("year") or 0),
        "make":           v.get("make") or "",
        "model":          v.get("model") or "",
        "trim":           v.get("trim") or v.get("series") or "",
        "price":          _clean_price(v.get("price") or v.get("originalprice")),
        "mileage":        _clean_mileage(v.get("mileage")),
        "exterior_color": v.get("exteriorcolor") or v.get("exteriorcolorstandard") or "",
        "interior_color": v.get("interiorcolor") or v.get("interiorcolorstandard") or "",
        "body_style":     v.get("body") or v.get("body_style") or "",
        "condition":      v.get("condition") or "",
        "fuel_type":      v.get("fuel") or v.get("fuel_type") or "",
        "transmission":   v.get("transmission") or "",
        "image_url":      image_url,
        "listing_url":    listing_url,
        "dealer_id":      dealer_id_from_payload,
        "location_name":  location_name,
    }


# ---------------------------------------------------------------------------
# HTTP / page fetching
# ---------------------------------------------------------------------------

def _fetch_page(offset: int = 0, max_retries: int = 3) -> Optional[Dict]:
    """
    Fetch one paginated inventory page from the Overfuel SSR endpoint and
    return the parsed __NEXT_DATA__ JSON dict.

    Never raises — returns None only after all retry attempts are exhausted.
    The caller (pagination loop) treats None as a signal to stop.
    Retries up to max_retries times with exponential back-off (5s, 10s).
    """
    url = f"{BASE_URL}/inventory?limit={PAGE_SIZE}&offset={offset}"
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=45) as client:
                r = client.get(url, headers=HEADERS)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                script = soup.find("script", {"id": "__NEXT_DATA__"})
                if script and script.string:
                    return json.loads(script.string)
                logger.warning(
                    f"No __NEXT_DATA__ at offset={offset} (attempt {attempt}/{max_retries})"
                )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP {e.response.status_code} fetching offset={offset} "
                f"(attempt {attempt}/{max_retries}): {e}"
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Timeout fetching offset={offset} (attempt {attempt}/{max_retries})"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error fetching offset={offset} "
                f"(attempt {attempt}/{max_retries}): {e}"
            )

        if attempt < max_retries:
            sleep_sec = 5 * attempt
            logger.info(f"Retrying offset={offset} in {sleep_sec}s...")
            time.sleep(sleep_sec)

    logger.error(f"Failed to fetch offset={offset} after {max_retries} attempts")
    return None


def _extract(data: Dict) -> Tuple[List[Dict], int]:
    """
    Pull (results_list, total_count) out of the __NEXT_DATA__ JSON tree.
    Returns ([], 0) if the expected keys are missing (handles site changes gracefully).
    """
    try:
        inv = data["props"]["pageProps"]["inventory"]
        results = inv.get("results") or []
        total = inv.get("meta", {}).get("total", 0)
        return results, total
    except (KeyError, TypeError):
        return [], 0


# ---------------------------------------------------------------------------
# Core pagination + bucketing
# ---------------------------------------------------------------------------

def _bucket_vehicles(
    active_dealer_ids: Optional[frozenset[int]] = None,
) -> Tuple[DealerVehicleMap, int, str]:
    """
    Execute a single linear pagination pass over the Overfuel inventory feed
    and bucket normalized vehicle dicts by dealer_id.

    Args:
        active_dealer_ids:
            If provided, only bucket vehicles whose dealer_id is in this set.
            Vehicles from unknown/inactive dealers are counted but discarded.
            If None, ALL dealer_ids seen in the payload are bucketed (discovery mode).

    Returns:
        (dealer_vehicle_map, total_raw_vehicles_seen, method_string)

        dealer_vehicle_map: dict[dealer_id -> list[normalized_vehicle_dict]]
        total_raw_vehicles_seen: count of raw vehicle records across all pages
        method_string: short label for ScrapeLog.method field

    Design notes:
        - Pre-allocates bucket keys from active_dealer_ids so dealers with zero
          vehicles on this run still appear in the map with an empty list.  This
          is important for change detection — an empty bucket means all previously
          active vehicles for that dealer were removed.
        - The loop stops when the running offset >= total reported by the API,
          or when a page returns no results (handles API under-reporting gracefully).
        - A None page (fetch failure) triggers a break rather than an infinite retry.
          The caller's per-dealer processing will detect the empty bucket and set
          that dealer's status to "error" / "no_data".
    """
    # Pre-allocate buckets for all active dealers (empty list = safe signal for removal detection)
    if active_dealer_ids is not None:
        dealer_buckets: DealerVehicleMap = {did: [] for did in active_dealer_ids}
    else:
        dealer_buckets = {}  # discovery mode — keys added on-the-fly

    total_raw = 0
    offset = 0
    total_global: Optional[int] = None
    page_num = 0

    while True:
        page_num += 1
        data = _fetch_page(offset=offset)

        if data is None:
            logger.warning(
                f"Page fetch returned None at offset={offset} (page {page_num}). "
                "Stopping pagination — downstream dealers will see partial data."
            )
            break

        results, total = _extract(data)

        if total_global is None:
            total_global = total
            logger.info(
                f"Overfuel total inventory: {total} vehicles across all ALM stores"
            )

        if not results:
            logger.info(f"Empty results at offset={offset} — end of feed.")
            break

        page_vehicles = len(results)
        total_raw += page_vehicles
        bucketed_this_page = 0
        discarded_this_page = 0

        for raw_v in results:
            normalized = normalize_vehicle(raw_v)
            did = normalized.get("dealer_id")

            if did is None:
                logger.debug(
                    f"Vehicle stock={normalized.get('stock_number')!r} has no dealer_id "
                    "— discarding"
                )
                discarded_this_page += 1
                continue

            if active_dealer_ids is not None and did not in active_dealer_ids:
                # Vehicle belongs to a dealer not in our active set
                discarded_this_page += 1
                continue

            # Discovery mode: create bucket on first encounter
            if did not in dealer_buckets:
                dealer_buckets[did] = []

            # Drop vehicles with empty stock_number — they cannot be change-detected
            if not normalized.get("stock_number"):
                logger.debug(f"Vehicle dealer_id={did} has no stock_number — discarding")
                discarded_this_page += 1
                continue

            dealer_buckets[did].append(normalized)
            bucketed_this_page += 1

        logger.info(
            f"  Page {page_num} offset={offset}: "
            f"{page_vehicles} raw, {bucketed_this_page} bucketed, "
            f"{discarded_this_page} discarded"
        )

        offset += page_vehicles

        if total_global and offset >= total_global:
            logger.info(
                f"Pagination complete: offset={offset} >= total={total_global}"
            )
            break

    # VIN reconciliation — fix vehicles misattributed in the unfiltered feed
    if active_dealer_ids is not None:
        logger.info("Starting VIN reconciliation via per-dealer supplemental fetches...")
        dealer_buckets = _reconcile_by_vin(dealer_buckets, active_dealer_ids)

    # Bucket summary
    active_buckets = {did: vlist for did, vlist in dealer_buckets.items() if vlist}
    logger.info(
        f"Bucketing done: {total_raw} raw vehicles, "
        f"{len(active_buckets)} dealers with data, "
        f"{sum(len(v) for v in dealer_buckets.values())} total bucketed"
    )
    for did, vlist in sorted(dealer_buckets.items()):
        name = DEALER_REGISTRY.get(did, {}).get("name", f"dealer_id={did}")
        logger.info(f"  {name} (id={did}): {len(vlist)} vehicles")

    return dealer_buckets, total_raw, "overfuel_single_pass_bucket"


# ---------------------------------------------------------------------------
# Per-dealer filtered fetch + VIN reconciliation
# ---------------------------------------------------------------------------

def _fetch_dealer_filtered(dealer_id: int) -> List[Dict]:
    """
    Fetch the dealer-filtered inventory page for one dealer and return a list
    of normalized vehicle dicts.

    Uses the Overfuel server-side filter (?dealer_id[]={dealer_id}) which
    returns the canonical attribution for that dealer — including vehicles that
    appear in the unfiltered feed under a different dealer_id or with a
    modified stock number suffix.

    One page (limit=500) is sufficient; no ALM dealer exceeds 500 vehicles.

    Never raises — returns [] on any HTTP/parse error so the caller can
    gracefully fall back to the unfiltered bucket data.
    """
    url = f"{BASE_URL}/inventory?limit={PAGE_SIZE}&offset=0&dealer_id[]={dealer_id}"
    try:
        with httpx.Client(follow_redirects=True, timeout=45) as client:
            r = client.get(url, headers=HEADERS)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            script = soup.find("script", {"id": "__NEXT_DATA__"})
            if script and script.string:
                results, _ = _extract(json.loads(script.string))
                normalized = []
                for raw_v in results:
                    nv = normalize_vehicle(raw_v)
                    # Force the dealer_id to the requested dealer in case the
                    # payload carries a different value (rare but observed).
                    nv["dealer_id"] = dealer_id
                    if nv.get("stock_number") and nv.get("vin"):
                        normalized.append(nv)
                return normalized
            logger.warning(f"_fetch_dealer_filtered({dealer_id}): no __NEXT_DATA__ found")
    except httpx.HTTPStatusError as e:
        logger.warning(f"_fetch_dealer_filtered({dealer_id}): HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning(f"_fetch_dealer_filtered({dealer_id}): {e}")
    return []


def _reconcile_by_vin(
    dealer_buckets: DealerVehicleMap,
    active_dealer_ids: frozenset[int],
) -> DealerVehicleMap:
    """
    Supplemental per-dealer fetch to fix vehicles misattributed in the
    unfiltered Overfuel feed.

    Some vehicles appear in the unfiltered feed with a different dealer_id
    and/or a modified stock number (e.g., trailing 'P' or 'A' suffix) compared
    to how they appear when queried via the dealer-filtered endpoint.  This
    function fetches each dealer's filtered page and uses VIN as the ground
    truth to move misattributed vehicles into the correct bucket.

    Algorithm:
      1. Build a global vin_index: VIN -> (owner_dealer_id, vehicle_dict)
         from the current unfiltered buckets.
      2. For each active dealer (sorted for deterministic ordering):
         a. Fetch its filtered page via _fetch_dealer_filtered().
         b. For each filtered vehicle whose VIN is NOT already in this
            dealer's bucket:
            - If the VIN is in another dealer's bucket: remove it from there
              and add the filtered version (with correct stock_number) here.
            - If the VIN isn't in any bucket: add the filtered version here
              (it may have been discarded due to a missing stock_number in the
              unfiltered feed).
      3. Log totals and return the updated buckets.

    Failures in _fetch_dealer_filtered() return [] and are silently skipped —
    the unfiltered data is used as-is for that dealer.
    """
    # Build VIN → (dealer_id, vehicle) index from unfiltered buckets
    vin_index: Dict[str, Tuple[int, Dict]] = {}
    for did, vehicles in dealer_buckets.items():
        for v in vehicles:
            vin = v.get("vin", "")
            if vin:
                vin_index[vin] = (did, v)

    moves = 0
    additions = 0

    for dealer_id in sorted(active_dealer_ids):
        filtered = _fetch_dealer_filtered(dealer_id)
        if not filtered:
            continue

        # VINs already correctly attributed to this dealer
        bucket_vins = {v.get("vin", "") for v in dealer_buckets.get(dealer_id, [])}

        for fv in filtered:
            vin = fv.get("vin", "")
            if not vin or vin in bucket_vins:
                continue  # already in the right place

            if vin in vin_index:
                # Move from wrong bucket to correct bucket
                wrong_did, wrong_v = vin_index[vin]
                dealer_buckets[wrong_did] = [
                    v for v in dealer_buckets[wrong_did] if v.get("vin") != vin
                ]
                logger.info(
                    f"  VIN {vin}: moved dealer {wrong_did}→{dealer_id} "
                    f"stock {wrong_v.get('stock_number')!r}→{fv.get('stock_number')!r}"
                )
                moves += 1
            else:
                logger.info(
                    f"  VIN {vin}: added to dealer {dealer_id} "
                    f"stock {fv.get('stock_number')!r} (absent from unfiltered feed)"
                )
                additions += 1

            dealer_buckets.setdefault(dealer_id, []).append(fv)
            bucket_vins.add(vin)
            vin_index[vin] = (dealer_id, fv)

    logger.info(f"VIN reconciliation: {moves} moved, {additions} added")
    return dealer_buckets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_all_dealers(
    active_dealers: Optional[List[DealerConfig]] = None,
) -> Tuple[DealerVehicleMap, int, str]:
    """
    Main entry point for the 24-dealer scrape.

    Executes a single pagination pass through the Overfuel feed and returns
    vehicles bucketed by dealer_id.

    Args:
        active_dealers:
            List of DealerConfig objects representing the dealers to process.
            Built by main.py from the `dealers` DB table (is_active=True rows).
            If None, runs in discovery mode — captures ALL dealer_ids seen in
            the live feed without filtering. Discovery mode is used to find
            what Overfuel dealer_ids are actually present so DEALER_REGISTRY
            can be updated.

    Returns:
        (dealer_vehicle_map, total_raw, method)

        dealer_vehicle_map:
            dict[dealer_id -> list[vehicle_dict]]
            Every active dealer is guaranteed a key, even if its list is empty.
            Empty list signals all vehicles were removed from that dealer since
            the last scrape — main.py uses this to trigger removal events.

        total_raw:
            Total raw vehicle records seen across all paginated pages.
            Used for aggregate ScrapeLog.vehicles_found.

        method:
            Short string for ScrapeLog.method.

    Usage in main.py:
        active_dealers = db.query(models.Dealer).filter(
            models.Dealer.is_active == True
        ).order_by(models.Dealer.scrape_priority, models.Dealer.name).all()

        configs = [
            DealerConfig(dealer_id=d.id, name=d.name, city=d.city or "")
            for d in active_dealers
        ]
        dealer_map, total_raw, method = scrape_all_dealers(configs)
    """
    if active_dealers is None:
        logger.info("scrape_all_dealers() called in DISCOVERY MODE — capturing all dealer_ids")
        return _bucket_vehicles(active_dealer_ids=None)

    if not active_dealers:
        logger.warning("scrape_all_dealers() called with empty dealer list — nothing to scrape")
        return {}, 0, "no_active_dealers"

    active_ids = frozenset(d.dealer_id for d in active_dealers)
    logger.info(
        f"Starting single-pass scrape for {len(active_dealers)} active dealer(s): "
        f"{sorted(active_ids)}"
    )
    return _bucket_vehicles(active_dealer_ids=active_ids)


def scrape_single_dealer(
    dealer_id: int,
    dealer_name: str = "",
) -> List[Dict]:
    """
    Narrow wrapper — scrapes the full feed and returns only the vehicles for
    one specific dealer.

    This is intentionally expensive (it paginates through all ~6,900 vehicles)
    because Overfuel offers no per-dealer feed endpoint.  Use this sparingly:
    - Manual re-trigger via POST /api/scrape/trigger {"dealer_id": 323}
    - Test harness single-dealer assertions

    For scheduled 6-hour runs, always use scrape_all_dealers() which amortizes
    the full pagination cost across all 24 dealers in a single pass.

    Returns:
        List of normalized vehicle dicts for the requested dealer.
        Empty list if the dealer has no vehicles or the feed is unreachable.
    """
    if not dealer_name and dealer_id in DEALER_REGISTRY:
        dealer_name = DEALER_REGISTRY[dealer_id]["name"]
    if not dealer_name:
        dealer_name = f"dealer_id={dealer_id}"

    logger.info(f"scrape_single_dealer: {dealer_name} (dealer_id={dealer_id})")
    config = DealerConfig(dealer_id=dealer_id, name=dealer_name)
    dealer_map, _total, _method = scrape_all_dealers(active_dealers=[config])
    vehicles = dealer_map.get(dealer_id, [])
    logger.info(
        f"scrape_single_dealer result: {len(vehicles)} vehicles for {dealer_name}"
    )
    return vehicles


# ---------------------------------------------------------------------------
# Discovery utility (run manually during Sprint 0 onboarding)
# ---------------------------------------------------------------------------

def _discover_dealer_ids() -> Dict[int, Dict[str, str]]:
    """
    Paginate the full Overfuel feed and collect every unique dealer_id + dealer
    name seen in the payload.  Prints a DEALER_REGISTRY snippet you can paste
    into this file.

    Run from shell:
        cd /Users/emadsiddiqui/ALM/backend
        source venv/bin/activate
        python -c "from scraper import _discover_dealer_ids; _discover_dealer_ids()"
    """
    discovered: Dict[int, Dict[str, str]] = {}
    offset = 0
    total_global: Optional[int] = None

    print("Starting dealer discovery pass...")

    while True:
        data = _fetch_page(offset=offset)
        if data is None:
            print(f"Fetch failed at offset={offset}. Stopping.")
            break

        results, total = _extract(data)
        if total_global is None:
            total_global = total
            print(f"Total Overfuel vehicles: {total}")

        if not results:
            break

        for raw_v in results:
            did = raw_v.get("dealer_id")
            if did is None:
                raw_dealer = raw_v.get("dealer")
                if isinstance(raw_dealer, dict):
                    did = raw_dealer.get("id") or raw_dealer.get("dealer_id")
            if did is None:
                continue
            try:
                did = int(did)
            except (ValueError, TypeError):
                continue

            if did not in discovered:
                raw_dealer = raw_v.get("dealer")
                name = ""
                city = ""
                if isinstance(raw_dealer, dict):
                    name = raw_dealer.get("name") or ""
                    city = raw_dealer.get("city") or ""
                discovered[did] = {"name": name, "city": city}

        offset += len(results)
        if total_global and offset >= total_global:
            break

    print("\n--- Discovered dealer_ids ---")
    print("DEALER_REGISTRY: Dict[int, Dict[str, str]] = {")
    for did, info in sorted(discovered.items()):
        confirmed = "  # CONFIRMED" if did in CONFIRMED_DEALER_IDS else ""
        print(f"    {did}: {{\"name\": \"{info['name']}\", \"city\": \"{info['city']}\"}},{confirmed}")
    print("}")
    print(f"\nTotal unique dealers found: {len(discovered)}")

    return discovered
