# Anime Streaming Platform — Final Business Report

**Prepared by:** Data Analytics · **Data as of:** 2026-06-30 · **Period covered:** Jan 2023 – Jun 2026 (42 months)
**Sources:** governed KPI layer (`docs/kpi_definitions.md`), notebooks 01–05, SQL layer — every figure in this report reconciles to `powerbi/kpi_snapshot.csv`.

---

## 1 · Executive Summary

The platform ends H1 2026 **growing fast and leaking fast**.

**The five numbers that matter:**

| | Value | Trajectory |
|---|---|---|
| Monthly recurring revenue | **$22,551** | +70% YoY, compounding smoothly |
| Monthly active users | **1,527** | +120% YoY, spiking on season launches |
| Monthly churn | **~7%** | improved from 8.5% (2024) but still severe |
| Stickiness (DAU/MAU) | **0.038** | ~1.2 viewing days/month — far below the 0.15–0.30 streaming norm |
| Customer satisfaction | **7.07 / 10** | only 35.6% of users score 8+ |

**Three messages for leadership:**

1. **Growth is real but rented, not owned.** Revenue compounds because acquisition
   outruns churn, and audiences arrive on content drops (+34% MAU in season-launch
   months) — then leave. The product has not yet turned visits into habits: depth per
   viewer (≈0.4 hours per active user per month) has been flat for three years while
   reach doubled.

2. **The leak has a shape.** 58.6% of all churn happens in the first three months, and
   the churners' own words match their logs: *lost interest* (28.1%) and *technical
   issues* (27.5%) dominate; price is only 9.4%. Early churners are not no-shows — 75%
   watch in their first month — they show up, buffer, and leave.

3. **Experience, not catalogue, is the constraint.** Content rates 7.77/10 and churned
   users watched the *same* genre mix as loyalists. But viewing sessions average 8.9
   minutes of buffering, and the same catalogue loses 1.3 rating points when buffering
   exceeds 20 minutes. The cheapest satisfaction lever is engineering, not licensing.

**The sized prize:** converting half of the 1,331 paid early churners into ordinary
churners (10.1-month lifetimes instead of 1.7) is worth **≈ $43.8k — 11.7% of every
dollar collected to date** (§8, Recommendation 5).

---

## 2 · Objective & Scope

Simulate the full analytics function of an anime streaming platform (Crunchyroll-style)
and answer its four standing business questions:

1. What is the state of the business? (governed KPIs, §6)
2. Who are our users and how do they behave? (§7)
3. Why do subscribers churn, and what would keep them? (§7–8)
4. Where should content, marketing and engineering budget go next? (§8)

**Scope:** descriptive and diagnostic analytics — pandas, SQL, KPI design, dashboarding,
business storytelling. Predictive modelling is deliberately out of scope (flagged in
Future Scope where it is the natural next step).

## 3 · The Dataset

A synthetic but behaviourally realistic dataset, generated with documented business
rules (persona-driven viewing, tenure-dependent churn hazard, plan economics, QoS
effects) and then deliberately degraded with controlled data-quality issues.

| Property | Value |
|---|---|
| Raw export | `anime_streaming_raw.csv` — **41,582 rows × 40 columns**, one wide table |
| Grain | one watch event (user × episode × timestamp) |
| Entities | 7,993 users · 64 titles · 12 genres · 4 subscription plans |
| Window | 2023-01-19 → 2026-06-30 |
| Clean model | star schema: `dim_user`, `dim_content`, `dim_date`, `fact_watch_events` (41,046 events), `fact_subscriptions` |
| Reproducibility | single seed (42); `scripts/generate_dataset.py` → notebook 01 → `scripts/load_database.py` rebuilds everything |

## 4 · Data Quality & Cleaning Summary

The raw export contained every classic failure mode of a production data dump. All
handling decisions and their rationale live in notebook 01; the log is
`docs/cleaning_log.md`.

