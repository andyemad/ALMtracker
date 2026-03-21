# ALM Inventory Tracker — Multi-Location Data Pipeline Design

**Created**: 2026-03-10
**Agent**: Data Engineer (engineering-ai-engineer)
**Input**: `/Users/emadsiddiqui/ALM/backend/scraper.py` (current single-location scraper)
**Output**: Implementation plan for 24x volume multi-location pipeline
**References**: ARCHITECTURE.md, SPRINT.md

---

## 1. Current Pipeline Audit

### Existing scraper.py Analysis

**File**: `/Users/emadsiddiqui/ALM/backend/scraper.py`

The current pipeline has a clean, well-structured flow:

```
_fetch_page(offset) -> raw JSON (via httpx + BeautifulSoup __NEXT_DATA__ extraction)
    |
_extract(data) -> (results: List[Dict], total: int)
    |
[filter: v.get("dealer_id") == 323]  <-- single-location filter
    |
normalize_vehicle(v) -> clean Dict with our schema fields
    |
return (all_vehicles: List[Dict], method: str)
```

**What works well** (keep these patterns):
- `httpx` + `BeautifulSoup` for `__NEXT_DATA__` extraction — reliable and fast
- `normalize_vehicle()` already extracts `dealer_id` and `location_name` from the `dealer` dict
- `_clean_price()` and `_clean_mileage()` — robust type coercion
- `PAGE_SIZE=500` — optimal for Overfuel's API
- Single pagination pass through all ~6,898 vehicles — already correct architecture
- Error handling in `_fetch_page()` catches exceptions per page with logging

**What must change**:
- `DEALER_ID = 323` and `DEALER_NAME` — hardcoded constants must be removed
- Filter `v.get("dealer_id") == DEALER_ID` — must become multi-dealer bucketing
- Return type `Tuple[List[Dict], str]` — must become `Tuple[Dict[int, List[Dict]], str]`
- No retry logic on failed page fetches — must add exponential backoff
- No rate limiting between page requests — must add for politeness
- `scrape_all_vehicles()` function signature — must accept dealer filter parameter

---

## 2. Pipeline Architecture (Target)

### Data Flow Diagram

```
Phase 1: Fetch (HTTP)
+------------------------------------------+
|  almcars.com /inventory?limit=500&offset=N |
|  __NEXT_DATA__ JSON (Next.js SSR)          |
+------------------------------------------+
        |
        v (paginate: offset += 500 per page, ~14 pages total)
Phase 2: Parse
+------------------------------------------+
|  _fetch_page(offset) -> raw Dict          |
|  _extract(data) -> (results, total)       |
|  BeautifulSoup + json.loads               |
+------------------------------------------+
        |
        v (per vehicle in results)
Phase 3: Bucket by Dealer
+------------------------------------------+
|  dealer_id = v.get("dealer_id")           |
|  if dealer_id in active_dealer_set:       |
|      dealer_buckets[dealer_id].append(v)  |
+------------------------------------------+
        |
        v (per dealer's raw vehicles)
Phase 4: Normalize
+------------------------------------------+
|  normalize_vehicle(v) -> clean dict       |
|  Field mapping: Overfuel -> our schema    |
|  Type coercion: price, mileage, int(year) |
|  URL construction: slug or stock_number   |
+------------------------------------------+
        |
        v
Phase 5: Validation
+------------------------------------------+
|  _validate_vehicle(v) -> (valid, errors)  |
|  Required fields: stock_number, make, year|
|  Business rules: year > 1980, price > 0   |
|  Logging: warn on invalid records         |
+------------------------------------------+
        |
        v
Phase 6: Return
+------------------------------------------+
|  Dict[int, List[Dict]] keyed by dealer_id |
|  {323: [276 vehicles], 401: [180 veh], ...}|
+------------------------------------------+
        |
        v (in main.py run_scrape_all)
Phase 7: Persistence (Change Detection)
+------------------------------------------+
|  Per dealer: active_map lookup by         |
|  (dealer_id, stock_number) composite key  |
|  Additions: new Vehicle rows              |
|  Removals: is_active = False              |
|  Price changes: VehicleEvent created      |
+------------------------------------------+
```

---

## 3. New scraper.py Implementation Plan

### 3.1 Remove Hardcoded Constants

**Before** (remove these):
```python
DEALER_ID = 323           # ALM Mall of Georgia
DEALER_NAME = "ALM Mall of Georgia"
```

**After** (add this structure):
```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class DealerConfig:
    """Immutable config for a single ALM dealer location."""
    dealer_id: int
    name: str
    city: str = ""
    state: str = "GA"
    is_active: bool = True
```

