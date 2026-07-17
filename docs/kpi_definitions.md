# KPI Definitions — Anime Streaming Platform Analytics

This document is the **single source of truth** for every KPI used in this project.
Each KPI has one owner-approved formula; the notebook (`notebooks/04_kpi_layer.ipynb`),
the SQL layer (`sql/04_business_kpis.sql`) and the Power BI measures (Module 7) all
implement *these* definitions, so a number quoted in a meeting can always be traced
back to this page.

**25 KPIs across five pillars:** Audience & Growth · Revenue · Retention & Churn ·
Engagement · Quality & Satisfaction.

---

## Conventions (read first — every formula depends on these)

| Convention | Rule |
|---|---|
| **As-of date** | `2026-06-30` — the dataset export date. All "current" snapshot KPIs are measured here. |
| **Active subscriber** | `Subscription_Status = 'Active'` (equivalently: `Subscription_End_Date IS NULL`). Includes the Free tier — Free users are registered accounts we can monetize with ads and convert to paid. |
| **Paying subscriber** | Active subscriber with `Monthly_Fee > 0` (Basic \$4.99, Premium \$9.99, Family \$14.99). |
| **Active during month M** | `Subscription_Start_Date <= last day of M` AND (`Subscription_End_Date IS NULL` OR `Subscription_End_Date >= first day of M`). Used for monthly churn denominators. |
| **Active at end of month M** | `Subscription_Start_Date <= last day of M` AND (`End IS NULL` OR `End > last day of M`). Used for MRR, ARPU trend points. |
| **Month grain** | Calendar months, Jan 2023 → Jun 2026 (42 months). Jan 2023 is partial (first sign-up 2023-01-19) and is excluded from trend *charts* but kept in exports, flagged. |
| **Rates** | Expressed as percentages with 1 decimal; ratios (stickiness) as 0–1 with 2 decimals. |

---

## Pillar A — Audience & Growth

### 1. Total Registered Users
- **Formula:** `COUNT(DISTINCT User_ID)` in `dim_user`
- **Business meaning:** The total size of the account base ever acquired — the top of every funnel and the denominator for lifetime-quality metrics.
- **Watch out:** Grows monotonically; never quote it as evidence of health on its own.

### 2. Active Subscribers
- **Formula:** `COUNT(User_ID) WHERE Subscription_Status = 'Active'`
- **Business meaning:** The live account base as of the export date — how many relationships we actually still have. The primary "size of business" number.

### 3. New Subscribers per Month (+ MoM growth %)
- **Formula:** `COUNT(User_ID) GROUP BY month(Subscription_Start_Date)`; growth = `(New_M − New_{M−1}) / New_{M−1}`
- **Business meaning:** Acquisition velocity. Read together with churn: a business can grow sign-ups and still shrink.

### 4. Monthly Active Users (MAU)
- **Formula:** `COUNT(DISTINCT User_ID)` with ≥ 1 watch event in the calendar month (from `fact_watch_events`)
- **Business meaning:** How many accounts actually *use* the product each month — the honest audience number, immune to zombie subscriptions.
- **Watch out:** MAU is behaviour-based; Active Subscribers is contract-based. The gap between them is disengaged-but-paying users — churn risk.

### 5. Average Daily Active Users (DAU)
- **Formula:** For each calendar day, `COUNT(DISTINCT User_ID)` with a watch event; average across days in the month.
- **Business meaning:** Habit strength at the daily level; the pulse a streaming product lives on.

### 6. Stickiness (DAU / MAU)
- **Formula:** `Avg_DAU / MAU` for the same month (0–1)
- **Business meaning:** Of the people who show up in a month, what fraction shows up on an average day? Streaming benchmarks sit around 0.15–0.30; movement matters more than the level.

---

## Pillar B — Revenue

### 7. Monthly Recurring Revenue (MRR)
- **Formula:** `SUM(Monthly_Fee)` over subscribers active at the measurement point (as-of date for the snapshot; end of month for the trend)
- **Business meaning:** The revenue run-rate — what next month's subscription income will be if nothing changes. The single most-watched number in a subscription business.
- **Watch out:** MRR is a *rate*, not cash collected; refunds, proration and annual plans (not modelled here) complicate it in real systems.

### 8. Total Collected Revenue (lifetime)
- **Formula:** `SUM(Revenue)` in `fact_subscriptions` (paid users: `Monthly_Fee × Membership_Tenure`; Free users: estimated ad revenue, ~$14.3k of the total)
- **Business meaning:** Everything the platform has billed to date — the cumulative outcome of acquisition, pricing and retention combined.

### 9. ARPU — Average Revenue per User (monthly)
- **Formula:** `MRR / Active Subscribers` (Free users **included** in the denominator)
- **Business meaning:** Monetization efficiency of the whole active base. Including Free users is deliberate: it prices the cost of a large free tier and rises when conversion improves.

### 10. ARPPU — Average Revenue per Paying User
- **Formula:** `MRR / Active Paying Subscribers`
- **Business meaning:** What a paying relationship is worth per month; moves with plan mix (Family \$14.99 vs Basic \$4.99), not with conversion.
- **Watch out:** ARPPU ≥ ARPU always. Quote the right one: ARPPU for pricing decisions, ARPU for overall monetization.