| Issue | Scale | Treatment |
|---|---|---|
| Full-row duplicates | 412 | dropped |
| Whitespace / case variants | 2,624 cells; 12 plan labels | trimmed; mapped to 4 canonical plans |
| Numerics stored as text (`$9.99`, `"85%"`) | 9 columns | parsed and typed |
| Impossible ages (250), watch times (5,000 min), negative buffering | 75 values | nulled as sensor error |
| End-before-start subscription dates | 206 | end date nulled, re-derived where possible |
| Future-dated watch events | 124 rows | dropped (beyond export date) |
| Scattered missing values | 3,738 recovered | row-level recovery from duplicate/user context |
| **Cancelled users with unrecoverable end dates** | **36 users** | **status declared authoritative** — counted in lifetime churn, excluded from the dated monthly engine; documented in the KPI layer because the choice moves June actives by 36 and MRR by ~$140 |

The last row is the report's honest-analyst exhibit: reconciling contract *status*
against *dates* surfaced a contradiction the pipeline could not repair, so the decision
was made explicit and priced rather than silently absorbed.

**Feature engineering (10):** viewer segment, engagement score (0–100 composite), age
group, completion bucket, retention status, weekend/peak-hour flags, subscription
length, revenue per month, and the date dimension.

## 5 · Method — One Source of Truth

Three independent implementations of every metric — **pandas** (notebook 04), **SQL**
(SQLite + 45 annotated queries), and **DAX** (`powerbi/measures.md`) — all implement the
single formula documented in `docs/kpi_definitions.md`, and the pandas and SQL layers
are machine-verified to agree **to the cent** on every cross-checkable value. Numbers
quoted in this report are the governed snapshot values (`powerbi/kpi_snapshot.csv`).

## 6 · KPI Snapshot (as of 2026-06-30)

**Audience & growth** — 7,993 registered · 3,524 active subscribers (44.1%) · MAU 1,527
(+120% YoY) · avg DAU 58.5 · stickiness 0.038 · 320 new subscribers in June (12-month
avg ≈ 304/month).

**Revenue** — MRR $22,551 (+70% YoY) · lifetime revenue $374,694 (of which ≈ $14.3k is
free-tier ad revenue) · ARPU $6.40 · ARPPU $9.31 · paid conversion 60.0% · MRR mix:
Premium 49%, Family 33%, Basic 18%.

**Retention & churn** — lifetime churn 55.9% · monthly churn 7.8% (Jun), 6.8% 2026-H1
average · early-churn share 58.6% · average churned lifetime 5.0 months · naive LTV
≈ $46.6 · loyal core (12 m+) 16.5% of users.

**Engagement** — 9,681 total watch hours · 0.34 hours per MAU (June) · completion 61.5%
(only 4.5% of plays reach 90%+) · binge rate 6.5% of user-days · engagement score 50.0.

**Quality & satisfaction** — CSAT 7.07 (35.6% satisfied) · content rating 7.77 · buffering
8.9 min/event · free-tier ad CTR 7.8%.

## 7 · Key Insights

### Growth quality
- **Reach without depth.** MAU doubled in a year, but hours-per-MAU has been flat
  (~0.37 → 0.41) since 2023 and stickiness is 0.038. Season-launch months lift MAU +34%
  and hours +54% (2025–26), then the audience recedes — engagement is event-driven.
- **Acquisition channels are interchangeable.** Lifetime value per user varies only
  ~13% across six channels ($43.0–$48.6). Channel strategy should be decided by cost,
  which the platform does not yet capture (Future Scope).

### The anatomy of churn
- **Churn concentrates where onboarding lives**: 73% of 0–3-month users churn vs 15%
  past two years — risk roughly halves each tenure band survived.
- **Stated reasons match the logs** — a rare luxury: technical-issue churners really had
  the worst buffering (9.6 min); lost-interest churners the lowest engagement (44.6);
  price churners were *engaged* (51.6) — they liked the product, not the bill; payment-
  failure churners were the most engaged of all (56.9) — involuntary losses.
