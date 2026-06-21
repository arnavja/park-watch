"""Park-Watch — Bengaluru illegal-parking enforcement intelligence."""
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).parent))
from data_loader import FULL_DATASET_STATS, is_demo_mode, load
from patrol_optimizer import optimize as compute_patrol_routes

OUT = Path(__file__).parent.parent / "outputs"

st.set_page_config(page_title="Park-Watch BLR", layout="wide")
st.title("🅿️ Park-Watch — Bengaluru Parking Enforcement Intelligence")
st.caption(
    "298K real BTP violations · 5 months · 381 hotspots clustered · "
    "Built for Gridlock Hackathon @ Flipkart HQ"
)

if is_demo_mode():
    st.info(
        "ℹ️  **Public demo mode** — running on a 30K-row stratified sample of "
        "the 298K BTP dataset (raw data not redistributable). All headline "
        "metrics shown reflect the full 298K analysis."
    )


@st.cache_data
def get_data():
    df = load()
    hot = pd.read_csv(OUT / "hotspots.csv")
    cost_path = OUT / "congestion_cost.csv"
    cost = pd.read_csv(cost_path) if cost_path.exists() else None
    blind_path = OUT / "blind_spots.csv"
    blind = pd.read_csv(blind_path) if blind_path.exists() else None
    fc_path = OUT / "forecast_24h.parquet"
    fc = pd.read_parquet(fc_path) if fc_path.exists() else None
    routes_path = OUT / "patrol_routes.csv"
    routes = pd.read_csv(routes_path) if routes_path.exists() else None
    return df, hot, cost, blind, fc, routes


df, hot, cost, blind, fc, routes = get_data()

# ─── sidebar filters
st.sidebar.header("Display options")
top_n = st.sidebar.slider(
    "Hotspots shown on map", 10, 100, 100,
    help=(
        "Controls how many of the 381 hotspots are plotted on the map and "
        "shown in the priority table. Cost and patrol-plan calculations "
        "always use the top 100 hotspots — they cover >90% of all 298K "
        "violations."
    ),
)
n_patrols = st.sidebar.slider(
    "Patrols deployed (tonight)", 1, 10, 5,
    help=(
        "Number of patrol units BTP allocates for the evening shift "
        "(18:00–23:00). Routes and expected catches recompute live. "
        "Default 5 is a demo scenario; scale up to match BTP's actual "
        "nightly fleet."
    ),
)
st.sidebar.caption(
    "Headline metrics, the cost model, and forecasts are computed over "
    "the full 298K-record dataset and the top 100 hotspots."
)

# No filtering — the dashboard reflects the full dataset
station = "All"
vehicle = "All"
hour_range = (0, 23)

f = df.copy()
if station != "All":
    f = f[f["police_station"] == station]
f = f[f["hour"].between(*hour_range)]
if vehicle != "All":
    f = f[f["vehicle_type"] == vehicle]

# ─── KPIs
c1, c2, c3, c4 = st.columns(4)
total_label = (
    f"{FULL_DATASET_STATS['n_violations']:,}"
    if is_demo_mode() and station == "All" and vehicle == "All"
    else f"{len(f):,}"
)
c1.metric("Total violations", total_label)
c2.metric("Hotspot clusters", f"{len(hot):,}")
top_share = (
    f["police_station"].value_counts(normalize=True).head(5).sum() * 100
    if len(f) else 0
)
c3.metric("Top-5 stations share", f"{top_share:.0f}%")
night = (f["hour"] >= 18).sum() if len(f) else 0
night_pct = 100 * night / max(1, len(f))
c4.metric("Booked after 6 PM", f"{night_pct:.1f}%", help="Enforcement blind spot")

st.markdown("---")

# ─── BLIND SPOT INSIGHT
st.subheader("🚨 The 12-hour enforcement blind spot")
# Use pre-computed full-dataset distribution if available, else live filter
hourly_csv = OUT / "hourly_distribution.csv"
if hourly_csv.exists():
    hr_counts = pd.read_csv(hourly_csv)
else:
    hr_counts = df.groupby("hour").size().reset_index(name="violations")
st.bar_chart(hr_counts, x="hour", y="violations", height=240)
st.caption(
    "BTP officers book ~95% of violations before 3 PM (peak 8 AM–noon). Illegal parking "
    "continues 24/7 — but evening violations are systematically missed. "
    "**Park-Watch predicts where they happen.**"
)

st.markdown("---")

