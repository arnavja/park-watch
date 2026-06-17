"""Generate hackathon-submission cover image (1200×630 — standard OG/social size)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
OUT = ROOT / "outputs" / "cover.png"
SRC = ROOT / "outputs" / "screens" / "full_dashboard.png"

# Brand palette
NAVY = (11, 42, 74)
ORANGE = (255, 107, 43)
WHITE = (255, 255, 255)
LIGHT = (242, 244, 248)

W, H = 1200, 630


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    # Background: BLR hotspot heatmap from the dashboard
    full = Image.open(SRC)
    # Heatmap is at PNG y ≈ 5500–7200 (the Folium map with red dots over BLR)
    bg_strip = full.crop((400, 5500, 3000, 7200))
    # Scale to fit canvas at 1.6× width so the map fills nicely
    target_w = int(W * 1.4)
    bg_strip = bg_strip.resize(
        (target_w, int(bg_strip.height * target_w / bg_strip.width))
    )
    # Position so the map shows on the right side
    x0 = max(0, bg_strip.width - W)
    y0 = max(0, (bg_strip.height - H) // 2)
    bg = bg_strip.crop((x0, y0, x0 + W, y0 + H))

    # Cover canvas
    cover = Image.new("RGB", (W, H), WHITE)
    cover.paste(bg, (0, 0))

    # Dark overlay so text is legible
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    panel_w = int(W * 0.58)
    draw.rectangle((0, 0, panel_w, H), fill=(*NAVY, 245))
    for i in range(80):
        a = int(245 * (1 - i / 80))
        draw.rectangle((panel_w + i, 0, panel_w + i + 1, H), fill=(*NAVY, a))
    # Top + bottom subtle bands to hide any dashboard chrome
    draw.rectangle((0, 0, W, 20), fill=(*NAVY, 200))
    draw.rectangle((0, H - 20, W, H), fill=(*NAVY, 200))
    cover = Image.alpha_composite(cover.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(cover)

    # Brand mark
    draw.text((50, 50), "PARK-WATCH", font=_font(46, bold=True), fill=WHITE)
    draw.rectangle((50, 110, 110, 116), fill=ORANGE)

    # Title
    draw.text(
        (50, 145),
        "AI-driven parking enforcement",
        font=_font(34), fill=WHITE,
    )
    draw.text(
        (50, 188),
        "intelligence for Bengaluru",
        font=_font(34), fill=WHITE,
    )

    # Stats block
    y = 285
    stats = [
        ("298,450", "real BTP violations analysed"),
        ("₹389 Cr", "annual congestion cost mapped"),
        ("4.5×", "patrol enforcement output"),
    ]
    for value, label in stats:
        draw.text((50, y), value, font=_font(28, bold=True), fill=ORANGE)
        draw.text((180, y + 5), label, font=_font(18), fill=LIGHT)
        y += 50

    # Footer
    draw.text(
        (50, H - 70),
        "Gridlock Hackathon  ·  Flipkart HQ × BTP  ·  Team Byte Titans",
        font=_font(15), fill=LIGHT,
    )
    draw.text(
        (50, H - 45),
        "park-watch.streamlit.app",
        font=_font(15, bold=True), fill=ORANGE,
    )

    cover.save(OUT, optimize=True)
    print(f"Saved cover → {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