- **Two behaviours mark survivors**: users who ever watchlist churn at 41.3% vs 66.4%,
  and users with a single 3-episode binge day churn at 28.7% vs 61.1%. (Correlational —
  but both are cheap to promote and measurable in week one.)

### The experience tax
- **Buffering rewrites perception of the catalogue**: identical content rates 8.13 under
  2 minutes of buffering and 6.80 past 20 minutes; completion falls 65.0% → 53.4%.
- **It's the network, not the device**: fiber ≈ 3.2 min on every screen; satellite 22–28;
  mobile data 13–15. Mobile's poor completion (56.4% vs 70.4% on TV) is a connectivity
  story — and mobile is 51% of all viewing, so the platform's majority experience is its
  worst one.
- CSAT falls monotonically with buffering (7.31 → 6.65 across user quartiles) and with
  support tickets (7.47 at zero → 5.75 at 3+). The buffering→churn link runs through
  satisfaction, not through a naive single-variable cut (the report of the confound is
  in notebook 05, Q24).

### Content strategy
- **Shonen is 50.3% of all watch hours** — a load-bearing dependency; the next tier
  (Isekai 8.8%, Fantasy 7.5%, Seinen 7.3%) is the diversification budget.
- **Isekai is the value trap**: #2 in consumption, second-worst rating (7.23) — demand
  without delight; the highest-upside shelf to upgrade.
- **Volume and quality are different lists**: only 3 of the top-10-by-hours titles are
  also top-10-by-rating. The under-watched "critics' shelf" is already licensed —
  surfacing it is free satisfaction.
- **Depth pays**: 25+-episode titles average 183 watch hours vs 87 for short seasons
  (r = 0.70) — long-runners amortize licence cost and fuel binges.

### Monetization
- **Premium funds the platform** (49% of MRR from 25% of accounts); Family is a
  retention product ($14.99/account but ≈ $3.75/member); the free tier earns real ad
  money (CTR 7.8%, rising to 10.3% for 45+ viewers — the inventory to price up).
- **Revenue is concentrated**: the top 10% of users contribute 51.6% of lifetime
  revenue; the 16.5% loyal core contributes 51.1%. Financially, this is a loyalty
  business with an acquisition funnel attached.
- **Conversion gaps are geographic**: Germany converts at 64.4%, the USA (largest
  market, 1,718 users) at 59.3%, Canada at 56.3% — with engagement flat across
  countries, the gap looks like pricing/payment friction, not intent.

## 8 · Recommendations (funded, ranked)

| # | Recommendation | Evidence | Expected impact | Owner |
|---|---|---|---|---|
| 1 | **Network-aware QoS program**: lower default bitrate on cellular, download-over-WiFi prompts, QoS priority for new accounts | buffering −1.3 rating pts; mobile = 51% of viewing; network not device | Largest single lever on completion, CSAT and the 27.5% technical-issue churn slice | Engineering |
| 2 | **Watchlist-first onboarding**: prompt a save in session one; track "% new users with ≥1 watchlist add, week 1" as the activation metric | 41.3% vs 66.4% churn split | Leading indicator + habit seed; feeds #5 | Product |
| 3 | **Convert the 442 free lookalikes** (engagement above the paying median) with a targeted upgrade offer | 13.8% of free base already behaves paid | ≈ $660+/month MRR per campaign wave at 30% take-up; repeatable quarterly | Growth |
| 4 | **Reason-segmented win-back**: card-retry/grace for payment failures, downgrade path for price churners, "we fixed it" after QoS ships | stated reasons verified against logs | Cheapest saves first — payment failures are engaged users lost involuntarily | CRM |
| 5 | **Onboarding overhaul for months 0–3**: content-match quiz, first-session quality bar, early QoS priority | 58.6% of churn is early; early churners attend but don't connect | **≈ $43.8k** (= 11.7% of lifetime revenue) at a conservative 50% success rate | Product + Eng |

