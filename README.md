# Park-Watch — Bengaluru Parking Enforcement Intelligence

Submission for **Gridlock Hackathon · Theme 1 (Parking-Induced Congestion)** — Flipkart HQ × Bengaluru Traffic Police.

## What it does

Turns **298K real BTP parking violations** (Nov 2023 – Apr 2024) into an actionable enforcement dashboard:

1. **Hotspot detection** — DBSCAN over geo-coordinates → 381 illegal-parking zones across Bengaluru
2. **Blind-spot insight** — quantifies BTP's 12-hour evening enforcement gap (95% of bookings happen 8 AM–3 PM)
3. **Priority ranking** — top hotspots ranked by violation density, with per-zone vehicle mix and time-of-day signature
4. **Interactive map** — heatmap + clickable hotspots with address, top vehicle, time patterns

## Key finding

> **BTP officers book ~95% of violations between 8 AM and 3 PM. Evening illegal parking is largely invisible to enforcement.**
> Park-Watch surfaces these blind spots and ranks zones by where targeted patrols would have highest impact.

## Top hotspots discovered

| Rank | Zone | Violations | Lead vehicle |
|---|---|---|---|
| 1 | KR Market Junction (Upparpet) | 56,214 | SCOOTER |
| 2 | Safina Plaza (Shivajinagar) | 25,122 | PASSENGER AUTO |
| 3 | Malleshwaram | 10,246 | CAR |
| 4 | HAL Old Airport / Outer Ring Rd | 10,157 | SCOOTER |

## Quickstart

```bash
cd park_watch
python3 src/data_loader.py   # build parquet cache
python3 src/hotspots.py      # cluster + write outputs/hotspots.csv
streamlit run src/dashboard.py
```

## Stack

- **Data:** pandas + pyarrow (parquet cache for 298K rows)
- **Clustering:** scikit-learn DBSCAN with haversine metric, 60m eps, min 40 points
- **Dashboard:** Streamlit + Folium (heatmap + marker cluster)

## Repo layout

```
data/        Symlinked BTP CSV + parquet cache
src/
  data_loader.py   Load, clean, time-parse, parquet cache
  hotspots.py      DBSCAN clustering + per-cluster stats
  dashboard.py     Streamlit app
outputs/     hotspots.csv + clustered violation IDs
notebooks/   (TBD — for impact-quantification + congestion modeling)
```

## Roadmap

- [x] Data loader + parquet cache
- [x] DBSCAN hotspot clustering (381 zones)
- [x] Streamlit dashboard with map + KPIs
- [ ] Congestion-impact model (OSMnx road graph + flow-loss estimate per hotspot)
- [ ] Blind-spot predictor (gradient boost: predict evening hotspot intensity from morning bookings)
- [ ] Enforcement-route optimizer (TSP-style patrol path through top-N zones)
