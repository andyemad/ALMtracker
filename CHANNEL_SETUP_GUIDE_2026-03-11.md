# ALM Channel Setup Guide

This is the minimum setup required to let ALM run paid acquisition and social funnels with as little manual work as possible.

## What Is Already Live

- Public lead funnel: `http://localhost:5173/find`
- Example tracked URLs:
  - `http://localhost:5173/find?source=tiktok-organic&campaign=budget-elantra`
  - `http://localhost:5173/find?source=meta-paid&campaign=atl-rogue-retargeting`
  - `http://localhost:5173/find?source=google-paid&campaign=used-elantra-atl`
- Leads now store:
  - `source`
  - `campaign`
  - `sms_consent`
  - `sms_consent_at`
  - `call_consent`
  - `call_consent_at`
  - `consent_text`

That makes the funnel usable for attribution and outreach review instead of dumping everything into notes.

## 1. Google Ads + Merchant Center

Goal: run Google vehicle/search campaigns against ALM inventory.

### Access

1. In Google Ads, go to `Admin` -> `Access and security`.
2. Add the operator email as `Admin`.
3. In Merchant Center, go to `Access and services` -> `People and access`.
4. Add the same operator email as `Admin`.
5. If the business uses Google Business Manager, a super admin can also add app access from there.
6. In Google Payments Center, add the same operator email if that person needs billing visibility.

### Linking

1. In Merchant Center, go to `Settings` -> `Access and services` -> `Apps and services`.
2. Add the Google Ads account and link it.
3. If the Ads account is owned by someone else, use the Ads customer ID and approve the request in Google Ads `Tools` -> `Data manager`.

### Vehicle inventory

ALM has two paths:

- Fastest: use a Google-approved vehicle feed provider.
- More controllable: generate the vehicle feed directly from ALM and upload it through the vehicle listings flow.

The feed must include the full active inventory each upload, not partial deltas. Core required fields include dealership details, price, condition, make, model, year, and mileage for used vehicles. Vehicle detail page links and image links should be present so Google can crawl them and rank them correctly.

### Official docs

- [Manage access to your Google Ads account](https://support.google.com/google-ads/answer/6372672?hl=en)
- [Link a Google Ads account to Merchant Center](https://support.google.com/merchants/answer/12499498?hl=en)
- [Manage people and access levels in Merchant Center](https://support.google.com/merchants/answer/12160472?hl=en)
- [Manage your business as a super admin](https://support.google.com/merchants/answer/14883496?hl=en-uk)
- [Manage users in your payments profile](https://support.google.com/paymentscenter/answer/7162853?hl=en)
- [Vehicle feed setup](https://developers.google.com/vehicle-listings/integration-process/feed-setup)
- [Vehicle feed specification](https://developers.google.com/vehicle-listings/reference/feed-specification)
- [Vehicle feed service provider program](https://support.google.com/merchants/answer/15531232?hl=en-GB)
- [Merchant Center misrepresentation policy](https://support.google.com/merchants/answer/6150127)

## 2. Meta Business / Ads

Goal: run Meta prospecting, retargeting, and lead capture against ALM inventory campaigns.

### Access

1. Create or open the business in Meta Business Manager / Business Suite.
2. Add the operator as a person with admin access to the business.
3. Assign the operator to:
   - the Facebook Page
   - the Instagram account
   - the Ad Account
   - the Pixel / dataset if one already exists
4. Turn on two-factor authentication for admins.

### Tracking

Run both browser and server-side measurement:

- Pixel for browser events
- Conversions API for server-side events

That is the correct setup for lead attribution and retargeting durability.

### Official docs

- [About Conversions API](https://www.facebook.com/business/help/AboutConversionsAPI)
- [Manage roles on a shared Instagram business account](https://www.facebook.com/help/218638451837962)
- [Verify your organization's email domain in Admin Center](https://www.facebook.com/help/1287147125099160/)
- [Give people in your organisation a managed Meta account](https://www.facebook.com/help/656903351980825/)

## 3. Capped Virtual Card

Goal: let campaigns buy approved software or ad spend without giving an agent unlimited card access.

### Minimum rules

Use a dedicated virtual card, not your main physical card.

Set:

- a monthly cap
- per-transaction limit
- vendor lock where possible
- transaction alerts

### Practical options

- If your current issuer supports virtual cards already, use that first.
- If not, Privacy.com is the cleanest online-spend workflow for per-vendor controls.

### Spend policy for ALM

- Auto-approved vendors only: Google, Meta, TikTok, Twilio, Vercel, approved SaaS
- No new vendor without approval
- No recurring tool over the monthly cap without approval
- No hardware, gift cards, travel, or cash-equivalent purchases

### Official docs

- [Capital One virtual cards](https://www.capitalone.com/help-center/credit-cards/using-virtual-credit-cards/)
- [Privacy business cards and limits](https://support.privacy.com/hc/en-us/articles/7970104378519-Can-I-use-Privacy-for-my-business)
- [Create a Privacy card](https://support.privacy.com/hc/en-us/articles/360012402693-How-do-I-create-a-new-Privacy-Card)

## 4. TikTok Marketing

Yes, ALM can run TikTok.

The correct creative approach is not fake AI cars. Use real inventory photos or phone video from ALM, then add AI help around them:

- AI voiceover
- captions
- hooks
- variants
- thumbnail text
- comment reply scripts

Do not rely on fully synthetic car visuals for inventory that a buyer may actually show up to inspect. That creates trust and compliance risk fast.

### Setup

1. Create or convert the profile to a TikTok Business Account.
2. Create a TikTok Business Center.
3. Create or request access to the ad account.
4. Install TikTok Pixel and ideally Events API.
5. Send traffic to ALM `/find` with campaign parameters.

### Recommended ALM TikTok angle

- `I can search 24 ALM stores for you`
- `SUVs under $30k in Atlanta`
- `Budget commuter cars in stock right now`
- `Price drop alerts`
- `DM ELANTRA` / `DM ROGUE` / `DM TRUCK` to get matched inventory

### Official docs

- [Create ad accounts in Business Center](https://ads.tiktok.com/help/article/create-ad-accounts-in-business-center)
- [Request access to ad accounts in Business Center](https://ads.tiktok.com/help/article/request-access-to-ad-accounts-in-business-center)
- [Set up and verify TikTok web data connection](https://ads.tiktok.com/help/article/get-started-pixel)

## Recommended Order

1. Fix zero-price inventory and missing merchandising issues.
2. Set up Google access, Merchant Center, and payments access.
3. Set up Meta business access and tracking.
4. Create the capped virtual card.
5. Launch Google search + vehicle listings first.
6. Launch Meta retargeting second.
7. Launch TikTok organic and Spark Ads after the first 10-20 strong inventory videos exist.

## What Still Needs Building In ALM

- proper backend event push for leads into ad platforms / CRM
- zero-price recovery queue
- outreach sequencing for consented leads
- offline conversion uploads for sold deals

Until those are in place, ALM can generate and attribute leads, but some follow-up and closed-loop optimization will still be partially manual.
