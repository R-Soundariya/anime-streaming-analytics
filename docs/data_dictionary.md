# Data Dictionary — `data/raw/anime_streaming_raw.csv`

**Grain:** one row = one watch event (a user watching one episode).
User-, subscription- and account-level attributes are denormalised onto every
row, as in a typical warehouse export handed to an analyst. ~41.5k rows,
41 columns, export window **2023-01-01 → 2026-06-30**.

> ⚠️ This file is **intentionally messy** (see *Known quality issues* per column
> and the summary table at the bottom). `data/raw/injection_report.json` is the
> generator's answer key — the cleaning notebook uses it only to *verify*
> recovery, never as an input.

## User & demographics

| Column | Clean type | Description | Known quality issues |
|---|---|---|---|
| `User_ID` | str | Unique user key, `U00001`–`U08000`. | — |
| `Age` | int (13–70) | Age at sign-up. | ~3% missing; ~30 impossible outliers (150–300) |
| `Gender` | category | `Male`, `Female`, `Other`. | Variants `M`, `F`, `other` (~4%) |
| `Country` | category | 13 markets (USA, Japan, India, Brazil, …). | ~2% missing; USA also as `United States`, `U.S.` |
| `Region` | category | Continent-level rollup of `Country`. | — |
| `Language` | category | Preferred audio language (sub = `Japanese`). | ~3% missing |
| `Referral_Source` | category | Acquisition channel (Social Media, Friend Referral, …). | — |

## Subscription & revenue

| Column | Clean type | Description | Known quality issues |
|---|---|---|---|
| `Subscription_Plan` | category | `Free`, `Basic`, `Premium`, `Family`. | Case/whitespace variants (`premium`, `PREMIUM`, `Family␣␣`) ~7% |
| `Subscription_Start_Date` | date | Sign-up date. | ~3% in `DD-MM-YYYY` instead of ISO |
| `Subscription_End_Date` | date | Cancellation date; empty while active. | ~3% `DD-MM-YYYY`; ~0.5% **before** start date |
| `Subscription_Status` | category | `Active`, `Cancelled`. | — |
| `Cancellation_Reason` | category | Only for cancelled users (Too Expensive, Technical Issues, …). | Empty for active users (legitimate, not missing) |
| `Monthly_Fee` | float | Plan price: 0 / 4.99 / 9.99 / 14.99 USD. | ~2% stored as text `$9.99` |
| `Revenue` | float | Lifetime revenue to date (fee × months; ad revenue for Free). | User-level value repeated per row — **do not SUM at event grain** |
| `Membership_Tenure` | int | Months from sign-up to cancellation/export date. | — |
| `Payment_Method` | category | Credit/Debit Card, PayPal, UPI (India), Gift Card; `None` for Free. | ~2% missing |

## Content

| Column | Clean type | Description | Known quality issues |
|---|---|---|---|
| `Anime_Title` | str | One of 64 licensed titles. | ~2% stray leading/trailing whitespace |
| `Studio` | str | Producing studio (MAPPA, Ufotable, Madhouse, …). | ~2% stray whitespace |
| `Genre` | category | 12 genres (Shonen, Isekai, Seinen, Sports, …). | ~2% missing |
| `Episode_Number` | int | Episode watched (early episodes over-represented — series drop-off). | ~2% stored as text `12.0` |
| `Episode_Length` | int | Episode runtime, 20–26 min. | — |

## Watch event & engagement

| Column | Clean type | Description | Known quality issues |
|---|---|---|---|
| `Watch_Date` | datetime | Event timestamp (evening/weekend peaks are real). | Mixed formats: ISO, `DD/MM/YYYY HH:MM` (~4%), `Month D, YYYY HH:MM` (~2%); ~0.3% dates after export date |
| `Watch_Time_Minutes` | float | Minutes actually watched. | ~1.5% missing; ~25 outliers (2,000–6,000) |
| `Completion_Percentage` | float (0–100) | Share of the episode watched. | ~2% stored as text `85.3%`; ~1.5% null despite watch time > 0 (incomplete sessions) |
| `Watch_Session` | int (1–6) | Number of viewing sessions that day (binge indicator). | — |
| `Session_Duration` | float | Total minutes in the session incl. browsing. | — |
| `User_Rating` | int 1–10, nullable | Rating given after watching (~55% unrated — legitimate nulls). | ~1% sentinel string `Not Rated` |
| `Like` / `Share` / `Download` / `Watchlist` | 0/1 | Engagement actions on the episode/title. | Download ≈ 0 for Free (feature gated) |
| `Search_Source` | category | How content was found (Browse, Search Bar, Recommendation, Watchlist, Trending). | — |
| `Recommendation_Clicked` | 0/1 | Whether a recommendation drove the view. | — |

## Platform & experience

| Column | Clean type | Description | Known quality issues |
|---|---|---|---|
| `Device` | category | `Mobile`, `Smart TV`, `Desktop`, `Tablet`. | ~2.5% missing; ~3% lowercase variants |
| `Operating_System` | category | Consistent with device (Android, iOS, Windows, Tizen, …). | ~1.5% missing |
| `Internet_Type` | category | `Fiber`, `Broadband`, `Mobile Data`, `Satellite`. | — |
| `Buffering_Time` | float | Seconds of buffering in the event (driven by connection type). | ~20 impossible negative values |
| `Ad_Shown` / `Ad_Clicked` | 0/1 | Ads are served to Free users only. | — |
| `Support_Tickets` | int | User's lifetime support tickets. | — |
| `Customer_Satisfaction` | int 1–10 | Latest CSAT survey score (user-level, repeated per row). | — |

## Intentional data-quality issues (summary)

| Issue class | Where | Approx. volume |
|---|---|---|
| Duplicate rows | full-row copies | ~1% (412 rows) |
| Missing values | Age, Country, Device, Language, Genre, OS, Payment, Watch_Time | 1.5–3% per column |
| Outliers | Age 150–300; Watch_Time 2,000–6,000 min; negative Buffering | ~75 rows |
| Impossible dates | End before Start; Watch_Date after export date | ~330 rows |
| Mixed date formats | Watch_Date, subscription dates | 2–6% per column |
| Numbers stored as text | `$9.99`, `85.3%`, `12.0`, `Not Rated` | ~2% per column |
| Inconsistent categories | Plan, Gender, Country, Device | 3–7% per column |
| Stray whitespace | Anime_Title, Studio | ~2% per column |
| Incomplete sessions | Completion null while Watch_Time > 0 | ~1.5% |

## Modelling notes for analysis

- **Grain trap:** `Revenue`, `Monthly_Fee`, `Membership_Tenure`, `Support_Tickets`,
  `Customer_Satisfaction` are user-level values repeated on every event row.
  Aggregate them with `drop_duplicates("User_ID")` (or via the star schema),
  never with a raw event-level `SUM`.
- **Family ARPU:** a Family account averages ~3.5 profiles, so revenue per
  *individual* ≈ 14.99 / 3.5 ≈ $4.28 — below Basic ($4.99). Use this assumption
  when computing per-member economics.
- Built-in relationships you should be able to *discover* in analysis:
  paid plans watch more; completion ↔ rating (r ≈ 0.8); buffering ↔ CSAT
  (r ≈ −0.2); churn hazard falls with tenure (~11%/mo early vs ~3%/mo after a
  year); Shonen ≈ half of watch time; evenings & weekends dominate; sign-ups
  grow year over year.
