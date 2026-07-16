-- ============================================================================
-- 02 · JOINS, SUBQUERIES & CTEs
-- Anime Streaming Platform Analytics (SQLite)
-- ============================================================================

-- Q12 · Which genre's fans are worth the most
-- Business: revenue attribution by taste — the licensing budget compass.
-- Technique: CTE assigns each user a dominant genre (ROW_NUMBER over an
--            aggregate), then joins to user-grain revenue. Never SUM revenue
--            at event grain — it double-counts.
WITH user_genre AS (
    SELECT f.User_ID,
           c.Genre,
           ROW_NUMBER() OVER (PARTITION BY f.User_ID
                              ORDER BY SUM(f.Watch_Time_Minutes) DESC) AS rn
    FROM fact_watch_events f
    JOIN dim_content c USING (Content_ID)
    GROUP BY f.User_ID, c.Genre
)
SELECT ug.Genre                              AS dominant_genre,
       COUNT(*)                              AS fans,
       ROUND(SUM(s.Revenue), 0)              AS lifetime_revenue,
       ROUND(SUM(s.Revenue) / COUNT(*), 2)   AS revenue_per_fan
FROM user_genre ug
JOIN fact_subscriptions s USING (User_ID)
WHERE ug.rn = 1
GROUP BY ug.Genre
ORDER BY lifetime_revenue DESC;

-- Q13 · Most loyal customers
-- Business: the profile of a perfect customer — who to study and to protect.
-- Technique: multi-table JOIN with composite ordering.
SELECT u.User_ID, u.Country, u.Subscription_Plan,
       s.Membership_Tenure                    AS tenure_months,
       u.Engagement_Score,
       ROUND(s.Revenue, 0)                    AS lifetime_revenue
FROM dim_user u
JOIN fact_subscriptions s USING (User_ID)
WHERE u.Subscription_Status = 'Active'
ORDER BY s.Membership_Tenure DESC, u.Engagement_Score DESC
LIMIT 15;

-- Q14 · Power watchers: users at 2x the average total watch time
-- Business: the heavy-usage cohort that stresses infrastructure and loves you.
-- Technique: CTE of per-user totals filtered by a scalar subquery on itself.
WITH user_totals AS (
    SELECT User_ID, SUM(Watch_Time_Minutes) AS total_min
    FROM fact_watch_events
    GROUP BY User_ID
)
SELECT COUNT(*)                                          AS power_watchers,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM user_totals), 1) AS pct_of_users,
       ROUND(MIN(total_min) / 60.0, 1)                   AS min_hours,
       ROUND(MAX(total_min) / 60.0, 1)                   AS max_hours
FROM user_totals
WHERE total_min > 2 * (SELECT AVG(total_min) FROM user_totals);

-- Q15 · Most completed anime
-- Business: completion is the truest quality signal — no self-selection like ratings.
-- Technique: HAVING enforces a minimum sample before ranking an average.
SELECT c.Anime_Title, c.Genre,
       COUNT(*)                               AS views,
       ROUND(AVG(f.Completion_Percentage), 1) AS avg_completion_pct
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Anime_Title, c.Genre
HAVING COUNT(*) >= 150
ORDER BY avg_completion_pct DESC
LIMIT 10;

-- Q16 · Highest-rated anime (minimum 100 ratings)
-- Business: brand-building titles for marketing to lead with.
-- Technique: aggregate over a NULL-heavy column — AVG ignores NULLs; the
--            HAVING guard stops tiny samples from topping the chart.
SELECT c.Anime_Title, c.Studio,
       COUNT(f.User_Rating)              AS ratings,
       ROUND(AVG(f.User_Rating), 2)      AS avg_rating
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
WHERE f.User_Rating IS NOT NULL
GROUP BY c.Anime_Title, c.Studio
HAVING COUNT(f.User_Rating) >= 100
ORDER BY avg_rating DESC
LIMIT 10;