The `DealerConfig` objects are built from the `locations.py` registry or from the database
`Dealer` table. The scraper receives a set of dealer_ids to collect; it does not need the
full config during the fetch phase (that comes from the DB in main.py).

---

### 3.2 New Function Signatures

```python
def scrape_all_locations(
    dealer_ids: Optional[Set[int]] = None,
    timeout_per_page: float = 45.0,
    page_delay: float = 0.3,
) -> Tuple[Dict[int, List[Dict]], str]:
    """
    Scrape all ALM locations in a single pagination pass.

    Args:
        dealer_ids: Set of Overfuel dealer_ids to collect. If None, collects ALL dealers.
        timeout_per_page: HTTP timeout in seconds per page fetch.
        page_delay: Seconds to sleep between page fetches (rate limiting).

    Returns:
        Tuple of:
        - Dict mapping dealer_id -> List of normalized vehicle dicts
        - Method string (e.g. "httpx_multi_dealer")
    """


def scrape_single_dealer(
    dealer_id: int,
    dealer_name: str = "",
    timeout_per_page: float = 45.0,
) -> Tuple[List[Dict], str]:
    """
    Scrape a single dealer by filtering the full pagination pass.
    Convenience wrapper around scrape_all_locations for targeted re-scrapes.

    Returns:
        Tuple of:
        - List of normalized vehicle dicts for this dealer only
        - Method string
    """
    result, method = scrape_all_locations(
        dealer_ids={dealer_id},
        timeout_per_page=timeout_per_page,
    )
    return result.get(dealer_id, []), method
```

---

### 3.3 Core Pagination Loop (Updated)

```python
def scrape_all_locations(
    dealer_ids: Optional[Set[int]] = None,
    timeout_per_page: float = 45.0,
    page_delay: float = 0.3,
) -> Tuple[Dict[int, List[Dict]], str]:
    """Single pagination pass; buckets by dealer_id."""
    import time

    # If no filter provided, collect ALL dealers encountered
    collect_all = dealer_ids is None

    dealer_buckets: Dict[int, List[Dict]] = {}
    if dealer_ids:
        # Pre-initialize buckets so dealers with 0 vehicles still appear
        for did in dealer_ids:
            dealer_buckets[did] = []

    offset = 0
    total_global: Optional[int] = None
    pages_fetched = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3

    logger.info(
        f"Starting scrape: dealer_ids={dealer_ids or 'ALL'}, "
        f"page_size={PAGE_SIZE}"
    )

    while True:
        data = _fetch_page(offset=offset, timeout=timeout_per_page)

        if not data:
            consecutive_errors += 1
            logger.warning(
                f"Page fetch failed at offset={offset} "
                f"(error {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})"
            )
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(f"Aborting: {MAX_CONSECUTIVE_ERRORS} consecutive page failures")
                break
            # Exponential backoff before retry
            time.sleep(2 ** consecutive_errors)
            continue

        consecutive_errors = 0  # reset on success
        results, total = _extract(data)

        if total_global is None:
            total_global = total
            logger.info(f"Total Overfuel inventory: {total} vehicles across all stores")

        if not results:
            logger.info(f"Empty results at offset={offset}, pagination complete")
            break

        # Bucket vehicles by dealer_id
        for v in results:
            did = v.get("dealer_id")
            if did is None:
                logger.debug(f"Vehicle missing dealer_id: stock={v.get('stocknumber', 'UNKNOWN')}")
                continue

            if collect_all or did in dealer_ids:
                if did not in dealer_buckets:
                    dealer_buckets[did] = []
                normalized = normalize_vehicle(v)
                if _validate_vehicle(normalized):
                    dealer_buckets[did].append(normalized)

        pages_fetched += 1
        offset += len(results)

        # Log progress every 5 pages
        if pages_fetched % 5 == 0:
            total_collected = sum(len(vs) for vs in dealer_buckets.values())
            logger.info(
                f"Progress: page {pages_fetched}, offset={offset}/{total_global}, "
                f"collected={total_collected} vehicles across {len(dealer_buckets)} dealers"
            )

        if total_global and offset >= total_global:
            logger.info(f"Pagination complete: {pages_fetched} pages, offset={offset}")
            break

        # Rate limiting between page fetches
        if page_delay > 0:
            time.sleep(page_delay)

    # Summary log
    total_collected = sum(len(vs) for vs in dealer_buckets.values())
    dealer_summary = ", ".join(
        f"dealer {did}: {len(vs)}"
        for did, vs in sorted(dealer_buckets.items())
    )
    logger.info(
        f"Scrape complete: {total_collected} vehicles from {len(dealer_buckets)} dealers "
        f"({pages_fetched} pages) | {dealer_summary}"
    )

    if not dealer_buckets or total_collected == 0:
        logger.warning("0 vehicles collected — check dealer_ids or site structure")
        return {}, "no_results"

    return dealer_buckets, "httpx_multi_dealer"
```

