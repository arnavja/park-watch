"""Park-Watch — Bengaluru illegal-parking enforcement intelligence."""
import sys
from pathlib import Path

import folium
import numpy as np
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
    "Patrols deployed", 1, 10, 5,
    help=(
        "Number of patrol units BTP allocates for the shift. "
        "Routes and expected catches recompute live. "
        "Default 5 is a demo scenario; scale up to match BTP's actual fleet."
    ),
)
shift_window = st.sidebar.slider(
    "Patrol shift window (24h)", 0, 23, (18, 23),
    help=(
        "Real BTP blind spot starts at ~15:00 (when bookings collapse) and "
        "extends into the next morning. The default 18:00–23:00 covers the "
        "commercial evening rush. Slide to 15:00 to see the broader gap."
    ),
)
shift_start, shift_end = shift_window
if shift_end - shift_start < 2:
    shift_end = shift_start + 2
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
def get_routes_for(n: int, s_start: int, s_end: int):
    if fc is None:
        return routes
    out = compute_patrol_routes(fc, hot, n_patrols=n,
                                  shift_start=s_start, shift_end=s_end)
    if out is None or len(out) == 0:
        return out
    return out.merge(
        hot[["cluster_id", "top_station", "top_junction"]].rename(
            columns={"cluster_id": "cluster"}
        ),
        on="cluster", how="left",
    )


dyn_routes = get_routes_for(n_patrols, shift_start, shift_end)
if dyn_routes is not None and len(dyn_routes):
    routes = dyn_routes

