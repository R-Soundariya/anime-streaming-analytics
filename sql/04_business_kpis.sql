-- ============================================================================
-- 04 · BUSINESS KPI QUERIES — executive metrics as SQL
-- Anime Streaming Platform Analytics (SQLite)
-- ============================================================================

-- Q37 · Executive KPI snapshot (one row)
-- Business: the numbers a CEO asks for before coffee.
-- Technique: scalar subqueries composed into a single-row dashboard feed.
SELECT (SELECT COUNT(*) FROM dim_user)                                       AS total_users,
       (SELECT COUNT(*) FROM dim_user WHERE Subscription_Status = 'Active')  AS active_users,
       (SELECT ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM dim_user), 1)
        FROM dim_user WHERE Subscription_Status = 'Cancelled')               AS churn_rate_pct,
       (SELECT ROUND(SUM(Revenue), 0) FROM fact_subscriptions)               AS lifetime_revenue,
       (SELECT ROUND(SUM(Monthly_Fee), 0) FROM fact_subscriptions
        WHERE Subscription_Status = 'Active')                                AS current_mrr,
       (SELECT ROUND(SUM(Watch_Time_Minutes) / 60.0, 0)
        FROM fact_watch_events)                                              AS total_watch_hours,
       (SELECT ROUND(AVG(Customer_Satisfaction), 2) FROM dim_user)           AS avg_csat;

-- Q38 · Monthly churn hazard by tenure bucket
-- Business: proves the risk window is months 1-3 — where onboarding money goes.
-- Technique: a VALUES CTE of bucket bounds drives correlated subqueries;
--            each bucket's cancellations are normalised by the users who
--            survived long enough to be at risk, per month in the bucket.
WITH bounds (bucket, lo, hi) AS (
    VALUES ('01-03m', 1, 3), ('04-06m', 4, 6), ('07-12m', 7, 12),
           ('13-24m', 13, 24), ('25m+', 25, 42)
)
SELECT b.bucket,
       (SELECT COUNT(*) FROM fact_subscriptions
        WHERE Subscription_Status = 'Cancelled'
          AND Membership_Tenure BETWEEN b.lo AND b.hi)     AS cancellations,
       (SELECT COUNT(*) FROM fact_subscriptions
        WHERE Membership_Tenure >= b.lo)                   AS users_at_risk,
       ROUND(100.0 * (SELECT COUNT(*) FROM fact_subscriptions
                      WHERE Subscription_Status = 'Cancelled'
                        AND Membership_Tenure BETWEEN b.lo AND b.hi)
             / (SELECT COUNT(*) FROM fact_subscriptions
                WHERE Membership_Tenure >= b.lo)
             / (b.hi - b.lo + 1), 2)                       AS monthly_hazard_pct
FROM bounds b;

-- Q39 · ARPU and revenue mix by plan
-- Business: which tier actually funds the platform.
-- Technique: window share-of-total on top of a grouped aggregate.
SELECT s.Subscription_Plan,
       COUNT(*)                                            AS users,
       ROUND(AVG(s.Revenue_Per_Month), 2)                  AS arpu_monthly,
       ROUND(SUM(s.Revenue), 0)                            AS lifetime_revenue,
       ROUND(100.0 * SUM(s.Revenue)
             / SUM(SUM(s.Revenue)) OVER (), 1)             AS revenue_share_pct
FROM fact_subscriptions s
GROUP BY s.Subscription_Plan
ORDER BY lifetime_revenue DESC;

-- Q40 · Free vs paid behaviour gap
-- Business: the conversion pitch — what paying unlocks, in user behaviour.
-- Technique: CASE collapses four plans into two cohorts inside one pass.
SELECT CASE WHEN u.Subscription_Plan = 'Free' THEN 'Free' ELSE 'Paid' END AS cohort,
       COUNT(DISTINCT u.User_ID)                       AS users,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT u.User_ID), 1) AS events_per_user,
       ROUND(AVG(f.Completion_Percentage), 1)          AS avg_completion_pct,
       ROUND(AVG(f.Watch_Time_Minutes), 1)             AS avg_watch_min,
       ROUND(100.0 * AVG(f.Ad_Shown), 1)               AS ad_exposure_pct
