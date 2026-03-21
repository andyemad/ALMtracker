# ALM Inventory Tracker — 24-Location Expansion: Integration Readiness Report

**Assessment Date:** 2026-03-10
**Assessor:** TestingRealityChecker (Integration Agent)
**Evidence Base:** Full source-code read of all produced artifacts + live pytest run
**Verdict:** NOT READY

---

## Reality Check: The "357 Tests Passing" Claim

The test suite reports `357 passed, 54 xfailed, 14 xpassed in 2.31s`.
The session claimed "all tests passing." This framing is misleading and must be
corrected before any deployment decision is made.

- 357 tests pass against the EXISTING single-location codebase only.
- 54 new multi-location tests are explicitly marked `xfail`. pytest counts
  xfail as a non-failure by convention. These tests fail in reality. Every
  one of them tests functionality that does not exist in main.py.
- 14 tests show XPASS. These are xfail tests that accidentally passed because
  the assertion they contain is trivially satisfied by the current codebase
  (e.g., "vehicles without dealer_id filter returns all" passes because the
  filter was never added, so everything is returned). These are not evidence
  of multi-location functionality.
- 0 multi-location features are implemented in the running application.

The test suite is good quality work. The xfail pattern is the correct
approach for tests-before-implementation. The problem is the claim, not
the tests.

---

## Audit Findings

### A. Compatibility: new models.py versus existing main.py

**Finding: WILL CAUSE ImportError ON DEPLOY**

main.py line 19:

    from scraper import scrape_all_vehicles

The new scraper.py exports `scrape_all_dealers()` and `scrape_single_dealer()`.
The function `scrape_all_vehicles` does not exist anywhere in the new
scraper.py. Deploying the new scraper.py with main.py unchanged causes an
ImportError at startup. The FastAPI process will not start. All 276 existing
vehicles become inaccessible until the error is manually corrected.

Even if the import were patched, main.py's `run_scrape()` (lines 40-154)
calls `scrape_all_vehicles()` and unpacks a 2-tuple:

    vehicles, method = scrape_all_vehicles()

The new `scrape_all_dealers()` returns a 3-tuple `(DealerVehicleMap, int, str)`.
If the import were corrected without updating the call site, unpack would
raise `ValueError: too many values to unpack`.

The `run_scrape()` function also builds its entire change-detection state
keyed only by `stock_number`:

    active_map = {v.stock_number: v for v in ...}
    scraped_map = {v["stock_number"]: v for v in vehicles ...}

With 24 dealers, different dealers can and do share stock numbers. When dealer
A and dealer B both have a vehicle with stock number "X123", the dict will
hold only one of them. The other will either be treated as a new vehicle
(triggering a spurious "added" event and attempting an insert that will
violate a uniqueness constraint) or be treated as an existing vehicle from the
wrong dealer (corrupting that vehicle's data silently). This is the most
dangerous correctness bug in the expansion.

**Additional gaps in main.py that were not implemented:**

- `_vehicle_dict()` does not include `dealer_id` or `location_name`. API
  responses will be missing these fields even after migration runs.
- `_event_dict()`, `_alert_dict()`, and `_log_dict()` similarly omit all
  new fields added to their respective models.
- There is no call to `run_migrations()` anywhere in main.py. The migration
  must be wired into the startup event or run manually before every deploy.
- There is no `seed_dealers()` call in the startup event. The dealers table
  will remain empty until migrations.py is run manually.

### B. Is migrations.py truly idempotent?

**Finding: YES, WITH ONE CRITICAL EDGE CASE**

The migration script is well-written. Each step guards on existence before
acting. ALTER TABLE ADD COLUMN calls are protected by `_column_exists()`
checks. Index creation calls are protected by `_index_exists()` checks. The
dealer seed loop queries before inserting. Running the migration twice on the
same database produces the same result as running it once. Data is preserved.

The critical edge case: Step 7 creates `ix_uq_dealer_stock` as a UNIQUE INDEX
on `(dealer_id, stock_number)`. This is the new composite constraint. However,
the old v1.0 UNIQUE constraint on `stock_number` alone cannot be dropped in
SQLite without recreating the entire vehicles table. Both constraints will
coexist in the database after migration.

Because all 276 existing rows have `dealer_id=323`, no collision occurs during
the migration itself. However, once the multi-dealer scraper begins inserting
vehicles from other dealers, any stock number that also exists at dealer 323
will be rejected by the old UNIQUE(stock_number) constraint with an
IntegrityError, even though the new composite constraint would permit it.

This means that the core multi-dealer feature — two dealers sharing a stock
number — cannot actually work in the migrated production database until the
old constraint is removed via table recreation. The migration documentation
describes this as "causes no collision" without clarifying that it blocks
multi-dealer operation for the most common collision scenario.

### C. Does new scraper.py connect with main.py's run_scrape()?

**Finding: NO CONNECTION EXISTS**

They are completely disconnected. main.py imports `scrape_all_vehicles` which
no longer exists. The new scraper's public API (`scrape_all_dealers`,
`scrape_single_dealer`) is not referenced anywhere in main.py. No caller in
main.py has been updated to pass `active_dealers` as `DealerConfig` objects,
to unpack the 3-tuple return, or to iterate the `DealerVehicleMap` and process
each dealer's vehicle list in a separate change-detection loop.

