# ALM Agent Playbook

## Goal

Use the installed skill-based agents to improve the ALM product and run an inventory sell-through workflow with minimal user intervention.

## Part 1: Product Improvement Stack

Use these agents for ALM product work:

- `agents-orchestrator`: runs the overall workflow and keeps handoffs tight.
- `frontend-developer`: ships dashboard, inventory, and lead workflow improvements in the React app.
- `ux-architect`: turns ALM into a faster daily operating tool for store teams.
- `analytics-reporter`: defines the KPIs that matter for sell-through, lead conversion, and aged inventory.
- `testing-reality-checker`: verifies that the shipped workflow actually works.
- `accessibility-auditor`: makes sure operators can use the app reliably across devices and conditions.

## Improvement Already Shipped

This pass added a sell-through panel to the dashboard:

- Source: `frontend/src/pages/Dashboard.tsx`
- Behavior: fetches the oldest active units and surfaces them as a "Units To Move First" queue.
- Purpose: gives ALM a concrete action list for what to push first instead of only showing passive reporting.

## Part 2: Inventory Sell-Through Stack

Use this as the core sales workflow:

- `agents-orchestrator`: owns the loop.
- `analytics-reporter`: finds which units should move now.
- `growth-hacker`: proposes experiments to increase sell-through.
- `content-creator`: writes listings, posts, and outreach content.
- `ad-creative-strategist`: writes ad variants and creative test hypotheses.
- `paid-social-strategist`: manages Meta, TikTok, and social remarketing strategy.
- `ppc-campaign-strategist`: manages Google and high-intent search/shopping strategy.
- `tracking-measurement-specialist`: makes sure every lead and sale can be attributed.
- `legal-compliance-checker`: reviews offers, claims, consent, and data handling.

## Spending Guardrails

Do not give agents an unrestricted credit card.

Use this policy instead:

- Only use a virtual card with a hard monthly cap.
- Only allow approved vendors.
- Require explicit user approval for any new vendor.
- Require explicit user approval for recurring subscriptions.
- Require explicit user approval for any single spend above `$250`.
- Require explicit user approval before increasing ad budgets above the agreed weekly ceiling.
- Log every spend with vendor, amount, purpose, expected outcome, and rollback plan.
- Never allow agents to buy vehicle inventory, scraped lead lists, financing products, or anything deceptive.

## Orchestrator Prompt

Use this prompt with `agents-orchestrator`:

```text
Use the agents-orchestrator skill.

You are running the ALM project. Your goal is to increase sales velocity for active inventory, especially aged units, while keeping operator workload low and keeping spend controlled.

Use the following agent stack:
- analytics-reporter
- growth-hacker
- content-creator
- ad-creative-strategist
- paid-social-strategist
- ppc-campaign-strategist
- tracking-measurement-specialist
- legal-compliance-checker
- frontend-developer when ALM product gaps block execution

Rules:
- Treat the ALM dashboard and its backend data as the source of truth.
- Focus first on units with high days_on_lot, stale pricing, and weak lead activity.
- If inventory data quality is unreliable, such as missing prices or reset aging fields, pause campaign launch work and run a data-recovery and merchandising pass first.
- Do not ask the user for routine decisions. Ask only for approvals, missing credentials, or blocked business choices.
- Do not spend money without obeying the spending guardrails.
- Escalate before any new vendor, any recurring tool, or any spend above the pre-approved cap.

Execution loop:
1. analytics-reporter identifies the top units to move this week and explains why.
2. growth-hacker proposes 3-5 demand-generation experiments ranked by speed and expected impact.
3. content-creator and ad-creative-strategist create channel-specific copy and creative briefs for those units.
4. paid-social-strategist and ppc-campaign-strategist build the paid and organic distribution plan.
5. tracking-measurement-specialist defines the event and attribution checks needed before launch.
6. legal-compliance-checker reviews claims, offers, and data collection.
7. frontend-developer proposes ALM changes only when the product is slowing sales execution.

Output format:
- Weekly priority inventory list
- Campaign plan by channel
- Exact assets or tooling needed
- Measurement plan
- Risks and approvals needed
- Next 3 actions that can be executed immediately
```

## Public Funnel

ALM now has a public lead-capture page at:

- `/find`
- Example TikTok link: `/find?source=tiktok-organic&campaign=budget-elantra`
- Example Meta link: `/find?source=meta-paid&campaign=atl-rogue-retargeting`
- Example Google link: `/find?source=google-paid&campaign=used-elantra-atl`

Use that page as the default destination for organic social, paid social, text campaigns, and creator traffic unless a channel-specific landing page is intentionally being tested.

## Fast Follow Prompts

### Weekly Sell-Through Prompt

```text
Use the agents-orchestrator skill on the ALM project. Review current inventory and produce this week's sell-through plan for the 20 highest-priority units. Keep budget conservative. Only ask me for approvals that are truly blocking.
```

### Product Gap Prompt

```text
Use the frontend-developer and analytics-reporter skills on the ALM project. Identify the smallest product change that would most improve the team's ability to move aged inventory, then implement it if it does not require a backend schema change.
```

### Campaign QA Prompt

```text
Use the tracking-measurement-specialist and legal-compliance-checker skills on the ALM project. Review the current sell-through campaign plan and list anything that would make attribution unreliable or create compliance risk.
```
