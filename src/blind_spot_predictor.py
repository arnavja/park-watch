"""Predict illegal-parking intensity per hotspot per hour.

The BTP enforcement window is 8 AM–3 PM (95% of bookings). Outside this
window, violations still happen — they're just invisible. We train on
hourly per-hotspot counts (using only booking data we have) to learn
spatial-temporal patterns, then forecast the next 24h per hotspot.

Hours 16:00–07:00 with predicted volume > threshold = enforcement blind spot.
These zones should receive *targeted* patrols outside normal hours.

Model: XGBoost regressor on:
- Calendar features (hour, dow, month, is_weekend)
- Lag features (1h, 24h, 7d) per hotspot
- Hotspot identity features (cluster_id, lat, lon, top_vehicle_idx)
- Rolling mean (7d trailing) per hotspot
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = Path(__file__).parent.parent
OUT = ROOT / "outputs"


def build_panel(df: pd.DataFrame, clustered: pd.DataFrame) -> pd.DataFrame:
    """Hourly panel per (cluster, datetime_hour)."""
    df = df.merge(clustered[["id", "cluster"]], on="id", how="left")
    df = df[df["cluster"] >= 0].copy()
    df["hour_dt"] = df["dt"].dt.floor("h")

    counts = (
        df.groupby(["cluster", "hour_dt"])
        .size()
        .reset_index(name="violations")
    )

    # Reindex: every (cluster, hour) cell, fill missing with 0
    full_hours = pd.date_range(
        counts["hour_dt"].min(),
        counts["hour_dt"].max(),
        freq="h", tz=counts["hour_dt"].dt.tz,
    )
    clusters = counts["cluster"].unique()
    idx = pd.MultiIndex.from_product(
        [clusters, full_hours], names=["cluster", "hour_dt"]
    )
    panel = counts.set_index(["cluster", "hour_dt"]).reindex(
        idx, fill_value=0
    ).reset_index()
    return panel


def add_features(panel: pd.DataFrame, hotspots: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["cluster", "hour_dt"]).copy()
    panel["hour"] = panel["hour_dt"].dt.hour
    panel["dow"] = panel["hour_dt"].dt.dayofweek
    panel["month"] = panel["hour_dt"].dt.month
    panel["is_weekend"] = (panel["dow"] >= 5).astype(int)

    g = panel.groupby("cluster", group_keys=False)
    panel["lag_1h"]   = g["violations"].shift(1)
    panel["lag_24h"]  = g["violations"].shift(24)
    panel["lag_7d"]   = g["violations"].shift(24 * 7)
    panel["roll_7d"]  = g["violations"].shift(1).rolling(24 * 7, min_periods=24).mean().reset_index(level=0, drop=True)

    # Spatial features
    spatial = hotspots[["cluster_id", "lat", "lon", "top_vehicle"]].copy()
    spatial = spatial.rename(columns={"cluster_id": "cluster"})
    spatial["top_vehicle_idx"] = pd.Categorical(spatial["top_vehicle"]).codes
    panel = panel.merge(
        spatial[["cluster", "lat", "lon", "top_vehicle_idx"]],
        on="cluster", how="left",
    )

    # Annual / seasonal calendar features (festivals, monsoon, day-of-year)
    from calendar_features import add_calendar_features
    panel = add_calendar_features(panel, dt_col="hour_dt")

    return panel.dropna().reset_index(drop=True)


from calendar_features import CALENDAR_FEATS

FEATS = [
    "hour", "dow", "month", "is_weekend",
    "lag_1h", "lag_24h", "lag_7d", "roll_7d",
    "lat", "lon", "top_vehicle_idx",
] + CALENDAR_FEATS


def train_eval(panel: pd.DataFrame):
    """Chronological train/val/test split with early stopping.

    - Train: oldest 70%
    - Val:   next 15% (early-stopping signal)
    - Test:  most recent 15% (held-out for honest reporting)
    """
    q70 = panel["hour_dt"].quantile(0.70)
    q85 = panel["hour_dt"].quantile(0.85)
    train = panel[panel["hour_dt"] < q70]
    val   = panel[(panel["hour_dt"] >= q70) & (panel["hour_dt"] < q85)]
    test  = panel[panel["hour_dt"] >= q85]
    print(f"Train: {len(train):,}  Val: {len(val):,}  Test: {len(test):,}")
    print(f"  cutoff train→val:  {q70}")
    print(f"  cutoff val→test:   {q85}")

    model = xgb.XGBRegressor(
        n_estimators=1500,        # large; early stopping picks the best round
        max_depth=6,              # ↓ from 7 — guards against overfit
        learning_rate=0.05,       # ↓ slower learning + more rounds
        subsample=0.8, colsample_bytree=0.8,
        reg_lambda=1.0,           # L2 regularization
        min_child_weight=5,       # discourages tiny terminal splits
        tree_method="hist",       # fastest CPU algorithm; no GPU on Mac
        n_jobs=-1, random_state=1,
        early_stopping_rounds=30,
    )
    # Time-decay sample weights: more recent observations matter more.
    # half-life ≈ 90 days → weights for old data decay smoothly.
    latest = train["hour_dt"].max()
    age_days = (latest - train["hour_dt"]).dt.total_seconds() / 86400
    sample_w = np.exp(-age_days / 90.0).clip(lower=0.1)

    model.fit(
        train[FEATS], train["violations"],
        sample_weight=sample_w,
        eval_set=[(train[FEATS], train["violations"]),
                  (val[FEATS],   val["violations"])],
        verbose=False,
    )
    best_iter = model.best_iteration
    print(f"  Best iteration: {best_iter}  "
          f"(stopped of 1500 max)")

    # Honest train vs test gap check
    pred_tr = np.clip(model.predict(train[FEATS]), 0, None)
    pred_va = np.clip(model.predict(val[FEATS]),   0, None)
    pred_te = np.clip(model.predict(test[FEATS]),  0, None)

    def _stats(y, p, name):
        mae = mean_absolute_error(y, p)
        r2  = r2_score(y, p)
        print(f"  {name:>5s}  MAE={mae:.3f}  R²={r2:.3f}  "
              f"mean(y)={y.mean():.3f}")
        return mae, r2

    print("\nOverfit check — gap between train and test is the diagnostic:")
    tr_mae, tr_r2 = _stats(train["violations"], pred_tr, "Train")
    va_mae, va_r2 = _stats(val["violations"],   pred_va, "Val")
    te_mae, te_r2 = _stats(test["violations"],  pred_te, "Test")

    gap_r2  = tr_r2 - te_r2
    gap_mae = te_mae - tr_mae
    print(f"\n  Train→Test R² drop:  {gap_r2:+.3f}  "
          f"({'OK' if gap_r2 < 0.15 else 'OVERFIT WARNING'})")
    print(f"  Train→Test MAE rise: {gap_mae:+.3f}  "
          f"({'OK' if gap_mae < 0.10 else 'OVERFIT WARNING'})")

    # Feature importance
    print("\nTop feature importances:")
    fi = pd.Series(model.feature_importances_, index=FEATS).sort_values(
        ascending=False
    )
    for f, v in fi.items():
        print(f"  {f:>16s}  {v:.3f}")

    return model, test, pred_te


def forecast_blind_spots(model, panel: pd.DataFrame) -> pd.DataFrame:
    """For each hotspot, predict next-24-hour violation pattern starting from
    the most recent hour, and aggregate "blind-spot" hours (15:00–07:00).
    """
    last_hour = panel["hour_dt"].max()
    start = last_hour + pd.Timedelta(hours=1)

    rows = []
    for cluster, sub in panel.groupby("cluster"):
        if len(sub) < 24 * 7:
            continue
        recent = sub.sort_values("hour_dt").tail(24 * 7 + 24).copy()
        for offset in range(24):
            hr = start + pd.Timedelta(hours=offset)
            r = {
                "cluster": cluster,
                "hour_dt": hr,
                "hour": hr.hour,
                "dow": hr.dayofweek,
                "month": hr.month,
                "is_weekend": int(hr.dayofweek >= 5),
                "lag_1h":  recent["violations"].iloc[-1],
                "lag_24h": recent["violations"].iloc[-24]
                    if len(recent) >= 24 else 0,
                "lag_7d":  recent["violations"].iloc[-24*7]
                    if len(recent) >= 24*7 else 0,
                "roll_7d": recent["violations"].tail(24*7).mean(),
                "lat": sub["lat"].iat[0],
                "lon": sub["lon"].iat[0],
                "top_vehicle_idx": sub["top_vehicle_idx"].iat[0],
            }
            rows.append(r)

    fc = pd.DataFrame(rows)
    # Calendar features need adding at inference time too
    from calendar_features import add_calendar_features
    fc = add_calendar_features(fc, dt_col="hour_dt")
    fc["pred"] = np.clip(model.predict(fc[FEATS]), 0, None)
    fc["is_blind_spot_hour"] = ~fc["hour"].between(8, 14)
    return fc


def summarize_blind_spots(fc: pd.DataFrame, hotspots: pd.DataFrame) -> pd.DataFrame:
    blind = fc[fc["is_blind_spot_hour"]]
    g = blind.groupby("cluster")["pred"].sum().reset_index(
        name="predicted_blind_spot_violations_next24h"
    )
    g = g.merge(
        hotspots[["cluster_id", "top_station", "top_junction", "top_vehicle",
                  "sample_address", "n_violations"]].rename(
            columns={"cluster_id": "cluster"}
        ),
        on="cluster", how="left",
    )
    return g.sort_values(
        "predicted_blind_spot_violations_next24h", ascending=False
    ).reset_index(drop=True)


if __name__ == "__main__":
    from data_loader import load
    print("Loading data…")
    df = load()
    clustered = pd.read_parquet(OUT / "violations_clustered.parquet")
    hotspots = pd.read_csv(OUT / "hotspots.csv")

    print("Building hourly panel…")
    panel = build_panel(df, clustered)
    print(f"  Panel: {len(panel):,} (cluster × hour) rows")

    panel_f = add_features(panel, hotspots)
    print(f"  After features: {len(panel_f):,} rows")

    print("\nTraining XGBoost…")
    model, test, pred = train_eval(panel_f)

    print("\nForecasting next 24h per hotspot…")
    fc = forecast_blind_spots(model, panel_f)
    summary = summarize_blind_spots(fc, hotspots)
    summary.to_csv(OUT / "blind_spots.csv", index=False)
    fc.to_parquet(OUT / "forecast_24h.parquet", index=False)

    print(f"\nTop 10 predicted blind-spot zones (next 24h):")
    print(summary.head(10).to_string())
    total_blind = summary["predicted_blind_spot_violations_next24h"].sum()
    print(f"\nTotal predicted unbooked violations in next 24h "
          f"(blind-spot hours 15:00–07:00): {total_blind:.0f}")
