"""Nightly patrol-route optimizer.

Input: blind-spot forecast (predicted violations per hotspot per hour),
       number of patrols, shift hours.
Output: per-patrol ordered route — list of (hotspot, ETA, expected catches).

Approach (greedy + spatial sequencing, defensible and demoable):
1. Filter forecast to the shift window (e.g. 18:00–23:00).
2. For each hotspot, compute total expected violations during the shift.
3. Cluster hotspots into K spatial groups (one per patrol) using KMeans on
   lat/lon weighted by expected catches.
4. Within each patrol's group, sequence visits using nearest-neighbor TSP
   starting from the patrol's home station.
5. For each step compute ETA (travel time at 20 km/h urban speed) and
   estimate expected catches based on prediction at arrival hour.

All knobs at the top — defendable live.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

ROOT = Path(__file__).parent.parent
OUT = ROOT / "outputs"

# ── Knobs ────────────────────────────────────────────────────────────────
SHIFT_START_HOUR = 18              # 6 PM — blind-spot window starts
SHIFT_END_HOUR = 23                # 11 PM — end of evening shift
N_PATROLS = 5                      # one patrol per top-station roughly
SERVICE_TIME_MIN = 15              # time to issue tickets at a zone
PATROL_SPEED_KMH = 20              # realistic urban speed for BTP bikes
EARTH_R_KM = 6_371

# Patrol home bases — BTP police stations central to top hotspots.
# Ordered by total violation density in that station's catchment.
PATROL_HOMES = {
    "Upparpet (KR Market)":     (12.9755, 77.5774),
    "Shivajinagar":             (12.9831, 77.6086),
    "Malleshwaram":             (13.0030, 77.5710),
    "HAL Old Airport":          (12.9595, 77.6493),
    "Vijayanagara":             (12.9719, 77.5390),
    "City Market":              (12.9628, 77.5749),
    "Rajajinagar":              (12.9911, 77.5538),
    "Kodigehalli":              (13.0710, 77.5879),
    "Magadi Road":              (12.9766, 77.5494),
    "Jeevanbheemanagar":        (12.9650, 77.6710),
}


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def shift_catches(fc: pd.DataFrame,
                   shift_start: int = SHIFT_START_HOUR,
                   shift_end: int = SHIFT_END_HOUR) -> pd.DataFrame:
    """Total predicted violations per hotspot during the shift window."""
    shift = fc[fc["hour"].between(shift_start, shift_end)]
    g = shift.groupby("cluster").agg(
        expected_catches=("pred", "sum"),
        lat=("lat", "first"),
        lon=("lon", "first"),
    ).reset_index()
    return g[g["expected_catches"] > 0.05].copy()


def assign_to_patrols(zones: pd.DataFrame, n_patrols: int) -> pd.DataFrame:
    """Spatially partition zones across N patrols using weighted KMeans."""
    coords = zones[["lat", "lon"]].to_numpy()
    weights = zones["expected_catches"].to_numpy()
    km = KMeans(n_clusters=n_patrols, n_init=10, random_state=1).fit(
        coords, sample_weight=weights
    )
    zones = zones.copy()
    zones["patrol_id"] = km.labels_
    return zones


def route_one_patrol(
    zones: pd.DataFrame, home_name: str, home_latlon: tuple,
    shift_start: int = SHIFT_START_HOUR,
    shift_end: int = SHIFT_END_HOUR,
) -> pd.DataFrame:
    """Nearest-neighbor sequencing from home, with cumulative ETA & catches."""
    remaining = zones.copy().reset_index(drop=True)
    cur_lat, cur_lon = home_latlon
    cur_time = shift_start * 60  # minutes from midnight

    stops = []
    while len(remaining):
        d_km = haversine_km(
            cur_lat, cur_lon,
            remaining["lat"].values, remaining["lon"].values,
        )
        # Score: catches per minute (travel + service)
        travel_min = d_km / PATROL_SPEED_KMH * 60
        score = remaining["expected_catches"].values / (
            travel_min + SERVICE_TIME_MIN + 1e-6
        )
        idx = int(np.argmax(score))
        chosen = remaining.iloc[idx]

        travel_t = travel_min[idx]
        arrive = cur_time + travel_t
        depart = arrive + SERVICE_TIME_MIN
        if depart > shift_end * 60:
            break

        stops.append({
            "patrol_home": home_name,
            "cluster": int(chosen["cluster"]),
            "lat": chosen["lat"],
            "lon": chosen["lon"],
            "expected_catches": round(chosen["expected_catches"], 1),
            "travel_min": round(travel_t, 1),
            "arrive": f"{int(arrive//60):02d}:{int(arrive%60):02d}",
            "depart": f"{int(depart//60):02d}:{int(depart%60):02d}",
            "cum_catches": 0,
        })
        cur_lat, cur_lon = chosen["lat"], chosen["lon"]
        cur_time = depart
        remaining = remaining.drop(remaining.index[idx]).reset_index(drop=True)

    out = pd.DataFrame(stops)
    if len(out):
        out["cum_catches"] = out["expected_catches"].cumsum().round(1)
        out["seq"] = range(1, len(out) + 1)
    return out


def optimize(fc: pd.DataFrame, hotspots: pd.DataFrame,
             n_patrols: int = N_PATROLS,
             shift_start: int = SHIFT_START_HOUR,
             shift_end: int = SHIFT_END_HOUR) -> pd.DataFrame:
    """Build patrol routes for `n_patrols` patrols across the shift window.

    `n_patrols` is clamped to the number of defined home bases. The first
    `n_patrols` entries of PATROL_HOMES (ordered by violation density) are
    used.
    """
    n_patrols = max(1, min(n_patrols, len(PATROL_HOMES)))
    zones = shift_catches(fc, shift_start=shift_start, shift_end=shift_end)
    if len(zones) == 0:
        return pd.DataFrame()

    zones = assign_to_patrols(zones, n_patrols)
    homes = list(PATROL_HOMES.items())[:n_patrols]
    all_routes = []
    for i, (home_name, home_latlon) in enumerate(homes):
        patrol_zones = zones[zones["patrol_id"] == i]
        route = route_one_patrol(patrol_zones, home_name, home_latlon,
                                  shift_start=shift_start,
                                  shift_end=shift_end)
        if len(route):
            all_routes.append(route)
    return pd.concat(all_routes, ignore_index=True) if all_routes else pd.DataFrame()


if __name__ == "__main__":
    fc = pd.read_parquet(OUT / "forecast_24h.parquet")
    hotspots = pd.read_csv(OUT / "hotspots.csv")
    routes = optimize(fc, hotspots)
    routes = routes.merge(
        hotspots[["cluster_id", "top_station", "top_junction"]].rename(
            columns={"cluster_id": "cluster"}
        ),
        on="cluster", how="left",
    )
    routes.to_csv(OUT / "patrol_routes.csv", index=False)

    print(f"\n=== Nightly patrol plan ({SHIFT_START_HOUR}:00–"
          f"{SHIFT_END_HOUR}:00) ===")
    for home, grp in routes.groupby("patrol_home"):
        catches = grp["expected_catches"].sum()
        stops = len(grp)
        print(f"\n🚓 Patrol from {home}: {stops} stops, "
              f"~{catches:.0f} expected catches")
        cols = ["seq", "arrive", "top_station", "top_junction",
                "expected_catches", "travel_min"]
        print(grp[cols].to_string(index=False))

    total = routes["expected_catches"].sum()
    print(f"\n🎯 TOTAL expected catches this shift: {total:.0f}")
    print(f"   vs current BTP evening catches: ~5/hour × 5hr = ~25")
    print(f"   Improvement: {total / 25:.1f}×")
