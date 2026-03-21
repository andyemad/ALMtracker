# ALM Inventory Tracker — 24-Location Expansion Sprint Plan

**Created:** 2026-03-10
**Updated:** 2026-03-10 (AgentsOrchestrator pipeline review)
**Author:** Sprint Prioritizer Agent (product-sprint-prioritizer)
**Scope:** Expand from single-location (ALM Mall of Georgia, dealer_id=323) to all 24 ALM dealerships
**Current State:** 276 vehicles from 1 dealer | FastAPI + SQLite + React/Vite

---

## Executive Summary

The current system is purpose-built for a single dealer. Expanding to 24 locations requires
changes across every layer of the stack: the data model needs a location dimension, the scraper
must discover and iterate all dealer IDs, the API needs location-aware filtering, and the frontend
must expose multi-location navigation and cross-location analytics. The work is decomposed into
four sprints totaling roughly 34 story points, ordered so each sprint ships usable, tested
increments rather than holding everything until the end.

**RICE Scoring Summary (top items):**
| Task | Reach | Impact | Confidence | Effort | RICE Score |
|---|---|---|---|---|---|
| Dealer registry + discovery | 24 locations | 3.0 | 0.90 | 1.5 | 43.2 |
| Vehicle model — dealer_id FK | 24 locations | 3.0 | 0.95 | 0.5 | 136.8 |
| Scraper refactor — multi-dealer | 24 locations | 3.0 | 0.85 | 2.0 | 30.6 |
| Location filter in API | 24 locations | 2.5 | 0.90 | 0.5 | 108.0 |
| Location selector — frontend | 24 locations | 2.5 | 0.85 | 1.0 | 51.0 |

---

## Dependency Map

```
[S1-1] Dealer Registry
      |
      +---> [S1-2] DB Migration (dealer_id FK on vehicles)
                  |
                  +---> [S1-3] Scraper Refactor
                  |           |
                  |           +---> [S2-1] Scheduler Parallelism
                  |           +---> [S2-2] Per-dealer ScrapeLog
                  |
                  +---> [S1-4] API location params
                              |
                              +---> [S2-3] Stats per-location
                              +---> [S3-1] Frontend location selector
                              +---> [S3-2] Location overview page
                              +---> [S3-3] Cross-location inventory view
```

---

## Sprint 0 — Discovery & Prep (Pre-Work, 1–2 days)

> These tasks are not story-pointed; they are prerequisite research that informs estimates.
> Complete before Sprint 1 planning.

### S0-1: Dealer ID Discovery
**Goal:** Enumerate all 24 ALM dealer IDs from the Overfuel `__NEXT_DATA__` payload.
**Method:**
1. Fetch `https://www.almcars.com/inventory?limit=500&offset=0` and parse `__NEXT_DATA__`.
2. Extract all unique `dealer_id` + `dealer.name` pairs from `props.pageProps.inventory.results`.
3. Paginate through all ~14 pages (total ~6,898 vehicles) and collect the full set.
4. Record in a static Python dict: `DEALER_REGISTRY = {dealer_id: {"name": ..., "city": ...}}`.

**Output:** Populated `DEALER_REGISTRY` constant ready for Sprint 1 implementation.
**Owner:** Backend engineer
**Time:** 2–4 hours

### S0-2: Volume Baseline
**Goal:** Understand per-dealer vehicle counts to size DB growth and estimate scrape time.
**Method:** Run the discovery script, group vehicle counts by dealer_id, compute totals.
**Output:** Spreadsheet or table: dealer_id, name, vehicle count. Confirm ~6,898 total vs 276 current.
**Owner:** Backend engineer
**Time:** 1–2 hours

### S0-3: Overfuel Field Validation
**Goal:** Confirm `dealer_id` field is present and stable across all pages and all dealer types.
**Method:** Spot-check 3–5 pages, verify dealer_id is populated on every vehicle object.
**Output:** Go/no-go confirmation for the scraper filter strategy.
**Owner:** Backend engineer
**Time:** 1 hour

---

## Sprint 1 — Foundation (Data Model + Scraper Core)

**Sprint Goal:** The database correctly stores vehicles with dealer attribution, and the scraper
can ingest all 24 dealers' inventory in a single run without breaking the existing Mall of Georgia data.

**Capacity:** 10 story points | **Duration:** 1 week

---

### S1-1: Dealer Registry Model
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S0-1 (discovery complete)

**Description:**
Add a `Dealer` table to `models.py` to be the authoritative source for all ALM locations.
This replaces the hard-coded `DEALER_ID = 323` and `DEALER_NAME` constants in `scraper.py`.

**File:** `/Users/emadsiddiqui/ALM/backend/models.py`

New SQLAlchemy model to add:
```python
class Dealer(Base):
    __tablename__ = "dealers"

    id = Column(Integer, primary_key=True)          # Overfuel dealer_id (e.g. 323)
    name = Column(String, nullable=False)            # "ALM Mall of Georgia"
    city = Column(String, nullable=True)             # "Buford"
    state = Column(String, nullable=True, default="GA")
    is_active = Column(Boolean, default=True)        # scrape this dealer?
    scrape_priority = Column(Integer, default=1)     # lower = scrape first
    created_at = Column(DateTime, default=datetime.utcnow)
    last_scraped = Column(DateTime, nullable=True)
```

**Seed data:** Populated from S0-1 discovery output. Insert via an Alembic migration seed
or a one-time `seed_dealers()` startup function that is idempotent (skips if rows exist).