The scraper itself is well-designed. `normalize_vehicle()`, `_bucket_vehicles()`,
and `_fetch_page()` are clean and correct. The `_discover_dealer_ids()` utility
is useful. None of this code is reachable from the running application.

### D. Integration gaps: designed but not implemented

**Finding: EXTENSIVE**

The following are described in ARCHITECTURE.md and SPRINT.md as deliverables
of Sprint 1, but do not exist in any code file audited:

1. GET /api/dealers — not in main.py. test_dealers.py is entirely xfail.
2. GET /api/dealers/{id}/stats — not in main.py. All tests xfail.
3. dealer_id query parameter on GET /api/vehicles — not in main.py.
   TestVehiclesDealerIdFilter class is 5 xfail, 2 xpass (coincidental).
4. location_name query parameter on GET /api/vehicles — not in main.py.
5. dealer_id parameter on GET /api/filter-options — not in main.py.
6. dealer_id scoping on GET /api/stats — not in main.py.
7. Dealer-scoped watchlist matching — alerts.py `get_matching_vehicles()`
   and `vehicle_matches_alert()` have no dealer_id awareness. An alert with
   dealer_id=323 set in the database will still match vehicles from all 24
   dealers because alerts.py ignores the dealer_id field entirely.
8. Dealer-scoped lead matching — lead_matches() in main.py has no dealer_id
   parameter.
9. Multi-dealer run_scrape() loop — the entire scrape function is
   single-dealer-aware only (stock_number key, no dealer dimension).
10. seed_dealers() startup call — specified in ARCHITECTURE.md, not in main.py.
11. Dealer ID discovery (Sprint 0) — DEALER_REGISTRY contains 23 placeholder
    IDs (401-423) that are sequential guesses. _discover_dealer_ids() has not
    been run. No actual Overfuel dealer IDs beyond 323 are confirmed.
12. Frontend multi-location changes — zero. No location selector, no
    per-dealer views, no dealer navigation exists in the React frontend.

### E. Is SQLite the right database for 24x the data volume?

**Finding: ACCEPTABLE FOR NOW, REQUIRES MONITORING**

At 6,900 rows the SQLite file will remain under 50 MB. SQLite handles millions
of rows on indexed columns without difficulty. The scraper's single-pass design
avoids concurrent write pressure. WAL mode (enabled by migrations.py) improves
concurrent read performance.

Specific risks to monitor:

1. Scrape duration. A full 14-page pass with BeautifulSoup parsing per page
   will take significantly longer than the current 276-vehicle run. If a
   scrape takes more than 6 hours (the scheduler interval), a second scrape
   thread begins before the first finishes. APScheduler will fire two
   concurrent scrape sessions both holding open DB sessions and writing to
   the same tables. With SQLite WAL mode this does not deadlock but can
   create race conditions in the change-detection maps.

2. The `active_map` in `run_scrape()` loads ALL active vehicles into memory:
   `db.query(models.Vehicle).filter(is_active == True).all()`
   At 6,900 vehicles this is still manageable (~5 MB of Python objects) but
   should be moved to a per-dealer batch query once run_scrape() is rewritten.

SQLite is acceptable for the 24-location scale. PostgreSQL should be
considered only if concurrent user load grows significantly or scrape durations
approach the 6-hour interval.

### F. Top 5 risks to production deployment

**Risk 1 — Application startup failure (CRITICAL)**
Deploying new scraper.py with unchanged main.py causes ImportError on
`scrape_all_vehicles`. The backend process will not start. The 276 existing
vehicles are inaccessible until the error is manually resolved.

**Risk 2 — Silent data corruption from stock number key collision (CRITICAL)**
The `active_map` in run_scrape() is keyed by stock_number alone. With 24
dealers, same-stock-number vehicles from different dealers will overwrite each
other in this dict, causing incorrect change detection. Vehicles will be
incorrectly added, removed, or have their prices changed. This produces no
error — it corrupts data silently.