---

### 3.4 Improved _fetch_page with Retry

```python
def _fetch_page(offset: int = 0, timeout: float = 45.0, max_retries: int = 2) -> Optional[Dict]:
    """
    Fetch a single inventory page with exponential backoff retry.
    """
    import time
    url = f"{BASE_URL}/inventory?limit={PAGE_SIZE}&offset={offset}"

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                r = client.get(url, headers=HEADERS)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                script = soup.find("script", {"id": "__NEXT_DATA__"})
                if script and script.string:
                    data = json.loads(script.string)
                    # Validate expected structure before returning
                    if "props" not in data:
                        logger.warning(f"Unexpected __NEXT_DATA__ structure at offset={offset}")
                        return None
                    return data
                else:
                    logger.warning(f"No __NEXT_DATA__ script tag at offset={offset}")
                    return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** (attempt + 2)  # 4s, 8s, 16s for rate limits
                logger.warning(f"Rate limited (429) at offset={offset}, waiting {wait}s")
                time.sleep(wait)
            elif e.response.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"Server error {e.response.status_code} at offset={offset}, retry in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"HTTP {e.response.status_code} at offset={offset}: non-retryable")
                return None
        except Exception as e:
            wait = 2 ** attempt
            logger.error(f"Failed to fetch offset={offset} (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(wait)

    logger.error(f"All {max_retries + 1} attempts failed for offset={offset}")
    return None
```

---

### 3.5 Vehicle Validation Layer (New)

```python
def _validate_vehicle(v: Dict) -> bool:
    """
    Validate a normalized vehicle dict.
    Returns True if vehicle is valid and should be persisted.
    Logs warnings for invalid records.
    """
    stock = v.get("stock_number", "")
    if not stock:
        logger.debug(f"Skipping vehicle with empty stock_number: vin={v.get('vin', 'N/A')}")
        return False

    year = v.get("year", 0)
    if year and (year < 1980 or year > 2030):
        logger.warning(f"Suspicious year={year} for stock={stock}, keeping record")
        # Don't reject — just warn; could be a classic car or future model

    make = v.get("make", "")
    if not make:
        logger.warning(f"Vehicle stock={stock} has no make — keeping with empty make")
        # Don't reject — partial data is still useful

    price = v.get("price")
    if price is not None and price < 0:
        logger.warning(f"Negative price={price} for stock={stock}, nullifying")
        v["price"] = None  # Mutate in place

    return True  # Accept all records that have a stock_number
```

---

### 3.6 normalize_vehicle() Updates

The existing `normalize_vehicle()` already handles `dealer_id` extraction (line 103) and
`location_name` via the `dealer` dict (lines 78-83). The only change needed is ensuring
the `dealer_id` field is surfaced from the correct Overfuel path.

**Verify this works for all 24 dealers** — the field mapping should be:
```python
# In Overfuel __NEXT_DATA__, each vehicle has:
# {
#   "dealer_id": 323,
#   "dealer": {"name": "ALM Mall of Georgia", "city": "Buford"},
#   "stocknumber": "P12345",
#   ...
# }
```

The existing code at lines 78-104 handles this correctly. No changes needed to `normalize_vehicle()`.

---

## 4. Deduplication Strategy

### When Does Deduplication Occur?

A vehicle appears in multiple dealer buckets when:
1. A vehicle is in transit between ALM locations (temporary scenario)
2. The Overfuel API assigns a vehicle to multiple dealers (platform quirk)
3. A VIN is entered twice under different stock numbers (data entry error)

**Frequency**: Low. ALM locations are independent franchises and generally maintain
separate inventory systems. VIN-based deduplication is a safety net, not the primary path.

### VIN Deduplication Rules