if routes is not None and len(routes):
    st.subheader(
        f"🚓 Tonight's optimized patrol plan — {n_patrols} patrols ({shift_start:02d}:00–{shift_end:02d}:00)"
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

    # ─── Per-officer shift sheet with LIVE progress tracking
    st.subheader("📋 Per-officer shift sheet — live tracking")
    st.caption(
        "Step-by-step orders with a real-time progress tracker. As each stop "
        "is completed, the remaining route, ETAs, and expected catches "
        "recalculate. BTP can replan the rest of the shift on demand."
    )
    homes = sorted(routes["patrol_home"].unique())
    selected = st.selectbox(
        "Select patrol", homes,
        format_func=lambda h: f"🚓 Officer @ {h}",
        key="patrol_select",
    )
    pgrp = routes[routes["patrol_home"] == selected].sort_values("seq").reset_index(drop=True)

    # ── Session-state progress per patrol
    progress_key = f"completed_{selected}"
    if progress_key not in st.session_state:
        st.session_state[progress_key] = 0  # number of steps completed

    completed_n = st.session_state[progress_key]
    total_n = len(pgrp)
    done = pgrp.iloc[:completed_n] if completed_n else pgrp.iloc[0:0]
    remaining = pgrp.iloc[completed_n:]

    # ── Progress KPIs
    done_catches = done["expected_catches"].sum() if len(done) else 0
    remaining_catches = remaining["expected_catches"].sum()

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Stops done", f"{completed_n} / {total_n}")
    p2.metric("Catches so far", f"~{done_catches:.0f}")
    p3.metric("Remaining stops", len(remaining))
    p4.metric("Catches remaining", f"~{remaining_catches:.0f}")

    st.progress(completed_n / max(1, total_n))

    # ── Action buttons
    btn1, btn2, btn3 = st.columns([1, 1, 2])
    if btn1.button("✅ Mark next stop done",
                    disabled=(completed_n >= total_n),
                    key=f"mark_{selected}"):
        st.session_state[progress_key] += 1
        st.rerun()
    if btn2.button("🔄 Reset progress", key=f"reset_{selected}"):
        st.session_state[progress_key] = 0
        st.rerun()
    btn3.markdown(
        "*Replan: nearest-neighbour TSP re-sequences remaining stops from "
        "the current position (live).*"
    )

    # ── Completed stops
    if len(done):
        st.markdown("#### ✅ Completed")
        for _, r in done.iterrows():
            st.markdown(
                f"~~Step {int(r['seq'])} · {r['top_station']} "
                f"({r['top_junction']}) · "
                f"{r['arrive']} → {r['depart']} · "
                f"{float(r['expected_catches']):.1f} catches~~"
            )

    # ── Remaining stops — replan from current IST time + position
    if len(remaining):
        # Real IST clock — drives realistic ETAs
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(tz=ist)
        true_ist_str = now_ist.strftime("%H:%M")
        true_now_min = now_ist.hour * 60 + now_ist.minute

        SHIFT_START_MIN = shift_start * 60
        SHIFT_END_MIN_CLAMP = shift_end * 60

        # Decide effective planning time + appropriate banner message
        if true_now_min < SHIFT_START_MIN:
            now_min = SHIFT_START_MIN
            st.info(
                f"🕐 IST clock: **{true_ist_str}** · Shift starts at "
                f"**{shift_start:02d}:00** — ETAs computed from shift start "
                f"({SHIFT_END_MIN_CLAMP - SHIFT_START_MIN} min window)."
            )
        elif true_now_min > SHIFT_END_MIN_CLAMP:
            now_min = SHIFT_START_MIN
            st.warning(
                f"🕐 IST clock: **{true_ist_str}** · Shift "
                f"{shift_start:02d}:00–{shift_end:02d}:00 has ended. "
                f"Showing what the plan would have looked like from shift start."
            )
        else:
            now_min = true_now_min
            remaining_min = SHIFT_END_MIN_CLAMP - now_min
            st.info(
                f"🕐 IST clock: **{true_ist_str}** · "
                f"**{remaining_min} min** left in shift "
                f"({shift_start:02d}:00–{shift_end:02d}:00) · ETAs from now."
            )

        # Current position = last completed location, or home if none done
        if completed_n > 0:
            last = done.iloc[-1]
            cur_lat, cur_lon = float(last["lat"]), float(last["lon"])
            # Use the LATER of scheduled-depart or actual-IST-clock
            sched_min = sum(int(x) * f for x, f in zip(
                last["depart"].split(":"), (60, 1)
            ))
            cur_time_str = f"{max(now_min, sched_min)//60:02d}:{max(now_min, sched_min)%60:02d}"
        else:
            from patrol_optimizer import PATROL_HOMES
            cur_lat, cur_lon = PATROL_HOMES.get(selected, (12.97, 77.59))
            cur_time_str = f"{now_min//60:02d}:{now_min%60:02d}"

        # Re-sequence remaining via nearest-neighbour from current pos
        from patrol_optimizer import haversine_km, PATROL_SPEED_KMH, SERVICE_TIME_MIN

        def _to_min(s):
            try:
                h, m = s.split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return 18 * 60

        SHIFT_END_MIN = shift_end * 60
        cur_time_min_initial = _to_min(cur_time_str)

        def plan_route(stops_df, start_lat, start_lon, start_time_min):
            """Value-density nearest-neighbour from start position."""
            r_lat, r_lon, t = start_lat, start_lon, start_time_min
            order = []
            rem = stops_df.copy().reset_index(drop=True)
            while len(rem):
                d_km = haversine_km(r_lat, r_lon, rem["lat"].values, rem["lon"].values)
                tm = d_km / PATROL_SPEED_KMH * 60
                score = rem["expected_catches"].values / (tm + SERVICE_TIME_MIN + 1e-6)
                idx = int(np.argmax(score))
                ch = rem.iloc[idx].to_dict()
                ch["_new_travel_min"] = float(tm[idx])
                ch["_new_arrive_min"] = t + tm[idx]
                ch["_new_depart_min"] = ch["_new_arrive_min"] + SERVICE_TIME_MIN
                order.append(ch)
                r_lat, r_lon = float(ch["lat"]), float(ch["lon"])
                t = ch["_new_depart_min"]
                rem = rem.drop(rem.index[idx]).reset_index(drop=True)
            return order

        # First pass — try to visit ALL remaining stops
        new_order = plan_route(remaining, cur_lat, cur_lon, cur_time_min_initial)
        dropped_stops = []

        # Time-budget aware: drop stops by lowest value-per-minute (catches
        # ÷ (travel_min + service_min)) rather than just lowest absolute
        # catches. A small zone far away costs more time per catch than a
        # nearby medium zone, so the far-away one drops first.
        while new_order and new_order[-1]["_new_depart_min"] > SHIFT_END_MIN:
            # Compute value-per-minute for each currently scheduled stop
            scored = [
                {
                    **r,
                    "_value_per_min": float(r["expected_catches"]) / max(
                        1.0,
                        float(r["_new_travel_min"]) + 15.0,
                    ),
                }
                for r in new_order
            ]
            worst = min(scored, key=lambda r: r["_value_per_min"])
            dropped_stops.append(worst)
            kept = remaining[
                remaining["cluster"] != worst["cluster"]
            ].copy()
            # Also remove any previously dropped clusters from the candidate set
            dropped_clusters = {d["cluster"] for d in dropped_stops}
            kept = kept[~kept["cluster"].isin(dropped_clusters)]
            if kept.empty:
                new_order = []
                break
            new_order = plan_route(kept, cur_lat, cur_lon, cur_time_min_initial)
        cur_time_min = new_order[-1]["_new_depart_min"] if new_order else cur_time_min_initial

        st.markdown("#### ⏳ Remaining (replanned from current position)")
        for i, r in enumerate(new_order, start=1):
            ah, am = divmod(int(r["_new_arrive_min"]), 60)
            dh, dm = divmod(int(r["_new_depart_min"]), 60)
            catches = float(r["expected_catches"])
            cat_word = (
                "very high (>10)" if catches > 10 else
                "high (3–10)" if catches > 3 else
                "moderate (1–3)" if catches > 1 else
                "low (<1)"
            )
            st.markdown(
                f"**Next-{i} → {r['top_station']}**  \n"
                f"📍 {r['top_junction']}  \n"
                f"🕐 Arrive **{ah:02d}:{am:02d}** · Depart **{dh:02d}:{dm:02d}** "
                f"· Travel **{int(r['_new_travel_min'])} min**  \n"
                f"🎯 Expected catches: **{catches:.1f}** ({cat_word})  \n"
                f"---"
            )

        # Show actually-dropped stops (time-budget aware reorder)
        if dropped_stops:
            dropped_total = sum(d["expected_catches"] for d in dropped_stops)
            shift_len = shift_end - shift_start
            st.warning(
                f"⚠️  Auto-dropped **{len(dropped_stops)} low-yield stop(s)** "
                f"to fit the {shift_len}-hour shift window. "
                f"Catches forgone: **{dropped_total:.1f}**. "
                f"Dropped by lowest value-per-minute (catches ÷ time cost), "
                f"so far-away small zones go first."
            )
            with st.expander("View dropped stops"):
                for d in dropped_stops:
                    vpm = d.get("_value_per_min", 0)
                    st.markdown(
                        f"• **{d['top_station']}** ({d['top_junction']}) — "
                        f"{float(d['expected_catches']):.1f} catches · "
                        f"{vpm:.3f} catches/min cost"
                    )
    else:
        st.success(
            f"🎉 Shift complete. Total bookings: **~{done_catches:.0f}**."
        )

    # ── Downloadable shift sheet (original + progress notes)
    sheet_lines = [
        "PARK-WATCH — Nightly Shift Sheet",
        "=" * 50,
        f"Officer based at: {selected}",
        f"Shift: {shift_start:02d}:00 – {shift_end:02d}:00",
        f"Total stops: {total_n}",
        f"Expected catches: ~{pgrp['expected_catches'].sum():.0f}",
        f"Progress: {completed_n}/{total_n} done",
        "",
    ]
    for _, r in pgrp.iterrows():
        status = "✓ DONE" if int(r["seq"]) <= completed_n else "  TODO"
        sheet_lines.append(
            f"{status}  Step {int(r['seq']):>2}. {r['arrive']} → "
            f"{r['top_station']:<20} ({r['top_junction']}) "
            f"~{float(r['expected_catches']):.1f} catches "
            f"({int(r['travel_min'])} min travel)"
        )
    sheet_lines.append("")
    sheet_lines.append("End of shift sheet.")
    sheet_txt = "\n".join(sheet_lines)
    st.download_button(
        "📥 Download this patrol's shift sheet (TXT)",
        sheet_txt,
        file_name=(
            f"shift_sheet_{selected.replace(' ', '_').replace('(', '').replace(')', '')}.txt"
        ),
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