**Risk 3 — Old UNIQUE constraint blocks multi-dealer inserts (CRITICAL)**
The SQLite UNIQUE constraint on stock_number alone (from v1.0) survives the
migration and cannot be dropped without table recreation. Any vehicle from a
second dealer that shares a stock number with an existing dealer 323 vehicle
will fail with IntegrityError on insert. The multi-dealer scraper cannot
function until this constraint is removed.

**Risk 4 — 23 of 24 dealer IDs are placeholder guesses (HIGH)**
DEALER_REGISTRY IDs 401-423 are sequential guesses that are almost certainly
wrong. If any of those IDs match real Overfuel dealer IDs for non-ALM
locations or different ALM locations than intended, vehicles will be
bucketed and attributed to the wrong dealer in the database. No multi-dealer
expansion can be trusted until _discover_dealer_ids() is run against the live
feed and confirmed.

**Risk 5 — Migration not wired into startup (HIGH)**
run_migrations() is never called in main.py. If the updated main.py and
models.py are deployed but migrations.py is not run manually first,
Base.metadata.create_all() creates the dealers table but does NOT add new
columns to existing tables. The first scrape attempt will fail with
OperationalError: no such column.

### G. What MUST be done before any multi-location code ships

In strict dependency order:

1. Run `_discover_dealer_ids()` against the live Overfuel feed. Update
   DEALER_REGISTRY in scraper.py and DEALER_SEED in migrations.py with
   confirmed IDs. This is the prerequisite for everything else.

2. Back up alm.db before any migration:
   `cp /Users/emadsiddiqui/ALM/backend/alm.db /Users/emadsiddiqui/ALM/backend/alm.db.pre-v2`

3. Run migrations.py against production alm.db and verify with
   `_verify_migration()`. All checks must pass before the backend restarts.

4. Recreate the vehicles table (or add an application-layer guard) to remove
   the old UNIQUE(stock_number) constraint. The composite constraint
   UNIQUE(dealer_id, stock_number) must be the only uniqueness boundary.

5. Rewrite main.py — specifically the import line, run_scrape(), all
   _*_dict() helpers, and the startup event — to be compatible with the new
   scraper.py API and new model fields. This is the largest single remaining
   work item.

6. Update alerts.py to check alert.dealer_id before matching vehicles, so
   dealer-scoped watchlist alerts function correctly.

7. Remove xfail marks in the test suite as each item above ships. Confirm
   the previously-xfail tests now pass because the feature is implemented,
   not by coincidence.

---

## Test Suite Accuracy Assessment

**conftest.py stub problem:**

The conftest stubs the scraper at module level with:

    _scraper_stub.scrape_all_dealers = _mock.MagicMock(return_value=({}, "stub"))

The real `scrape_all_dealers()` returns a 3-tuple `(DealerVehicleMap, int, str)`.
The stub returns a 2-tuple `({}, "stub")`. Any test that exercises a code path
calling `scrape_all_dealers()` with this stub will receive the wrong type and
either silently pass or fail with a misleading error. The stub must be corrected
to `return_value=({}, 0, "stub")` before integration tests can be trusted.

**test_multi_location.py import problem:**

Line 43 of test_multi_location.py attempts to import `scrape_all_locations`:

    from scraper import scrape_all_locations

This function does not exist in scraper.py. The function is `scrape_all_dealers`.
Because the entire test file is marked xfail with strict=False, this ImportError
is suppressed by pytest and counted as an expected failure rather than a setup
error. When the xfail protection is removed, this will produce an ImportError
that prevents the test from running at all.

**XPASS tests are not evidence of functionality:**

Two tests in TestVehiclesDealerIdFilter show XPASS:
- `test_no_dealer_id_returns_vehicles_from_all_dealers` — passes because
  there is no dealer_id filter, so all vehicles are returned. This is a
  trivially true assertion given the current codebase, not evidence the
  feature works.
- `test_same_stock_number_different_dealers_both_returned_without_filter` —
  also passes trivially because the current schema allows two separate vehicle
  rows even without the composite constraint (the old constraint would fire
  on insert, but the test creates the collision by direct ORM manipulation
  after initial insert, bypassing the constraint check).

---

## Prioritized Blockers

**Blocker 1 — ImportError prevents startup**
main.py imports `scrape_all_vehicles` which does not exist in new scraper.py.
Deploying new scraper.py without updating main.py kills the application.
File: `/Users/emadsiddiqui/ALM/backend/main.py` line 19.

