-- ============================================================================
-- 01 · FOUNDATIONS — GROUP BY, HAVING, CASE, percentages
-- Anime Streaming Platform Analytics (SQLite)
-- ============================================================================

-- Q01 · Table row counts
-- Business: sanity-check the load before trusting any query on top of it.
-- Technique: UNION ALL to stack scalar aggregates into one result.
SELECT 'dim_user' AS table_name, COUNT(*) AS rows_ FROM dim_user
UNION ALL SELECT 'dim_content', COUNT(*) FROM dim_content
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date
UNION ALL SELECT 'fact_subscriptions', COUNT(*) FROM fact_subscriptions
UNION ALL SELECT 'fact_watch_events', COUNT(*) FROM fact_watch_events;

-- Q02 · Users, active users and churn rate by plan
-- Business: which tiers hold their customers? The one-table health check.
-- Technique: conditional aggregation with CASE inside SUM.
SELECT Subscription_Plan,
       COUNT(*)                                                        AS users,
       SUM(CASE WHEN Subscription_Status = 'Active' THEN 1 ELSE 0 END) AS active,
       ROUND(100.0 * SUM(CASE WHEN Subscription_Status = 'Cancelled'
                              THEN 1 ELSE 0 END) / COUNT(*), 1)        AS churn_pct
FROM dim_user
GROUP BY Subscription_Plan
ORDER BY users DESC;

-- Q03 · Top 10 anime by watch hours
-- Business: the renewal shortlist — which licenses earn their fee.
-- Technique: fact-to-dimension JOIN, GROUP BY, ORDER BY aggregate, LIMIT.
SELECT c.Anime_Title,
       c.Genre,
       ROUND(SUM(f.Watch_Time_Minutes) / 60.0, 0) AS watch_hours,
       COUNT(*)                                   AS views
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Anime_Title, c.Genre
ORDER BY SUM(f.Watch_Time_Minutes) DESC
LIMIT 10;

-- Q04 · Most-watched studios
-- Business: which studios deserve output deals rather than per-title licensing.
-- Technique: JOIN + COUNT(DISTINCT) to measure audience, not just volume.
SELECT c.Studio,
       ROUND(SUM(f.Watch_Time_Minutes) / 60.0, 0) AS watch_hours,
       COUNT(DISTINCT f.User_ID)                  AS unique_viewers,
       COUNT(*)                                   AS views
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Studio
ORDER BY watch_hours DESC
LIMIT 10;

-- Q05 · Highest-revenue countries
-- Business: where the money lives — prioritise localisation and payments.
-- Technique: JOIN subscriptions to user geography; revenue is user-grain.
SELECT u.Country,
       COUNT(*)                                AS users,
       ROUND(SUM(s.Revenue), 0)                AS lifetime_revenue,
       ROUND(SUM(s.Revenue) / COUNT(*), 2)     AS revenue_per_user
FROM fact_subscriptions s
JOIN dim_user u USING (User_ID)
GROUP BY u.Country
ORDER BY lifetime_revenue DESC
LIMIT 10;

-- Q06 · Device share of viewing
-- Business: which platforms the apps team should prioritise.
-- Technique: percentage of total via a scalar subquery.
SELECT Device,
       COUNT(*)                                                            AS events,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM fact_watch_events), 1) AS share_pct
FROM fact_watch_events
GROUP BY Device
ORDER BY events DESC;

-- Q07 · Viewing quality by plan
-- Business: do paying users actually watch more and finish more?
-- Technique: CASE in ORDER BY to sort a category logically, not alphabetically.
SELECT u.Subscription_Plan,
       COUNT(*)                                  AS events,
       ROUND(AVG(f.Watch_Time_Minutes), 1)       AS avg_watch_min,
       ROUND(AVG(f.Completion_Percentage), 1)    AS avg_completion_pct,
       ROUND(AVG(f.Buffering_Time), 1)           AS avg_buffering_s
FROM fact_watch_events f
JOIN dim_user u USING (User_ID)
GROUP BY u.Subscription_Plan
ORDER BY CASE u.Subscription_Plan
             WHEN 'Free' THEN 1 WHEN 'Basic' THEN 2
             WHEN 'Premium' THEN 3 ELSE 4 END;

-- Q08 · Genres that both scale and hold attention
-- Business: candidates for more licensing spend — volume AND completion.
-- Technique: HAVING filters on aggregates after GROUP BY (WHERE cannot).
SELECT c.Genre,
       COUNT(*)                               AS views,
       ROUND(AVG(f.Completion_Percentage), 1) AS avg_completion_pct
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Genre
HAVING COUNT(*) >= 1500 AND AVG(f.Completion_Percentage) >= 60
ORDER BY views DESC;

-- Q09 · Engagement tiers and their churn
-- Business: quantify how strongly engagement protects retention.
-- Technique: CASE bucketing of a continuous score into named tiers.
SELECT CASE WHEN Engagement_Score >= 75 THEN 'A · 75-100'
            WHEN Engagement_Score >= 50 THEN 'B · 50-74'
            WHEN Engagement_Score >= 25 THEN 'C · 25-49'
            ELSE 'D · 0-24' END               AS engagement_tier,
       COUNT(*)                               AS users,
       ROUND(100.0 * SUM(CASE WHEN Subscription_Status = 'Cancelled'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_pct
FROM dim_user
GROUP BY engagement_tier
ORDER BY engagement_tier;

-- Q10 · Why users cancel
-- Business: each reason routes to a different owner (pricing, content, infra).
-- Technique: WHERE against NULL + share-of-total via subquery.
SELECT Cancellation_Reason,
       COUNT(*) AS cancelled_users,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM fact_subscriptions
                                 WHERE Cancellation_Reason IS NOT NULL), 1) AS share_pct
FROM fact_subscriptions
WHERE Cancellation_Reason IS NOT NULL
GROUP BY Cancellation_Reason
ORDER BY cancelled_users DESC;

-- Q11 · Audio-language preference by watch time
-- Business: sub vs dub investment — where dubbing budgets pay off.
-- Technique: aggregate on a joined dimension attribute with share of total.
SELECT u.Language,
       ROUND(SUM(f.Watch_Time_Minutes) / 60.0, 0) AS watch_hours,
       ROUND(100.0 * SUM(f.Watch_Time_Minutes)
             / (SELECT SUM(Watch_Time_Minutes) FROM fact_watch_events), 1) AS share_pct
FROM fact_watch_events f
JOIN dim_user u USING (User_ID)
GROUP BY u.Language
ORDER BY watch_hours DESC;
