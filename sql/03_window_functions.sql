-- ============================================================================
-- 03 · WINDOW FUNCTIONS — ranking, LAG/LEAD, running totals, rolling averages
-- Anime Streaming Platform Analytics (SQLite)
-- ============================================================================

-- Q23 · Each user's most recent watch event
-- Business: "last seen watching" — feeds win-back campaigns and resume rows.
-- Technique: ROW_NUMBER() PARTITION BY user, keep rn = 1. The canonical
--            "latest row per entity" pattern.
WITH latest AS (
    SELECT f.User_ID, f.Watch_Date, c.Anime_Title, f.Episode_Number,
           ROW_NUMBER() OVER (PARTITION BY f.User_ID
                              ORDER BY f.Watch_Date DESC) AS rn
    FROM fact_watch_events f
    JOIN dim_content c USING (Content_ID)
)
SELECT User_ID, Watch_Date, Anime_Title, Episode_Number
FROM latest
WHERE rn = 1
ORDER BY Watch_Date DESC
LIMIT 10;

-- Q24 · Top 3 titles inside every genre
-- Business: genre-level renewal shortlists in one pass, not 12 queries.
-- Technique: RANK() partitioned by genre over an aggregated CTE.
WITH genre_hours AS (
    SELECT c.Genre, c.Anime_Title,
           SUM(f.Watch_Time_Minutes) / 60.0 AS hours
    FROM fact_watch_events f
    JOIN dim_content c USING (Content_ID)
    GROUP BY c.Genre, c.Anime_Title
),
ranked AS (
    SELECT Genre, Anime_Title, hours,
           RANK() OVER (PARTITION BY Genre ORDER BY hours DESC) AS genre_rank
    FROM genre_hours
)
SELECT Genre, genre_rank, Anime_Title, ROUND(hours, 0) AS watch_hours
FROM ranked
WHERE genre_rank <= 3
ORDER BY Genre, genre_rank;

-- Q25 · Studios ranked by viewer rating
-- Business: a quality league table for licensing negotiations.
-- Technique: DENSE_RANK (no gaps on ties) over a HAVING-guarded aggregate.
WITH studio_ratings AS (
    SELECT c.Studio,
           COUNT(f.User_Rating)         AS ratings,
           AVG(f.User_Rating)           AS avg_rating
    FROM fact_watch_events f
    JOIN dim_content c USING (Content_ID)
    WHERE f.User_Rating IS NOT NULL
    GROUP BY c.Studio
    HAVING COUNT(f.User_Rating) >= 200
)
SELECT DENSE_RANK() OVER (ORDER BY avg_rating DESC) AS quality_rank,
       Studio, ratings, ROUND(avg_rating, 2) AS avg_rating
FROM studio_ratings
ORDER BY quality_rank;

