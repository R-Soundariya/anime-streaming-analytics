"""Synthetic dataset generator — Anime Streaming Platform Analytics.

Produces the raw, intentionally messy "company data export" that the rest of
the portfolio project cleans and analyses:

    data/raw/anime_streaming_raw.csv     (~40,000 watch-event rows, 41 columns)
    data/raw/injection_report.json       (answer key: counts of injected issues)

Design principles
-----------------
1. Behaviour first, mess second. Clean, internally consistent data is
   simulated from user personas and a content catalogue, so real business
   relationships hold (Premium watches more than Free, buffering hurts
   satisfaction, churn hazard falls with tenure, Shonen dominates watch
   share, evenings/weekends peak, ...). Data-quality issues are injected
   afterwards at controlled, documented rates.
2. Reproducible. A single RNG seed drives everything; re-running the script
   produces an identical file.
3. Event grain. One row = one watch event; user- and subscription-level
   attributes are denormalised onto every row, exactly like a typical messy
   warehouse export handed to an analyst.

Usage
-----
    python scripts/generate_dataset.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

SEED = 42
N_USERS = 8_000
TARGET_EVENTS = 40_000
WINDOW_START = pd.Timestamp("2023-01-01")
WINDOW_END = pd.Timestamp("2026-06-30")  # "export date" of the dataset

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CSV_PATH = RAW_DIR / "anime_streaming_raw.csv"
REPORT_PATH = RAW_DIR / "injection_report.json"

PLAN_FEES = {"Free": 0.0, "Basic": 4.99, "Premium": 9.99, "Family": 14.99}
PLAN_WEIGHTS = {"Free": 0.40, "Basic": 0.25, "Premium": 0.25, "Family": 0.10}
# Multipliers that drive how much each plan watches (Family = shared account).
PLAN_WATCH_MULT = {"Free": 0.6, "Basic": 1.0, "Premium": 1.5, "Family": 1.8}
# Multipliers on monthly churn hazard (paid annual-ish commitment => stickier).
PLAN_CHURN_MULT = {"Free": 1.25, "Basic": 1.15, "Premium": 0.80, "Family": 0.60}

# country: (region, weight, {audio language: prob})
COUNTRIES: dict[str, tuple[str, float, dict[str, float]]] = {
    "USA":          ("North America", 0.22, {"Japanese": 0.45, "English": 0.55}),
    "Japan":        ("Asia",          0.13, {"Japanese": 1.00}),
    "India":        ("Asia",          0.12, {"Japanese": 0.35, "English": 0.40, "Hindi": 0.25}),
    "Brazil":       ("South America", 0.09, {"Japanese": 0.45, "Portuguese": 0.55}),
    "Mexico":       ("North America", 0.06, {"Japanese": 0.40, "Spanish": 0.60}),
    "Philippines":  ("Asia",          0.06, {"Japanese": 0.40, "English": 0.60}),
    "UK":           ("Europe",        0.06, {"Japanese": 0.50, "English": 0.50}),
    "Indonesia":    ("Asia",          0.05, {"Japanese": 0.50, "English": 0.50}),
    "Canada":       ("North America", 0.05, {"Japanese": 0.45, "English": 0.55}),
    "Germany":      ("Europe",        0.05, {"Japanese": 0.55, "German": 0.45}),
    "France":       ("Europe",        0.05, {"Japanese": 0.50, "French": 0.50}),
    "Australia":    ("Oceania",       0.03, {"Japanese": 0.45, "English": 0.55}),
    "South Korea":  ("Asia",          0.03, {"Japanese": 0.50, "Korean": 0.50}),
}

DEVICES = ["Mobile", "Smart TV", "Desktop", "Tablet"]
DEVICE_OS = {
    "Mobile":   (["Android", "iOS"], [0.62, 0.38]),
    "Smart TV": (["Android TV", "Tizen", "webOS"], [0.45, 0.30, 0.25]),
    "Desktop":  (["Windows", "macOS"], [0.72, 0.28]),
    "Tablet":   (["Android", "iPadOS"], [0.55, 0.45]),
}
DEVICE_INTERNET = {
    "Mobile":   (["Mobile Data", "Broadband", "Fiber", "Satellite"], [0.55, 0.20, 0.20, 0.05]),
    "Smart TV": (["Fiber", "Broadband", "Mobile Data", "Satellite"], [0.45, 0.45, 0.05, 0.05]),
    "Desktop":  (["Fiber", "Broadband", "Satellite"], [0.50, 0.45, 0.05]),
    "Tablet":   (["Broadband", "Fiber", "Mobile Data", "Satellite"], [0.35, 0.30, 0.30, 0.05]),
}
# Mean buffering seconds per event by connection quality.
INTERNET_BUFFER_BASE = {"Fiber": 3.0, "Broadband": 6.0, "Mobile Data": 14.0, "Satellite": 22.0}
# Completion adjustment by device (big screen => fewer abandoned episodes).
DEVICE_COMPLETION_ADJ = {"Smart TV": 7.0, "Desktop": 3.0, "Tablet": 0.0, "Mobile": -5.0}

SEARCH_SOURCES = ["Browse", "Search Bar", "Recommendation", "Watchlist", "Trending"]
SEARCH_SOURCE_W = [0.30, 0.25, 0.22, 0.13, 0.10]
REFERRALS = ["Social Media", "Friend Referral", "Google Search", "YouTube", "Advertisement", "App Store"]
REFERRAL_W = [0.28, 0.22, 0.18, 0.14, 0.12, 0.06]
CANCEL_REASONS = [
    "Too Expensive", "Not Enough Content", "Technical Issues",
    "Switched to Competitor", "Lost Interest", "Payment Failure",
]
SEASON_LAUNCH_MONTHS = {1, 4, 7, 10}  # anime seasons => viewing bumps
HOUR_WEIGHTS = np.array(
    [1.0, 0.5, 0.3, 0.2, 0.2, 0.3, 0.8, 1.5, 2.0, 2.0, 2.2, 2.5,
     3.0, 3.0, 2.5, 2.5, 3.0, 4.0, 5.0, 7.0, 8.0, 8.0, 7.0, 4.0]
)  # evening peak 19:00-23:00


@dataclass(frozen=True)
class Anime:
    title: str
    studio: str
    genre: str
    episodes: int
    quality: float  # latent critical quality on a 1-10 scale


# Ordered roughly by real-world popularity; selection weight ~ 1/rank^0.75,
# so top Shonen titles dominate watch share (Zipf-like long tail).
CATALOG: list[Anime] = [
    Anime("One Piece", "Toei Animation", "Shonen", 1000, 8.9),
    Anime("Attack on Titan", "MAPPA", "Shonen", 87, 9.1),
    Anime("Demon Slayer: Kimetsu no Yaiba", "Ufotable", "Shonen", 55, 8.8),
    Anime("Jujutsu Kaisen", "MAPPA", "Shonen", 47, 8.7),
    Anime("My Hero Academia", "Bones", "Shonen", 138, 8.0),
    Anime("Naruto Shippuden", "Studio Pierrot", "Shonen", 500, 8.3),
    Anime("Solo Leveling", "A-1 Pictures", "Fantasy", 25, 8.6),
    Anime("Chainsaw Man", "MAPPA", "Shonen", 12, 8.6),
    Anime("Spy x Family", "Wit Studio", "Slice of Life", 37, 8.5),
    Anime("Frieren: Beyond Journey's End", "Madhouse", "Fantasy", 28, 9.2),
    Anime("Bleach: Thousand-Year Blood War", "Studio Pierrot", "Shonen", 26, 8.9),
    Anime("One Punch Man", "Madhouse", "Shonen", 24, 8.6),
    Anime("Hunter x Hunter", "Madhouse", "Shonen", 148, 9.0),
    Anime("Fullmetal Alchemist: Brotherhood", "Bones", "Shonen", 64, 9.1),
    Anime("Death Note", "Madhouse", "Thriller", 37, 8.9),
    Anime("Sword Art Online", "A-1 Pictures", "Isekai", 96, 7.5),
    Anime("Re:Zero - Starting Life in Another World", "White Fox", "Isekai", 50, 8.4),
    Anime("That Time I Got Reincarnated as a Slime", "8bit", "Isekai", 72, 8.1),
    Anime("Mushoku Tensei: Jobless Reincarnation", "Studio Bind", "Isekai", 48, 8.4),
    Anime("Overlord", "Madhouse", "Isekai", 52, 7.9),
    Anime("KonoSuba", "Studio Deen", "Isekai", 33, 8.2),
    Anime("Vinland Saga", "MAPPA", "Seinen", 48, 8.8),
    Anime("Oshi no Ko", "Doga Kobo", "Seinen", 24, 8.6),
    Anime("Tokyo Ghoul", "Studio Pierrot", "Seinen", 48, 7.8),
    Anime("Monster", "Madhouse", "Seinen", 74, 8.9),
    Anime("Hell's Paradise", "MAPPA", "Seinen", 13, 8.2),
    Anime("Haikyu!!", "Production I.G", "Sports", 85, 8.7),
    Anime("Blue Lock", "8bit", "Sports", 38, 8.3),
    Anime("Kuroko's Basketball", "Production I.G", "Sports", 75, 8.2),
    Anime("Kaguya-sama: Love Is War", "A-1 Pictures", "Romance", 37, 8.6),
    Anime("Horimiya", "CloverWorks", "Romance", 26, 8.2),
    Anime("My Dress-Up Darling", "CloverWorks", "Romance", 12, 8.3),
    Anime("Your Lie in April", "A-1 Pictures", "Romance", 22, 8.7),
    Anime("Fruits Basket", "TMS Entertainment", "Shojo", 63, 8.5),
    Anime("Ouran High School Host Club", "Bones", "Shojo", 26, 8.2),
    Anime("Kimi ni Todoke", "Production I.G", "Shojo", 38, 8.0),
    Anime("Violet Evergarden", "Kyoto Animation", "Slice of Life", 13, 8.7),
    Anime("K-On!", "Kyoto Animation", "Slice of Life", 39, 8.0),
    Anime("Bocchi the Rock!", "CloverWorks", "Slice of Life", 12, 8.6),
    Anime("Barakamon", "Kinema Citrus", "Slice of Life", 12, 8.2),
    Anime("The Apothecary Diaries", "OLM", "Seinen", 48, 8.9),
    Anime("Made in Abyss", "Kinema Citrus", "Fantasy", 25, 8.7),
    Anime("Delicious in Dungeon", "Studio Trigger", "Fantasy", 24, 8.5),
    Anime("Ranking of Kings", "Wit Studio", "Fantasy", 23, 8.6),
    Anime("Mob Psycho 100", "Bones", "Comedy", 37, 8.6),
    Anime("Gintama", "Sunrise", "Comedy", 367, 8.9),
    Anime("The Disastrous Life of Saiki K.", "J.C.Staff", "Comedy", 120, 8.4),
    Anime("Grand Blue", "Zero-G", "Comedy", 12, 8.4),
    Anime("Steins;Gate", "White Fox", "Thriller", 24, 9.0),
    Anime("The Promised Neverland", "CloverWorks", "Thriller", 23, 8.3),
    Anime("Erased", "A-1 Pictures", "Thriller", 12, 8.3),
    Anime("Parasyte: The Maxim", "Madhouse", "Horror", 24, 8.3),
    Anime("Another", "P.A. Works", "Horror", 12, 7.5),
    Anime("Higurashi: When They Cry", "Passione", "Horror", 26, 7.9),
    Anime("Neon Genesis Evangelion", "Gainax", "Mecha", 26, 8.5),
    Anime("Code Geass", "Sunrise", "Mecha", 50, 8.7),
    Anime("Mobile Suit Gundam: The Witch from Mercury", "Sunrise", "Mecha", 24, 8.1),
    Anime("86 Eighty-Six", "A-1 Pictures", "Mecha", 23, 8.6),
    Anime("Cyberpunk: Edgerunners", "Studio Trigger", "Seinen", 10, 8.6),
    Anime("Dandadan", "Science SARU", "Shonen", 12, 8.7),
    Anime("Dr. Stone", "TMS Entertainment", "Shonen", 58, 8.3),
    Anime("Black Clover", "Studio Pierrot", "Shonen", 170, 7.9),
    Anime("Fire Force", "David Production", "Shonen", 48, 7.8),
    Anime("Tokyo Revengers", "LIDENFILMS", "Shonen", 50, 7.9),
]

# Injection rates for data-quality issues (documented in docs/data_dictionary.md).
MESS = {
    "duplicate_rate": 0.010,
    "missing_rates": {
        "Age": 0.030, "Country": 0.020, "Device": 0.025, "Language": 0.030,
        "Watch_Time_Minutes": 0.015, "Genre": 0.020, "Payment_Method": 0.020,
        "Operating_System": 0.015,
    },
    "age_outliers": 30,
    "watch_time_outliers": 25,
    "negative_buffering": 20,
    "end_before_start_rate": 0.005,
    "future_watch_rate": 0.003,
    "date_format_dmy_rate": 0.040,
    "date_format_verbose_rate": 0.020,
    "sub_date_dmy_rate": 0.030,
    "fee_dollar_rate": 0.020,
    "completion_pct_rate": 0.020,
    "episode_float_str_rate": 0.020,
    "plan_variant_rate": 0.070,
    "gender_variant_rate": 0.040,
    "country_variant_rate": 0.030,
    "device_variant_rate": 0.030,
    "whitespace_rate": 0.020,
    "rating_na_string_rate": 0.010,
    "incomplete_session_rate": 0.015,
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def weighted_choice(rng: np.random.Generator, options: list[str], weights: list[float], size: int) -> np.ndarray:
    """Vectorised categorical sampling with normalised weights."""
    p = np.asarray(weights, dtype=float)
    return rng.choice(options, size=size, p=p / p.sum())


def choice_by_group(
    rng: np.random.Generator,
    group_values: np.ndarray,
    mapping: dict[str, tuple[list[str], list[float]]],
    size: int,
) -> np.ndarray:
    """Sample a categorical column whose distribution depends on another column.

    e.g. Operating_System conditioned on Device.
    """
    out = np.empty(size, dtype=object)
    for group, (options, weights) in mapping.items():
        mask = group_values == group
        n = int(mask.sum())
        if n:
            out[mask] = weighted_choice(rng, options, weights, n)
    return out


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------

def generate_users(rng: np.random.Generator) -> pd.DataFrame:
    """Create N_USERS personas with demographics, plan, and latent behaviour traits.

    Latent traits (engagement, buffer_proneness) are what create realistic
    correlations downstream — they influence watch volume, completion,
    ratings, satisfaction, support tickets and churn simultaneously.
    """
    n = N_USERS

    # Age: mixture of young-core, mid, and older segments.
    seg = rng.choice([0, 1, 2], size=n, p=[0.60, 0.30, 0.10])
    age = np.where(seg == 0, rng.normal(24, 6, n),
                   np.where(seg == 1, rng.normal(33, 8, n), rng.normal(45, 10, n)))
    age = np.clip(np.round(age), 13, 70).astype(int)

    gender = weighted_choice(rng, ["Male", "Female", "Other"], [0.54, 0.41, 0.05], n)

    country_names = list(COUNTRIES)
    country = weighted_choice(rng, country_names, [COUNTRIES[c][1] for c in country_names], n)
    region = np.array([COUNTRIES[c][0] for c in country])

    plan = weighted_choice(rng, list(PLAN_WEIGHTS), list(PLAN_WEIGHTS.values()), n)
    fee = np.array([PLAN_FEES[p] for p in plan])

    # Engagement in (0, 1): paid plans skew higher (self-selection).
    engagement = rng.beta(2.2, 2.8, n)
    engagement *= np.array([{"Free": 0.80, "Basic": 1.00, "Premium": 1.20, "Family": 1.25}[p] for p in plan])
    engagement = np.clip(engagement, 0.05, 0.98)

    # Proneness to buffering (bad ISP / congested network), in (0, 1).
    buffer_prone = rng.beta(2.0, 5.0, n)

    # Sign-up dates skewed toward the recent past => subscriber growth trend.
    total_days = (WINDOW_END - WINDOW_START).days
    start_day = np.floor(total_days * rng.random(n) ** 0.55).astype(int)
    sub_start = WINDOW_START + pd.to_timedelta(start_day, unit="D")

    # Primary device skews by age (younger => mobile).
    p_mobile = np.clip(0.75 - (age - 18) * 0.012, 0.15, 0.75)
    device_pref = np.empty(n, dtype=object)
    u = rng.random(n)
    rest = weighted_choice(rng, ["Smart TV", "Desktop", "Tablet"], [0.45, 0.40, 0.15], n)
    device_pref[:] = np.where(u < p_mobile, "Mobile", rest)

    # Audio language conditioned on country.
    language = np.empty(n, dtype=object)
    for c, (_, _, langs) in COUNTRIES.items():
        mask = country == c
        if mask.sum():
            language[mask] = weighted_choice(rng, list(langs), list(langs.values()), int(mask.sum()))

    payment = np.empty(n, dtype=object)
    free_mask = plan == "Free"
    payment[free_mask] = "None"
    india_paid = (~free_mask) & (country == "India")
    other_paid = (~free_mask) & (country != "India")
    payment[india_paid] = weighted_choice(rng, ["UPI", "Credit Card", "Debit Card", "PayPal"],
                                          [0.50, 0.20, 0.20, 0.10], int(india_paid.sum()))
    payment[other_paid] = weighted_choice(rng, ["Credit Card", "Debit Card", "PayPal", "Gift Card"],
                                          [0.45, 0.25, 0.20, 0.10], int(other_paid.sum()))

    referral = weighted_choice(rng, REFERRALS, REFERRAL_W, n)

    # Favourite genre sampled from global genre popularity (drives title choice).
    genre_w = pd.Series([1 / (i + 1) ** 0.75 for i in range(len(CATALOG))],
                        index=[a.genre for a in CATALOG]).groupby(level=0).sum()
    fav_genre = weighted_choice(rng, list(genre_w.index), list(genre_w.values), n)

    return pd.DataFrame({
        "user_id": [f"U{i:05d}" for i in range(1, n + 1)],
        "age": age, "gender": gender, "country": country, "region": region,
        "plan": plan, "fee": fee, "engagement": engagement, "buffer_prone": buffer_prone,
        "sub_start": sub_start, "device_pref": device_pref, "language": language,
        "payment": payment, "referral": referral, "fav_genre": fav_genre,
    })


def simulate_churn(rng: np.random.Generator, users: pd.DataFrame) -> pd.DataFrame:
    """Month-by-month churn simulation with hazard falling as tenure grows.

    Hazard ≈ 13%/month in month 1 decaying to ~3%/month floor, scaled by
    plan stickiness, engagement, and buffering pain. This produces the
    classic streaming pattern: churn concentrates in the first 3 months and
    long-tenure subscribers are the most loyal.
    """
    n = len(users)
    max_months = np.maximum(
        1, ((WINDOW_END - users["sub_start"]).dt.days / 30.44).astype(int).to_numpy()
    )
    plan_f = users["plan"].map(PLAN_CHURN_MULT).to_numpy()
    eng_f = 1.45 - 0.9 * users["engagement"].to_numpy()
    buf_f = 1.0 + 0.6 * users["buffer_prone"].to_numpy()

    churn_month = np.zeros(n, dtype=int)  # 0 => still active
    alive = np.ones(n, dtype=bool)
    for m in range(1, int(max_months.max()) + 1):
        base = 0.028 + 0.10 * np.exp(-0.35 * (m - 1))
        hazard = np.clip(base * plan_f * eng_f * buf_f, 0, 0.5)
        eligible = alive & (max_months >= m)
        churned_now = eligible & (rng.random(n) < hazard)
        churn_month[churned_now] = m
        alive &= ~churned_now

    churned = churn_month > 0
    tenure = np.where(churned, churn_month, max_months)
    sub_end = users["sub_start"] + pd.to_timedelta((churn_month * 30.44).round(), unit="D")
    sub_end = sub_end.where(pd.Series(churned, index=users.index), pd.NaT)
    sub_end = sub_end.clip(upper=WINDOW_END)

    users = users.copy()
    users["status"] = np.where(churned, "Cancelled", "Active")
    users["sub_end"] = sub_end
    users["tenure_months"] = tenure

    # Cancellation reason, weighted by each churner's traits.
    eng = users["engagement"].to_numpy()
    paid = (users["fee"] > 0).to_numpy().astype(float)
    weights = np.column_stack([
        paid * (1.2 - eng),                                # Too Expensive
        np.full(n, 0.6),                                   # Not Enough Content
        0.4 + 2.2 * users["buffer_prone"].to_numpy(),      # Technical Issues
        np.full(n, 0.5),                                   # Switched to Competitor
        0.4 + (1 - eng),                                   # Lost Interest
        paid * 0.25,                                       # Payment Failure
    ])
    weights = np.clip(weights, 1e-6, None)
    cum = np.cumsum(weights / weights.sum(axis=1, keepdims=True), axis=1)
    picks = (rng.random((n, 1)) > cum).sum(axis=1)
    users["cancel_reason"] = np.where(churned, np.array(CANCEL_REASONS)[picks], None)

    # Lifetime revenue to date: subscription fees, or ad revenue for Free users.
    ad_rev = np.round(0.8 * tenure * (0.5 + eng), 2)
    users["revenue"] = np.where(paid.astype(bool), np.round(users["fee"] * tenure, 2), ad_rev)

    # Support load and satisfaction driven by the same latent traits.
    users["support_tickets"] = rng.poisson(0.25 + 1.7 * users["buffer_prone"].to_numpy())
    csat = 7.4 + 2.1 * eng - 3.4 * users["buffer_prone"].to_numpy() \
        - 0.35 * users["support_tickets"].to_numpy() + rng.normal(0, 0.7, n)
    users["satisfaction"] = np.clip(np.round(csat), 1, 10).astype(int)
    return users


def generate_events(rng: np.random.Generator, users: pd.DataFrame) -> pd.DataFrame:
    """Simulate watch events at TARGET_EVENTS scale, one row per episode watched."""
    # --- allocate events per user: tenure x plan behaviour x engagement ----
    score = (
        users["tenure_months"].to_numpy()
        * users["plan"].map(PLAN_WATCH_MULT).to_numpy()
        * (0.25 + users["engagement"].to_numpy())
    )
    counts = np.maximum(1, np.round(score * TARGET_EVENTS / score.sum()).astype(int))
    idx = np.repeat(np.arange(len(users)), counts)
    ev = users.iloc[idx].reset_index(drop=True)
    n = len(ev)

    # --- title choice: 65% from favourite genre, else global popularity ----
    global_w = np.array([1 / (i + 1) ** 0.75 for i in range(len(CATALOG))])
    global_w /= global_w.sum()
    genres = np.array([a.genre for a in CATALOG])
    title_idx = rng.choice(len(CATALOG), size=n, p=global_w)
    use_fav = rng.random(n) < 0.65
    for g in np.unique(genres):
        g_idx = np.flatnonzero(genres == g)
        g_w = global_w[g_idx] / global_w[g_idx].sum()
        mask = use_fav & (ev["fav_genre"].to_numpy() == g)
        if mask.sum():
            title_idx[mask] = rng.choice(g_idx, size=int(mask.sum()), p=g_w)

    quality = np.array([CATALOG[i].quality for i in title_idx])
    n_eps = np.array([CATALOG[i].episodes for i in title_idx])
    ep_length = np.clip(rng.normal(23, 1.5, n).round(), 20, 26).astype(int)
    # Early episodes get watched more than late ones (drop-off along a series).
    episode = 1 + np.floor(rng.random(n) ** 1.5 * (n_eps - 1)).astype(int)

    # --- watch timestamp: within active sub, season/weekend/evening bias ---
    start_day = (ev["sub_start"] - WINDOW_START).dt.days.to_numpy()
    end = ev["sub_end"].fillna(WINDOW_END)
    active_days = np.maximum((end - ev["sub_start"]).dt.days.to_numpy(), 1)

    def sample_offsets() -> np.ndarray:
        return np.floor(rng.random(n) * active_days).astype(int)

    off1, off2 = sample_offsets(), sample_offsets()
    m1 = pd.Series(WINDOW_START + pd.to_timedelta(start_day + off1, unit="D")).dt.month.to_numpy()
    m2 = pd.Series(WINDOW_START + pd.to_timedelta(start_day + off2, unit="D")).dt.month.to_numpy()
    in_season1 = np.isin(m1, list(SEASON_LAUNCH_MONTHS))
    in_season2 = np.isin(m2, list(SEASON_LAUNCH_MONTHS))
    offset = np.where(~in_season1 & in_season2 & (rng.random(n) < 0.6), off2, off1)

    # Weekend bias: shift ~30% of weekday events to the following Saturday.
    abs_day = start_day + offset
    dow = (WINDOW_START.weekday() + abs_day) % 7  # Mon=0 .. Sun=6
    shift = (5 - dow) % 7
    shifted = offset + shift
    move = (dow < 5) & (rng.random(n) < 0.30) & (shifted <= active_days - 1)
    offset = np.where(move, shifted, offset)

    hour = rng.choice(24, size=n, p=HOUR_WEIGHTS / HOUR_WEIGHTS.sum())
    minute = rng.integers(0, 60, n)
    watch_dt = (WINDOW_START + pd.to_timedelta(start_day + offset, unit="D")
                + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m"))

    # --- device / network / streaming quality --------------------------------
    device = ev["device_pref"].to_numpy().copy()
    switch = rng.random(n) < 0.30
    device[switch] = rng.choice(DEVICES, size=int(switch.sum()))
    os_ = choice_by_group(rng, device, DEVICE_OS, n)
    internet = choice_by_group(rng, device, DEVICE_INTERNET, n)

    buf_base = pd.Series(internet).map(INTERNET_BUFFER_BASE).to_numpy()
    buffering = buf_base * (0.4 + 2.0 * ev["buffer_prone"].to_numpy()) * rng.lognormal(0, 0.4, n)
    buffering = np.clip(buffering, 0, 180).round(1)

    # --- engagement outcomes: completion -> watch time -> rating -------------
    eng = ev["engagement"].to_numpy()
    dev_adj = pd.Series(device).map(DEVICE_COMPLETION_ADJ).to_numpy()
    completion = 38 + 46 * eng + 2.5 * (quality - 8.2) + dev_adj - 0.30 * buffering \
        + rng.normal(0, 11, n)
    completion = np.clip(completion, 2, 100).round(1)

    watch_time = np.clip(ep_length * completion / 100 + rng.normal(0, 1, n), 0.5, ep_length).round(1)

    rated = rng.random(n) < (0.32 + 0.25 * eng)
    rating_val = np.clip(
        np.round(quality + (completion - 70) / 13 - buffering / 45 + rng.normal(0, 0.9, n)), 1, 10
    )
    rating = np.where(rated, rating_val, np.nan)

    sessions = np.clip(1 + rng.poisson(0.4 + 1.6 * eng), 1, 6)
    session_dur = np.clip(watch_time * (1 + 0.9 * rng.random(n)) + rng.random(n) * 8, 5, 300).round(1)

    like = (rng.random(n) < np.clip(0.03 + 0.20 * eng + 0.08 * (completion > 85), 0, 1)).astype(int)
    share = (rng.random(n) < (0.01 + 0.05 * eng)).astype(int)
    paid = (ev["fee"] > 0).to_numpy()
    download = (rng.random(n) < np.where(paid, 0.05 + 0.15 * eng, 0.01)).astype(int)
    watchlist = (rng.random(n) < (0.08 + 0.20 * eng)).astype(int)

    search_source = weighted_choice(rng, SEARCH_SOURCES, SEARCH_SOURCE_W, n)
    rec_clicked = np.where(search_source == "Recommendation", 1,
                           (rng.random(n) < 0.05).astype(int))
    ad_shown = np.where(~paid, (rng.random(n) < 0.92).astype(int), 0)
    ad_clicked = np.where(ad_shown == 1, (rng.random(n) < 0.08).astype(int), 0)

    return pd.DataFrame({
        "User_ID": ev["user_id"],
        "Age": ev["age"],
        "Gender": ev["gender"],
        "Country": ev["country"],
        "Region": ev["region"],
        "Subscription_Plan": ev["plan"],
        "Subscription_Start_Date": ev["sub_start"],
        "Subscription_End_Date": ev["sub_end"],
        "Subscription_Status": ev["status"],
        "Cancellation_Reason": ev["cancel_reason"],
        "Monthly_Fee": ev["fee"],
        "Revenue": ev["revenue"],
        "Anime_Title": [CATALOG[i].title for i in title_idx],
        "Studio": [CATALOG[i].studio for i in title_idx],
        "Genre": [CATALOG[i].genre for i in title_idx],
        "Episode_Number": episode,
        "Episode_Length": ep_length,
        "Watch_Date": watch_dt,
        "Watch_Time_Minutes": watch_time,
        "Completion_Percentage": completion,
        "Watch_Session": sessions,
        "Device": device,
        "Operating_System": os_,
        "Internet_Type": internet,
        "Language": ev["language"],
        "User_Rating": rating,
        "Like": like,
        "Share": share,
        "Download": download,
        "Watchlist": watchlist,
        "Search_Source": search_source,
        "Recommendation_Clicked": rec_clicked,
        "Ad_Shown": ad_shown,
        "Ad_Clicked": ad_clicked,
        "Buffering_Time": buffering,
        "Session_Duration": session_dur,
        "Membership_Tenure": ev["tenure_months"],
        "Payment_Method": ev["payment"],
        "Support_Tickets": ev["support_tickets"],
        "Customer_Satisfaction": ev["satisfaction"],
        "Referral_Source": ev["referral"],
    })


# --------------------------------------------------------------------------
# Mess injection
# --------------------------------------------------------------------------

def inject_mess(rng: np.random.Generator, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Corrupt the clean simulation at documented rates; return df + answer key.

    Order matters: value-level corruption first, then formats/strings, then
    duplicates (so duplicated rows are exact copies of already-messy rows),
    then a full shuffle.
    """
    df = df.copy()
    report: dict[str, int] = {}
    n = len(df)

    def sample(k: int | float) -> np.ndarray:
        size = int(k if k >= 1 else round(k * n))
        return rng.choice(n, size=min(size, n), replace=False)

    # -- outliers -----------------------------------------------------------
    i = sample(MESS["age_outliers"])
    df.loc[i, "Age"] = rng.integers(150, 300, len(i))
    report["age_outliers"] = len(i)

    i = sample(MESS["watch_time_outliers"])
    df.loc[i, "Watch_Time_Minutes"] = rng.integers(2000, 6000, len(i)).astype(float)
    report["watch_time_outliers"] = len(i)

    i = sample(MESS["negative_buffering"])
    df.loc[i, "Buffering_Time"] = -rng.integers(5, 50, len(i)).astype(float)
    report["negative_buffering"] = len(i)

    # -- impossible dates -----------------------------------------------------
    cancelled = np.flatnonzero((df["Subscription_Status"] == "Cancelled").to_numpy())
    i = rng.choice(cancelled, size=round(MESS["end_before_start_rate"] * n), replace=False)
    df.loc[i, "Subscription_End_Date"] = (
        df.loc[i, "Subscription_Start_Date"] - pd.to_timedelta(rng.integers(10, 400, len(i)), unit="D")
    )
    report["end_before_start"] = len(i)

    i = sample(MESS["future_watch_rate"])
    df.loc[i, "Watch_Date"] = df.loc[i, "Watch_Date"] + pd.to_timedelta(
        rng.integers(200, 600, len(i)), unit="D"
    )
    report["future_watch_dates"] = len(i)

    # -- missing values -------------------------------------------------------
    for col, rate in MESS["missing_rates"].items():
        i = sample(rate)
        df.loc[i, col] = np.nan
        report[f"missing_{col}"] = len(i)

    i = sample(MESS["incomplete_session_rate"])
    df.loc[i, "Completion_Percentage"] = np.nan
    report["incomplete_sessions"] = len(i)

    # -- inconsistent categories ---------------------------------------------
    i = sample(MESS["plan_variant_rate"])
    variants = rng.choice(3, len(i))
    plans = df.loc[i, "Subscription_Plan"].astype(str)
    df["Subscription_Plan"] = df["Subscription_Plan"].astype(object)
    df.loc[i, "Subscription_Plan"] = np.where(
        variants == 0, plans.str.lower(),
        np.where(variants == 1, plans.str.upper(), plans + "  "),
    )
    report["plan_variants"] = len(i)

    i = sample(MESS["gender_variant_rate"])
    gmap = {"Male": "M", "Female": "F", "Other": "other"}
    df["Gender"] = df["Gender"].astype(object)
    df.loc[i, "Gender"] = df.loc[i, "Gender"].map(lambda g: gmap.get(g, g))
    report["gender_variants"] = len(i)

    usa = np.flatnonzero((df["Country"] == "USA").to_numpy())
    i = rng.choice(usa, size=min(round(MESS["country_variant_rate"] * n), len(usa)), replace=False)
    df["Country"] = df["Country"].astype(object)
    df.loc[i, "Country"] = rng.choice(["United States", "U.S."], len(i))
    report["country_variants"] = len(i)

    i = sample(MESS["device_variant_rate"])
    df["Device"] = df["Device"].astype(object)
    df.loc[i, "Device"] = df.loc[i, "Device"].astype(str).str.lower()
    report["device_variants"] = len(i)

    # -- stray whitespace ------------------------------------------------------
    for col in ("Anime_Title", "Studio"):
        i = sample(MESS["whitespace_rate"])
        df.loc[i, col] = "  " + df.loc[i, col].astype(str) + " "
        report[f"whitespace_{col}"] = len(i)

    # -- wrong types stored as text -------------------------------------------
    i = sample(MESS["fee_dollar_rate"])
    df["Monthly_Fee"] = df["Monthly_Fee"].astype(object)
    df.loc[i, "Monthly_Fee"] = df.loc[i, "Monthly_Fee"].map(lambda v: f"${v}")
    report["fee_dollar_strings"] = len(i)

    i = sample(MESS["completion_pct_rate"])
    df["Completion_Percentage"] = df["Completion_Percentage"].astype(object)
    df.loc[i, "Completion_Percentage"] = df.loc[i, "Completion_Percentage"].map(
        lambda v: f"{v}%" if pd.notna(v) else v
    )
    report["completion_pct_strings"] = len(i)

    i = sample(MESS["episode_float_str_rate"])
    df["Episode_Number"] = df["Episode_Number"].astype(object)
    df.loc[i, "Episode_Number"] = df.loc[i, "Episode_Number"].map(lambda v: f"{float(v)}")
    report["episode_float_strings"] = len(i)

    i = sample(MESS["rating_na_string_rate"])
    df["User_Rating"] = df["User_Rating"].astype(object)
    # "Not Rated" (not "N/A") so pandas' default NA parsing doesn't silently
    # convert the sentinel back to NaN when the CSV is read.
    df.loc[i, "User_Rating"] = "Not Rated"
    report["rating_na_strings"] = len(i)

    # -- mixed date formats (whole columns become strings) ---------------------
    wd = pd.to_datetime(df["Watch_Date"])
    fmt = np.full(n, 0)
    fmt[sample(MESS["date_format_dmy_rate"])] = 1
    fmt[sample(MESS["date_format_verbose_rate"])] = 2
    df["Watch_Date"] = np.select(
        [fmt == 1, fmt == 2],
        [wd.dt.strftime("%d/%m/%Y %H:%M"), wd.dt.strftime("%B %d, %Y %H:%M")],
        default=wd.dt.strftime("%Y-%m-%d %H:%M"),
    )
    report["watch_date_dmy"] = int((fmt == 1).sum())
    report["watch_date_verbose"] = int((fmt == 2).sum())

    for col in ("Subscription_Start_Date", "Subscription_End_Date"):
        d = pd.to_datetime(df[col])
        alt = np.zeros(n, dtype=bool)
        alt[sample(MESS["sub_date_dmy_rate"])] = True
        formatted = np.where(alt, d.dt.strftime("%d-%m-%Y"), d.dt.strftime("%Y-%m-%d"))
        df[col] = np.where(d.isna(), None, formatted)
        report[f"dmy_{col}"] = int((alt & d.notna().to_numpy()).sum())

    # -- duplicates + shuffle ---------------------------------------------------
    dup_idx = sample(MESS["duplicate_rate"])
    df = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)
    report["duplicate_rows"] = len(dup_idx)

    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df, report


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    rng = np.random.default_rng(SEED)
    print(f"Simulating {N_USERS:,} users ({WINDOW_START.date()} -> {WINDOW_END.date()}) ...")

    users = simulate_churn(rng, generate_users(rng))
    events = generate_events(rng, users)
    print(f"  clean events : {len(events):,} rows x {events.shape[1]} cols")

    messy, report = inject_mess(rng, events)
    print(f"  messy events : {len(messy):,} rows (after duplicate injection)")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    messy.to_csv(CSV_PATH, index=False)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    churn_rate = (users["status"] == "Cancelled").mean()
    print(f"\nUsers        : {len(users):,}  (churn rate {churn_rate:.1%})")
    print(f"Watch events : {len(messy):,}")
    print(f"CSV          : {CSV_PATH}")
    print(f"Answer key   : {REPORT_PATH}")
    print("\nInjected issues:")
    for k, v in report.items():
        print(f"  {k:<35} {v:>6,}")


if __name__ == "__main__":
    main()
