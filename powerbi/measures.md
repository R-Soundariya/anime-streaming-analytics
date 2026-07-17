# DAX Measures — Anime Streaming Analytics

Every measure implements the formula documented in
[`docs/kpi_definitions.md`](../docs/kpi_definitions.md) (KPI IDs referenced throughout).
Paste each block into a measure on the `_Measures` table (see setup below), or copy the
whole file section by section.

## Setup conventions (do these first)

1. **Home table:** create an empty table for measures — Modeling → New table →
   `_Measures = ROW("x", 1)`, hide the `x` column, and set every measure's Home table
   to `_Measures`.
2. **Mark the date table:** select `dim_date` → Table tools → *Mark as date table* →
   `Date`. Time-intelligence functions (`DATEADD`) silently misbehave without this.
3. **Relationships** must match the diagram in `dashboard_build_guide.md` — in
   particular the **inactive** `fact_subscriptions[Subscription_Start_Date] → dim_date[Date]`
   relationship that the acquisition measures activate with `USERELATIONSHIP`.
4. Format strings for every measure are listed in the table at the end of this file.

---

## Base counts

```dax
Total Registered Users = COUNTROWS ( dim_user )        // KPI A1
```

```dax
Active Subscribers =                                    // KPI A2
CALCULATE (
    COUNTROWS ( fact_subscriptions ),
    fact_subscriptions[Subscription_Status] = "Active"
)
```

```dax
Cancelled Subscribers =
CALCULATE (
    COUNTROWS ( fact_subscriptions ),
    fact_subscriptions[Subscription_Status] = "Cancelled"
)
```

```dax
Paying Subscribers =
CALCULATE (
    COUNTROWS ( fact_subscriptions ),
    fact_subscriptions[Subscription_Status] = "Active",
    fact_subscriptions[Monthly_Fee] > 0
)
```

---

## Pillar A — Audience & Growth

```dax
New Subscribers =                                       // KPI A3
// fact_subscriptions' *active* relationship is to dim_user; date context must
// come through the inactive start-date relationship, activated here.
CALCULATE (
    COUNTROWS ( fact_subscriptions ),
    USERELATIONSHIP ( fact_subscriptions[Subscription_Start_Date], dim_date[Date] )
)
```

```dax
MAU =                                                   // KPI A4
// Month-grain visuals give this the month context automatically.
DISTINCTCOUNT ( fact_watch_events[User_ID] )
```

```dax
Avg DAU =                                               // KPI A5
// Averaged over days WITH activity (matches kpi_definitions #5); the full
// calendar contains silent early days that would otherwise dilute the average.
AVERAGEX (
    FILTER (
        VALUES ( dim_date[Date] ),
        CALCULATE ( COUNTROWS ( fact_watch_events ) ) > 0
    ),
    CALCULATE ( DISTINCTCOUNT ( fact_watch_events[User_ID] ) )
)
```

```dax
Stickiness (DAU/MAU) = DIVIDE ( [Avg DAU], [MAU] )      // KPI A6
```

```dax
New Subscribers MoM % =
VAR Prev =
    CALCULATE ( [New Subscribers], DATEADD ( dim_date[Date], -1, MONTH ) )
RETURN
    DIVIDE ( [New Subscribers] - Prev, Prev )
```

---

## Pillar B — Revenue

```dax
MRR =                                                   // KPI B1 (as-of snapshot)
CALCULATE (
    SUM ( fact_subscriptions[Monthly_Fee] ),
    fact_subscriptions[Subscription_Status] = "Active"
)
```

```dax
MRR (Trend) =                                           // month-end MRR from the KPI engine
// kpi_monthly rows are month-grain; on a month axis SUM returns that month's MRR.
// In a multi-month context (a card), report the LATEST month, never the sum.
VAR LastMonth = MAX ( kpi_monthly[Month] )
RETURN
    CALCULATE ( SUM ( kpi_monthly[MRR] ), kpi_monthly[Month] = LastMonth )
```

```dax
MRR YoY % =
VAR Prev =
    CALCULATE ( [MRR (Trend)], DATEADD ( dim_date[Date], -12, MONTH ) )
RETURN
    DIVIDE ( [MRR (Trend)] - Prev, Prev )
```

```dax
Lifetime Revenue = SUM ( fact_subscriptions[Revenue] )  // KPI B2
```

```dax
ARPU = DIVIDE ( [MRR], [Active Subscribers] )           // KPI B3
```

```dax
ARPPU = DIVIDE ( [MRR], [Paying Subscribers] )          // KPI B4
```

```dax
Paid Conversion Rate =                                  // KPI B5
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_subscriptions ), fact_subscriptions[Monthly_Fee] > 0 ),
    COUNTROWS ( fact_subscriptions )
)
```

```dax
MRR Share =                                             // plan-mix visuals
DIVIDE ( [MRR], CALCULATE ( [MRR], ALL ( fact_subscriptions[Subscription_Plan] ) ) )
```

---

## Pillar C — Retention & Churn

