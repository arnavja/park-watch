# HackerEarth submission — paste-ready text

## Project Title

**Park-Watch: AI-Driven Parking Enforcement Intelligence for Bengaluru**

---

## Short Description (1–2 sentences, ~250 characters)

Park-Watch analyses 298K real BTP parking-violation records to identify illegal-parking hotspots, quantify their congestion cost in ₹/month, predict violations during enforcement blind spots, and generate optimal nightly patrol routes for BTP officers.

---

## Long Description (paragraph form)

Park-Watch is an end-to-end parking enforcement intelligence system built directly on **298,450 real Bengaluru Traffic Police violation records** from November 2023 to April 2024. It addresses Theme 1 (Poor Visibility on Parking-Induced Congestion) by turning the existing BTP data exhaust into four actionable analytical layers.

**Module 1 — Hotspot detection:** DBSCAN clustering on geo-coordinates (60 m epsilon, min 40 points, haversine metric) collapses 298K individual bookings into **381 distinct illegal-parking zones** across the BBMP area, ranked by violation density.

**Module 2 — Congestion cost:** For each hotspot we snap to the nearest road segment via OSMnx, infer lane count and free-flow speed from OSM tags, estimate lane-blockage from violation density × dwell time, and apply the BPR delay function (α=0.15, β=4) to translate blockage into vehicle-hours lost. Valued at ₹200/hour (Government of Karnataka economic-survey baseline), the top 100 hotspots cost the city **₹389 Cr per year — approximately 10% of Bengaluru's total ₹38,000 Cr congestion bill, attributable to just 100 parking zones**.

**Module 3 — Violation forecasting:** Profiling the data revealed a structural enforcement gap — **~95% of BTP bookings happen before 3 PM, with peak activity 8 AM – noon**, and near-zero activity after 6 PM. This is not because illegal parking stops, but because officers go home. We trained an XGBoost regressor on 1.38 million (hotspot × hour) observations with 11 features (calendar + autoregressive lags + spatial + vehicle). Using a strict 70/15/15 chronological train/val/test split with early stopping (iter 59 of 1500 max), the model achieves **test R² = 0.43** with a train→test gap of just **+0.07** (well below the 0.15 overfitting threshold). The forecast predicts **~722 unbooked violations per 24 hours** across the top 100 hotspots in the 15:00–07:00 enforcement blind spot.

**Module 4 — Patrol route optimization:** Weighted KMeans assigns blind-spot hotspots to 5 patrols home-based at real BTP stations (Upparpet, Shivajinagar, Malleshwaram, HAL Old Airport, Vijayanagara), with weights balanced by expected catches. Within each patrol, nearest-neighbor TSP minimises travel at 20 km/h urban speed plus 15-minute service time per zone. The output for a 5-hour evening shift: **37 optimised stops yielding 113 expected catches — 4.5× the current BTP evening output (~25)** with the same officer-hours and same patrol budget.

All four modules feed into a **live Streamlit dashboard** (https://park-watch.streamlit.app) that BTP officers can navigate themselves — filter by police station, hour, or vehicle type; click any hotspot for full details; view the color-coded patrol map for tonight. Every numerical assumption (dwell time, value-of-time, lane capacity, BPR parameters, patrol speed) is an explicit, defensible knob.

Park-Watch is built entirely on the data BTP already collects. It requires no new sensors, no new data pipelines, and no new hardware — only a dashboard. It is the intelligence layer that closes Bengaluru's 12-hour enforcement coverage gap.

---

## Technology & Category Tags

**Tags:**
- Machine Learning
- Data Science
- Computer Science
- Smart City
- Urban Planning
- Geographic Information Systems (GIS)
- Predictive Analytics
- Public Safety

**Technologies used:**
Python, pandas, scikit-learn, XGBoost, OSMnx, NetworkX, Streamlit, Folium, python-pptx

---

## Application URL

https://park-watch.streamlit.app

## Public GitHub Repository

https://github.com/arnavja/park-watch

## Video Presentation

*(To record — 3–5 min screen walkthrough of the dashboard, narrating the four modules and the headline numbers)*

## Slide Presentation

[Park_Watch_Pitch.pptx](outputs/Park_Watch_Pitch.pptx) — 10 slides, embedded dashboard screenshots

## Cover Image

*(To create — recommend the BLR hotspot heatmap with the title overlay)*

---

## Team — Byte_me_kaar

- Arnav Jain ([@arnavja](https://github.com/arnavja)) — IIIT Bangalore, B.Tech DSAI 2nd year