**Acceptance Criteria:**
- [ ] `dealers` table created on app startup via `Base.metadata.create_all`
- [ ] All 24 dealers seeded with correct `dealer_id`, `name`, `city`
- [ ] `is_active=True` for all 24 by default
- [ ] Existing vehicles table unchanged at this point
- [ ] `GET /api/dealers` endpoint returns all dealers (read-only, list)
- [ ] Idempotent seed: running startup twice does not duplicate rows

---

### S1-2: Database Migration — Add dealer_id to Vehicles
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S1-1

**Description:**
Add `dealer_id` (FK to `dealers.id`) and `location_name` (denormalized string for query
performance) to the `Vehicle` model. Add `dealer_id` to `VehicleEvent` and `ScrapeLog` for
full traceability. Migrate the existing 276 MoG records to `dealer_id=323`.

**File:** `/Users/emadsiddiqui/ALM/backend/models.py`

Changes to `Vehicle`:
```python
dealer_id = Column(Integer, ForeignKey("dealers.id"), nullable=True, index=True)
location_name = Column(String, nullable=True, index=True)   # denormalized for speed
```

Changes to `VehicleEvent`:
```python
dealer_id = Column(Integer, nullable=True, index=True)
location_name = Column(String, nullable=True)
```

Changes to `ScrapeLog`:
```python
dealer_id = Column(Integer, nullable=True, index=True)
location_name = Column(String, nullable=True)
vehicles_scraped = Column(Integer, default=0)   # rename from vehicles_found for clarity
```

**Migration strategy (SQLite — no Alembic required initially):**
Since SQLite does not support `ALTER TABLE ADD COLUMN ... NOT NULL` without a default,
use nullable columns with a post-migration UPDATE:
```sql
UPDATE vehicles SET dealer_id = 323, location_name = 'ALM Mall of Georgia'
WHERE dealer_id IS NULL;
```
Run this in a startup migration guard in `database.py`.

**File:** `/Users/emadsiddiqui/ALM/backend/database.py`

Add a `run_migrations()` function called on startup that:
1. Checks if `dealer_id` column exists on `vehicles` (via `PRAGMA table_info`)
2. If not, executes the ALTER TABLE and UPDATE statements
3. Logs the migration result

**Acceptance Criteria:**
- [ ] All existing 276 vehicles have `dealer_id=323` and `location_name='ALM Mall of Georgia'`
- [ ] New vehicles created by scraper include `dealer_id` and `location_name`
- [ ] `VehicleEvent` records include `dealer_id`
- [ ] `ScrapeLog` records include `dealer_id` and `location_name`
- [ ] SQLite migration is idempotent (safe to re-run on existing DB)
- [ ] No data loss in existing records

---

### S1-3: Scraper Refactor — Multi-Dealer Architecture
**Priority:** P0
**Effort:** 3 points (~1.5 days)
**Dependencies:** S1-1, S1-2

**Description:**
Refactor `scraper.py` to accept an iterable of dealer configs and scrape all of them
in a single pass through the paginated Overfuel inventory. The current approach already
fetches all ~6,898 vehicles and filters to `dealer_id=323`; extend this to collect
vehicles for all registered dealers simultaneously.

**File:** `/Users/emadsiddiqui/ALM/backend/scraper.py`

Key architectural changes:
1. Remove the `DEALER_ID = 323` and `DEALER_NAME` module-level constants.
2. Add `DealerConfig` named tuple or dataclass:
   ```python
   from dataclasses import dataclass
   @dataclass
   class DealerConfig:
       dealer_id: int
       name: str
       city: str = ""
   ```
3. Refactor `scrape_all_vehicles()` signature to:
   ```python
   def scrape_all_vehicles(
       dealers: List[DealerConfig] | None = None
   ) -> Tuple[Dict[int, List[Dict]], str]:
       """
       Returns a dict mapping dealer_id -> list of normalized vehicles.
       If dealers is None, uses all active dealers from the registry.
       """
   ```
4. In the pagination loop, bucket each scraped vehicle into its dealer's list:
   ```python
   for v in results:
       did = v.get("dealer_id")
       if did in dealer_set:
           dealer_buckets[did].append(normalize_vehicle(v))
   ```
5. `normalize_vehicle()` already extracts `dealer_id` and `location_name` — verify
   these are correctly populated from the Overfuel `dealer` dict for all locations.
6. Return value changes from `(List[Dict], str)` to `(Dict[int, List[Dict]], str)`.
7. Add a `scrape_single_dealer(dealer_id: int) -> List[Dict]` convenience wrapper
   for targeted re-scrapes and testing.

**Acceptance Criteria:**
- [ ] Single HTTP pagination pass collects all dealers simultaneously (no N*14 page fetches)
- [ ] Returns per-dealer bucketed results: `{323: [...], 401: [...], ...}`
- [ ] `scrape_single_dealer(323)` returns only MoG vehicles (backward-compat test)
- [ ] `normalize_vehicle()` correctly populates `dealer_id` and `location_name` for 5+ tested dealers
- [ ] Scrape of all 24 dealers completes in under 90 seconds (target: match current ~60s single-dealer)
- [ ] Logging shows per-dealer counts: `"ALM Mall of Georgia: 276 vehicles"`
- [ ] Graceful handling if a dealer has 0 vehicles (new store, no inventory yet)

---

### S1-4: main.py — Update run_scrape() for Multi-Dealer
**Priority:** P0
**Effort:** 3 points (~1.5 days)
**Dependencies:** S1-2, S1-3

**Description:**
Update the core `run_scrape()` function in `main.py` to process the new multi-dealer
return format. The change detection logic (additions, removals, price changes) must now
operate per-dealer to avoid cross-location stock number collisions.