```dax
Overall Churn Rate =                                    // KPI C1
DIVIDE ( [Cancelled Subscribers], COUNTROWS ( fact_subscriptions ) )
```

```dax
Monthly Churn Rate =                                    // KPI C2
// Weighted correctly across any month selection: total cancellations over
// total starting actives — never an average of monthly rates.
DIVIDE ( SUM ( kpi_monthly[Cancellations] ), SUM ( kpi_monthly[Active_Start] ) )
```

```dax
Early Churn Share =                                     // KPI C3
DIVIDE (
    CALCULATE (
        COUNTROWS ( fact_subscriptions ),
        fact_subscriptions[Subscription_Status] = "Cancelled",
        fact_subscriptions[Membership_Tenure] <= 3
    ),
    [Cancelled Subscribers]
)
```

```dax
Avg Customer Lifetime =                                 // KPI C4 (months, churned only)
CALCULATE (
    AVERAGE ( fact_subscriptions[Membership_Tenure] ),
    fact_subscriptions[Subscription_Status] = "Cancelled"
)
```

```dax
Loyal Share =                                           // KPI C5
DIVIDE (
    CALCULATE ( COUNTROWS ( dim_user ), dim_user[Retention_Status] = "Loyal (12m+ active)" ),
    COUNTROWS ( dim_user )
)
```

```dax
Customer LTV = [ARPPU] * [Avg Customer Lifetime]        // naive LTV, per report caveats
```

---

## Pillar D — Engagement

```dax
Total Watch Hours =                                     // KPI D1
DIVIDE ( SUM ( fact_watch_events[Watch_Time_Minutes] ), 60 )
```

```dax
Hours per MAU = DIVIDE ( [Total Watch Hours], [MAU] )   // KPI D2
```

```dax
Avg Completion Rate =                                   // KPI D3
AVERAGE ( fact_watch_events[Completion_Percentage] )
```

```dax
Completed Share =                                       // KPI D4 (>=90% of all events,
DIVIDE (                                                // unrated/null completions count
    CALCULATE (                                         // in the denominator)
        COUNTROWS ( fact_watch_events ),
        fact_watch_events[Completion_Percentage] >= 90
    ),
    COUNTROWS ( fact_watch_events )
)
```

```dax
Binge Rate =                                            // KPI D5
// Share of user-days with 3+ episodes. SUMMARIZE builds the user-day table in
// the current filter context, so it respects every slicer.
VAR UserDays =
    SUMMARIZE ( fact_watch_events, fact_watch_events[User_ID], fact_watch_events[Date_ID] )
VAR BingeDays =
    FILTER ( UserDays, CALCULATE ( COUNTROWS ( fact_watch_events ) ) >= 3 )
RETURN
    DIVIDE ( COUNTROWS ( BingeDays ), COUNTROWS ( UserDays ) )
```

```dax
Avg Engagement Score = AVERAGE ( dim_user[Engagement_Score] )   // KPI D6
```

---

## Pillar E — Quality & Satisfaction

```dax
CSAT = AVERAGE ( dim_user[Customer_Satisfaction] )      // KPI E1
```

```dax
Satisfied Share =                                       // KPI E2 (CSAT >= 8)
DIVIDE (
    CALCULATE ( COUNTROWS ( dim_user ), dim_user[Customer_Satisfaction] >= 8 ),
    COUNTROWS ( dim_user )
)
```

```dax
Avg Content Rating = AVERAGE ( fact_watch_events[User_Rating] )  // KPI E3
```

```dax
Avg Buffering (min) = AVERAGE ( fact_watch_events[Buffering_Time] )  // KPI E4
```

```dax
Ad CTR =                                                // KPI E5
DIVIDE ( SUM ( fact_watch_events[Ad_Clicked] ), SUM ( fact_watch_events[Ad_Shown] ) )
```

---

## Format strings

| Measure | Format |
|---|---|
| Total Registered Users, Active/Cancelled/Paying Subscribers, New Subscribers, MAU | `#,0` |
| Avg DAU | `#,0.0` |
| Stickiness (DAU/MAU) | `0.000` |
| MRR, MRR (Trend), Lifetime Revenue | `$#,0` |
| ARPU, ARPPU, Customer LTV | `$#,0.00` |
| Paid Conversion, churn rates, shares, Completed Share, Binge Rate, Satisfied Share, Ad CTR, MoM/YoY % | `0.0%` |
| Total Watch Hours | `#,0` |
| Hours per MAU | `0.00` |
| Avg Completion Rate | `0.0"%"` (values are already 0–100) |
| Avg Customer Lifetime | `0.0 "months"` |
| CSAT, Avg Content Rating | `0.00` |
| Avg Buffering (min) | `0.0 "min"` |
| Avg Engagement Score | `0.0` |

**Validation note.** The pandas KPI layer (`notebooks/04_kpi_layer.ipynb`) and the SQLite
layer agree to the cent on every cross-checkable value; these DAX measures implement the
same formulas against the same exported tables, and the expected values for the as-of
snapshot are in `kpi_snapshot.csv` — after wiring the model, compare a card for each
measure against that table's `Value` column (a ready-made acceptance test).