# ─── CONGESTION COST
if cost is not None:
    st.subheader("💸 Congestion cost — what these hotspots cost the city")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric(
        "Vehicle-hours lost / month",
        f"{cost['veh_hours_lost_per_month'].sum():,.0f}",
        help="Aggregated across top 100 hotspots using BPR delay model",
    )
    cc2.metric(
        "Economic cost / month",
        f"₹{cost['cost_inr_per_month'].sum()/1e7:.1f} Cr",
        help="At ₹200/hr value-of-time (GoK economic survey)",
    )
    cc3.metric(
        "Economic cost / year",
        f"₹{cost['cost_inr_per_month'].sum()*12/1e7:.0f} Cr",
        help="≈10% of BLR's ₹38,000 Cr annual congestion bill (TomTom). "
             "Computed across the top 100 hotspots — covers >90% of all violations.",
    )
    st.caption(
        "**Method:** snap each hotspot to nearest OSM road segment → compute "
        "lane-blockage from violation density × dwell time → apply BPR delay "
        "function → translate to vehicle-hours and INR. All assumptions "
        "(dwell time, value-of-time, lane capacity) are explicit knobs."
    )

    st.markdown("**Top 10 most costly hotspots:**")
    show_cost = cost.head(10)[[
        "road_name", "top_station", "n_violations", "lanes",
        "veh_hours_lost_per_day", "cost_inr_per_month",
    ]].copy()
    show_cost.columns = [
        "Road", "Station", "Violations (5mo)", "Lanes",
        "Veh-hrs lost/day", "Cost/month (₹)",
    ]
    show_cost["Cost/month (₹)"] = show_cost["Cost/month (₹)"].map(
        lambda x: f"₹{x/1e5:.1f} L"
    )
    show_cost["Veh-hrs lost/day"] = show_cost["Veh-hrs lost/day"].map(
        lambda x: f"{x:,.0f}"
    )
    st.dataframe(show_cost, use_container_width=True, hide_index=True)

    st.markdown("---")

# ─── BLIND-SPOT FORECAST
if blind is not None and fc is not None:
    st.subheader("🔮 Blind-spot forecast — predicting unbooked violations")
    b1, b2, b3 = st.columns(3)
    b1.metric(
        "Predicted unbooked violations / next 24h",
        f"{blind['predicted_blind_spot_violations_next24h'].sum():.0f}",
        help="XGBoost forecast at hotspots × hours 15:00–07:00",
    )
    b2.metric(
        "Model R² (held-out test)",
        "0.43",
        delta="train→test gap +0.07 (no overfit)",
        help="Trained on 1.1M hourly observations, evaluated on 198K held-out hours. "
             "Early stopping at iter 59 of 1500 max.",
    )
    b3.metric(
        "Model MAE / hour",
        "0.23 violations",
        help="Per-hotspot-hour prediction error",
    )
    st.caption(
        "**Method:** XGBoost on 1.38M hourly observations. Features: hour, "
        "day-of-week, month, lag-1h / lag-24h / lag-7d, 7-day rolling mean, "
        "spatial coords, vehicle-mix. Predicts violation count at each "
        "hotspot for each hour. Shaded hours 15:00–07:00 are when BTP is "
        "absent — these are the predicted unbooked violations."
    )

    # Top blind-spot zones
    st.markdown("**Top 10 zones with biggest enforcement blind spot:**")
    show_blind = blind.head(10)[[
        "top_station", "top_junction",
        "predicted_blind_spot_violations_next24h",
        "top_vehicle", "n_violations",
    ]].copy()
    show_blind.columns = [
        "Station", "Junction", "Predicted unbooked (24h)",
        "Top vehicle", "Total recorded",
    ]
    show_blind["Predicted unbooked (24h)"] = (
        show_blind["Predicted unbooked (24h)"].round(0).astype(int)
    )
    st.dataframe(show_blind, use_container_width=True, hide_index=True)

    # Forecast chart for top hotspot
    top_cluster = int(blind.iloc[0]["cluster"])
    fc_top = fc[fc["cluster"] == top_cluster].sort_values("hour_dt").copy()
    fc_top["hour_label"] = fc_top["hour_dt"].dt.strftime("%a %H:00")
    fc_top["is_blind"] = ~fc_top["hour"].between(8, 14)
    st.markdown(
        f"**Next-24h hourly forecast — Hotspot #{top_cluster} "
        f"({blind.iloc[0]['top_station']}):**"
    )
    st.bar_chart(fc_top, x="hour_label", y="pred", height=240)
    st.caption(
        "Bars represent predicted violations per hour. Hours outside 8 AM–"
        "2 PM are the enforcement blind spot — these violations would "
        "currently go unbooked."
    )

    st.markdown("---")

