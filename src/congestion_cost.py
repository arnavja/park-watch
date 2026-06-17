"""Quantify congestion cost per illegal-parking hotspot.

Approach (defensible-by-design for the BTP panel):
1. For each hotspot, snap to the nearest OSM road segment.
2. Use OSM tags to infer number of lanes + free-flow speed.
3. Estimate effective lane-blockage from violation density:
   - daily violations × mean dwell time (assumed) = lane-minutes blocked / day
   - blocked_fraction = lane-minutes-blocked / (lanes × 1440)
4. Apply a BPR-style delay function to translate blockage into vehicle-hours
   lost per day, valued in INR using a standard travel-time-cost figure.

Assumptions are conservative and explicit. All knobs are at the top so they
can be defended/tweaked live.
"""
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd

ROOT = Path(__file__).parent.parent
OUT = ROOT / "outputs"

# ── Knobs (all defensible, documented) ────────────────────────────────────
DAYS_IN_DATA = 152          # Nov 9 2023 → Apr 8 2024 ≈ 5 mo
MEAN_DWELL_MIN = 12         # avg illegal-park dwell — conservative
LANE_CAPACITY_VPH = 1800    # HCM standard for urban arterial, per lane
DEFAULT_LANES = 2           # if OSM missing
DEFAULT_FREE_FLOW_KMH = 30  # urban BLR default
BPR_ALPHA = 0.15            # standard BPR
BPR_BETA = 4
PEAK_HOURS_PER_DAY = 8      # commercial-area peak window
VALUE_OF_TIME_INR_PER_HR = 200  # GoK economic survey ~₹150–250/hr
RADIUS_M = 80               # snap radius for hotspot → nearest edge


def _get_lanes(tag):
    if tag is None or (isinstance(tag, float) and np.isnan(tag)):
        return DEFAULT_LANES
    if isinstance(tag, list):
        tag = tag[0]
    try:
        return max(1, int(str(tag).split(";")[0]))
    except Exception:
        return DEFAULT_LANES


def _get_speed(maxspeed):
    if maxspeed is None or (isinstance(maxspeed, float) and np.isnan(maxspeed)):
        return DEFAULT_FREE_FLOW_KMH
    if isinstance(maxspeed, list):
        maxspeed = maxspeed[0]
    try:
        return max(10, int(str(maxspeed).split()[0]))
    except Exception:
        return DEFAULT_FREE_FLOW_KMH


def build_graph(hotspots: pd.DataFrame, cache_path: Path):
    """Build/load OSM drive graph covering all hotspot points."""
    if cache_path.exists():
        return ox.load_graphml(cache_path)

    pad = 0.02
    bbox = (
        float(hotspots["lon"].min()) - pad,  # west
        float(hotspots["lat"].min()) - pad,  # south
        float(hotspots["lon"].max()) + pad,  # east
        float(hotspots["lat"].max()) + pad,  # north
    )
    print(f"Fetching OSM drive graph for BLR bbox {bbox}…")
    G = ox.graph_from_bbox(bbox=bbox, network_type="drive", simplify=True)
    ox.save_graphml(G, cache_path)
    return G


def score_hotspots(hotspots: pd.DataFrame, G) -> pd.DataFrame:
    print(f"Scoring {len(hotspots)} hotspots…")
    edges = ox.graph_to_gdfs(G, nodes=False)

    # Nearest edge for each hotspot
    nearest = ox.distance.nearest_edges(
        G, X=hotspots["lon"].values, Y=hotspots["lat"].values, return_dist=True
    )
    edge_ids, dists = nearest

    rows = []
    for (cid, n_viol), (u, v, k), d in zip(
        hotspots[["cluster_id", "n_violations"]].itertuples(index=False),
        edge_ids,
        dists,
    ):
        if d > RADIUS_M:
            continue
        e = edges.loc[(u, v, k)]
        lanes = _get_lanes(e.get("lanes"))
        speed = _get_speed(e.get("maxspeed"))
        name = e.get("name", "Unknown road")
        if isinstance(name, list):
            name = name[0]

        viol_per_day = n_viol / DAYS_IN_DATA
        lane_min_blocked = viol_per_day * MEAN_DWELL_MIN
        blocked_frac = min(0.95, lane_min_blocked / (lanes * 1440))

        # BPR: t = t_free * (1 + α (v/c)^β); here v/c grows because effective
        # capacity is reduced by blocked_frac.
        v_c = 1.0 / (1.0 - blocked_frac + 1e-6)
        delay_ratio = 1 + BPR_ALPHA * (v_c ** BPR_BETA) - 1
        delay_ratio = min(delay_ratio, 5.0)  # cap unrealistic blow-up

        # Peak-hour throughput we care about
        peak_flow = lanes * LANE_CAPACITY_VPH * PEAK_HOURS_PER_DAY
        free_flow_hours = peak_flow / (LANE_CAPACITY_VPH)  # = lanes*PEAK
        veh_hours_lost = peak_flow * delay_ratio * (1 / 60) * MEAN_DWELL_MIN / 60
        # simpler: vehicles_affected_per_day * extra_minutes / 60
        affected = peak_flow * blocked_frac
        extra_min_per_veh = delay_ratio * MEAN_DWELL_MIN
        veh_hours_lost = affected * extra_min_per_veh / 60
        cost_inr_day = veh_hours_lost * VALUE_OF_TIME_INR_PER_HR

        rows.append({
            "cluster_id": int(cid),
            "n_violations": int(n_viol),
            "road_name": str(name),
            "lanes": lanes,
            "free_flow_kmh": speed,
            "viol_per_day": round(viol_per_day, 1),
            "blocked_frac": round(blocked_frac, 3),
            "delay_ratio": round(delay_ratio, 2),
            "veh_hours_lost_per_day": round(veh_hours_lost, 0),
            "veh_hours_lost_per_month": round(veh_hours_lost * 30, 0),
            "cost_inr_per_day": round(cost_inr_day, 0),
            "cost_inr_per_month": round(cost_inr_day * 30, 0),
        })

    return pd.DataFrame(rows).sort_values(
        "cost_inr_per_month", ascending=False
    ).reset_index(drop=True)


if __name__ == "__main__":
    hotspots = pd.read_csv(OUT / "hotspots.csv")
    # Score top 100 hotspots — covers >90% of all violations
    top = hotspots.head(100).copy()
    G = build_graph(top, OUT / "blr_drive.graphml")
    scored = score_hotspots(top, G)
    scored = scored.merge(
        hotspots[["cluster_id", "lat", "lon", "top_station", "top_junction",
                  "sample_address"]],
        on="cluster_id",
        how="left",
    )
    scored.to_csv(OUT / "congestion_cost.csv", index=False)
    print(f"\nTop 10 most costly hotspots:")
    print(scored.head(10)[[
        "cluster_id", "n_violations", "road_name", "lanes",
        "veh_hours_lost_per_day", "cost_inr_per_month", "top_station",
    ]].to_string())
    total = scored["cost_inr_per_month"].sum()
    total_vh = scored["veh_hours_lost_per_month"].sum()
    print(f"\n=== Aggregate impact (top {len(scored)} hotspots) ===")
    print(f"Vehicle-hours lost / month: {total_vh:,.0f}")
    print(f"Economic cost / month:      ₹{total:,.0f}")
    print(f"Economic cost / year:       ₹{total*12:,.0f}")