**Critical bug to prevent:** Stock numbers are NOT globally unique across ALM locations.
Two dealers can have the same stock number. The uniqueness key must change from
`stock_number` alone to `(dealer_id, stock_number)`.

**File:** `/Users/emadsiddiqui/ALM/backend/main.py`

Changes:
1. Update `run_scrape()` to call the new `scrape_all_vehicles()` and iterate over
   the returned `{dealer_id: vehicles}` dict.
2. Change the `active_map` key from `stock_number` to `(dealer_id, stock_number)`:
   ```python
   active_map = {
       (v.dealer_id, v.stock_number): v
       for v in db.query(models.Vehicle)
           .filter(models.Vehicle.is_active == True)
           .all()
   }
   ```
3. For each dealer, run additions/removals/price-change detection independently.
4. Each `ScrapeLog` record now includes `dealer_id`. Create one aggregate log per
   full scrape run plus per-dealer sub-logs (or a single log with a JSON summary
   field). Recommended: single aggregate log for now, with `dealer_id=None` meaning
   "all dealers", plus per-dealer counts in a new `details` JSON column.
5. Update `Vehicle` uniqueness: change the `stock_number` unique constraint
   to a composite unique constraint `(dealer_id, stock_number)`.

**File:** `/Users/emadsiddiqui/ALM/backend/models.py`
```python
from sqlalchemy import UniqueConstraint
class Vehicle(Base):
    ...
    __table_args__ = (
        UniqueConstraint("dealer_id", "stock_number", name="uq_dealer_stock"),
    )
```

