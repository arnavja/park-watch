"""Capture screenshots of the running Streamlit dashboard for the pitch deck."""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent.parent / "outputs" / "screens"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:8501"


def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Use a tall viewport so the whole Streamlit page fits at once
        ctx = browser.new_context(
            viewport={"width": 1600, "height": 6000},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        time.sleep(12)  # Folium maps + charts need a moment

        page.screenshot(path=str(OUT / "full_dashboard.png"), full_page=True)
        print(f"✓ full_dashboard.png")

        # Crop sections from full page
        from PIL import Image
        full = Image.open(OUT / "full_dashboard.png")
        W, H = full.size
        print(f"  full page: {W}×{H}")

        # Empirically tuned crops (px) — y values are top of each section
        # at 2× device scale (so full PNG height ≈ 2× CSS height)
        sections = [
            ("01_kpis_blindspot.png",   0,    1100),
            ("02_congestion_cost.png",  950,  2050),
            ("03_forecast.png",         2050, 3150),
            ("04_hotspot_map.png",      3150, 4250),
            ("05_patrol_routes.png",    4250, 5450),
        ]
        scale = 2  # device_scale_factor=2
        for name, y0, y1 in sections:
            y0p, y1p = y0 * scale, min(y1 * scale, H)
            cropped = full.crop((0, y0p, W, y1p))
            cropped.save(OUT / name)
            print(f"✓ {name}  (y {y0}–{y1}px CSS  →  {cropped.size})")

        browser.close()
        print(f"\nAll screenshots → {OUT}")


if __name__ == "__main__":
    capture()
