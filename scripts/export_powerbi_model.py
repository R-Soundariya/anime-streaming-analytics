"""Export the Power BI data model to powerbi/model/.

Produces the eight tables the dashboard suite imports (see
powerbi/dashboard_build_guide.md):

  Star schema  : dim_user, dim_content, dim_date, fact_watch_events, fact_subscriptions
  KPI tables   : kpi_snapshot, kpi_monthly, kpi_by_plan (copied from powerbi/)

The star-schema tables come from data/processed/ with one deliberate change:
dim_date is rebuilt on a FULL calendar (2023-01-01 .. 2026-06-30). The processed
dim_date starts at the first watch event (2023-01-27), but Power BI date tables
must span whole years/months for time-intelligence DAX, and kpi_monthly keys on
month-start dates that would otherwise be missing.

Run after the pipeline (generate_dataset.py -> 01 notebook -> 04 notebook):
    .venv\\Scripts\\python.exe scripts\\export_powerbi_model.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
POWERBI = ROOT / "powerbi"
MODEL = POWERBI / "model"

CALENDAR_START = "2023-01-01"
CALENDAR_END = "2026-06-30"


def build_full_calendar(processed_dim_date: pd.DataFrame) -> pd.DataFrame:
    """Full-month calendar with the same columns as the processed dim_date.

    Is_Season_Launch is a property of the month; recover the month flags from
    the processed table and apply them to every day of the full calendar.
    """
    launch_months = (processed_dim_date
                     .assign(_m=processed_dim_date["Date"].dt.to_period("M"))
                     .groupby("_m")["Is_Season_Launch"].max())

    cal = pd.DataFrame({"Date": pd.date_range(CALENDAR_START, CALENDAR_END, freq="D")})
    cal["Date_ID"] = cal["Date"].dt.strftime("%Y%m%d").astype(int)
    cal["Year"] = cal["Date"].dt.year
    cal["Quarter"] = cal["Date"].dt.quarter
    cal["Month"] = cal["Date"].dt.month
    cal["Month_Name"] = cal["Date"].dt.month_name()
    cal["Day_Name"] = cal["Date"].dt.day_name()
    cal["Is_Weekend"] = cal["Date"].dt.dayofweek >= 5
    cal["Is_Season_Launch"] = (cal["Date"].dt.to_period("M").map(launch_months)
                               .fillna(False).astype(bool))
    # Month_Start lets kpi_monthly[Month] relate to the date table cleanly
    cal["Month_Start"] = cal["Date"].dt.to_period("M").dt.start_time
    return cal[["Date_ID", "Date", "Year", "Quarter", "Month", "Month_Name",
                "Day_Name", "Is_Weekend", "Is_Season_Launch", "Month_Start"]]


def main() -> int:
    MODEL.mkdir(exist_ok=True)

    dim_user = pd.read_csv(PROCESSED / "dim_user.csv")
    dim_content = pd.read_csv(PROCESSED / "dim_content.csv")
    dim_date_processed = pd.read_csv(PROCESSED / "dim_date.csv", parse_dates=["Date"])
    fact_events = pd.read_csv(PROCESSED / "fact_watch_events.csv", parse_dates=["Watch_Date"])
    fact_subs = pd.read_csv(PROCESSED / "fact_subscriptions.csv",
                            parse_dates=["Subscription_Start_Date", "Subscription_End_Date"])

    dim_date = build_full_calendar(dim_date_processed)

    tables = {
        "dim_user": dim_user,
        "dim_content": dim_content,
        "dim_date": dim_date,
        "fact_watch_events": fact_events,
        "fact_subscriptions": fact_subs,
        "kpi_snapshot": pd.read_csv(POWERBI / "kpi_snapshot.csv"),
        "kpi_monthly": pd.read_csv(POWERBI / "kpi_monthly.csv", parse_dates=["Month"]),
        "kpi_by_plan": pd.read_csv(POWERBI / "kpi_by_plan.csv"),
    }

    # ---- referential integrity: every foreign key must land in its dimension ----
    checks = [
        ("fact_watch_events.Date_ID -> dim_date",
         fact_events["Date_ID"].isin(dim_date["Date_ID"]).all()),
        ("fact_watch_events.User_ID -> dim_user",
         fact_events["User_ID"].isin(dim_user["User_ID"]).all()),
        ("fact_watch_events.Content_ID -> dim_content",
         fact_events["Content_ID"].isin(dim_content["Content_ID"]).all()),
        ("fact_subscriptions.User_ID -> dim_user (1:1)",
         fact_subs["User_ID"].isin(dim_user["User_ID"]).all()
         and fact_subs["User_ID"].is_unique),
        ("kpi_monthly.Month -> dim_date.Date",
         tables["kpi_monthly"]["Month"].isin(dim_date["Date"]).all()),
        ("dim_date spans full months",
         dim_date["Date"].min() == pd.Timestamp(CALENDAR_START)
         and dim_date["Date"].max() == pd.Timestamp(CALENDAR_END)
         and len(dim_date) == (pd.Timestamp(CALENDAR_END) - pd.Timestamp(CALENDAR_START)).days + 1),
    ]

    failed = 0
    print("REFERENTIAL INTEGRITY")
    for name, ok in checks:
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print(f"*** {failed} check(s) failed - model NOT exported ***")
        return 1

    print()
    print("EXPORT -> powerbi/model/")
    for name, df in tables.items():
        path = MODEL / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  {name + '.csv':24s} {len(df):>7,} rows x {df.shape[1]:>2} cols "
              f"({path.stat().st_size / 1024:,.0f} KB)")
    print()
    print("Done. Point Power BI's Folder connector at powerbi/model/ "
          "(see dashboard_build_guide.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