**Acceptance Criteria:**
- [ ] Full scrape of all 24 dealers runs without error
- [ ] Existing 276 MoG vehicles are not duplicated or incorrectly flagged as removed
- [ ] Stock number collisions across dealers are handled correctly (vehicle from dealer A
      with stock# "12345" is distinct from dealer B's "12345")
- [ ] VehicleEvents are created with correct `dealer_id`
- [ ] ScrapeLog records `total` vehicle count across all dealers plus per-dealer breakdown
- [ ] Price change detection still works within a single dealer's vehicles
- [ ] `GET /api/stats` still returns correct numbers (update query to sum across all active dealers)

---

## Sprint 2 — API & Scheduler Hardening

**Sprint Goal:** The API is fully location-aware. Operators can query any single location or
all locations. The scheduler handles 24-location scrapes reliably with per-dealer logging.

**Capacity:** 10 story points | **Duration:** 1 week

---

### S2-1: Concurrent Scraping with Per-Dealer Scheduling
**Priority:** P1
**Effort:** 3 points (~1.5 days)
**Dependencies:** S1-3, S1-4

**Description:**
The current scheduler fires a single `run_scrape()` every 6 hours. With 24 dealers and
~6,900 vehicles across ~14 pages, one full scrape run is acceptable (all dealers are
collected in a single pagination pass). However, we need to add resilience for partial
failures and optionally allow staggered per-dealer scheduling.

**File:** `/Users/emadsiddiqui/ALM/backend/main.py`

Changes:
1. Add `run_scrape_for_dealer(dealer_id: int, db: Session)` that calls
   `scrape_single_dealer()` and runs change detection for just that dealer.
   Used for manual re-scrapes and future per-dealer scheduling.
2. Keep the existing 6-hour full-scrape job as the primary schedule.
3. Add retry logic: if the full scrape fails, retry after 15 minutes (max 3 attempts).
4. Add a `scrape_timeout` guard: if scrape exceeds 5 minutes, log error and abort.
5. Update `POST /api/scrape/trigger` to accept an optional `dealer_id` body param
   to trigger a single-dealer scrape.
6. Store per-dealer vehicle counts in `ScrapeLog.details` as JSON:
   ```json
   {"dealers": [{"id": 323, "name": "MoG", "found": 276, "added": 2, "removed": 1}]}
   ```

**Acceptance Criteria:**
- [ ] Full 24-dealer scrape completes reliably every 6 hours
- [ ] Failed scrape retries automatically after 15 minutes (up to 3 times)
- [ ] `POST /api/scrape/trigger` with `{"dealer_id": 323}` scrapes only MoG
- [ ] `POST /api/scrape/trigger` with no body scrapes all dealers
- [ ] Scrape timeout of 5 minutes prevents hung jobs
- [ ] Per-dealer counts visible in ScrapeLog details
- [ ] Scheduler does not stack jobs (replace_existing=True already set — verify)

---

### S2-2: API — Location-Aware Filtering
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S1-2, S1-4

**Description:**
Add `dealer_id` and `location_name` as filter parameters to the vehicle list and
stats endpoints. Add a `GET /api/dealers` endpoint for the frontend location selector.

**File:** `/Users/emadsiddiqui/ALM/backend/main.py`

Changes to `GET /api/vehicles`:
```python
dealer_id: Optional[int] = None,
location_name: Optional[str] = None,
```
Filter logic:
```python
if dealer_id:
    q = q.filter(models.Vehicle.dealer_id == dealer_id)
if location_name:
    q = q.filter(models.Vehicle.location_name.ilike(f"%{location_name}%"))
```

Changes to `GET /api/stats`:
```python
dealer_id: Optional[int] = None,
```
When `dealer_id` is provided, all counts (`total_active`, `added_today`, etc.) are
scoped to that dealer. When omitted, aggregate across all dealers.

Add `location_name` to `_vehicle_dict()` and `_event_dict()` response serializers.

New endpoint `GET /api/dealers`:
```python
@app.get("/api/dealers")
def list_dealers(db: Session = Depends(get_db), active_only: bool = True):
    q = db.query(models.Dealer)
    if active_only:
        q = q.filter(models.Dealer.is_active == True)
    dealers = q.order_by(models.Dealer.name).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "city": d.city,
            "state": d.state,
            "is_active": d.is_active,
            "last_scraped": d.last_scraped.isoformat() if d.last_scraped else None,
        }
        for d in dealers
    ]
```

New endpoint `GET /api/dealers/{dealer_id}/stats`:
Returns the same structure as `/api/stats` but scoped to one dealer.

Changes to `GET /api/events`:
Add `dealer_id: Optional[int] = None` filter.

Changes to `GET /api/filter-options`:
Add `dealer_id: Optional[int] = None` — when provided, makes/body styles are scoped
to that dealer's active inventory.

Changes to `GET /api/vehicles/export`:
Add `dealer_id: Optional[int] = None` — export scoped to one dealer or all.
Add `location_name` column to CSV output.

**Acceptance Criteria:**
- [ ] `GET /api/vehicles?dealer_id=323` returns only MoG vehicles
- [ ] `GET /api/vehicles` (no dealer_id) returns all 24 dealers' vehicles
- [ ] `GET /api/stats?dealer_id=323` returns MoG-specific counts
- [ ] `GET /api/stats` (no dealer_id) returns aggregate across all dealers
- [ ] `GET /api/dealers` returns all 24 dealers with correct metadata
- [ ] `GET /api/dealers/323/stats` returns MoG-specific stats
- [ ] `GET /api/filter-options?dealer_id=323` returns only MoG makes/body styles
- [ ] `GET /api/vehicles/export` CSV includes `location_name` column
- [ ] `GET /api/vehicles/export?dealer_id=323` exports only MoG vehicles
- [ ] All existing API tests still pass (no regressions)

---

### S2-3: Watchlist — Location Scope
**Priority:** P1
**Effort:** 1 point (~0.5 days)
**Dependencies:** S2-2

**Description:**
Watchlist alerts currently match against all active vehicles. Add an optional
`dealer_id` field to `WatchlistAlert` so a user can create an alert scoped to
a specific location (e.g., "Notify me when a used BMW under $30k lands at MoG").

**File:** `/Users/emadsiddiqui/ALM/backend/models.py`
```python
class WatchlistAlert(Base):
    ...
    dealer_id = Column(Integer, nullable=True)  # None = all locations
    location_name = Column(String, nullable=True)
```

**File:** `/Users/emadsiddiqui/ALM/backend/alerts.py`

Update `vehicle_matches_alert()` to check `dealer_id` constraint:
```python
if a.dealer_id is not None and v.dealer_id != a.dealer_id:
    return False
```

Update `get_matching_vehicles()` to pre-filter by `dealer_id` before iterating.

Update `_alert_dict()` in `main.py` to include `dealer_id` and `location_name`.

Update `POST /api/watchlist` and `PUT /api/watchlist/{id}` to accept `dealer_id`.

**Acceptance Criteria:**
- [ ] Existing watchlist alerts (dealer_id=None) still match across all locations
- [ ] New alert with `dealer_id=323` only matches MoG vehicles
- [ ] Email notifications identify the specific location in the subject and body
- [ ] `match_count` in watchlist response correctly respects dealer scope
- [ ] Migration: existing alerts get `dealer_id=NULL` (match all) — no data change needed

---

### S2-4: Lead Matching — Location Awareness
**Priority:** P1
**Effort:** 1 point (~0.5 days)
**Dependencies:** S2-2

**Description:**
`GET /api/leads/{id}/matches` currently returns up to 10 matching vehicles from all
locations. Add optional `dealer_id` scoping and add `location_name` to match results
so sales staff know which lot to direct the customer to.

**File:** `/Users/emadsiddiqui/ALM/backend/main.py`

Update `lead_matches()`:
```python
@app.get("/api/leads/{lead_id}/matches")
def lead_matches(
    lead_id: int,
    dealer_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
```
Add `dealer_id` filter to the query when provided.
Include `location_name` in the returned vehicle dicts.

**Acceptance Criteria:**
- [ ] `GET /api/leads/5/matches` returns matches from all locations
- [ ] `GET /api/leads/5/matches?dealer_id=323` returns only MoG matches
- [ ] Each matched vehicle in the response includes `dealer_id` and `location_name`
- [ ] Existing lead matching logic (make/model/budget) unchanged

---

### S2-5: ScrapeLog — Per-Dealer Detail View
**Priority:** P2
**Effort:** 1 point (~0.5 days)
**Dependencies:** S1-4, S2-2

**Description:**
Add `GET /api/scrape-logs?dealer_id={id}` filtering and surface per-dealer breakdown
from the `details` JSON column in the ScrapeLog API response.

**File:** `/Users/emadsiddiqui/ALM/backend/main.py`

Update `list_scrape_logs()`:
```python
def list_scrape_logs(
    db: Session = Depends(get_db),
    limit: int = 20,
    dealer_id: Optional[int] = None,
):
```

Update `_log_dict()` to include `details` field (parsed JSON or None).

**Acceptance Criteria:**
- [ ] `GET /api/scrape-logs` returns aggregate logs with `details` breakdown
- [ ] `GET /api/scrape-logs?dealer_id=323` returns logs for MoG specifically
- [ ] `details` field in response contains per-dealer vehicle counts

---

## Sprint 3 — Frontend: Multi-Location UI

**Sprint Goal:** Users can browse inventory by location, compare locations side-by-side on the
dashboard, and the UI clearly communicates which dealer's data is in view at all times.

**Capacity:** 10 story points | **Duration:** 1 week

---

### S3-1: Global Location Selector (Context + Sidebar)
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S2-2

**Description:**
Add a React context (`LocationContext`) that holds the currently selected dealer.
The Sidebar gains a location dropdown. All pages read from this context to scope their API calls.

**Files:**
- New: `/Users/emadsiddiqui/ALM/frontend/src/context/LocationContext.tsx`
- Modified: `/Users/emadsiddiqui/ALM/frontend/src/components/Sidebar.tsx`
- Modified: `/Users/emadsiddiqui/ALM/frontend/src/api.ts`
- Modified: `/Users/emadsiddiqui/ALM/frontend/src/types.ts`

New `Dealer` type in `types.ts`:
```typescript
export interface Dealer {
  id: number
  name: string
  city: string | null
  state: string | null
  is_active: boolean
  last_scraped: string | null
}
```

New API call in `api.ts`:
```typescript
export const getDealers = () =>
  api.get<Dealer[]>('/dealers').then(r => r.data)
```

`LocationContext.tsx` pattern:
```typescript
interface LocationContextValue {
  dealers: Dealer[]
  selectedDealer: Dealer | null   // null = "All Locations"
  setSelectedDealer: (d: Dealer | null) => void
}
```

Sidebar changes:
- Below the logo area, add a `<select>` or custom dropdown showing all 24 dealers
  plus an "All Locations" option at the top.
- Selected dealer name replaces "Mall of Georgia" in the logo subtitle.
- Persist selection in `localStorage` across page refreshes.

**Acceptance Criteria:**
- [ ] Sidebar displays a location selector with all 24 dealers
- [ ] "All Locations" is the default selection
- [ ] Selecting a dealer updates the global context
- [ ] Selection persists after browser refresh (localStorage)
- [ ] Sidebar subtitle reflects the currently selected location
- [ ] Location selector is visually distinct and does not clutter the sidebar

---

### S3-2: Dashboard — Location-Aware Stats
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S3-1, S2-2

**Description:**
Update the Dashboard page to pass the selected `dealer_id` to all API calls.
When "All Locations" is selected, show aggregate stats with a location breakdown table.

**File:** `/Users/emadsiddiqui/ALM/frontend/src/pages/Dashboard.tsx`

Changes:
1. Consume `LocationContext` to get `selectedDealer`.
2. Pass `dealer_id: selectedDealer?.id` to `getStats()`, `getEvents()`, `getScrapeLogs()`.
3. Update the page header subtitle:
   - "All Locations — 24 stores, live inventory intel" (when All Locations)
   - "ALM Buckhead — live inventory intel" (when specific dealer selected)
4. When "All Locations" is selected, add a new "By Location" breakdown section showing
   a bar chart of vehicle counts per dealer (data from a new `GET /api/dealers` call
   that includes vehicle counts — see S2-2 extension).
5. The inventory trend chart title updates to reflect the scope.

New API extension needed (add to S2-2 or as a separate task):
`GET /api/dealers` should include `active_vehicle_count` per dealer for the bar chart.
Add this to the `list_dealers()` response:
```python
"active_vehicle_count": db.query(models.Vehicle)
    .filter(models.Vehicle.dealer_id == d.id, models.Vehicle.is_active == True)
    .count()
```

**Acceptance Criteria:**
- [ ] Dashboard stats (total, added today, removed today, avg price) reflect selected location
- [ ] Trend chart data is scoped to selected location
- [ ] Activity feed events are scoped to selected location
- [ ] "All Locations" view shows a per-dealer vehicle count bar chart
- [ ] Dashboard header subtitle reflects currently selected location
- [ ] Stats load without error for any of the 24 dealers
- [ ] Switching locations triggers a data reload within 500ms

---

### S3-3: Inventory Page — Location Filter Integration
**Priority:** P0
**Effort:** 2 points (~1 day)
**Dependencies:** S3-1, S2-2

**Description:**
Update the Inventory page to pass `dealer_id` from the global location context to all
API calls. Add a `Location` column to the vehicle table when "All Locations" is selected.

**File:** `/Users/emadsiddiqui/ALM/frontend/src/pages/Inventory.tsx`

Changes:
1. Consume `LocationContext`.
2. Pass `dealer_id: selectedDealer?.id` to `getVehicles()` and `getFilterOptions()`.
3. When "All Locations" is selected, add a `Location` column to the table:
   ```typescript
   {
     accessorKey: 'location_name',
     header: 'Location',
     size: 160,
     cell: ({ getValue }) => (
       <span className="text-slate-400 text-xs">{getValue() as string || '—'}</span>
     ),
   }
   ```
4. When "All Locations" is selected, add a location filter dropdown to the filter panel
   (in addition to the global selector, for ad-hoc filtering without changing global scope).
5. Update the page subtitle: "276 vehicles · ALM Mall of Georgia" vs "6,898 vehicles · All Locations".
6. Update the Export CSV download URL to include `dealer_id` query param.
7. Reset to page 1 whenever the selected location changes (add `selectedDealer` to the
   `useCallback` dependency array of the `load` function).

**Acceptance Criteria:**
- [ ] Inventory table shows only selected dealer's vehicles when a location is chosen
- [ ] "All Locations" shows all 6,900+ vehicles (paginated)
- [ ] `Location` column appears in the table only when "All Locations" is selected
- [ ] Filter panel includes a per-page location filter when "All Locations" is active
- [ ] Make filter dropdown is scoped to selected location's inventory
- [ ] Export CSV includes `location_name` and respects the selected dealer filter
- [ ] Page count and total vehicle count update correctly on location change
- [ ] Table resets to page 1 on location change

---

### S3-4: Locations Overview Page (New Page)
**Priority:** P1
**Effort:** 2 points (~1 day)
**Dependencies:** S2-2, S3-1

**Description:**
Add a new `/locations` page that gives a bird's-eye view of all 24 ALM locations.
Each location card shows: name, city, active vehicle count, avg price, days since
last scrape, and a mini trend indicator.

**Files:**
- New: `/Users/emadsiddiqui/ALM/frontend/src/pages/Locations.tsx`
- Modified: `/Users/emadsiddiqui/ALM/frontend/src/App.tsx`
- Modified: `/Users/emadsiddiqui/ALM/frontend/src/components/Sidebar.tsx`

New route in `App.tsx`:
```tsx
<Route path="/locations" element={<Locations />} />
```

New nav link in `Sidebar.tsx`:
```typescript
{ to: '/locations', icon: MapPin, label: 'Locations' }
```

`Locations.tsx` layout:
- Grid of 24 location cards (responsive: 1/2/3/4 columns)
- Each card: dealer name, city badge, vehicle count, avg price, last scraped time
- Click on a card sets that dealer as the selected location in context AND navigates to `/inventory`
- Sort controls: by name, by vehicle count, by avg price
- Search/filter bar to narrow by name or city

API calls:
- `GET /api/dealers` (with `active_vehicle_count` from S3-2)
- Optionally batch-fetch per-dealer stats or compute on backend

**Acceptance Criteria:**
- [ ] Locations page accessible via sidebar nav
- [ ] All 24 dealers displayed as cards in a responsive grid
- [ ] Each card shows: name, city, vehicle count, avg list price, last scraped
- [ ] Clicking a card navigates to Inventory filtered to that location
- [ ] Sort by name / vehicle count / avg price works
- [ ] Search input filters visible cards by dealer name or city
- [ ] Cards for dealers with 0 vehicles are visually de-emphasized (not removed)
- [ ] "Last scraped" time shown as relative ("3 hours ago")

---

### S3-5: Activity Page — Location Scoping
**Priority:** P1
**Effort:** 1 point (~0.5 days)
**Dependencies:** S3-1, S2-2

**Description:**
Update the Activity page to pass `dealer_id` from the global location context to the
events API call. When "All Locations" is selected, add a `Location` column to the
activity feed table.

**File:** `/Users/emadsiddiqui/ALM/frontend/src/pages/Activity.tsx`

Changes:
1. Consume `LocationContext`.
2. Pass `dealer_id` to `getEvents()`.
3. Add a `Location` column when "All Locations" is active.
4. Update the page subtitle to reflect location scope.

**Acceptance Criteria:**
- [ ] Activity feed shows events scoped to selected location
- [ ] "All Locations" shows events from all dealers
- [ ] `Location` column visible when "All Locations" is active
- [ ] Event filter (added/removed/price_change) still works in combination with location filter

---

### S3-6: api.ts and types.ts — Location Field Updates
**Priority:** P0
**Effort:** 1 point (~0.5 days)
**Dependencies:** S2-2

**Description:**
Update the TypeScript type definitions and API client to include all new location-related
fields returned by the updated backend.

**File:** `/Users/emadsiddiqui/ALM/frontend/src/types.ts`

Add to `Vehicle`:
```typescript
dealer_id: number | null
location_name: string | null
```

Add to `VehicleEvent`:
```typescript
dealer_id: number | null
location_name: string | null
```

Add new `Dealer` interface (shown in S3-1 above).

Add to `Stats` (for `GET /api/stats?dealer_id=...`):
```typescript
dealer_id: number | null
location_name: string | null
```

Add to `ScrapeLog`:
```typescript
dealer_id: number | null
location_name: string | null
details: object | null
```

**File:** `/Users/emadsiddiqui/ALM/frontend/src/api.ts`

Update `VehicleFilters`:
```typescript
dealer_id?: number
location_name?: string
```

Add `getDealers()` and `getDealerStats(dealerId: number)` functions.

Update `getStats()` to accept optional `dealer_id` param.
Update `getEvents()` to accept optional `dealer_id` param.
Update `getScrapeLogs()` to accept optional `dealer_id` and `limit` params.

**Acceptance Criteria:**
- [ ] TypeScript compiles with no errors after type updates
- [ ] No `any` types introduced
- [ ] All API functions correctly typed for request params and response shapes
- [ ] `getDealers()` returns `Dealer[]`
- [ ] `getDealerStats(323)` returns `Stats` scoped to MoG

---

## Sprint 4 — Polish, Testing & Deployment Hardening

**Sprint Goal:** The 24-location system is stable, tested, observable, and ready for production
use. Performance is validated at scale. The SMTP email feature is configured.

**Capacity:** 4 points (lighter sprint to allow for bug fixes from Sprint 3 feedback)
**Duration:** 3–4 days

---

### S4-1: Performance — Query Optimization & DB Indexes
**Priority:** P0
**Effort:** 1 point (~0.5 days)
**Dependencies:** All Sprint 1 & 2 tasks

**Description:**
With ~6,900 vehicles across 24 dealers, queries that previously ran against 276 rows
now run against a dataset 25x larger. Add indexes and verify query plans.

**File:** `/Users/emadsiddiqui/ALM/backend/models.py`

Verify/add composite indexes on `Vehicle`:
```python
__table_args__ = (
    UniqueConstraint("dealer_id", "stock_number", name="uq_dealer_stock"),
    Index("ix_vehicle_dealer_active", "dealer_id", "is_active"),
    Index("ix_vehicle_make_model", "make", "model"),
    Index("ix_vehicle_price", "price"),
    Index("ix_vehicle_days_on_lot", "days_on_lot"),
)
```

Run query plans (via `EXPLAIN QUERY PLAN` in SQLite) on the most common filters:
- `vehicles?is_active=true` (all active)
- `vehicles?dealer_id=323&is_active=true`
- `vehicles?make=Toyota&dealer_id=323`
- `stats` (aggregate counts)

**Acceptance Criteria:**
- [ ] All listed indexes created
- [ ] `GET /api/vehicles` responds in under 200ms for 6,900-vehicle dataset
- [ ] `GET /api/stats` responds in under 200ms
- [ ] `GET /api/vehicles?dealer_id=323` query plan uses `ix_vehicle_dealer_active` index
- [ ] No full-table scans on filtered vehicle queries

---

### S4-2: Backend Integration Tests
**Priority:** P1
**Effort:** 1 point (~0.5 days)
**Dependencies:** All Sprint 1 & 2 tasks

**Description:**
Add pytest-based integration tests covering the critical multi-location paths.
Use an in-memory SQLite database for test isolation.

**File (new):** `/Users/emadsiddiqui/ALM/backend/tests/test_multi_location.py`

Test cases:
1. `test_scraper_buckets_by_dealer()` — mock HTTP, verify vehicles land in correct dealer bucket
2. `test_stock_collision_isolation()` — same stock# for two dealers creates two separate Vehicle rows
3. `test_change_detection_per_dealer()` — removal in dealer A does not affect dealer B
4. `test_api_vehicles_filter_by_dealer_id()` — `GET /api/vehicles?dealer_id=323` scoped correctly
5. `test_api_stats_aggregate()` — `GET /api/stats` sums across all dealers
6. `test_api_stats_per_dealer()` — `GET /api/stats?dealer_id=323` scoped correctly
7. `test_watchlist_scoped_match()` — alert with dealer_id=323 does not trigger on dealer B vehicles
8. `test_lead_matches_scoped()` — `GET /api/leads/1/matches?dealer_id=323` scoped correctly
9. `test_migration_preserves_existing_vehicles()` — existing vehicles retain dealer_id=323 after migration
10. `test_dealer_registry_seeded()` — all 24 dealers present after startup

**Acceptance Criteria:**
- [ ] All 10 tests pass with `pytest backend/tests/`
- [ ] Tests run against in-memory SQLite (no touching production `alm.db`)
- [ ] Test coverage >= 80% for `main.py`, `scraper.py`, `alerts.py`
- [ ] Tests run in under 30 seconds total

---

### S4-3: SMTP Email Configuration
**Priority:** P1
**Effort:** 0.5 points (~2–3 hours)
**Dependencies:** S2-3

**Description:**
Complete the previously deferred SMTP configuration. The `alerts.py` email function is
already implemented; this task configures the environment and tests delivery.

**File:** `/Users/emadsiddiqui/ALM/backend/.env` (create if not exists)
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_FROM_NAME=ALM Inventory Tracker
```

Update `alerts.py` `_send_email()`:
1. Add `From` display name: `f"{from_name} <{smtp_user}>"`
2. Update email body to include `location_name` for each matched vehicle
3. Update subject line: `[ALM Alert] {alert.name} @ {location} — {count} match(es)`
   (use "All Locations" if alert has no dealer_id)
4. Add HTML email alternative (MIME multipart with simple HTML table for vehicle listings)

**Acceptance Criteria:**
- [ ] Email sent successfully when SMTP credentials are configured
- [ ] Email body includes vehicle location name
- [ ] Email subject identifies the location
- [ ] Graceful no-op when SMTP_USER/SMTP_PASS are empty (existing behavior preserved)
- [ ] HTML email renders correctly in Gmail and Outlook (test with real send)

---

### S4-4: start.sh and Deployment Documentation
**Priority:** P1
**Effort:** 0.5 points (~2–3 hours)
**Dependencies:** All tasks

**Description:**
Update the project startup script and environment documentation for the expanded system.

**File:** `/Users/emadsiddiqui/ALM/start.sh`

Verify the existing start.sh works with no changes (nvm sourcing, backend/frontend startup).
Add an environment validation step that logs a warning if SMTP is not configured.

**File (update):** `/Users/emadsiddiqui/ALM/backend/.env.example`
```
# Required for email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=

# Optional tuning
SCRAPE_INTERVAL_HOURS=6
SCRAPE_TIMEOUT_SECONDS=300
SCRAPE_MAX_RETRIES=3
```

Operational runbook additions:
- How to disable a specific dealer from scraping: set `is_active=False` in `dealers` table
- How to trigger a single-dealer rescrape: `POST /api/scrape/trigger {"dealer_id": 323}`
- How to verify all dealers are seeded: `GET /api/dealers`
- Expected scrape duration at 24 locations: ~90 seconds

**Acceptance Criteria:**
- [ ] `./start.sh` starts the full stack cleanly on a fresh clone
- [ ] `.env.example` documents all supported environment variables
- [ ] Startup logs confirm dealer count: "Seeded 24 dealers"
- [ ] Startup logs confirm migration status: "Migration applied" or "Migration skipped (already applied)"

---

## Full Backlog Summary

| ID | Task | Priority | Points | Sprint | Dependencies |
|---|---|---|---|---|---|
| S0-1 | Dealer ID Discovery | P0 | - | Pre-work | — |
| S0-2 | Volume Baseline | P0 | - | Pre-work | S0-1 |
| S0-3 | Overfuel Field Validation | P0 | - | Pre-work | — |
| S1-1 | Dealer Registry Model | P0 | 2 | Sprint 1 | S0-1 |
| S1-2 | DB Migration — dealer_id FK | P0 | 2 | Sprint 1 | S1-1 |
| S1-3 | Scraper Refactor — Multi-Dealer | P0 | 3 | Sprint 1 | S1-1, S1-2 |
| S1-4 | main.py — Update run_scrape() | P0 | 3 | Sprint 1 | S1-2, S1-3 |
| S2-1 | Concurrent Scraping + Per-Dealer Scheduler | P1 | 3 | Sprint 2 | S1-3, S1-4 |
| S2-2 | API — Location-Aware Filtering | P0 | 2 | Sprint 2 | S1-2, S1-4 |
| S2-3 | Watchlist — Location Scope | P1 | 1 | Sprint 2 | S2-2 |
| S2-4 | Lead Matching — Location Awareness | P1 | 1 | Sprint 2 | S2-2 |
| S2-5 | ScrapeLog — Per-Dealer Detail | P2 | 1 | Sprint 2 | S1-4, S2-2 |
| S3-1 | Global Location Selector (Context + Sidebar) | P0 | 2 | Sprint 3 | S2-2 |
| S3-2 | Dashboard — Location-Aware Stats | P0 | 2 | Sprint 3 | S3-1, S2-2 |
| S3-3 | Inventory Page — Location Filter | P0 | 2 | Sprint 3 | S3-1, S2-2 |
| S3-4 | Locations Overview Page | P1 | 2 | Sprint 3 | S2-2, S3-1 |
| S3-5 | Activity Page — Location Scoping | P1 | 1 | Sprint 3 | S3-1, S2-2 |
| S3-6 | api.ts and types.ts Updates | P0 | 1 | Sprint 3 | S2-2 |
| S4-1 | Query Optimization & DB Indexes | P0 | 1 | Sprint 4 | All S1/S2 |
| S4-2 | Backend Integration Tests | P1 | 1 | Sprint 4 | All S1/S2 |
| S4-3 | SMTP Email Configuration | P1 | 0.5 | Sprint 4 | S2-3 |
| S4-4 | start.sh + Deployment Docs | P1 | 0.5 | Sprint 4 | All |
| **TOTAL** | | | **34 pts** | **4 sprints** | |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Overfuel changes `__NEXT_DATA__` schema | Medium | High | Pin scraper to schema version, add validation assertions |
| Stock numbers not unique across dealers | High | High | P0 fix in S1-4 — composite unique key `(dealer_id, stock_number)` |
| Scrape time exceeds scheduler interval at 24 dealers | Low | Medium | Benchmarked at ~60s for all 6,900 vehicles (well under 6h) |
| SQLite write lock contention with concurrent reads during scrape | Medium | Medium | Use WAL mode (`PRAGMA journal_mode=WAL`) in database.py |
| Dealer IDs change if Overfuel rebuilds ALM's catalog | Low | High | Store dealer IDs in seeded DB table (editable), not hard-coded |
| Missing dealer_id on some Overfuel vehicle records | Low | Medium | Validated in S0-3; handle with null-safe fallback and logging |
| Frontend re-renders on every location switch causing UI jank | Low | Low | Memoize API calls with React Query or useMemo; debounce selector |
| DB grows large quickly (6,900 vehicles + events) | Medium | Low | Add `VACUUM` schedule; SQLite handles up to 1M rows comfortably |

---

## Definition of Done (All Tasks)

- Code passes linting: `ruff check backend/` and `tsc --noEmit` in frontend
- No regressions on existing single-location (dealer_id=323) behavior
- All new API endpoints return correct HTTP status codes (200, 404, 422)
- Error states handled gracefully — no unhandled exceptions reaching the user
- Logging is present at INFO level for all new scrape and DB operations
- For P0 tasks: manual verification by developer before marking complete
- For P1/P2 tasks: covered by at least one automated test or manual test log

---

## Technical Debt Notes

The following items are out of scope for this expansion but should be tracked:

1. **Alembic migrations:** The current startup-migration approach will become fragile beyond 2-3
   schema changes. Add Alembic after Sprint 2 ships.
2. **PostgreSQL migration:** SQLite is suitable for this scale (~7k vehicles) but if ALM expands
   beyond 50 locations or adds real-time features, PostgreSQL removes write-lock concerns.
3. **React Query:** The current `useEffect` + `useState` pattern for data fetching will benefit
   from React Query (caching, background refetch, loading states) as the number of API calls grows.
4. **Authentication:** No auth layer exists. If this app is deployed beyond localhost, add basic
   auth or JWT before exposing to a network.
5. **Watchlist email HTML templates:** The current plain-text email in `alerts.py` should be
   upgraded to an HTML template (Jinja2) for a professional appearance.

---

## CRITICAL ORCHESTRATOR NOTE (Added by AgentsOrchestrator)

After full codebase review, the following items were confirmed from existing code:

- `stock_number = Column(String, unique=True)` in models.py line 11 — this MUST be changed to
  a composite `UniqueConstraint("dealer_id", "stock_number")` before any multi-location data is written
  or the DB will throw integrity errors when two dealers share a stock number format.

- `scraper.py` already extracts `dealer_id` (line 103) and `location_name` (line 79-83) in
  `normalize_vehicle()` — these fields are ready to use in the Vehicle model once the column is added.

- The existing `active_map` in `main.py` (line 50-53) keys on `stock_number` alone — this is the
  second critical fix required in S1-4.

- `database.py` uses SQLite without WAL mode — this is safe now but must be added before 24-location
  concurrent writes begin (see S4-1 risk note).

- Task S0-1 (Dealer ID Discovery) is the only true blocker. All other sprint tasks can be designed
  and scaffolded in parallel; the actual dealer IDs are only needed when seeding the `dealers` table.