-- Q17 · Premium revenue by country
-- Business: where the highest-value tier concentrates — pricing-test markets.
-- Technique: filtered JOIN with per-group ARPU.
SELECT u.Country,
       COUNT(*)                            AS premium_users,
       ROUND(SUM(s.Revenue), 0)            AS lifetime_revenue,
       ROUND(AVG(s.Revenue_Per_Month), 2)  AS avg_monthly_arpu
FROM fact_subscriptions s
JOIN dim_user u USING (User_ID)
WHERE s.Subscription_Plan = 'Premium'
GROUP BY u.Country
ORDER BY lifetime_revenue DESC
LIMIT 10;

-- Q18 · Broadest-reach titles
-- Business: watch hours can be a few superfans; reach = true catalogue anchors.
-- Technique: COUNT(DISTINCT) against a scalar-subquery denominator.
SELECT c.Anime_Title,
       COUNT(DISTINCT f.User_ID)                                       AS unique_viewers,
       ROUND(100.0 * COUNT(DISTINCT f.User_ID)
             / (SELECT COUNT(*) FROM dim_user), 1)                     AS reach_pct
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Anime_Title
ORDER BY unique_viewers DESC
LIMIT 10;

-- Q19 · Active but silent: users with zero interactions
-- Business: engagement risk pool — active on paper, disengaged in behaviour.
-- Technique: NOT EXISTS anti-join ("Like" is quoted — LIKE is an SQL keyword).
SELECT COUNT(*) AS silent_active_users,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM dim_user
                                 WHERE Subscription_Status = 'Active'), 1) AS pct_of_active
FROM dim_user u
WHERE u.Subscription_Status = 'Active'
  AND NOT EXISTS (
        SELECT 1
        FROM fact_watch_events f
        WHERE f.User_ID = u.User_ID
          AND (f."Like" = 1 OR f.Share = 1 OR f.Watchlist = 1 OR f.Download = 1)
      );

-- Q20 · Buffering by connection type vs the platform average
-- Business: sizes the infra problem per segment instead of one blended number.
-- Technique: CROSS JOIN a one-row CTE to compare each group to the whole.
WITH overall AS (
    SELECT AVG(Buffering_Time) AS avg_buffer FROM fact_watch_events
)
SELECT f.Internet_Type,
       COUNT(*)                                   AS events,
       ROUND(AVG(f.Buffering_Time), 1)            AS avg_buffering_s,
       ROUND(AVG(f.Buffering_Time) - o.avg_buffer, 1) AS vs_platform_avg
FROM fact_watch_events f
CROSS JOIN overall o
GROUP BY f.Internet_Type, o.avg_buffer
ORDER BY avg_buffering_s DESC;

-- Q21 · Completion profile by device
-- Business: the finish-vs-abandon mix per screen — informs autoplay/resume UX.
-- Technique: CASE pivot — long categories turned into wide percentage columns.
SELECT Device,
       COUNT(*) AS events,
       ROUND(100.0 * AVG(CASE WHEN Completion_Bucket = 'Completed (90-100%)'
                              THEN 1.0 ELSE 0 END), 1) AS completed_pct,
       ROUND(100.0 * AVG(CASE WHEN Completion_Bucket = 'Abandoned (<25%)'
                              THEN 1.0 ELSE 0 END), 1) AS abandoned_pct
FROM fact_watch_events
GROUP BY Device
ORDER BY completed_pct DESC;

-- Q22 · Studio engagement depth
-- Business: which studios create fans (repeat viewing), not just impressions.
-- Technique: CTE computing two grains (events, viewers) combined into a ratio.
WITH studio_stats AS (
    SELECT c.Studio,
           COUNT(*)                  AS views,
           COUNT(DISTINCT f.User_ID) AS viewers,
           AVG(f.Completion_Percentage) AS avg_completion
    FROM fact_watch_events f
    JOIN dim_content c USING (Content_ID)
    GROUP BY c.Studio
)
SELECT Studio, views, viewers,
       ROUND(1.0 * views / viewers, 2)  AS views_per_viewer,
       ROUND(avg_completion, 1)         AS avg_completion_pct
FROM studio_stats
WHERE viewers >= 300
ORDER BY views_per_viewer DESC
LIMIT 10;