```python
def deduplicate_by_vin(
    dealer_buckets: Dict[int, List[Dict]]
) -> Dict[int, List[Dict]]:
    """
    Remove duplicate vehicles (same VIN) across dealers.
    When a VIN appears in multiple dealers, keep it at the dealer with
    the lower dealer_id (arbitrary but deterministic tie-breaking).

    Note: Vehicles with empty VINs are NOT deduplicated (VIN may be
    genuinely absent for some used vehicle listings).
    """
    seen_vins: Dict[str, int] = {}  # vin -> dealer_id that owns it
    cleaned: Dict[int, List[Dict]] = {did: [] for did in dealer_buckets}

    # Process dealers in sorted order for deterministic tie-breaking
    for dealer_id in sorted(dealer_buckets.keys()):
        for vehicle in dealer_buckets[dealer_id]:
            vin = vehicle.get("vin", "")
            if not vin:
                # No VIN — cannot deduplicate, keep it
                cleaned[dealer_id].append(vehicle)
                continue

            if vin in seen_vins:
                prev_dealer = seen_vins[vin]
                logger.warning(
                    f"Duplicate VIN {vin}: dealer {prev_dealer} (kept) vs "
                    f"dealer {dealer_id} (dropped). Stock: {vehicle.get('stock_number')}"
                )
                # Do not append to cleaned — duplicate dropped
            else:
                seen_vins[vin] = dealer_id
                cleaned[dealer_id].append(vehicle)

    total_before = sum(len(vs) for vs in dealer_buckets.values())
    total_after = sum(len(vs) for vs in cleaned.values())
    if total_before != total_after:
        logger.info(f"Deduplication: removed {total_before - total_after} duplicate VINs")

    return cleaned
```

**Stock Number Deduplication** (within a single dealer):

If the same stock_number appears twice in one dealer's bucket (Overfuel data issue),
keep only the first occurrence:

```python
def deduplicate_within_dealer(vehicles: List[Dict]) -> List[Dict]:
    """Remove duplicate stock numbers within a single dealer's vehicle list."""
    seen: Dict[str, bool] = {}
    result = []
    for v in vehicles:
        stock = v.get("stock_number", "")
        if stock and stock in seen:
            logger.warning(f"Duplicate stock_number {stock} within same dealer — dropping second")
            continue
        if stock:
            seen[stock] = True
        result.append(v)
    return result
```

### Deduplication Pipeline Integration

```python
# In scrape_all_locations(), after collecting all results:
dealer_buckets = deduplicate_by_vin(dealer_buckets)
for dealer_id in dealer_buckets:
    dealer_buckets[dealer_id] = deduplicate_within_dealer(dealer_buckets[dealer_id])
```

---

## 5. Volume & Performance Analysis

### Current vs. Target Data Volume

| Metric | Current (1 dealer) | Target (24 dealers) | Notes |
|--------|-------------------|--------------------|-|
| Active vehicles | ~276 | ~6,900 | 25x growth |
| Pages per scrape | ~1 page (filter fast) | 14 pages (same!) | Already fetching all pages |
| HTTP requests/scrape | ~1-2 | 14 | Single pass, not 24x |
| Scrape duration (HTTP) | ~60s | ~65s | Same pagination, +5s overhead |
| DB writes/scrape | ~10-50 | ~250-1,250 | More change detection work |
| scrape_logs rows/month | ~120 | ~120 | One log per full run |
| vehicle_events rows/month | ~500 | ~12,500 | 25x event volume |

**Key insight**: The HTTP fetching cost does NOT scale with location count because the current
scraper already fetches ALL vehicles (from all 24 dealers) in its pagination loop. We're just
collecting more of the data we already download. The cost increase is primarily in DB write operations.

### Performance Targets

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Full scrape HTTP | under 90s | 14 pages * 5s/page + overhead |
| DB writes (full scrape) | under 30s | Batch commits per dealer |
| Total scrape run | under 2 minutes | Well under 6h schedule interval |
| `GET /api/vehicles` | under 200ms | With `ix_vehicle_dealer_active` index |
| `GET /api/stats` | under 150ms | Aggregate count queries |
| DB size (1 year) | under 500MB | Comfortably within SQLite limits |

### DB Growth Projection (1 Year)

```
Active vehicles: ~7,000 rows * 200 bytes = ~1.4 MB
Historical vehicles (inactive): ~14,000 rows * 200 bytes = ~2.8 MB
vehicle_events: ~150,000 rows * 300 bytes = ~45 MB
scrape_logs: ~1,460 rows (4/day) * 2KB each = ~3 MB
watchlist_alerts: negligible
leads: negligible

Total estimated: ~55 MB after 1 year
SQLite practical limit: ~2GB
Assessment: SQLite is adequate for this scale for 3-5 years
```

---

## 6. Error Handling & Resilience

### Partial Failure Strategy

When one dealer's data fails to scrape, do NOT fail the entire run:

