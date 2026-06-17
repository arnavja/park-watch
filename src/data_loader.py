"""Load + clean BTP parking-violation dataset."""
import ast
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent.parent / "data" / "violations.csv"
CACHE = Path(__file__).parent.parent / "data" / "violations.parquet"
SAMPLE = Path(__file__).parent.parent / "data" / "sample_violations.parquet"

# Headline numbers from the FULL 298K dataset — used for KPIs in demo mode
# so the dashboard still cites the real scale of the analysis.
FULL_DATASET_STATS = {
    "n_violations": 298_450,
    "n_hotspots": 381,
    "date_range": "Nov 2023 – Apr 2024",
}


def _parse_types(x):
    try:
        return ast.literal_eval(x) if isinstance(x, str) else []
    except Exception:
        return []


def is_demo_mode() -> bool:
    """True when only the demo sample is available (no parquet cache built).

    On Streamlit Cloud the raw 105 MB CSV is absent — the dashboard runs
    on the 30K-row stratified sample shipped with the repo.
    """
    return SAMPLE.exists() and not CACHE.exists()


def load(use_cache: bool = True) -> pd.DataFrame:
    # Demo mode — use the shipped 30K-row stratified sample
    if is_demo_mode():
        return pd.read_parquet(SAMPLE)
    if use_cache and CACHE.exists():
        return pd.read_parquet(CACHE)

    df = pd.read_csv(DATA, low_memory=False)
    df["dt"] = pd.to_datetime(
        df["created_datetime"], format="ISO8601", utc=True
    ).dt.tz_convert("Asia/Kolkata")
    df["hour"] = df["dt"].dt.hour
    df["dow"] = df["dt"].dt.dayofweek
    df["dow_name"] = df["dt"].dt.day_name()
    df["date"] = df["dt"].dt.date
    df["month"] = df["dt"].dt.month

    df["violations"] = df["violation_type"].map(_parse_types)
    df["primary_violation"] = df["violations"].map(
        lambda v: v[0] if v else "UNKNOWN"
    )
    df["is_parking"] = df["violations"].map(
        lambda v: any("PARK" in t for t in v)
    )

    # Drop rows with missing geo
    df = df.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    # Bengaluru bounding box sanity filter
    df = df[
        (df["latitude"].between(12.7, 13.4))
        & (df["longitude"].between(77.3, 77.9))
    ].reset_index(drop=True)

    keep = [
        "id", "latitude", "longitude", "location", "vehicle_type",
        "primary_violation", "violations", "is_parking",
        "dt", "hour", "dow", "dow_name", "date", "month",
        "police_station", "junction_name",
    ]
    df = df[keep]

    df.to_parquet(CACHE, index=False)
    return df


if __name__ == "__main__":
    df = load(use_cache=False)
    print(f"Loaded: {len(df):,} rows")
    print(df.head(3).to_string())