### 11. Paid Conversion Rate
- **Formula:** `Paying Subscribers (ever) / Total Registered Users`
- **Business meaning:** How well the free tier feeds the paid funnel.
- **Watch out:** This schema stores one plan per user (no upgrade history), so this is a *base-mix* proxy, not a true free→paid upgrade funnel — flagged as a data-model improvement in the final report.

---

## Pillar C — Retention & Churn

### 12. Overall Churn Rate (lifetime)
- **Formula:** `Cancelled Users / Total Registered Users`
- **Business meaning:** Of everyone ever acquired, how many we lost. A lifetime quality-of-acquisition measure, not an operating metric.

### 13. Monthly Churn Rate
- **Formula:** `Cancellations in month M / Subscribers active at start of M`
- **Business meaning:** The operating churn number — the leak in the bucket that acquisition must out-pump. This is the churn figure to track on a dashboard.
- **Watch out:** Denominator is start-of-month actives, *not* total users — using the wrong denominator understates churn badly.

### 14. Early Churn Share (≤ 3 months)
- **Formula:** `Churned with Membership_Tenure ≤ 3 / Total Churned`
- **Business meaning:** How much churn is an *onboarding* failure vs a long-term-value failure. Our EDA showed churn concentrates in months 1–3, so this KPI prices the onboarding opportunity.

### 15. Average Customer Lifetime (months)
- **Formula:** `AVG(Membership_Tenure)` over churned users
- **Business meaning:** How long a relationship lasts once it ends — pairs with ARPPU to approximate customer lifetime value (`LTV ≈ ARPPU × lifetime`).
- **Watch out:** Computed on churned users only; active users' tenures are still running (right-censored), so this *understates* true expected lifetime.

### 16. Loyal Share (12 m+ active)
- **Formula:** `Users with Retention_Status = 'Loyal (12m+ active)' / Total Registered Users`
- **Business meaning:** The size of the proven-loyal core — the segment that funds the platform and deserves protection (exclusives, perks) rather than discounts.

---

## Pillar D — Engagement

### 17. Total Watch Hours
- **Formula:** `SUM(Watch_Time_Minutes) / 60` over `fact_watch_events`
- **Business meaning:** Gross consumption — the currency of a streaming platform and the input to licensing decisions.

### 18. Watch Hours per MAU (monthly)
- **Formula:** `Monthly Watch Hours / MAU` for the same month
- **Business meaning:** Depth of engagement per active person. Total hours can rise purely because the base grows; hours-per-MAU says whether each viewer is actually watching more.

### 19. Completion Rate
- **Formula:** Primary: `AVG(Completion_Percentage)` over events where it is recorded. Secondary: share of events with `Completion_Percentage >= 90` ("completed").
- **Business meaning:** Content-market fit at the episode level: do people finish what they start? Low completion with high starts = a discovery problem or a quality problem.

### 20. Binge Rate
- **Formula:** `User-days with ≥ 3 episodes watched / All user-days with ≥ 1 episode`
- **Business meaning:** Share of viewing days that turn into binge sessions — the behaviour most correlated with retention in streaming. (A "user-day" is one user watching on one calendar day.)

### 21. Average Engagement Score
- **Formula:** `AVG(Engagement_Score)` from `dim_user` (composite 0–100 built in Module 2 from frequency, hours, completion and interactions)
- **Business meaning:** One-number user-level engagement for segmentation; the input behind the Viewer_Segment tiers.

---

## Pillar E — Quality & Satisfaction

### 22. CSAT — Customer Satisfaction
- **Formula:** Primary: `AVG(Customer_Satisfaction)` (1–10 scale). Secondary: share of users scoring ≥ 8 ("satisfied share").
- **Business meaning:** The perception layer that leads churn. The satisfied-share cut is more actionable than the mean because means hide bimodal bases.

### 23. Average Content Rating
- **Formula:** `AVG(User_Rating)` over rated watch events (1–10; ~54% of events are unrated and excluded)
- **Business meaning:** Perceived content quality. Read per title/genre for licensing; the platform-level number is a slow-moving health check.
- **Watch out:** Ratings are volunteered → selection bias (people rate what they feel strongly about). Never compare against the full-catalog average of another platform.

### 24. Average Buffering Time per Event (minutes)
- **Formula:** `AVG(Buffering_Time)` over `fact_watch_events`
- **Business meaning:** Delivery quality. EDA showed buffering correlates negatively with satisfaction and ratings, so this is the ops-side lever on CSAT.

### 25. Ad Click-Through Rate (Free tier)
- **Formula:** `SUM(Ad_Clicked) / SUM(Ad_Shown)` (ads are served to Free users only)
- **Business meaning:** Monetization efficiency of the free tier — with the Free base at ~40% of users, ad CTR is the other revenue engine besides conversion.

---

## Where each KPI lives

| Artifact | Contents |
|---|---|
| `notebooks/04_kpi_layer.ipynb` | Computes all 25 KPIs + monthly trends, with validation against the SQLite layer |
| `powerbi/kpi_snapshot.csv` | One row per measure (27 = 25 KPIs + the 2 secondary cuts of #19/#22) — feeds Power BI cards |
| `powerbi/kpi_monthly.csv` | Month × KPI wide table (42 rows) — feeds Power BI trend visuals |
| `powerbi/kpi_by_plan.csv` | Plan-level KPI cut — feeds plan slicers/small multiples |
| `sql/04_business_kpis.sql` | SQL formulations of the executive snapshot (Q37) and related KPIs |
