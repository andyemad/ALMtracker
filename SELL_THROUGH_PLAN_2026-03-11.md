# ALM Sell-Through Plan

Date: 2026-03-11

## Current Snapshot

- Active inventory: `6,921` units
- Budget inventory (`$12k-$25k`): `1,879` units
- Trade-ins: `562` units
- Zero-price or missing-price units: `42`
- Active watchlists: `0`
- Leads in CRM: `0`

## Critical Data Reality

`days_on_lot` is not currently trustworthy as a sales-priority signal.

- Current max `days_on_lot` in the database is `1`
- `min_days_on_lot=30` returns `0` units

That means the normal aged-inventory workflow cannot be used yet. The agents should treat ALM as being in a merchandising recovery state until inventory age history matures or is backfilled.

## Priority Order For Agents

### 1. Merchandising Recovery Queue

This is the highest-priority queue because paid distribution should not start on units with bad pricing.

- Zero-price units: `42`
- Highest-concentration stores:
  - `ALM Mall of Georgia`: `8`
  - `ALM Gwinnett`: `8`
  - `ALM Chevrolet South`: `4`
  - `ALM Newnan`: `3`
  - `ALM Marietta`: `3`
  - `ALM Kennesaw`: `3`

Sample zero-price units needing immediate cleanup:

| Stock # | Vehicle | Mileage | Store |
| --- | --- | ---: | --- |
| `SE102228` | 2025 Kia K4 LXS | 0 | ALM CDJR Perry |
| `TZ117683` | 2026 Chevrolet Silverado 1500 Custom | 7,833 | ALM Chevrolet South |
| `PC687478A` | 2012 Dodge Charger SRT8 | 144,000 | ALM Gwinnett |
| `KU873247` | 2019 Hyundai Tucson Sport | 60,644 | ALM Gwinnett |
| `SG643523A` | 2024 Toyota Land Cruiser Base | 439 | ALM Gwinnett |
| `NCJ88249A` | 2022 BMW 4 Series 430i | 17,205 | ALM Mall of Georgia |

Agent instruction:

- `analytics-reporter`: produce the full zero-price queue by store and make every morning.
- `content-creator`: hold creative work for these units until pricing is fixed.
- `ppc-campaign-strategist`: exclude these units from campaign feeds.
- `legal-compliance-checker`: verify no ads or listings are published with misleading or missing pricing.

### 2. Budget Commuter Cohort

This is the best first demand-generation cohort because ALM has real depth here and the offer is easy to understand.

Top active model clusters between `$12k` and `$25k`:

| Make | Model | Units | Avg Price | Avg Mileage |
| --- | --- | ---: | ---: | ---: |
| Hyundai | Elantra | 492 | $23,282 | 1,929 |
| Nissan | Altima | 191 | $20,266 | 40,392 |
| Nissan | Rogue | 135 | $20,555 | 42,944 |
| Kia | K4 | 99 | $22,891 | 8,299 |
| Kia | Soul | 71 | $19,025 | 23,474 |
| Chevrolet | Malibu | 53 | $17,770 | 58,071 |

Agent instruction:

- `growth-hacker`: treat this as the fastest path to volume.
- `content-creator`: create "budget commuter", "first-car", and "payment-conscious family" messaging variants.
- `ad-creative-strategist`: create 3 hooks per cohort:
  - low payment / budget-friendly
  - newer model / low-mileage
  - fuel-efficient daily driver
- `ppc-campaign-strategist`: prepare a Google Vehicle Ads pilot only for stores and units with clean price, VIN, mileage, and VDP data.
- `paid-social-strategist`: run remarketing and inventory-led creative around Elantra, Altima, Rogue, K4, Soul, and Malibu clusters.

### 3. Trade-In Truck and SUV Cohort

Trade-ins are a second priority because they are differentiated inventory and should convert well once merchandising is clean.

Top trade-in clusters:

| Make | Model | Units | Avg Price | Avg Mileage |
| --- | --- | ---: | ---: | ---: |
| Ford | F-150 | 23 | $33,641 | 100,894 |
| Nissan | Rogue | 18 | $20,040 | 59,997 |
| Hyundai | Tucson | 16 | $20,273 | 64,473 |
| Jeep | Wrangler | 16 | $22,592 | 87,245 |
| GMC | Sierra 1500 | 15 | $36,706 | 63,353 |
| Chevrolet | Silverado 1500 | 14 | $35,617 | 62,764 |

Agent instruction:

- `analytics-reporter`: rank by margin potential once pricing is clean.
- `content-creator`: use "local trade", "hard-to-find truck", and "used SUV value" messaging.
- `paid-social-strategist`: focus on store-radius inventory ads and remarketing, not broad awareness.
- `ppc-campaign-strategist`: isolate truck/SUV campaign groups from commuter inventory.

## Product Work Completed

Two product improvements were shipped to support this plan:

- Dashboard sell-through queue in [Dashboard.tsx](./frontend/src/pages/Dashboard.tsx)
- Min/max days-on-lot filters plus one-click aging presets in [Inventory.tsx](./frontend/src/pages/Inventory.tsx)

The aging filters are structurally ready, but their usefulness depends on `days_on_lot` recovering as a real signal.

## Agent Workflow For This Week

### Step 1. Preflight

Run `agents-orchestrator` with a hard rule that data quality comes before spend.

Expected outputs:

- zero-price cleanup queue
- pilot-store shortlist
- excluded units list

### Step 2. Launch Readiness

Run:

- `tracking-measurement-specialist`
- `legal-compliance-checker`
- `ppc-campaign-strategist`

Required checks:

- every promoted unit has price, VIN, mileage, availability, image, and VDP
- store/dealer location mapping is clean
- campaign destination data matches feed data
- lead tracking captures `stock_number`, `location_name`, `campaign`, and `source`

### Step 3. Creative Build

Run:

- `content-creator`
- `ad-creative-strategist`
- `paid-social-strategist`

Deliverables:

- 3 message angles for commuter units
- 3 message angles for trade-in trucks/SUVs
- VDP headline rewrite recommendations
- Meta/short-form video hooks
- Google asset copy aligned to inventory clusters

### Step 4. Pilot Distribution

Start with:

- one commuter-inventory pilot
- one trade-in pilot
- only stores with clean pricing and clean VDP data

Do not scale until:

- pricing hygiene is complete for promoted units
- tracking is verified
- lead capture is flowing into ALM or a connected CRM

## Required Approvals

- Google Ads access
- Merchant Center access
- Google Business Profile or store-location data access
- Meta ad account access if social ads are used
- A capped virtual card with pre-approved vendor list

## Sources

- [FTC Used Car Rule: Dealers Guide](https://www.ftc.gov/business-guidance/resources/used-car-rule-dealers-guide)
- [Google Vehicle Ads Overview](https://support.google.com/google-ads/answer/11189169?hl=en)
- [Google Vehicle Feed Guidelines](https://developers.google.com/vehicle-listings/reference/feed-specification)
- [Google Ads Misrepresentation Policy](https://support.google.com/adspolicy/answer/190438)
- [Google Ads Dishonest Pricing Practices](https://support.google.com/adspolicy/answer/15938375)

## Next 3 Actions

1. Fix all `42` zero-price units and prevent them from entering any paid feed.
2. Launch a commuter-inventory pilot from clean Hyundai, Nissan, Kia, and Chevrolet inventory only.
3. Add lead attribution capture into ALM so campaigns can be optimized on real outcomes instead of clicks.