**Blocker 2 — stock_number-only active_map causes silent data corruption**
The change-detection dict in run_scrape() must be rekeyed to
`(dealer_id, stock_number)` before any multi-dealer scrape runs.
File: `/Users/emadsiddiqui/ALM/backend/main.py` lines 50-54.

**Blocker 3 — Old UNIQUE(stock_number) constraint rejects multi-dealer inserts**
The constraint from v1.0 cannot be dropped without table recreation. It will
IntegrityError on any cross-dealer stock number collision.
File: `/Users/emadsiddiqui/ALM/backend/alm.db` (production schema).

**Blocker 4 — 23 of 24 dealer IDs are unverified placeholder guesses**
DEALER_REGISTRY IDs 401-423 are almost certainly wrong. Running the scraper
with these IDs will either miss ALM locations or attribute vehicles to wrong
locations.
File: `/Users/emadsiddiqui/ALM/backend/scraper.py` lines 101-133.

**Blocker 5 — Migration not called at startup**
run_migrations() is not called in main.py. Deploying new code without running
migrations.py first will cause OperationalError on the first scrape attempt.
File: `/Users/emadsiddiqui/ALM/backend/main.py` (startup event).

**Blocker 6 — run_scrape() not updated for multi-dealer flow**
The function must be rewritten to call scrape_all_dealers(), unpack the
3-tuple, and loop per dealer with composite key change detection.
File: `/Users/emadsiddiqui/ALM/backend/main.py` lines 40-154.

---

## Prioritized Warnings

**Warning 1 — alerts.py has no dealer_id awareness**
get_matching_vehicles() ignores alert.dealer_id. A dealer-scoped alert will
match vehicles from all 24 locations at scale.
File: `/Users/emadsiddiqui/ALM/backend/alerts.py` line 34.

**Warning 2 — _vehicle_dict() missing dealer fields**
API responses do not include dealer_id or location_name.
File: `/Users/emadsiddiqui/ALM/backend/main.py` lines 188-211.

**Warning 3 — conftest.py stub has wrong return type**
scrape_all_dealers mock returns 2-tuple, real function returns 3-tuple. This
masks integration bugs in tests.
File: `/Users/emadsiddiqui/ALM/backend/tests/conftest.py` line 38.

**Warning 4 — test_multi_location.py has wrong import name**
`scrape_all_locations` does not exist. The function is `scrape_all_dealers`.
File: `/Users/emadsiddiqui/ALM/backend/tests/test_multi_location.py` line 43.

**Warning 5 — No circuit breaker for empty scrape result**
If the Overfuel feed returns zero vehicles (network failure, site change),
run_scrape() will mark all 276 active vehicles as removed. A guard is needed:
if total_raw is 0, abort and log rather than processing removals.
File: `/Users/emadsiddiqui/ALM/backend/main.py` (removal loop).

**Warning 6 — APScheduler session leak**
The scheduler lambda creates a SessionLocal() that is never explicitly closed.
File: `/Users/emadsiddiqui/ALM/backend/main.py` lines 171-176.

**Warning 7 — No GET /api/dealers or GET /api/dealers/{id}/stats endpoints**
Entire test_dealers.py is xfail. These endpoints are specified in
ARCHITECTURE.md but not implemented.
File: `/Users/emadsiddiqui/ALM/backend/main.py` (missing endpoints).

**Warning 8 — Frontend not updated**
React frontend has no location selector, no per-dealer views, no dealer
navigation. This is expected for Sprint 1, but should not be forgotten.
Path: `/Users/emadsiddiqui/ALM/frontend/`.

---

## Concrete Next Steps In Order

**Step 1 — Sprint 0 (prerequisite, not yet done):**
    cd /Users/emadsiddiqui/ALM/backend
    source venv/bin/activate
    python -c "from scraper import _discover_dealer_ids; _discover_dealer_ids()"
Update DEALER_REGISTRY in scraper.py and DEALER_SEED in migrations.py with
confirmed Overfuel IDs. This unblocks everything downstream.

**Step 2 — Backup production database:**
    cp /Users/emadsiddiqui/ALM/backend/alm.db /Users/emadsiddiqui/ALM/backend/alm.db.pre-v2

**Step 3 — Run and verify migration:**
    cd /Users/emadsiddiqui/ALM/backend
    source venv/bin/activate
    python migrations.py
Confirm exit code 0 and all _verify_migration() checks pass. Do not restart
the backend before this step succeeds.

**Step 4 — Resolve the old UNIQUE(stock_number) constraint:**
Either recreate the vehicles table with only the composite unique constraint,
or implement an application-layer guard. Test that two vehicles with identical
stock_number but different dealer_id can both be inserted without error.

