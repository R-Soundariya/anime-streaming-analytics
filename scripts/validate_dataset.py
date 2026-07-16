"""Validation harness for the generated raw dataset.

Checks two things about data/raw/anime_streaming_raw.csv:

1. REALISM — the business relationships the generator promises actually hold
   (Premium > Free watch time, completion↔rating correlation, buffering hurts
   satisfaction, churn falls with tenure, Shonen dominates, evening/weekend
   peaks, subscriber growth).
2. MESS — the intentional data-quality issues are really present (duplicates,
   missing values, outliers, mixed date formats, category variants, ...).

The raw file is deliberately dirty, so checks run on a lightly-coerced copy
(numeric coercion + category normalisation) — the *real* cleaning is the job
of notebooks/01_data_cleaning.ipynb.

Usage
-----
    python scripts/validate_dataset.py       (exit code 0 = all checks pass)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "anime_streaming_raw.csv"

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str) -> None:
    RESULTS.append((bool(ok), label))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:<42} {detail}")


def light_coerce(raw: pd.DataFrame) -> pd.DataFrame:
    """Minimal, lossy coercion so business checks can run on dirty data."""
    df = raw.copy()
    df["plan"] = df["Subscription_Plan"].astype(str).str.strip().str.title()
    df["watch_min"] = pd.to_numeric(df["Watch_Time_Minutes"], errors="coerce")
    df["completion"] = pd.to_numeric(
        df["Completion_Percentage"].astype(str).str.rstrip("%"), errors="coerce"
    )
    df["rating"] = pd.to_numeric(df["User_Rating"], errors="coerce")
    df["buffering"] = pd.to_numeric(df["Buffering_Time"], errors="coerce")
    df["csat"] = pd.to_numeric(df["Customer_Satisfaction"], errors="coerce")
    df["tenure"] = pd.to_numeric(df["Membership_Tenure"], errors="coerce")
    df["fee"] = pd.to_numeric(
        df["Monthly_Fee"].astype(str).str.lstrip("$"), errors="coerce"
    )
    df["revenue"] = pd.to_numeric(df["Revenue"], errors="coerce")
    df["watch_dt"] = pd.to_datetime(df["Watch_Date"], format="mixed", dayfirst=False, errors="coerce")
    df["sub_start"] = pd.to_datetime(df["Subscription_Start_Date"], format="mixed", errors="coerce")
    # Drop the extreme injected outliers for relationship checks only.
    df.loc[df["watch_min"] > 500, "watch_min"] = np.nan
    df.loc[df["buffering"] < 0, "buffering"] = np.nan
    return df


def business_checks(df: pd.DataFrame) -> None:
    print("\n-- Business realism ------------------------------------------------")

    by_plan = df.groupby("plan")["watch_min"].mean()
    check(by_plan.get("Premium", 0) > by_plan.get("Free", 1e9),
          "Premium watches more than Free",
          f"Premium {by_plan.get('Premium'):.1f} vs Free {by_plan.get('Free'):.1f} min/event")

    r = df[["completion", "rating"]].dropna().corr().iloc[0, 1]
    check(r > 0.25, "Completion correlates with rating", f"r = {r:.2f}")

    r = df[["buffering", "csat"]].dropna().corr().iloc[0, 1]
    check(r < -0.15, "Buffering lowers satisfaction", f"r = {r:.2f}")

    rev = df.groupby("plan")["fee"].mean()
    family_arpu_per_member = rev.get("Family", 0) / 3.5  # avg profiles per family account
    check(rev.get("Family", 0) == rev.max() and family_arpu_per_member < rev.get("Basic", 0),
          "Family: top revenue, lowest ARPU/member",
          f"fee {rev.get('Family'):.2f} vs Basic {rev.get('Basic'):.2f}; "
          f"per-member {family_arpu_per_member:.2f}")

    # Monthly churn hazard by tenure: cancellations in months 1-3 vs 12+,
    # each divided by the users who survived long enough to be at risk.
    u = df.dropna(subset=["tenure"]).drop_duplicates("User_ID")
    cancelled = u["Subscription_Status"].astype(str).str.strip().str.title() == "Cancelled"
    early = (cancelled & (u["tenure"] <= 3)).sum() / max((u["tenure"] >= 1).sum(), 1) / 3
    at_risk_12 = (u["tenure"] >= 12).sum()
    late = (cancelled & (u["tenure"] >= 12)).sum() / max(at_risk_12, 1) / max(
        (u.loc[u["tenure"] >= 12, "tenure"] - 11).mean(), 1
    )
    check(early > late * 1.5, "Churn hazard falls with tenure",
          f"months 1-3: {early:.1%}/mo vs 12+: {late:.1%}/mo")

    genre_share = df.groupby(df["Genre"].astype(str).str.strip())["watch_min"].sum()
    genre_share = genre_share / genre_share.sum()
    check(genre_share.idxmax() == "Shonen", "Shonen dominates watch share",
          f"top genre = {genre_share.idxmax()} ({genre_share.max():.0%})")

    dt = df["watch_dt"].dropna()
    weekend = (dt.dt.weekday >= 5).mean()
    check(weekend > 0.31, "Weekend viewing bias", f"weekend share {weekend:.0%} (baseline 29%)")

    evening = dt.dt.hour.isin([19, 20, 21, 22, 23]).mean()
    check(evening > 0.30, "Evening peak (19:00-23:00)", f"evening share {evening:.0%} (baseline 21%)")

    signups = df.drop_duplicates("User_ID")["sub_start"].dt.year.value_counts().sort_index()
    growing = all(signups.get(y + 1, 0) > signups.get(y, 0) for y in (2023, 2024))
    check(growing, "Subscriber growth 2023->2025",
          " -> ".join(f"{y}: {signups.get(y, 0):,}" for y in (2023, 2024, 2025)))


def mess_checks(raw: pd.DataFrame) -> None:
    print("\n-- Intentional mess ------------------------------------------------")

    check(raw.duplicated().sum() > 100, "Duplicate rows present",
          f"{raw.duplicated().sum():,} duplicates")

    miss = raw[["Age", "Country", "Device", "Language"]].isna().sum().sum()
    check(miss > 1000, "Missing values present", f"{miss:,} NaNs in 4 sampled columns")

    age = pd.to_numeric(raw["Age"], errors="coerce")
    check((age > 120).sum() >= 10, "Age outliers present", f"{(age > 120).sum()} ages > 120")

    wt = pd.to_numeric(raw["Watch_Time_Minutes"], errors="coerce")
    check((wt > 1000).sum() >= 10, "Watch-time outliers present", f"{(wt > 1000).sum()} rows > 1000 min")

    buf = pd.to_numeric(raw["Buffering_Time"], errors="coerce")
    check((buf < 0).sum() >= 10, "Negative buffering present", f"{(buf < 0).sum()} negative rows")

    wd = raw["Watch_Date"].astype(str)
    dmy = wd.str.match(r"\d{2}/\d{2}/\d{4}").sum()
    verbose = wd.str.match(r"[A-Z][a-z]+ \d{1,2}, \d{4}").sum()
    check(dmy > 500 and verbose > 200, "Mixed Watch_Date formats",
          f"{dmy:,} DD/MM/YYYY + {verbose:,} verbose")

    plans = raw["Subscription_Plan"].astype(str)
    variants = (~plans.isin(["Free", "Basic", "Premium", "Family"])).sum()
    check(variants > 1000, "Plan category variants", f"{variants:,} non-canonical values")

    check(raw["Gender"].astype(str).isin(["M", "F", "other"]).sum() > 500,
          "Gender category variants",
          f"{raw['Gender'].astype(str).isin(['M', 'F', 'other']).sum():,} short-form values")

    check(raw["Country"].astype(str).isin(["United States", "U.S."]).sum() > 500,
          "Country spelling variants",
          f"{raw['Country'].astype(str).isin(['United States', 'U.S.']).sum():,} USA variants")

    fee_str = raw["Monthly_Fee"].astype(str).str.startswith("$").sum()
    check(fee_str > 400, "Fee stored as '$x.xx' text", f"{fee_str:,} rows")

    pct_str = raw["Completion_Percentage"].astype(str).str.endswith("%").sum()
    check(pct_str > 400, "Completion stored as 'x%' text", f"{pct_str:,} rows")

    na_str = (raw["User_Rating"].astype(str) == "Not Rated").sum()
    check(na_str > 200, "'Not Rated' rating strings", f"{na_str:,} rows")

    title_ws = (raw["Anime_Title"].astype(str) != raw["Anime_Title"].astype(str).str.strip()).sum()
    check(title_ws > 400, "Stray whitespace in titles", f"{title_ws:,} rows")

    start = pd.to_datetime(raw["Subscription_Start_Date"], format="mixed", errors="coerce")
    end = pd.to_datetime(raw["Subscription_End_Date"], format="mixed", errors="coerce")
    check((end < start).sum() >= 100, "End-before-start subscriptions", f"{(end < start).sum():,} rows")

    wd_parsed = pd.to_datetime(raw["Watch_Date"], format="mixed", errors="coerce")
    future = (wd_parsed > "2026-06-30").sum()
    check(future >= 50, "Future watch dates", f"{future:,} rows past export date")


def main() -> int:
    if not CSV_PATH.exists():
        print(f"Dataset not found: {CSV_PATH}\nRun scripts/generate_dataset.py first.")
        return 1

    raw = pd.read_csv(CSV_PATH, low_memory=False)
    n_rows, n_cols = raw.shape
    print(f"Loaded {n_rows:,} rows x {n_cols} columns from {CSV_PATH.name}")
    check(20_000 <= n_rows <= 50_000, "Row count within 20k-50k", f"{n_rows:,} rows")
    check(n_cols == 41, "All 41 spec columns present", f"{n_cols} columns")

    business_checks(light_coerce(raw))
    mess_checks(raw)

    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{'=' * 68}\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed"
          + (f" -- FAILED: {failed}" if failed else " -- dataset is ready."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
