"""Hotspot clustering using DBSCAN on geographic coordinates."""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

OUT = Path(__file__).parent.parent / "outputs"
OUT.mkdir(exist_ok=True)

EARTH_R_M = 6_371_000


def cluster(
    df: pd.DataFrame,
    eps_meters: float = 50.0,
    min_samples: int = 30,
) -> pd.DataFrame:
    """DBSCAN on lat/lon using haversine; eps in meters → radians."""
    coords = np.radians(df[["latitude", "longitude"]].to_numpy())
    eps_rad = eps_meters / EARTH_R_M
    db = DBSCAN(
        eps=eps_rad, min_samples=min_samples, metric="haversine", n_jobs=-1
    ).fit(coords)
    df = df.copy()
    df["cluster"] = db.labels_
    return df


def summarize(df_clustered: pd.DataFrame) -> pd.DataFrame:
    """Aggregate stats per hotspot cluster."""
    g = df_clustered[df_clustered["cluster"] >= 0]
    rows = []
    for cid, sub in g.groupby("cluster"):
        rows.append({
            "cluster_id": cid,
            "n_violations": len(sub),
            "lat": sub["latitude"].mean(),
            "lon": sub["longitude"].mean(),
            "top_station": sub["police_station"].mode().iat[0]
                if not sub["police_station"].mode().empty else None,
            "top_junction": sub["junction_name"].mode().iat[0]
                if not sub["junction_name"].mode().empty else None,
            "top_vehicle": sub["vehicle_type"].mode().iat[0]
                if not sub["vehicle_type"].mode().empty else None,
            "share_morning": (sub["hour"].between(8, 11)).mean(),
            "share_evening": (sub["hour"].between(17, 23)).mean(),
            "share_night": ((sub["hour"] <= 5)).mean(),
            "share_weekend": (sub["dow"] >= 5).mean(),
            "sample_address": sub["location"].iloc[0],
        })
    out = pd.DataFrame(rows).sort_values("n_violations", ascending=False)
    return out.reset_index(drop=True)


if __name__ == "__main__":
    from data_loader import load
    df = load()
    print(f"Clustering {len(df):,} violations…")
    cl = cluster(df, eps_meters=60, min_samples=40)
    n_clusters = (cl["cluster"] >= 0).sum()
    n_noise = (cl["cluster"] == -1).sum()
    print(f"  → {cl['cluster'].max() + 1} clusters")
    print(f"  → {n_clusters:,} clustered points, {n_noise:,} noise")
    summ = summarize(cl)
    summ.to_csv(OUT / "hotspots.csv", index=False)
    cl[["id", "latitude", "longitude", "cluster"]].to_parquet(
        OUT / "violations_clustered.parquet", index=False
    )
    print(f"\nTop 10 hotspots:")
    print(summ.head(10).to_string())