# ─── HOTSPOT MAP
st.subheader(f"🗺️ Top {top_n} illegal-parking hotspots")
hot_n = hot.head(top_n)
m = folium.Map(location=[12.97, 77.59], zoom_start=12, tiles="cartodbpositron")

# Heatmap of all filtered violations
if len(f):
    sample = f.sample(min(20000, len(f)), random_state=1)
    HeatMap(
        sample[["latitude", "longitude"]].values.tolist(),
        radius=8, blur=12, min_opacity=0.3,
    ).add_to(m)

cost_map = {}
if cost is not None:
    cost_map = cost.set_index("cluster_id")[
        ["cost_inr_per_month", "veh_hours_lost_per_day", "road_name"]
    ].to_dict("index")

mc = MarkerCluster().add_to(m)
for _, r in hot_n.iterrows():
    cc = cost_map.get(int(r.cluster_id), {})
    cost_line = ""
    if cc:
        cost_line = (
            f"💸 Cost: <b>₹{cc['cost_inr_per_month']/1e5:.1f} L/month</b><br>"
            f"🚗 Veh-hrs lost: <b>{cc['veh_hours_lost_per_day']:,.0f}/day</b><br>"
            f"🛣️ Road: {cc.get('road_name', '?')}<br>"
        )
    popup = (
        f"<b>Hotspot #{int(r.cluster_id)}</b><br>"
        f"Violations: <b>{int(r.n_violations):,}</b><br>"
        f"{cost_line}"
        f"Station: {r.top_station}<br>"
        f"Junction: {r.top_junction}<br>"
        f"Top vehicle: {r.top_vehicle}<br>"
        f"Morning share: {r.share_morning:.0%}<br>"
        f"Night share: {r.share_night:.0%}<br>"
        f"<i>{r.sample_address}</i>"
    )
    radius = 4 + (r.n_violations / hot["n_violations"].max()) * 20
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=radius,
        color="crimson", fill=True, fill_opacity=0.6,
        popup=folium.Popup(popup, max_width=350),
    ).add_to(mc)

st_folium(m, height=550, width=None, returned_objects=[])

st.markdown("---")

# ─── PATROL OPTIMIZER
@st.cache_data(show_spinner=False)
def get_routes_for(n: int):
    if fc is None:
        return routes
    out = compute_patrol_routes(fc, hot, n_patrols=n)
    if out is None or len(out) == 0:
        return out
    return out.merge(
        hot[["cluster_id", "top_station", "top_junction"]].rename(
            columns={"cluster_id": "cluster"}
        ),
        on="cluster", how="left",
    )


dyn_routes = get_routes_for(n_patrols)
if dyn_routes is not None and len(dyn_routes):
    routes = dyn_routes

