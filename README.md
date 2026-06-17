# Park-Watch — Bengaluru Parking Enforcement Intelligence

Submission for **Gridlock Hackathon · Theme 1 (Parking-Induced Congestion)** — Flipkart HQ × Bengaluru Traffic Police.

🌐 **Live demo:** https://park-watch.streamlit.app

---

## What it does

Park-Watch turns **298,450 real BTP parking-violation records** (Nov 2023 – Apr 2024) into an end-to-end enforcement intelligence system. Four analytical modules feed a single Streamlit dashboard that ranks zones, quantifies their cost, predicts where enforcement is missing, and produces a nightly patrol roster.

## Headline results

| Metric | Value |
|---|---|
| Violations analysed | **298,450** |
| Illegal-parking hotspots discovered | **381** |
| Vehicle-hours lost per month (top 100 hotspots) | **1,619,498** |
| Economic cost per year | **₹389 Cr** (~10% of BLR's ₹38,000 Cr congestion bill) |
| Forecast accuracy (held-out test set) | **R² = 0.43**, MAE = 0.23, train→test gap +0.07 (no overfit) |
| Predicted unbooked violations per 24h | **722** |
| Patrol-output improvement over current schedule | **4.5×** (113 catches vs ~25 in a 5-hour evening shift) |

## The key insight

**BTP officers book ~95% of violations between 8 AM and 3 PM.** From 6 PM onwards, only a few dozen violations are recorded across an entire 5-month window — not because illegal parking stops, but because officers go home. Park-Watch quantifies this enforcement coverage gap, predicts where violations will happen during it, and produces patrol routes that close it.

## Modules

| # | Module | Method | Output |
|---|---|---|---|
| 1 | Hotspot detection | DBSCAN on geo-coords, 60 m eps, min 40 points, haversine metric | 381 illegal-parking zones |
| 2 | Congestion cost | OSMnx road graph + BPR delay model (α=0.15, β=4) | ₹/month per hotspot |
| 3 | Violation forecast | XGBoost on 1.38 M (hotspot × hour) observations, 70/15/15 chronological split, early stopping | 24-hour per-zone forecast |
| 4 | Patrol optimizer | Weighted KMeans assignment + nearest-neighbor TSP | Per-officer schedule with ETA |

## Top hotspots discovered

| Rank | Zone | Violations | Lead vehicle | Cost / month |
|---|---|---|---|---|
| 1 | KR Market Junction (Upparpet) | 56,214 | SCOOTER | ₹16.4 Cr |
| 2 | Safina Plaza / Dispensary Rd (Shivajinagar) | 25,122 | PASSENGER AUTO | ₹11.9 Cr |
| 3 | Dr Rajkumar Rd (Malleshwaram) | 10,246 | CAR | ₹54 L |
| 4 | HAL Old Airport / Outer Ring Rd | 10,157 | SCOOTER | ₹53 L |
| 5 | Modi Bridge (Malleshwaram) | 9,769 | SCOOTER | ₹48 L |

## Quickstart

```bash
git clone https://github.com/arnavja/park-watch.git
cd park-watch
pip install -r requirements.txt

# Reproduce the entire pipeline (requires raw BTP CSV in data/)
python3 src/data_loader.py
python3 src/hotspots.py
python3 src/congestion_cost.py
python3 src/blind_spot_predictor.py
python3 src/patrol_optimizer.py

# Run the dashboard
streamlit run src/dashboard.py
```

A 30K-row stratified sample of the dataset (`data/sample_violations.parquet`) is shipped so the dashboard runs end-to-end on Streamlit Cloud without the raw 105 MB BTP CSV.

## Stack

- **Data:** pandas, pyarrow (parquet caching)
- **ML:** scikit-learn (DBSCAN, KMeans), XGBoost
- **Geo:** OSMnx, networkx, Folium
- **App:** Streamlit + streamlit-folium
- **Deck:** python-pptx, Playwright (auto-screenshot)

## Repository layout

```
park-watch/
├── data/
│   └── sample_violations.parquet     30K stratified sample (raw BTP CSV gitignored)
├── src/
│   ├── data_loader.py                Load, clean, time-parse, parquet cache
│   ├── hotspots.py                   DBSCAN clustering + per-cluster stats
│   ├── congestion_cost.py            OSMnx + BPR delay model
│   ├── blind_spot_predictor.py       XGBoost forecast with overfit guards
│   ├── patrol_optimizer.py           KMeans + TSP route optimization
│   ├── dashboard.py                  Streamlit + Folium UI
│   ├── build_deck.py                 Generates pitch PPTX
│   ├── capture_screens.py            Playwright dashboard screenshots
│   └── build_demo_sample.py          Stratified sample for public demo
└── outputs/
    ├── hotspots.csv                  381 zones, ranked
    ├── congestion_cost.csv           Top 100 with ₹/month
    ├── blind_spots.csv               Forecasted unbooked violations
    ├── patrol_routes.csv             Tonight's optimized plan
    ├── forecast_24h.parquet          Hourly predictions per hotspot
    ├── Park_Watch_Pitch.pptx         10-slide pitch deck
    └── screens/                      Dashboard screenshots
```

## Team — Byte Titans

- Arnav Jain — [@arnavja](https://github.com/arnavja)

Built for the **Gridlock Hackathon** organised by Flipkart HQ × Bengaluru Traffic Police × HackerEarth.