```python
# In scrape_all_locations() — per-dealer error isolation
# The pagination loop naturally handles this:
# - If dealer A's vehicles appear on pages 1-3 and page 2 fails,
#   the retry logic in _fetch_page() will recover.
# - Vehicles from other dealers on page 2 will also be missed,
#   but page 2 will be retried, recovering all dealers.
# - Persistent page failure (3 consecutive errors) aborts the run
#   and logs an error, but does not lose previously collected vehicles.

# In main.py run_scrape_all():
per_dealer_stats = []
for dealer_id, vehicles in dealer_vehicles.items():
    try:
        added, removed, price_changes = _process_dealer_vehicles(
            dealer_id, vehicles, active_map, db
        )
        per_dealer_stats.append({
            "id": dealer_id,
            "status": "success",
            "added": added,
            "removed": removed,
            "price_changes": price_changes,
        })
    except Exception as e:
        logger.error(f"Failed to process dealer {dealer_id}: {e}")
        per_dealer_stats.append({
            "id": dealer_id,
            "status": "error",
            "error": str(e),
        })
        # Continue with other dealers
        continue

db.commit()  # Commit successful dealers even if some failed
```

### Rate Limiting Defense

Overfuel's CDN (likely CloudFlare or Fastly) may rate-limit aggressive scrapers. Defense:

1. **0.3s delay between page fetches** (configurable via `page_delay` param)
2. **User-Agent rotation** (optional — current single UA seems to work fine)
3. **Exponential backoff on 429 responses** (implemented in `_fetch_page`)
4. **HTTP/2 keep-alive** (httpx default — reduces handshake overhead without appearing as bot)
5. **Single concurrent pagination** (no parallel page fetching — keeps request rate low)

**The key advantage**: We fetch pages once, not 24 times. Even with 14 pages at 0.3s delay,
total HTTP time is ~65-70 seconds. No rate limiter should trigger at this frequency.

### Monitoring & Alerting

```python
# Log structure for pipeline observability:
logger.info(
    "scrape_complete",
    extra={
        "pages_fetched": pages_fetched,
        "total_vehicles": total_collected,
        "dealers_scraped": len(dealer_buckets),
        "dealers_with_data": sum(1 for vs in dealer_buckets.values() if vs),
        "dealers_empty": sum(1 for vs in dealer_buckets.values() if not vs),
        "duration_seconds": elapsed,
        "consecutive_page_errors": consecutive_errors,
    }
)
```

---

## 7. New File: backend/locations.py

This file is created from the dealer discovery run (Sprint S0-1) and serves as the static
ground truth for all 24 ALM dealer IDs.

```python
"""
ALM Cars — Location Registry
Generated from Overfuel __NEXT_DATA__ discovery (2026-03-10).
Update this file if new ALM locations are added or dealer IDs change.
"""

# Format: dealer_id -> {"name": str, "city": str, "state": str, "slug": str}
# All locations are in Georgia (state="GA")
# Slugs are URL-friendly, lowercase, hyphen-separated

ALM_LOCATIONS: dict = {
    # NOTE: dealer_id values are placeholders — replace with actual IDs from S0-1 discovery
    323: {
        "name": "ALM Mall of Georgia",
        "city": "Buford",
        "state": "GA",
        "slug": "mall-of-georgia",
        "is_active": True,
        "scrape_priority": 1,
    },
    # Additional 23 dealers will be added after Sprint S0-1 discovery run
    # Example structure:
    # 401: {
    #     "name": "ALM Buckhead",
    #     "city": "Atlanta",
    #     "state": "GA",
    #     "slug": "buckhead",
    #     "is_active": True,
    #     "scrape_priority": 2,
    # },
}

# Convenience set for fast membership testing
ACTIVE_DEALER_IDS: frozenset = frozenset(
    did for did, info in ALM_LOCATIONS.items() if info.get("is_active", True)
)
```

---

## 8. Updated scraper.py — Complete Implementation

Below is the complete refactored `scraper.py` ready for implementation.

**File**: `/Users/emadsiddiqui/ALM/backend/scraper.py`