**Supporting moves:** protect Shonen renewals and audit the Isekai shelf (§7); surface
the critics' shelf in recommendations; coordinate acquisition pushes with season-launch
months and stagger exclusives into trough months; sell 45+/TV ad inventory at premium
CPMs and lighten ad load for under-25s.

### What *not* to do (equally evidence-based)

- **Don't reshuffle the catalogue to fight churn** — churned users' genre mix differs
  from loyalists' by at most ±1.1 pp.
- **Don't run discount-led win-back at scale** — only 9.4% of churners cite price, and
  price churners are the *most* recoverable with a downgrade path instead.
- **Don't re-weight acquisition channels on quality** — the spread is too narrow to
  matter; get CAC data first.

## 9 · Future Scope

1. **CAC per channel** — the missing half of every channel decision (Q7).
2. **Plan-change event history** — enables a true free→paid conversion funnel instead of
   the base-mix proxy (KPI B5's documented caveat).
3. **Activity-controlled churn model** — resolves the buffering→churn confound properly
   (notebook 05, Q24); the natural first ML extension of this project.
4. **Cohort survival curves & discounted LTV** — replace the naive ARPPU × lifetime
   estimate; quantify whether newer vintages retain better.
5. **Autoplay A/B test** — the binge-retention link is strong but correlational; this is
   the experiment that prices it.
6. **Live dashboard hardening** — user-level behavioural flags (watchlisted, binged) in
   the Power BI model so the Recommendations page is fully data-bound.

## 10 · Lessons Learned

1. **Definitions before dashboards.** The single highest-leverage artifact was
   `kpi_definitions.md` — every later layer (SQL, pandas, DAX) became an implementation
   detail of one contract, and disagreements became detectable bugs instead of meetings.
2. **Validate across stacks, to the cent.** Machine-checked reconciliation (pandas ↔
   SQLite ↔ KPI exports) caught real errors — including a wrong season-launch claim and
   a revenue formula that ignored ad revenue — that eyeballing would have shipped.
3. **Contradictions deserve decisions, not patches.** The 36 status-vs-date conflicts
   were priced ($140 MRR, 36 actives) and resolved by an explicit authority rule. Small
   number, right habit.
4. **Negative findings are deliverables.** "Genre doesn't drive churn" and "channels are
   interchangeable" redirect real budget; an analyst who only reports positive effects
   is a hazard.
5. **Denominators are where analyses die.** Monthly churn (start-of-month actives),
   completion (nulls in or out), Avg DAU (active days vs calendar days) — each was
   defined once, in writing, and implemented identically three times.

---

## Appendix — Artifact Map & Reproduction

| Layer | Artifact |
|---|---|
| Generation | `scripts/generate_dataset.py` (seed 42) · `docs/data_dictionary.md` |
| Cleaning | `notebooks/01_data_cleaning.ipynb` · `docs/cleaning_log.md` |
| EDA | `notebooks/02_eda.ipynb` (17 charts) |
| SQL | `scripts/load_database.py` · `sql/01–04` (45 queries) · `notebooks/03_sql_analysis.ipynb` |
| KPIs | `docs/kpi_definitions.md` · `notebooks/04_kpi_layer.ipynb` · `powerbi/kpi_*.csv` |
| Business questions | `notebooks/05_business_questions.ipynb` (31 questions) |
| Dashboards | `scripts/export_powerbi_model.py` · `powerbi/measures.md` · `powerbi/theme.json` · `powerbi/dashboard_build_guide.md` |

**Reproduce end-to-end:**

```
python scripts/generate_dataset.py
jupyter nbconvert --execute --inplace notebooks/01_data_cleaning.ipynb
python scripts/load_database.py
jupyter nbconvert --execute --inplace notebooks/02_eda.ipynb notebooks/03_sql_analysis.ipynb \
    notebooks/04_kpi_layer.ipynb notebooks/05_business_questions.ipynb
python scripts/export_powerbi_model.py
```
