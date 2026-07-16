"""Load the star schema into SQLite — Anime Streaming Platform Analytics.

Reads the cleaned star-schema CSVs from data/processed/ and builds
database/anime_streaming.db with:

- explicitly typed tables (TEXT/INTEGER/REAL) and primary keys
- foreign-key references from facts to dimensions
- indexes on every fact foreign key + the watch timestamp
- boolean columns normalised to 0/1 integers
- post-load referential-integrity checks

Usage
-----
    python scripts/load_database.py        (drops and rebuilds the database)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "processed"
DB_PATH = PROJECT_ROOT / "database" / "anime_streaming.db"

DDL = """
CREATE TABLE dim_user (
    User_ID                TEXT PRIMARY KEY,
    Age                    INTEGER NOT NULL,
    Age_Group              TEXT,
    Gender                 TEXT,
    Country                TEXT,
    Region                 TEXT,
    Language               TEXT,
    Subscription_Plan      TEXT NOT NULL,
    Subscription_Status    TEXT NOT NULL,
    Viewer_Segment         TEXT,
    Engagement_Score       REAL,
    Retention_Status       TEXT,
    Referral_Source        TEXT,
    Payment_Method         TEXT,
    Customer_Satisfaction  INTEGER,
    Support_Tickets        INTEGER
);

CREATE TABLE dim_content (
    Content_ID          INTEGER PRIMARY KEY,
    Anime_Title         TEXT NOT NULL UNIQUE,
    Studio              TEXT,
    Genre               TEXT,
    Episodes_Available  INTEGER,
    Avg_Episode_Length  REAL
);

CREATE TABLE dim_date (
    Date_ID           INTEGER PRIMARY KEY,
    Date              TEXT NOT NULL,
    Year              INTEGER,
    Quarter           INTEGER,
    Month             INTEGER,
    Month_Name        TEXT,
    Day_Name          TEXT,
    Is_Weekend        INTEGER,
    Is_Season_Launch  INTEGER
);

CREATE TABLE fact_subscriptions (
    User_ID                  TEXT PRIMARY KEY REFERENCES dim_user (User_ID),
    Subscription_Plan        TEXT NOT NULL,
    Subscription_Start_Date  TEXT NOT NULL,
    Subscription_End_Date    TEXT,
    Subscription_Status      TEXT NOT NULL,
    Cancellation_Reason      TEXT,
    Monthly_Fee              REAL,
    Membership_Tenure        INTEGER,
    Subscription_Length_Days INTEGER,
    Revenue                  REAL,
    Revenue_Per_Month        REAL
);

CREATE TABLE fact_watch_events (
    Event_ID               INTEGER PRIMARY KEY,
    User_ID                TEXT NOT NULL REFERENCES dim_user (User_ID),
    Content_ID             INTEGER NOT NULL REFERENCES dim_content (Content_ID),
    Date_ID                INTEGER NOT NULL REFERENCES dim_date (Date_ID),
    Watch_Date             TEXT NOT NULL,
    Watch_Hour             INTEGER,
    Peak_Hour              INTEGER,
    Weekend_Viewing        INTEGER,
    Episode_Number         INTEGER,
    Episode_Length         INTEGER,
    Watch_Time_Minutes     REAL,
    Completion_Percentage  REAL,
    Completion_Bucket      TEXT,
    Watch_Session          INTEGER,
    Session_Duration       REAL,
    Device                 TEXT,
    Operating_System       TEXT,
    Internet_Type          TEXT,
    Buffering_Time         REAL,
    User_Rating            REAL,
    "Like"                 INTEGER,
    Share                  INTEGER,
    Download               INTEGER,
    Watchlist              INTEGER,
    Search_Source          TEXT,
    Recommendation_Clicked INTEGER,
    Ad_Shown               INTEGER,
    Ad_Clicked             INTEGER
);

CREATE INDEX idx_fwe_user    ON fact_watch_events (User_ID);
CREATE INDEX idx_fwe_content ON fact_watch_events (Content_ID);
CREATE INDEX idx_fwe_date    ON fact_watch_events (Date_ID);
CREATE INDEX idx_fwe_ts      ON fact_watch_events (Watch_Date);
CREATE INDEX idx_subs_plan   ON fact_subscriptions (Subscription_Plan);
"""

TABLES = ["dim_user", "dim_content", "dim_date", "fact_subscriptions", "fact_watch_events"]

INTEGRITY_CHECKS = {
    "events with unknown user": """
        SELECT COUNT(*) FROM fact_watch_events f
        LEFT JOIN dim_user u USING (User_ID) WHERE u.User_ID IS NULL""",
    "events with unknown content": """
        SELECT COUNT(*) FROM fact_watch_events f
        LEFT JOIN dim_content c USING (Content_ID) WHERE c.Content_ID IS NULL""",
    "events with unknown date": """
        SELECT COUNT(*) FROM fact_watch_events f
        LEFT JOIN dim_date d USING (Date_ID) WHERE d.Date_ID IS NULL""",
    "subscriptions without user": """
        SELECT COUNT(*) FROM fact_subscriptions s
        LEFT JOIN dim_user u USING (User_ID) WHERE u.User_ID IS NULL""",
}


def normalise_booleans(df: pd.DataFrame) -> pd.DataFrame:
    """Convert bool dtypes and 'True'/'False' strings to 0/1 integers."""
    for col in df.columns:
        s = df[col]
        if s.dtype == bool:
            df[col] = s.astype(int)
        elif s.dtype == object and set(s.dropna().unique()) <= {"True", "False"}:
            df[col] = s.map({"True": 1, "False": 0})
    return df


def build() -> Path:
    """Drop and rebuild the SQLite database from the processed CSVs."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(DDL)
        for table in TABLES:
            frame = normalise_booleans(pd.read_csv(PROCESSED / f"{table}.csv"))
            frame.to_sql(table, conn, if_exists="append", index=False)
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<22} {n:>7,} rows")

        print("\nIntegrity checks:")
        failures = 0
        for label, sql in INTEGRITY_CHECKS.items():
            bad = conn.execute(sql).fetchone()[0]
            failures += bad
            print(f"  [{'PASS' if bad == 0 else 'FAIL'}] {label}: {bad}")
        if failures:
            raise RuntimeError("Referential integrity violated — inspect the load.")
        conn.execute("ANALYZE")
    print(f"\nDatabase ready: {DB_PATH}")
    return DB_PATH


if __name__ == "__main__":
    build()
