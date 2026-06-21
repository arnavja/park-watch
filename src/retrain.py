"""End-to-end retraining pipeline — Park-Watch production loop.

Runs all four analytical modules in sequence, producing the canonical
output files the dashboard consumes:

    data/violations.parquet         (built by data_loader)
    outputs/hotspots.csv            (built by hotspots)
    outputs/violations_clustered.parquet
    outputs/congestion_cost.csv     (built by congestion_cost)
    outputs/blind_spots.csv         (built by blind_spot_predictor)
    outputs/forecast_24h.parquet
    outputs/patrol_routes.csv       (built by patrol_optimizer)

Intended use in production:

    # Schedule weekly via cron:
    0 3 * * 0 cd /opt/park-watch && python3 src/retrain.py

    # Or manually with custom shift window:
    python3 src/retrain.py --shift-start 18 --shift-end 23 --patrols 5

The script is idempotent — re-running it on the same data produces the
same outputs (modulo XGBoost's internal threading non-determinism).
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

OUT = ROOT / "outputs"


def step(name):
    bar = "─" * 60
    print(f"\n{bar}\n  {name}\n{bar}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shift-start", type=int, default=18,
                    help="Patrol shift start hour (24h, IST)")
    ap.add_argument("--shift-end", type=int, default=23,
                    help="Patrol shift end hour (24h, IST)")
    ap.add_argument("--patrols", type=int, default=5,
                    help="Number of patrol units to deploy")
    args = ap.parse_args()

    t_start = time.time()

    # ── 1. Data load + clean
    step("[1/5] Load + clean BTP records")
    from data_loader import load
    df = load(use_cache=False)
    print(f"  → {len(df):,} rows  ·  parquet cache rebuilt")

    # ── 2. Hotspot clustering
    step("[2/5] DBSCAN hotspot clustering")
    from hotspots import cluster, summarize
    cl = cluster(df, eps_meters=60, min_samples=40)
    n_clusters = cl["cluster"].max() + 1
    print(f"  → {n_clusters} hotspot clusters discovered")
    summ = summarize(cl)
    summ.to_csv(OUT / "hotspots.csv", index=False)
    cl[["id", "latitude", "longitude", "cluster"]].to_parquet(
        OUT / "violations_clustered.parquet", index=False
    )

    # ── 3. Congestion cost
    step("[3/5] Congestion cost (OSMnx + BPR)")
    from congestion_cost import build_graph, score_hotspots
    hotspots = pd.read_csv(OUT / "hotspots.csv")
    top = hotspots.head(100).copy()
    G = build_graph(top, OUT / "blr_drive.graphml")
    scored = score_hotspots(top, G)
    scored = scored.merge(
        hotspots[["cluster_id", "lat", "lon", "top_station",
                  "top_junction", "sample_address"]],
        on="cluster_id", how="left",
    )
    scored.to_csv(OUT / "congestion_cost.csv", index=False)
    total_cost = scored["cost_inr_per_month"].sum()
    print(f"  → Top-100 monthly cost: ₹{total_cost/1e7:.1f} Cr")

    # ── 4. Blind-spot forecast
    step("[4/5] XGBoost forecast (train + 24h horizon)")
    from blind_spot_predictor import (
        build_panel, add_features, train_eval, forecast_blind_spots,
        summarize_blind_spots,
    )
    clustered = pd.read_parquet(OUT / "violations_clustered.parquet")
    panel = build_panel(df, clustered)
    panel_f = add_features(panel, hotspots)
    model, _, _ = train_eval(panel_f)
    fc = forecast_blind_spots(model, panel_f)
    summary = summarize_blind_spots(fc, hotspots)
    summary.to_csv(OUT / "blind_spots.csv", index=False)
    fc.to_parquet(OUT / "forecast_24h.parquet", index=False)
    total_blind = summary["predicted_blind_spot_violations_next24h"].sum()
    print(f"  → Predicted unbooked next-24h: {total_blind:.0f}")

    # ── 5. Patrol optimizer
    step("[5/5] Patrol route optimization")
    from patrol_optimizer import optimize
    routes = optimize(fc, hotspots, n_patrols=args.patrols)
    routes = routes.merge(
        hotspots[["cluster_id", "top_station", "top_junction"]].rename(
            columns={"cluster_id": "cluster"}
        ),
        on="cluster", how="left",
    )
    routes.to_csv(OUT / "patrol_routes.csv", index=False)
    n_stops = len(routes)
    catches = routes["expected_catches"].sum() if len(routes) else 0
    print(f"  → {args.patrols} patrols  ·  {n_stops} stops  ·  "
          f"{catches:.0f} expected catches")

    # ── Done
    duration = time.time() - t_start
    print(f"\n{'═'*60}\n  Retrain complete  ·  {duration:.1f}s wall-clock\n{'═'*60}")
    print("\nProduction schedule:  0 3 * * 0  cd /opt/park-watch && "
          "python3 src/retrain.py")


if __name__ == "__main__":
    main()
