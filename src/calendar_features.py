"""India + Karnataka calendar features for parking-violation forecasting.

Recurring annual patterns matter for Bengaluru parking:
  - Diwali / Ganesh Chaturthi / Karnataka Rajyotsava → market spikes
  - Christmas / NYE → Brigade Road, UB City, Church Street
  - Cricket match days → Chinnaswamy stadium area
  - Monsoon (Jun–Sep) → footpath encroachment patterns shift
  - Public holidays → residential vs commercial mix changes
"""
from __future__ import annotations

import pandas as pd

# Festivals + public holidays covering the dataset window (Nov 2023 – Apr 2024)
# and looking forward (so the model generalizes for inference in future periods).
INDIA_FESTIVALS = {
    # ── 2023 ──
    "2023-11-09": "dhanteras",
    "2023-11-12": "diwali",
    "2023-11-13": "govardhan_puja",
    "2023-11-15": "bhai_dooj",
    "2023-11-27": "guru_nanak_jayanti",
    "2023-12-25": "christmas",
    "2023-12-31": "nye",
    # ── 2024 ──
    "2024-01-01": "new_year",
    "2024-01-14": "makar_sankranti",
    "2024-01-15": "pongal",
    "2024-01-26": "republic_day",
    "2024-03-08": "mahashivratri",
    "2024-03-25": "holi",
    "2024-04-09": "ugadi",
    "2024-04-11": "eid_ul_fitr",
    "2024-04-17": "ram_navami",
    "2024-04-21": "mahavir_jayanti",
    # ── 2024 — outside dataset, included for forward inference ──
    "2024-08-15": "independence_day",
    "2024-09-07": "ganesh_chaturthi",
    "2024-10-12": "dussehra",
    "2024-10-31": "diwali_2024",
    "2024-11-01": "karnataka_rajyotsava",
    "2024-12-25": "christmas_2024",
}

# Windows where parking demand is structurally different — not just the day.
FESTIVAL_WINDOWS = [
    ("2023-11-09", "2023-11-15"),   # Diwali week
    ("2023-12-22", "2024-01-02"),   # Christmas → NYE
    ("2024-01-13", "2024-01-16"),   # Pongal / Sankranti
    ("2024-03-23", "2024-03-27"),   # Holi window
    ("2024-04-08", "2024-04-12"),   # Ugadi + Eid
]


def add_calendar_features(df: pd.DataFrame, dt_col: str = "hour_dt") -> pd.DataFrame:
    """Add yearly/seasonal calendar features."""
    df = df.copy()
    dt = df[dt_col]
    df["day_of_year"] = dt.dt.dayofyear
    df["week_of_year"] = dt.dt.isocalendar().week.astype(int)
    df["day_of_month"] = dt.dt.day
    df["is_month_end"] = (dt.dt.day >= 28).astype(int)

    date_str = dt.dt.strftime("%Y-%m-%d")
    df["is_festival"] = date_str.isin(INDIA_FESTIVALS).astype(int)

    # Festival window flag (broader than single day)
    in_window = pd.Series(False, index=df.index)
    for start, end in FESTIVAL_WINDOWS:
        s = pd.Timestamp(start, tz=dt.dt.tz)
        e = pd.Timestamp(end, tz=dt.dt.tz)
        in_window |= dt.between(s, e)
    df["is_festival_window"] = in_window.astype(int)

    # Monsoon (Jun 1 – Sep 30, IST) — Bengaluru pattern
    month = dt.dt.month
    df["is_monsoon"] = month.between(6, 9).astype(int)

    return df


CALENDAR_FEATS = [
    "day_of_year", "week_of_year", "day_of_month", "is_month_end",
    "is_festival", "is_festival_window", "is_monsoon",
]