```python
"""
ALM Cars Inventory Scraper — Multi-Location Edition
=====================================================
Site: almcars.com (powered by Overfuel, domain_id=214)
Architecture: Single pagination pass collects all 24 ALM dealers simultaneously.

How the site works:
  - /inventory (no location filter) returns ALL vehicles across all stores via SSR
  - The location filter on the URL is client-side only (SSR returns 0 with it)
  - We fetch all inventory with limit=500 per page (~14 pages for ~6,898 vehicles)
  - We bucket results by dealer_id to separate each location's vehicles

Overfuel vehicle field mapping:
  stocknumber     -> stock_number
  featuredphoto   -> image_url
  exteriorcolor   -> exterior_color
  body            -> body_style
  fuel            -> fuel_type
  dealer_id       -> dealer_id (int, maps to dealers.id)
  dealer.name     -> location_name (denormalized string)
"""

import httpx
import json
import logging
import time
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

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


def _clean_price(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _clean_mileage(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def normalize_vehicle(v: Dict) -> Dict:
    """Normalize a raw Overfuel vehicle dict into our internal schema."""
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

    dealer = v.get("dealer") or {}
    location_name = (
        dealer.get("name") if isinstance(dealer, dict)
        else str(dealer) if dealer
        else ""
    )

    return {
        "vin": v.get("vin") or "",
        "stock_number": stock,
        "dealer_id": v.get("dealer_id"),
        "location_name": location_name,
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
    }


def _validate_vehicle(v: Dict) -> bool:
    """Validate normalized vehicle. Returns False for records to skip."""
    if not v.get("stock_number"):
        return False
    price = v.get("price")
    if price is not None and price < 0:
        v["price"] = None  # Sanitize negative prices
    return True


def _fetch_page(offset: int = 0, timeout: float = 45.0, max_retries: int = 2) -> Optional[Dict]:
    """Fetch a single inventory page with exponential backoff retry."""
    url = f"{BASE_URL}/inventory?limit={PAGE_SIZE}&offset={offset}"

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                r = client.get(url, headers=HEADERS)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                script = soup.find("script", {"id": "__NEXT_DATA__"})
                if script and script.string:
                    data = json.loads(script.string)
                    if "props" not in data:
                        logger.warning(f"Unexpected __NEXT_DATA__ structure at offset={offset}")
                        return None
                    return data
                logger.warning(f"No __NEXT_DATA__ at offset={offset}")
                return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** (attempt + 2)
                logger.warning(f"Rate limited (429) at offset={offset}, retrying in {wait}s")
                time.sleep(wait)
            elif e.response.status_code >= 500 and attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"Server error at offset={offset}, retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"HTTP {e.response.status_code} at offset={offset}: fatal")
                return None
        except Exception as e:
            wait = 2 ** attempt
            logger.error(f"Fetch failed at offset={offset} (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(wait)

    return None


def _extract(data: Dict) -> Tuple[List[Dict], int]:
    try:
        inv = data["props"]["pageProps"]["inventory"]
        return inv.get("results") or [], inv.get("meta", {}).get("total", 0)
    except (KeyError, TypeError):
        return [], 0


def deduplicate_by_vin(dealer_buckets: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
    """Remove cross-dealer VIN duplicates. Keeps vehicle at lowest dealer_id."""
    seen_vins: Dict[str, int] = {}
    cleaned: Dict[int, List[Dict]] = {did: [] for did in dealer_buckets}

    for dealer_id in sorted(dealer_buckets.keys()):
        for vehicle in dealer_buckets[dealer_id]:
            vin = vehicle.get("vin", "")
            if not vin:
                cleaned[dealer_id].append(vehicle)
                continue
            if vin in seen_vins:
                logger.debug(
                    f"Duplicate VIN {vin}: dealer {seen_vins[vin]} (kept) "
                    f"vs dealer {dealer_id} (dropped)"
                )
            else:
                seen_vins[vin] = dealer_id
                cleaned[dealer_id].append(vehicle)

    return cleaned


def deduplicate_within_dealer(vehicles: List[Dict]) -> List[Dict]:
    """Remove duplicate stock numbers within a single dealer."""
    seen: set = set()
    result = []
    for v in vehicles:
        stock = v.get("stock_number", "")
        if stock in seen:
            logger.warning(f"Duplicate stock# {stock} within dealer — dropping duplicate")
            continue
        if stock:
            seen.add(stock)
        result.append(v)
    return result


def scrape_all_locations(
    dealer_ids: Optional[Set[int]] = None,
    timeout_per_page: float = 45.0,
    page_delay: float = 0.3,
) -> Tuple[Dict[int, List[Dict]], str]:
    """
    Scrape all ALM locations in a single pagination pass.
    Returns dict mapping dealer_id -> list of normalized vehicle dicts.
    """
    collect_all = dealer_ids is None
    dealer_buckets: Dict[int, List[Dict]] = {}
    if dealer_ids:
        for did in dealer_ids:
            dealer_buckets[did] = []

    offset = 0
    total_global: Optional[int] = None
    pages_fetched = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3
    start_time = time.time()

    logger.info(f"Scraping {'ALL' if collect_all else len(dealer_ids)} dealer(s), page_size={PAGE_SIZE}")

    while True:
        data = _fetch_page(offset=offset, timeout=timeout_per_page)

        if not data:
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(f"Aborting: {MAX_CONSECUTIVE_ERRORS} consecutive failures")
                break
            time.sleep(2 ** consecutive_errors)
            continue

        consecutive_errors = 0
        results, total = _extract(data)

        if total_global is None:
            total_global = total
            logger.info(f"Total Overfuel inventory: {total} vehicles")

        if not results:
            break

        for v in results:
            did = v.get("dealer_id")
            if did is None:
                continue
            if collect_all or did in dealer_ids:
                if did not in dealer_buckets:
                    dealer_buckets[did] = []
                normalized = normalize_vehicle(v)
                if _validate_vehicle(normalized):
                    dealer_buckets[did].append(normalized)

        pages_fetched += 1
        offset += len(results)

        if pages_fetched % 5 == 0:
            total_collected = sum(len(vs) for vs in dealer_buckets.values())
            logger.info(f"Page {pages_fetched}: offset={offset}/{total_global}, collected={total_collected}")

        if total_global and offset >= total_global:
            break

        if page_delay > 0:
            time.sleep(page_delay)

    # Deduplication passes
    dealer_buckets = deduplicate_by_vin(dealer_buckets)
    for did in dealer_buckets:
        dealer_buckets[did] = deduplicate_within_dealer(dealer_buckets[did])

    total_collected = sum(len(vs) for vs in dealer_buckets.values())
    elapsed = time.time() - start_time
    logger.info(
        f"Scrape done: {total_collected} vehicles from {len(dealer_buckets)} dealers, "
        f"{pages_fetched} pages in {elapsed:.1f}s"
    )

    if total_collected == 0:
        logger.warning("0 vehicles collected — verify dealer_ids and site structure")
        return {}, "no_results"

    return dealer_buckets, "httpx_multi_dealer"


def scrape_single_dealer(dealer_id: int, dealer_name: str = "") -> Tuple[List[Dict], str]:
    """
    Convenience wrapper: scrape a single dealer by paginating all inventory.
    Used for targeted manual re-scrapes and integration tests.
    """
    logger.info(f"Single-dealer scrape: dealer_id={dealer_id} name='{dealer_name}'")
    result, method = scrape_all_locations(dealer_ids={dealer_id})
    vehicles = result.get(dealer_id, [])
    logger.info(f"Single-dealer scrape complete: {len(vehicles)} vehicles for dealer {dealer_id}")
    return vehicles, method


# Backward compatibility shim — allows existing code that calls scrape_all_vehicles() to still work
def scrape_all_vehicles(dealer_id: int = 323) -> Tuple[List[Dict], str]:
    """
    DEPRECATED: Single-dealer scrape for backward compatibility.
    New code should call scrape_all_locations() or scrape_single_dealer().
    """
    import warnings
    warnings.warn(
        "scrape_all_vehicles() is deprecated. Use scrape_single_dealer() or scrape_all_locations().",
        DeprecationWarning,
        stacklevel=2
    )
    return scrape_single_dealer(dealer_id)
```

