#!/usr/bin/env python3
"""
handwriting_alternating.py - 4-line handwriting worksheets, every other line blank.

Where handwriting_practice.py fills the top half of the page and leaves the
bottom half blank, this one interleaves: line 1 carries the model text, line 2
is blank for you to copy it, line 3 carries the next model line, and so on all
the way down.  Copying is easier because what you are copying sits directly
above where you write it.

Every page keeps the same four-rule ruling (red ascender / blue midline / blue
baseline / red descender) on the blank lines as on the written ones, and each
page carries an even number of ruled lines so no model line is ever left
without its blank line underneath.

All the drawing, font embedding and cursive shaping is reused from
handwriting_practice.py, which sits next to this file and is not modified.

    ./handwriting_alternating.py "Some text to practise"
    ./handwriting_alternating.py -f lesson.txt --font kid-simple --italic
    pbpaste | ./handwriting_alternating.py --rows 14
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import handwriting_practice as hp
except ImportError:
    sys.exit("handwriting_practice.py must sit next to this script.")

Canvas, ScriptFont, PDF = hp.Canvas, hp.ScriptFont, hp.PDF
num, helv_width = hp.num, hp.helv_width


# --------------------------------------------------------------------------
# Geometry: the same sheet, but always an even number of ruled lines
# --------------------------------------------------------------------------


class AlternatingSheet(hp.Sheet):
    """A ruled page whose lines pair up as model / blank, model / blank."""

    def _fit_rows(self, top: float, bottom: float, want: int) -> int:
        n = super()._fit_rows(top, bottom, want)
        if n % 2:                       # an odd last line would have nowhere to copy to
            n -= 1
        return max(n, 2)

    @property
    def lines_per_page(self) -> int:
        return self.rows // 2

    def model_row(self, i: int) -> int:
        """Ruled row index that model line i is written on."""
        return 2 * i


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


def build_pdf(lines: list[str], font: ScriptFont, sheet: AlternatingSheet, opts) -> bytes:
    ink = opts.ink
    red, blue, guide = opts.rule_asc, opts.rule_mid, opts.guide_color
    size = opts.computed_size
    per_page = sheet.lines_per_page

    chunks = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    pdf = PDF()
    font_obj = font.embed(pdf)
    helv_r = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                     b"/Encoding /WinAnsiEncoding >>")
    helv_b = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                     b"/Encoding /WinAnsiEncoding >>")
    res = pdf.add(
        f"<< /Font << /F1 {font_obj} 0 R /HR {helv_r} 0 R /HB {helv_b} 0 R >> >>".encode("latin-1")
    )

    pages_obj = pdf.reserve()
    page_ids: list[int] = []
    total = len(chunks)

    for page_no, chunk in enumerate(chunks, start=1):
        c = Canvas()

        # ---- header ----
        if opts.header:
            c.helv(opts.title, sheet.left, sheet.title_y, 13.5, opts.title_color, bold=True)
            if opts.subtitle:
                c.helv(opts.subtitle, sheet.left, sheet.sub_y, 8.5, (0.35, 0.35, 0.35))
            if opts.tag:
                tw = helv_width(opts.tag, 10.5, bold=True)
                c.helv(opts.tag, sheet.right - tw, sheet.title_y, 10.5,
                       opts.title_color, bold=True)
            c.hline(sheet.left, sheet.right, sheet.rule_y, opts.title_color, 1.2)
            if sheet.field_y:
                y = sheet.field_y
                c.helv("Name:", sheet.left, y, 9, (0.2, 0.2, 0.2))
                c.hline(sheet.left + 32, sheet.left + 210, y - 2.5, (0.35, 0.35, 0.35), 0.6)
                dw = helv_width("Date:", 9)
                dx = sheet.right - 92
                c.helv("Date:", dx, y, 9, (0.2, 0.2, 0.2))
                c.hline(dx + dw + 4, sheet.right, y - 2.5, (0.35, 0.35, 0.35), 0.6)

        # ---- ruling: every line on the page, written or blank ----
        for i in range(sheet.rows):
            r = sheet.row(i)
            if opts.guides:
                span = r["asc"] - r["base"]
                dx = math.tan(math.radians(opts.slant)) * span
                x = sheet.left + opts.guide_step
                while x < sheet.right - 1:
                    c.line(x, r["base"], x + dx, r["asc"], guide, 0.6)
                    x += opts.guide_step
            c.hline(sheet.left, sheet.right, r["asc"], red, 1.5)
            c.hline(sheet.left, sheet.right, r["mid"], blue, 1.1,
                    dash=opts.midline_dash or None)
            c.hline(sheet.left, sheet.right, r["base"], blue, 1.5)
            c.hline(sheet.left, sheet.right, r["desc"], red, 1.5)

        # ---- the model lines, every other row ----
        for i, line in enumerate(chunk):
            if not line:
                continue
            r = sheet.row(sheet.model_row(i))
            c.script(font.show(line), sheet.left + opts.text_indent,
                     r["base"] + opts.baseline_shift, size, ink, opts.tracking,
                     opts.italic)

        # ---- footer ----
        if sheet.footer_y:
            c.hline(sheet.left, sheet.right, sheet.footer_y, (0.85, 0.85, 0.88), 0.4)
            if opts.footer:
                fw = helv_width(opts.footer, 7.5)
                c.helv(opts.footer, (sheet.left + sheet.right - fw) / 2,
                       sheet.footer_y - 14, 7.5, (0.5, 0.5, 0.5))
            if opts.page_numbers:
                label = f"Page {page_no} of {total}"
                lw = helv_width(label, 7.5)
                c.helv(label, sheet.right - lw, sheet.footer_y - 14, 7.5, (0.5, 0.5, 0.5))

        content = pdf.add_stream("", c.data())
        page_ids.append(pdf.add(
            f"<< /Type /Page /Parent {pages_obj} 0 R "
            f"/MediaBox [0 0 {num(sheet.w)} {num(sheet.h)}] "
            f"/Resources {res} 0 R /Contents {content} 0 R >>".encode("latin-1")
        ))

    kids = " ".join(f"{p} 0 R" for p in page_ids)
    pdf.put(pages_obj,
            f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("latin-1"))
    root = pdf.add(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("latin-1"))
    info = pdf.add(b"<< /Title " + hp.pdf_string(opts.title) +
                   b" /Producer (handwriting_alternating.py) >>")
    return pdf.build(root, info)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(
        prog="handwriting_alternating.py",
        description="Generate a 4-line handwriting worksheet with every other "
                    "line left blank: a model line, then a blank line to copy it "
                    "onto, all the way down the page.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  ./handwriting_alternating.py "The quick brown fox jumps over the lazy dog."
  ./handwriting_alternating.py -f lesson.txt --font kid-simple --italic
  pbpaste | ./handwriting_alternating.py --rows 14 --open
""",
    )
    p.add_argument("text", nargs="*", help="content to practise (or use -f / stdin)")
    p.add_argument("-f", "--file", help="read the content from a text file")
    p.add_argument("-o", "--output", help="output PDF path")
    p.add_argument("--open", dest="open_after", action="store_true",
                   help="open the PDF when it is finished")

    g = p.add_argument_group("layout")
    g.add_argument("--rows", type=int, default=12,
                   help="ruled lines per page, rounded down to an even number and "
                        "shrunk if they will not fit (default: 12, so 6 model lines)")
    g.add_argument("--unit", type=float, default=11.25,
                   help="spacing between the four rules, in points (default: 11.25)")
    g.add_argument("--min-gap", type=float, default=8.0,
                   help="smallest allowed gap between ruled lines (default: 8)")
    g.add_argument("--page", default="a4", choices=sorted(hp.PAGE_SIZES),
                   help="page size (default: a4)")
    g.add_argument("--margin", type=float, default=36.0, help="side margin (default: 36)")
    g.add_argument("--text-indent", type=float, default=4.0,
                   help="left inset for the model text (default: 4)")
    g.add_argument("--baseline-shift", type=float, default=0.0,
                   help="nudge the model text up/down, in points")

    g = p.add_argument_group("type")
    g.add_argument("--font", default=hp.DEFAULT_FONT,
                   help=f"preset name or font file path (default: {hp.DEFAULT_FONT})")
    g.add_argument("--font-index", type=int, default=0, help="face index inside a .ttc")
    g.add_argument("--fit", default="xheight", choices=["xheight", "ascender", "descender"],
                   help="how the face is scaled to the ruling (default: xheight)")
    g.add_argument("--font-scale", type=float, default=1.0,
                   help="extra multiplier on the computed size (default: 1.0)")
    g.add_argument("--overflow", type=float, default=1.25,
                   help="how far ascenders/descenders may pass their rule (default: 1.25)")
    g.add_argument("--tracking", type=float, default=0.0,
                   help="extra letter spacing in points")
    g.add_argument("--italic", nargs="?", type=float, const=12.0, default=0.0,
                   metavar="DEGREES",
                   help="slant the model text; bare --italic means 12 degrees")
    g.add_argument("--ink", type=hp.parse_rgb, default=(0.3, 0.3, 0.3),
                   help="model text colour: grey level, r,g,b or #rrggbb (default: 0.3)")
    g.add_argument("--lang", default="",
                   help='language tag for locale-aware letterforms, e.g. "nl"')
    g.add_argument("--list-fonts", action="store_true", help="show the font presets and exit")
    g.add_argument("--fetch-fonts", action="store_true",
                   help="download the school-handwriting fonts into ./fonts and exit")

    g = p.add_argument_group("ruling")
    g.add_argument("--rule-asc", type=hp.parse_rgb, default=(0.8, 0.1, 0.1),
                   help="ascender/descender rule colour (default: red)")
    g.add_argument("--rule-mid", type=hp.parse_rgb, default=(0.12, 0.52, 0.95),
                   help="midline/baseline rule colour (default: blue)")
    g.add_argument("--midline-dash", default="", metavar="PATTERN",
                   help='dash the midline, e.g. --midline-dash "3 3"')
    g.add_argument("--no-guides", dest="guides", action="store_false",
                   help="drop the vertical slant guides")
    g.add_argument("--guide-step", type=float, default=22.5,
                   help="spacing of the slant guides (default: 22.5)")
    g.add_argument("--guide-color", type=hp.parse_rgb, default=(0.92, 0.94, 0.97),
                   help="slant guide colour")
    g.add_argument("--slant", type=float, default=None,
                   help="slant guide angle in degrees "
                        "(default: follow --italic, else upright)")

    g = p.add_argument_group("page furniture")
    g.add_argument("--title", default="Handwriting Practice", help="header title")
    g.add_argument("--subtitle", default="", help="header subtitle")
    g.add_argument("--tag", default="", help="right-hand header label")
    g.add_argument("--footer", default="", help="centred footer text")
    g.add_argument("--title-color", type=hp.parse_rgb, default=(0.07, 0.27, 0.49),
                   help="header colour")
    g.add_argument("--no-header", dest="header", action="store_false", help="omit the header")
    g.add_argument("--no-name-date", dest="name_date", action="store_false",
                   help="omit the Name/Date fields")
    g.add_argument("--no-footer-rule", dest="footer_rule", action="store_false",
                   help="omit the footer rule")
    g.add_argument("--no-page-numbers", dest="page_numbers", action="store_false",
                   help="omit page numbers")

    g = p.add_argument_group("text handling")
    g.add_argument("--keep-linebreaks", action="store_true",
                   help="treat every input line as its own line instead of reflowing")
    g.add_argument("--paragraph-gap", type=int, default=0,
                   help="blank model lines inserted between paragraphs (default: 0)")

    # The shared Sheet still reads these; they have no meaning in this layout.
    p.set_defaults(split=0.5, content_rows=0, divider=False, divider_label="")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)

    if opts.fetch_fonts:
        return hp.fetch_fonts()

    if opts.list_fonts:
        hp.list_fonts()
        return 0

    text = hp.load_text(opts)
    if not text.strip():
        print("No content given.\n", file=sys.stderr)
        print('  ./handwriting_alternating.py "your text here"', file=sys.stderr)
        print("  ./handwriting_alternating.py -f lesson.txt", file=sys.stderr)
        print("  cat lesson.txt | ./handwriting_alternating.py", file=sys.stderr)
        return 2

    path, index = hp.resolve_font(opts.font, opts.font_index)
    font = ScriptFont(path, index)
    font.lang = opts.lang
    if font.needs_shaping and not font.shaping:
        print(f"  warning: {font.family} joins its letters through OpenType "
              "shaping.\n           Install uharfbuzz for correct joins:  "
              "pip install uharfbuzz", file=sys.stderr)

    sheet = AlternatingSheet(opts)

    font.synthetic_italic = opts.italic
    if opts.slant is None:                  # guides lean with the writing
        opts.slant = opts.italic

    opts.computed_size = hp.choose_size(font, sheet.unit, opts)
    overhang = math.tan(math.radians(opts.italic)) * 2 * sheet.unit
    max_w = (sheet.right - sheet.left) - opts.text_indent - overhang
    lines = hp.flow(font, text, opts.computed_size, max_w, opts)

    data = build_pdf(lines, font, sheet, opts)

    out = opts.output
    if not out:
        stem = os.path.splitext(os.path.basename(opts.file))[0] if opts.file else None
        out = f"{stem}-alternating.pdf" if stem else "handwriting-alternating.pdf"
    if not out.lower().endswith(".pdf"):
        out += ".pdf"
    with open(out, "wb") as fh:
        fh.write(data)

    pages = math.ceil(len(lines) / sheet.lines_per_page) if lines else 1
    print(f"Wrote {out}")
    print(f"  {pages} page(s) - {sheet.rows} ruled lines each, alternating "
          f"{sheet.lines_per_page} model + {sheet.lines_per_page} blank")
    print(f"  {len(lines)} line(s) of content in {font.family} "
          f"at {opts.computed_size:.1f}pt")
    if font.missing:
        shown = " ".join(f"{ch!r}" for ch in sorted(font.missing))
        print(f"  note: {font.family} has no glyph for {shown} - substituted",
              file=sys.stderr)

    if opts.open_after:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, out], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