-- Q26 · Month-over-month sign-up growth
-- Business: is acquisition accelerating or stalling?
-- Technique: LAG() to reach the previous row; growth % from current vs LAG.
WITH monthly AS (
    SELECT strftime('%Y-%m', Subscription_Start_Date) AS month,
           COUNT(*) AS signups
    FROM fact_subscriptions
    GROUP BY month
)
SELECT month, signups,
       LAG(signups) OVER (ORDER BY month)             AS prev_month,
       ROUND(100.0 * (signups - LAG(signups) OVER (ORDER BY month))
             / LAG(signups) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- Q27 · Net subscriber adds per month
-- Business: the headline growth number: sign-ups minus cancellations.
-- Technique: two CTEs LEFT JOINed on month (every month has sign-ups here,
--            so signups is the safe spine).
WITH s AS (
    SELECT strftime('%Y-%m', Subscription_Start_Date) AS month, COUNT(*) AS signups
    FROM fact_subscriptions GROUP BY month
),
c AS (
    SELECT strftime('%Y-%m', Subscription_End_Date) AS month, COUNT(*) AS cancels
    FROM fact_subscriptions
    WHERE Subscription_End_Date IS NOT NULL GROUP BY month
)
SELECT s.month, s.signups,
       COALESCE(c.cancels, 0)              AS cancels,
       s.signups - COALESCE(c.cancels, 0)  AS net_adds
FROM s
LEFT JOIN c ON c.month = s.month
ORDER BY s.month;

-- Q28 · Cumulative sign-ups (running total)
-- Business: the "users ever acquired" curve for the growth deck.
-- Technique: SUM() OVER (ORDER BY ...) — the running-total idiom.
WITH monthly AS (
    SELECT strftime('%Y-%m', Subscription_Start_Date) AS month, COUNT(*) AS signups
    FROM fact_subscriptions GROUP BY month
)
SELECT month, signups,
       SUM(signups) OVER (ORDER BY month) AS cumulative_signups
FROM monthly
ORDER BY month;

-- Q29 · Monthly watch hours with a 3-month rolling average
-- Business: smooths seasonal spikes so the underlying trend is visible.
-- Technique: AVG() OVER with ROWS BETWEEN 2 PRECEDING AND CURRENT ROW.
WITH monthly AS (
    SELECT strftime('%Y-%m', Watch_Date) AS month,
           SUM(Watch_Time_Minutes) / 60.0 AS watch_hours
    FROM fact_watch_events
    GROUP BY month
)
SELECT month,
       ROUND(watch_hours, 0) AS watch_hours,
       ROUND(AVG(watch_hours) OVER (ORDER BY month
                                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS rolling_3m
FROM monthly
ORDER BY month;

-- Q30 · Days between a user's consecutive watch sessions
-- Business: viewing cadence per plan — habit strength predicts retention.
-- Technique: LEAD() to reach the *next* event; julianday() for date math.
WITH gaps AS (
    SELECT User_ID, Watch_Date,
           LEAD(Watch_Date) OVER (PARTITION BY User_ID ORDER BY Watch_Date) AS next_watch
    FROM fact_watch_events
)
SELECT u.Subscription_Plan,
       ROUND(AVG(julianday(g.next_watch) - julianday(g.Watch_Date)), 1) AS avg_gap_days,
       COUNT(*) AS measured_gaps
FROM gaps g
JOIN dim_user u USING (User_ID)
WHERE g.next_watch IS NOT NULL
GROUP BY u.Subscription_Plan
ORDER BY avg_gap_days;

-- Q31 · Churn rate by engagement quartile
-- Business: turns "engagement matters" into a number per quartile.
-- Technique: NTILE(4) buckets users into equal quarters by score.
WITH quartiles AS (
    SELECT User_ID, Engagement_Score, Subscription_Status,
           NTILE(4) OVER (ORDER BY Engagement_Score) AS quartile
    FROM dim_user
)
SELECT quartile,
       COUNT(*)                                  AS users,
       ROUND(MIN(Engagement_Score), 1)           AS min_score,
       ROUND(MAX(Engagement_Score), 1)           AS max_score,
       ROUND(100.0 * SUM(CASE WHEN Subscription_Status = 'Cancelled'
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_pct
FROM quartiles
GROUP BY quartile
ORDER BY quartile;

-- Q32 · Genre share of total watch time
-- Business: portfolio concentration — how dependent are we on one genre?
-- Technique: window over an aggregate — SUM(SUM(x)) OVER () gives the grand
--            total on each grouped row without a second query.
SELECT c.Genre,
       ROUND(SUM(f.Watch_Time_Minutes) / 60.0, 0)          AS watch_hours,
       ROUND(100.0 * SUM(f.Watch_Time_Minutes)
             / SUM(SUM(f.Watch_Time_Minutes)) OVER (), 1)  AS share_pct
FROM fact_watch_events f
JOIN dim_content c USING (Content_ID)
GROUP BY c.Genre
ORDER BY watch_hours DESC;

-- Q33 · The top-revenue customer in every country
-- Business: local whales — candidates for VIP retention treatment.
-- Technique: ROW_NUMBER() PARTITION BY country ORDER BY revenue.
WITH ranked AS (
    SELECT u.Country, u.User_ID, s.Subscription_Plan, s.Revenue,
           ROW_NUMBER() OVER (PARTITION BY u.Country
                              ORDER BY s.Revenue DESC) AS rn
    FROM fact_subscriptions s
    JOIN dim_user u USING (User_ID)
)
SELECT Country, User_ID, Subscription_Plan,
       ROUND(Revenue, 0) AS lifetime_revenue
FROM ranked
WHERE rn = 1
ORDER BY Revenue DESC;

-- Q34 · Gateway anime: the first title new users watch
-- Business: acquisition content — what to put on the signed-out homepage.
-- Technique: FIRST_VALUE() over each user's timeline, deduplicated.
WITH firsts AS (
    SELECT DISTINCT User_ID,
           FIRST_VALUE(Content_ID) OVER (PARTITION BY User_ID
                                         ORDER BY Watch_Date) AS first_content
    FROM fact_watch_events
)
SELECT c.Anime_Title, c.Genre,
       COUNT(*) AS users_started_here
FROM firsts
JOIN dim_content c ON c.Content_ID = firsts.first_content
GROUP BY c.Anime_Title, c.Genre
ORDER BY users_started_here DESC
LIMIT 10;

-- Q35 · Daily active users with a 7-day rolling average (June 2026)
-- Business: the ops heartbeat metric, smoothed for weekday/weekend noise.
-- Technique: compute the window over a warm-up buffer (from May 25), then
--            filter to June — filtering first would corrupt the first week's
--            rolling values.
WITH daily AS (
    SELECT DATE(Watch_Date) AS day, COUNT(DISTINCT User_ID) AS dau
    FROM fact_watch_events
    WHERE Watch_Date >= '2026-05-25'
    GROUP BY day
),
windowed AS (
    SELECT day, dau,
           AVG(dau) OVER (ORDER BY day
                          ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS dau_7d
    FROM daily
)
SELECT day, dau, ROUND(dau_7d, 1) AS dau_7d_avg
FROM windowed
WHERE day >= '2026-06-01'
ORDER BY day;

-- Q36 · Monthly active users and their growth (last 12 months)
-- Business: MAU is the investor metric; MoM growth is its derivative.
-- Technique: COUNT(DISTINCT) per month + LAG on the aggregated CTE.
WITH mau AS (
    SELECT strftime('%Y-%m', Watch_Date) AS month,
           COUNT(DISTINCT User_ID) AS mau
    FROM fact_watch_events
    GROUP BY month
)
SELECT month, mau,
       ROUND(100.0 * (mau - LAG(mau) OVER (ORDER BY month))
             / LAG(mau) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM mau
ORDER BY month DESC
LIMIT 12;