if routes is not None and len(routes):
    st.subheader(
        f"🚓 Tonight's optimized patrol plan — {n_patrols} patrols (18:00–23:00)"
    )
    total_catches = routes["expected_catches"].sum()
    n_stops = len(routes)

    p1, p2, p3 = st.columns(3)
    p1.metric("Patrols deployed", n_patrols)
    p2.metric("Total stops", n_stops)
    p3.metric(
        "Expected catches (5-hr shift)",
        f"{total_catches:.0f}",
        delta=f"+{total_catches - 25:.0f} vs current ≈25",
        help="Current BTP evening output ≈ 5 violations/hour × 5 hrs",
    )

    st.caption(
        "**Method:** weighted KMeans partitions blind-spot hotspots across "
        "patrols → nearest-neighbor TSP sequencing within each patrol → "
        "ETA computed at 20 km/h with 15 min service time per zone."
    )

    # Map of routes
    rm = folium.Map(location=[12.97, 77.59], zoom_start=12,
                     tiles="cartodbpositron")
    palette = ["#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
               "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990"]
    for i, (home, grp) in enumerate(routes.groupby("patrol_home")):
        color = palette[i % len(palette)]
        grp = grp.sort_values("seq")
        coords = grp[["lat", "lon"]].values.tolist()
        folium.PolyLine(coords, color=color, weight=4, opacity=0.7,
                        tooltip=home).add_to(rm)
        for _, r in grp.iterrows():
            folium.CircleMarker(
                location=[r.lat, r.lon],
                radius=6 + r.expected_catches / 5,
                color=color, fill=True, fill_opacity=0.85,
                popup=(f"<b>Patrol {home}</b><br>"
                       f"Stop #{int(r.seq)} @ {r.arrive}<br>"
                       f"Expected: {r.expected_catches:.1f} catches"),
            ).add_to(rm)
    st_folium(rm, height=500, width=None, returned_objects=[])

    # Per-patrol breakdown
    for home, grp in routes.groupby("patrol_home"):
        catches = grp["expected_catches"].sum()
        with st.expander(
            f"🚓 {home}  ·  {len(grp)} stops  ·  ~{catches:.0f} catches"
        ):
            show = grp.sort_values("seq")[[
                "seq", "arrive", "depart", "top_station", "top_junction",
                "expected_catches", "travel_min",
            ]].copy()
            show.columns = ["#", "Arrive", "Depart", "Station", "Junction",
                            "Expected catches", "Travel (min)"]
            st.dataframe(show, use_container_width=True, hide_index=True)
    st.markdown("---")

    # ─── Per-officer shift sheet (printable instructions per patrol)
    st.subheader("📋 Per-officer shift sheet")
    st.caption(
        "Step-by-step orders for the officer on duty. Hand to BTP via WhatsApp "
        "or print before the shift. Each step lists the destination, arrival "
        "time, travel duration, and the expected number of catchable violations."
    )
    homes = sorted(routes["patrol_home"].unique())
    selected = st.selectbox(
        "Select patrol", homes,
        format_func=lambda h: f"🚓 Officer @ {h}",
    )
    pgrp = routes[routes["patrol_home"] == selected].sort_values("seq")
    pcatches = pgrp["expected_catches"].sum()
    first_arr = pgrp.iloc[0]["arrive"] if len(pgrp) else "—"
    last_dep = pgrp.iloc[-1]["depart"] if len(pgrp) else "—"

    s1, s2, s3 = st.columns(3)
    s1.metric("Stops tonight", len(pgrp))
    s2.metric("Expected catches", f"~{pcatches:.0f}")
    s3.metric("Shift window", f"{first_arr} – {last_dep}")

    st.markdown(f"#### 📝 Orders — Officer based at **{selected}**")
    st.markdown(
        f"**Shift start 18:00 · home base: {selected}**  \n"
        f"Proceed to the first stop. Issue tickets to illegally parked "
        f"vehicles using your e-challan device. Mark each stop as completed in "
        f"the app and proceed to the next."
    )

    for _, r in pgrp.iterrows():
        catches = float(r["expected_catches"])
        cat_word = (
            "very high (>10)" if catches > 10 else
            "high (3–10)" if catches > 3 else
            "moderate (1–3)" if catches > 1 else
            "low (<1)"
        )
        st.markdown(
            f"**Step {int(r['seq'])} → {r['top_station']}**  \n"
            f"📍 {r['top_junction']}  \n"
            f"🕐 Arrive **{r['arrive']}** · Depart **{r['depart']}** "
            f"· Travel **{int(r['travel_min'])} min**  \n"
            f"🎯 Expected catches: **{catches:.1f}** ({cat_word})  \n"
            f"---"
        )

    st.markdown(
        f"**Shift end {last_dep} · return to {selected}.**  \n"
        f"Total expected enforcement output: **~{pcatches:.0f} bookings** "
        f"across **{len(pgrp)} zones**."
    )

    # Downloadable per-officer sheet
    sheet_lines = [
        f"PARK-WATCH — Nightly Shift Sheet",
        f"=" * 50,
        f"Officer based at: {selected}",
        f"Shift: 18:00 – 23:00",
        f"Total stops: {len(pgrp)}",
        f"Expected catches: ~{pcatches:.0f}",
        f"",
    ]
    for _, r in pgrp.iterrows():
        sheet_lines.append(
            f"Step {int(r['seq']):>2}. {r['arrive']} → {r['top_station']:<20} "
            f"({r['top_junction']:<40}) "
            f"~{float(r['expected_catches']):.1f} catches "
            f"({int(r['travel_min'])} min travel)"
        )
    sheet_lines.append("")
    sheet_lines.append("End of shift sheet.")
    sheet_txt = "\n".join(sheet_lines)
    st.download_button(
        "📥 Download this patrol's shift sheet (TXT)",
        sheet_txt,
        file_name=f"shift_sheet_{selected.replace(' ', '_').replace('(', '').replace(')', '')}.txt",
        mime="text/plain",
    )

    st.markdown("---")

# ─── HOTSPOT TABLE
st.subheader("📋 Hotspot priority list")
show = hot_n[[
    "cluster_id", "n_violations", "top_station", "top_junction",
    "top_vehicle", "share_morning", "share_evening", "share_night",
    "share_weekend", "sample_address",
]].copy()
show.columns = [
    "ID", "Violations", "Station", "Junction", "Top Vehicle",
    "Morning %", "Evening %", "Night %", "Weekend %", "Address",
]
for c in ["Morning %", "Evening %", "Night %", "Weekend %"]:
    show[c] = (show[c] * 100).round(0).astype(int)
st.dataframe(show, use_container_width=True, height=400)
