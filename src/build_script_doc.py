"""Build a readable Word doc of the demo-video script."""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches

OUT = Path(__file__).parent.parent / "outputs" / "Demo_Video_Script.docx"

NAVY = RGBColor(0x0B, 0x2A, 0x4A)
ORANGE = RGBColor(0xFF, 0x6B, 0x2B)
GREY = RGBColor(0x60, 0x60, 0x60)


def _heading(doc, text, size=22, color=NAVY, after=6):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(size)
    r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(after)
    return p


def _section_header(doc, timestamp, action):
    p = doc.add_paragraph()
    r1 = p.add_run(f"[{timestamp}]   ")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = ORANGE
    r2 = p.add_run(action)
    r2.italic = True
    r2.font.size = Pt(11)
    r2.font.color.rgb = GREY
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)


def _script_para(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(14)
    r.font.name = "Georgia"
    p.paragraph_format.line_spacing = 1.4
    p.paragraph_format.space_after = Pt(6)


def _note(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(10)
    r.italic = True
    r.font.color.rgb = GREY
    p.paragraph_format.space_after = Pt(8)


def build():
    doc = Document()

    # Page margins
    for s in doc.sections:
        s.top_margin = Inches(0.7)
        s.bottom_margin = Inches(0.7)
        s.left_margin = Inches(0.9)
        s.right_margin = Inches(0.9)

    # ── Title block
    _heading(doc, "Park-Watch — Demo Video Script", size=22, after=2)
    _heading(doc, "Gridlock Hackathon · Theme 1 · Flipkart HQ × BTP",
             size=11, color=GREY, after=14)

    # ── Recording setup
    _heading(doc, "Before you hit record", size=14, after=4)
    for line in [
        "•  Open https://park-watch.streamlit.app in a fresh browser window — no other tabs visible.",
        "•  Quit other apps so the recording stays clean.",
        "•  Use QuickTime: File → New Screen Recording. Click the arrow next to Record → enable Built-in Microphone.",
        "•  Browser zoom 100%, 1080p output.",
        "•  Practice once before the real take. Speak slowly. Leave 1–2 seconds of silence at start and end.",
    ]:
        p = doc.add_paragraph()
        r = p.add_run(line)
        r.font.size = Pt(11)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.15)

    doc.add_paragraph()  # spacer

    # ── Script sections
    _heading(doc, "The script", size=16, after=4)

    sections = [
        ("0:00 – 0:20",
         "Show top of dashboard with the title visible.",
         "Hi, I'm Arnav from Team Byte_me_kaar, and this is Park-Watch — my submission for "
         "Theme 1 of the Gridlock Hackathon.\n\n"
         "Bengaluru Traffic Police already collects rich data on illegal parking — almost "
         "three hundred thousand violation records in just five months. The problem isn't "
         "data. The problem is that they can't see patterns in it, and they can't act on "
         "those patterns in real time. Park-Watch fixes both."),

        ("0:20 – 0:50",
         "Hover over the bar chart in the 'enforcement blind spot' section.",
         "Let me show you the most important thing I discovered.\n\n"
         "Look at this bar chart. These are the hours when BTP books violations. Tall bars "
         "all morning, peaking around 10 to 11 AM. After 2 PM, the chart falls off a cliff. "
         "By 3 PM it's near zero. At 7 PM, across five entire months, only twenty-seven "
         "violations were booked in all of Bengaluru. Twenty-seven.\n\n"
         "That's not because illegal parking stops in the evening. That's because officers "
         "go home. BTP is blind for roughly twelve hours every single day."),

        ("0:50 – 1:25",
         "Scroll down to the 'Congestion cost' section.",
         "The first question I asked is — what does this cost the city?\n\n"
         "For each hotspot, I pull the real road network from OpenStreetMap — lane count, "
         "speed limit, geometry. Then I apply the standard BPR delay function from "
         "transportation engineering. The result: the top one hundred parking hotspots cost "
         "Bengaluru three hundred eighty-nine crore rupees per year. That's roughly ten "
         "percent of the city's total congestion bill, coming from just one hundred zones.\n\n"
         "KR Market Junction alone — sixteen crores per month."),

        ("1:25 – 2:05",
         "Scroll to the 'Blind-spot forecast' section.",
         "Next, I built a forecasting model that predicts where violations will happen "
         "during the blind spot.\n\n"
         "XGBoost regression on 1.38 million hourly observations. Eleven features — calendar, "
         "autoregressive lags, location, vehicle mix. Strict chronological "
         "train-validation-test split with early stopping.\n\n"
         "Test R-squared is 0.43. Train-to-test gap is 0.07, well below the overfit "
         "threshold. The model is small and well-regularised.\n\n"
         "What it tells us: across the top hundred hotspots, roughly seven hundred and "
         "twenty-two illegal-parking incidents will go unbooked in the next twenty-four "
         "hours unless something changes."),

        ("2:05 – 2:40",
         "Scroll to the 'Tonight's optimized patrol plan' section — let the colored route map render.",
         "So I converted the forecast into action.\n\n"
         "Weighted K-Means assigns hotspots across five patrols, balanced by expected "
         "catches. Within each patrol, nearest-neighbour TSP minimises travel time at "
         "twenty kilometres per hour with fifteen minutes of service per stop.\n\n"
         "The output for tonight's evening shift: thirty-seven optimised stops, one hundred "
         "and thirteen expected catches. That's four-point-five times what BTP catches "
         "today, with the same officers and the same five-hour shift.\n\n"
         "No new sensors. No new cameras. Just a smarter route."),

        ("2:40 – 3:00",
         "Slow-scroll back up to the top of the dashboard.",
         "Park-Watch is the intelligence layer that closes BTP's twelve-hour enforcement "
         "coverage gap.\n\n"
         "It runs on the data BTP already has. It costs nothing extra to deploy. And every "
         "officer keeps doing what they already do — just smarter.\n\n"
         "Thank you."),
    ]

    for ts, action, script in sections:
        _section_header(doc, ts, action)
        for para in script.split("\n\n"):
            _script_para(doc, para)

    # ── After recording
    doc.add_page_break()
    _heading(doc, "After you've recorded", size=14, after=6)

    steps = [
        ("1.", "Trim the start/end silence in QuickTime (Edit → Trim)."),
        ("2.", "Export — File → Export As → 1080p."),
        ("3.", "Upload to YouTube as Unlisted (do not post publicly until after judging closes)."),
        ("4.", "Paste the YouTube link into the HackerEarth 'Video Presentation' field."),
    ]
    for num, text in steps:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{num}  ")
        r1.bold = True
        r1.font.size = Pt(12)
        r1.font.color.rgb = ORANGE
        r2 = p.add_run(text)
        r2.font.size = Pt(12)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Inches(0.15)

    doc.add_paragraph()

    _heading(doc, "Tips for the live take", size=13, after=4)
    tips = [
        "Read the script before recording so the words feel natural — not robotic.",
        "Pause briefly at every full stop. Recording feels faster than it is.",
        "If you misspeak, pause for 2 seconds and restart the sentence — easier to edit later.",
        "Smile when you hit the 4.5× line at 2:25. Judges notice energy.",
        "The script targets ~3:00. If you naturally run to 3:15, that's fine. Aim for under 3:30 total.",
    ]
    for t in tips:
        p = doc.add_paragraph()
        r = p.add_run("•  " + t)
        r.font.size = Pt(11)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Inches(0.15)

    doc.save(OUT)
    print(f"Saved → {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