**Step 5 — Update main.py (the largest remaining work item):**
- Line 19: change `from scraper import scrape_all_vehicles` to
  `from scraper import scrape_all_dealers, scrape_single_dealer`
- Startup event: add `from migrations import run_migrations` and call
  `run_migrations(engine)` before any scrape runs
- run_scrape(): rewrite to call scrape_all_dealers(), unpack the 3-tuple,
  and loop per dealer with (dealer_id, stock_number) composite keys
- _vehicle_dict(): add dealer_id and location_name fields
- _event_dict(), _alert_dict(), _log_dict(): add new fields from their models
- list_vehicles(): add dealer_id and location_name query parameters
- get_stats(): add dealer_id scoping
- filter_options(): add dealer_id scoping
- Add GET /api/dealers endpoint
- Add GET /api/dealers/{id}/stats endpoint

**Step 6 — Update alerts.py:**
Add dealer_id filtering to get_matching_vehicles() and
check_and_notify_watchlist() to respect alert.dealer_id when set.

**Step 7 — Fix test suite issues:**
- conftest.py line 38: change stub return to `({}, 0, "stub")`
- test_multi_location.py line 43: change `scrape_all_locations` to
  `scrape_all_dealers`

**Step 8 — Remove xfail marks as features ship:**
After each step above, remove corresponding xfail marks and confirm the
previously-failing tests now pass because the feature is implemented, not
by coincidence. Do not remove xfail marks before the feature is done.

**Step 9 — Frontend (Sprint 2-3):**
Add location selector, dealer filter state, and per-dealer analytics views
to the React frontend at `/Users/emadsiddiqui/ALM/frontend/`.

---

## Overall Readiness Verdict

**Verdict: NOT READY**

What was produced and is in good shape: SPRINT.md planning, ARCHITECTURE.md
design, migrations.py (idempotent, correct), scraper.py (well-designed,
disconnected), models.py (correct schema), and a test suite that correctly
anticipates the target state with xfail guards.

What was not produced: any changes to main.py. The application entry point is
entirely unchanged. No API endpoints have been added. The scraper is not
connected to any caller. The migration is not called at startup. The alerts
system is not updated. The frontend is not updated.

Deploying the new scraper.py or models.py today, with main.py unchanged, will
break the production system. The import will fail at startup. The 276 existing
vehicles will be inaccessible.

The safe path forward: keep the current production system running unchanged
while completing Steps 1-8 above. Deploy as a single atomic change after
Step 7 is complete, with a verified database backup in place.

Realistic timeline to production readiness: 2-3 focused development sessions.
The hardest work is Step 5 (main.py rewrite). Steps 1-4 are prerequisites that
can be completed in one session. The foundation is solid. The integration layer
is the remaining critical path.

---

**Files Audited:**
- /Users/emadsiddiqui/ALM/SPRINT.md
- /Users/emadsiddiqui/ALM/ARCHITECTURE.md
- /Users/emadsiddiqui/ALM/backend/models.py
- /Users/emadsiddiqui/ALM/backend/scraper.py
- /Users/emadsiddiqui/ALM/backend/migrations.py
- /Users/emadsiddiqui/ALM/backend/main.py
- /Users/emadsiddiqui/ALM/backend/alerts.py
- /Users/emadsiddiqui/ALM/backend/database.py
- /Users/emadsiddiqui/ALM/backend/tests/conftest.py
- /Users/emadsiddiqui/ALM/backend/tests/test_vehicles.py
- /Users/emadsiddiqui/ALM/backend/tests/test_dealers.py
- /Users/emadsiddiqui/ALM/backend/tests/test_multi_location.py
- /Users/emadsiddiqui/ALM/backend/tests/test_api_scrape.py
- /Users/emadsiddiqui/ALM/backend/tests/test_api_integration.py
- /Users/emadsiddiqui/ALM/backend/tests/test_api_vehicles.py
- /Users/emadsiddiqui/ALM/backend/tests/test_api_stats.py
- /Users/emadsiddiqui/ALM/backend/tests/test_watchlist.py
- /Users/emadsiddiqui/ALM/backend/tests/test_alerts.py

**Live Test Evidence:**
- Command: `cd /Users/emadsiddiqui/ALM/backend && python -m pytest tests/ -v --tb=short`
- Result: 357 passed, 54 xfailed, 14 xpassed in 2.31s
- Interpretation: 357 tests verify existing single-location functionality.
  0 multi-location features are implemented in the running application.
  54 xfail tests document what needs to be built.