---

## 9. Testing the Pipeline

### Unit Tests for scraper.py

```python
# File: /Users/emadsiddiqui/ALM/backend/tests/test_scraper.py

import pytest
from unittest.mock import patch, MagicMock
from scraper import (
    normalize_vehicle, _clean_price, _clean_mileage, _validate_vehicle,
    deduplicate_by_vin, deduplicate_within_dealer, scrape_all_locations,
)

def make_raw_vehicle(dealer_id=323, stock="P12345", vin="1HGCM82633A123456"):
    return {
        "dealer_id": dealer_id,
        "dealer": {"name": f"ALM Dealer {dealer_id}"},
        "stocknumber": stock,
        "vin": vin,
        "year": 2022,
        "make": "Toyota",
        "model": "Camry",
        "trim": "XSE",
        "price": "28500",
        "mileage": "15000",
        "exteriorcolor": "Silver",
        "body": "Sedan",
        "condition": "used",
        "fuel": "Gasoline",
        "slug": "2022-toyota-camry-xse",
    }

class TestNormalizeVehicle:
    def test_basic_normalization(self):
        raw = make_raw_vehicle()
        result = normalize_vehicle(raw)
        assert result["stock_number"] == "P12345"
        assert result["dealer_id"] == 323
        assert result["location_name"] == "ALM Dealer 323"
        assert result["price"] == 28500.0
        assert result["mileage"] == 15000
        assert result["body_style"] == "Sedan"
        assert result["fuel_type"] == "Gasoline"

    def test_image_url_scheme_fix(self):
        raw = make_raw_vehicle()
        raw["featuredphoto"] = "//cdn.example.com/image.jpg"
        result = normalize_vehicle(raw)
        assert result["image_url"].startswith("https://")

    def test_listing_url_from_slug(self):
        raw = make_raw_vehicle()
        raw["slug"] = "2022-toyota-camry-xse"
        result = normalize_vehicle(raw)
        assert "almcars.com/inventory/2022-toyota-camry-xse" in result["listing_url"]

    def test_empty_dealer_dict(self):
        raw = make_raw_vehicle()
        raw["dealer"] = {}
        result = normalize_vehicle(raw)
        assert result["location_name"] == ""

class TestCleanPrice:
    def test_string_with_dollar_sign(self):
        assert _clean_price("$28,500") == 28500.0

    def test_none_returns_none(self):
        assert _clean_price(None) is None

    def test_int_input(self):
        assert _clean_price(25000) == 25000.0

class TestValidateVehicle:
    def test_valid_vehicle(self):
        v = normalize_vehicle(make_raw_vehicle())
        assert _validate_vehicle(v) is True

    def test_empty_stock_number_rejected(self):
        v = normalize_vehicle(make_raw_vehicle(stock=""))
        assert _validate_vehicle(v) is False

    def test_negative_price_nullified(self):
        v = normalize_vehicle(make_raw_vehicle())
        v["price"] = -500.0
        _validate_vehicle(v)
        assert v["price"] is None

class TestDeduplication:
    def test_cross_dealer_vin_dedup(self):
        buckets = {
            323: [normalize_vehicle(make_raw_vehicle(dealer_id=323, vin="SAMEVIN"))],
            401: [normalize_vehicle(make_raw_vehicle(dealer_id=401, stock="Q99", vin="SAMEVIN"))],
        }
        result = deduplicate_by_vin(buckets)
        assert len(result[323]) == 1  # Kept (lower dealer_id)
        assert len(result[401]) == 0  # Dropped

    def test_empty_vin_not_deduped(self):
        buckets = {
            323: [normalize_vehicle(make_raw_vehicle(dealer_id=323, vin=""))],
            401: [normalize_vehicle(make_raw_vehicle(dealer_id=401, stock="Q99", vin=""))],
        }
        result = deduplicate_by_vin(buckets)
        assert len(result[323]) == 1
        assert len(result[401]) == 1  # Both kept — no VIN to compare

    def test_within_dealer_stock_dedup(self):
        vehicles = [
            normalize_vehicle(make_raw_vehicle(stock="SAME123")),
            normalize_vehicle(make_raw_vehicle(stock="SAME123")),  # duplicate
        ]
        result = deduplicate_within_dealer(vehicles)
        assert len(result) == 1

@patch("scraper._fetch_page")
class TestScrapeAllLocations:
    def test_buckets_by_dealer(self, mock_fetch):
        mock_data = {
            "props": {"pageProps": {"inventory": {
                "results": [
                    make_raw_vehicle(dealer_id=323, stock="A1"),
                    make_raw_vehicle(dealer_id=401, stock="B1"),
                    make_raw_vehicle(dealer_id=323, stock="A2"),
                ],
                "meta": {"total": 3}
            }}}
        }
        mock_fetch.return_value = mock_data
        result, method = scrape_all_locations(dealer_ids={323, 401})
        assert len(result[323]) == 2
        assert len(result[401]) == 1
        assert method == "httpx_multi_dealer"

    def test_filters_to_requested_dealers(self, mock_fetch):
        mock_data = {
            "props": {"pageProps": {"inventory": {
                "results": [
                    make_raw_vehicle(dealer_id=323, stock="A1"),
                    make_raw_vehicle(dealer_id=999, stock="C1"),  # not in requested set
                ],
                "meta": {"total": 2}
            }}}
        }
        mock_fetch.return_value = mock_data
        result, _ = scrape_all_locations(dealer_ids={323})
        assert 323 in result
        assert 999 not in result

    def test_handles_page_fetch_failure(self, mock_fetch):
        mock_fetch.side_effect = [None, None, None]  # All pages fail
        result, method = scrape_all_locations(dealer_ids={323})
        assert result == {}
        assert method == "no_results"
```

---

## 10. Pipeline Monitoring Checklist

After implementing the multi-location pipeline, verify the following on first run:

- [ ] All 24 dealers are represented in `dealer_buckets` output (even those with 0 vehicles)
- [ ] Total vehicle count matches Overfuel's `meta.total` within 5% (expected: ~6,898)
- [ ] No dealer has unexpectedly high count (>1,000) — would indicate duplicate records
- [ ] Scrape completes in under 2 minutes
- [ ] HTTP 429 rate limit response: NOT seen in logs (if seen, increase `page_delay`)
- [ ] Deduplication removed 0 VINs (expected for normal run; >0 indicates data quality issue)
- [ ] All new vehicles have non-null `dealer_id` in the database
- [ ] `dealers.last_scraped` updated for all 24 dealers after run

---

**Data pipeline designed by**: Data Engineer agent (engineering-ai-engineer)
**References**: ARCHITECTURE.md (data model), SPRINT.md (task context)
**Next step**: API Tester (Step 4) writes comprehensive test suite for all endpoints