FROM fact_watch_events f
JOIN dim_user u USING (User_ID)
GROUP BY cohort;

-- Q41 · Prime-time share by device
-- Business: where evening ad inventory and simulcast pushes should go.
-- Technique: AVG over a 0/1 flag is a percentage — the cleanest share idiom.
SELECT Device,
       COUNT(*)                              AS events,
       ROUND(100.0 * AVG(Peak_Hour), 1)      AS prime_time_share_pct,
       ROUND(100.0 * AVG(Weekend_Viewing), 1) AS weekend_share_pct
FROM fact_watch_events
GROUP BY Device
ORDER BY events DESC;

-- Q42 · Weekend vs weekday intensity (per calendar day)
-- Business: raw weekend totals mislead — there are only 2 weekend days per 7.
--           Per-day normalisation shows true intensity.
-- Technique: JOIN to dim_date and divide by COUNT(DISTINCT Date_ID).
SELECT CASE d.Is_Weekend WHEN 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       COUNT(*)                                       AS events,
       COUNT(DISTINCT d.Date_ID)                      AS calendar_days,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT d.Date_ID), 0) AS events_per_day,
       ROUND(AVG(f.Watch_Time_Minutes), 1)            AS avg_watch_min
FROM fact_watch_events f
JOIN dim_date d USING (Date_ID)
GROUP BY day_type;

-- Q43 · Sign-up cohorts: who is still with us
-- Business: cohort survival — is retention improving for newer vintages?
--           (Newer cohorts always look better; compare like-for-like ages.)
-- Technique: string-built quarter labels from strftime parts.
SELECT strftime('%Y', Subscription_Start_Date) || '-Q' ||
       ((CAST(strftime('%m', Subscription_Start_Date) AS INTEGER) + 2) / 3) AS signup_cohort,
       COUNT(*)                                        AS users,
       ROUND(100.0 * SUM(CASE WHEN Subscription_Status = 'Active'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS still_active_pct,
       ROUND(AVG(Membership_Tenure), 1)                AS avg_tenure_months
FROM fact_subscriptions
GROUP BY signup_cohort
ORDER BY signup_cohort;

-- Q44 · Acquisition channel quality
-- Business: marketing spend should follow paid conversion and retention,
--           not raw sign-up counts.
-- Technique: several conditional aggregates profiling each channel in one pass.
SELECT u.Referral_Source,
       COUNT(*)                                        AS users,
       ROUND(100.0 * SUM(CASE WHEN u.Subscription_Plan <> 'Free'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS paid_share_pct,
       ROUND(100.0 * SUM(CASE WHEN u.Subscription_Status = 'Cancelled'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_pct,
       ROUND(AVG(u.Engagement_Score), 1)               AS avg_engagement
FROM dim_user u
GROUP BY u.Referral_Source
ORDER BY paid_share_pct DESC;

-- Q45 · Support load vs satisfaction and churn
-- Business: every ticket bucket step costs satisfaction — quantify the link
--           between support pain and cancellations.
-- Technique: CASE bucketing + three conditional aggregates.
SELECT CASE WHEN Support_Tickets = 0 THEN '0 tickets'
            WHEN Support_Tickets <= 2 THEN '1-2 tickets'
            ELSE '3+ tickets' END                      AS ticket_bucket,
       COUNT(*)                                        AS users,
       ROUND(AVG(Customer_Satisfaction), 2)            AS avg_csat,
       ROUND(100.0 * SUM(CASE WHEN Subscription_Status = 'Cancelled'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_pct
FROM dim_user
GROUP BY ticket_bucket
ORDER BY ticket_bucket;
