#!/usr/bin/env python3
"""
md_to_pdf.py — Convert a markdown file to a presentable PDF using
reportlab (pure Python, no external binary dependency — avoids the
apt-package-availability problems hit with pandoc+wkhtmltopdf, which
isn't installable on Debian Trixie, the current python:3.12-slim base).

Uses Liberation Serif (metrically identical to Times New Roman; the real
Times New Roman is a licensed Microsoft font and can't be redistributed
via apt). Handles paragraphs (blank-line separated, matching this
project's .md convention) and # / ## headings. Basic **bold** / *italic*
markdown is converted to reportlab's inline markup.
"""
import sys
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

FONT_DIR = "/usr/share/fonts/truetype/liberation"

pdfmetrics.registerFont(TTFont("LiberationSerif", f"{FONT_DIR}/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("LiberationSerif-Bold", f"{FONT_DIR}/LiberationSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("LiberationSerif-Italic", f"{FONT_DIR}/LiberationSerif-Italic.ttf"))


def md_to_pdf(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=1 * inch, bottomMargin=1 * inch,
        leftMargin=1 * inch, rightMargin=1 * inch,
    )

    body_style = ParagraphStyle(
        "Body", fontName="LiberationSerif", fontSize=12,
        leading=12 * 1.4, spaceAfter=12, alignment=TA_LEFT,
    )
    h1_style = ParagraphStyle(
        "H1", fontName="LiberationSerif-Bold", fontSize=16,
        leading=16 * 1.3, spaceAfter=14, spaceBefore=6,
    )
    h2_style = ParagraphStyle(
        "H2", fontName="LiberationSerif-Bold", fontSize=14,
        leading=14 * 1.3, spaceAfter=10, spaceBefore=10,
    )

    story = []
    blocks = re.split(r"\n\s*\n", text.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            story.append(Paragraph(block[2:].strip(), h1_style))
        elif block.startswith("## "):
            story.append(Paragraph(block[3:].strip(), h2_style))
        else:
            para = " ".join(line.strip() for line in block.split("\n"))
            para = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", para)
            para = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", para)
            story.append(Paragraph(para, body_style))

    doc.build(story)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: md_to_pdf.py <input.md> <output.pdf>", file=sys.stderr)
        sys.exit(1)
    md_to_pdf(sys.argv[1], sys.argv[2])
