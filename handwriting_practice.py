#!/usr/bin/env python3
"""
handwriting_practice.py - generate 4-line handwriting practice worksheets as PDF.

Each page uses the classic 4-line ruling (red ascender / blue midline /
blue baseline / red descender) for the WHOLE page.  The top half of every page
is filled with your content in a handwriting font; the bottom half is left
blank on the same ruling so you can copy what you see above.  Content that does
not fit simply continues on the next page.

Pure Python - the only third-party import is fontTools, which ships with
Anaconda and most Python distributions.  Nothing else to install.

    ./handwriting_practice.py "Some text to practise"
    ./handwriting_practice.py -f lesson.txt -o lesson.pdf
    pbpaste | ./handwriting_practice.py --title "Module 8"
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import subprocess
import sys
import unicodedata
import zlib

# --------------------------------------------------------------------------
# Font presets.  First existing candidate wins.
# --------------------------------------------------------------------------

logging.getLogger("fontTools").setLevel(logging.ERROR)

_SUP = "/System/Library/Fonts/Supplemental"
_SYS = "/System/Library/Fonts"
_LIN = "/usr/share/fonts/truetype"

FONT_PRESETS: dict[str, list[tuple[str, int]]] = {
    # flowing joined-up scripts
    "cursive":      [(f"{_SUP}/SnellRoundhand.ttc", 0),
                     (f"{_LIN}/dejavu/DejaVuSerif-Italic.ttf", 0)],
    "cursive-bold": [(f"{_SUP}/SnellRoundhand.ttc", 1)],
    "chancery":     [(f"{_SUP}/Apple Chancery.ttf", 0)],
    "script":       [(f"{_SUP}/Savoye LET.ttc", 0)],
    # unjoined "manuscript" / print handwriting
    "print":        [(f"{_SUP}/Bradley Hand Bold.ttf", 0)],
    "note":         [(f"{_SYS}/Noteworthy.ttc", 0)],
    "chalk":        [(f"{_SUP}/ChalkboardSE.ttc", 1)],
    "comic":        [(f"{_SUP}/Comic Sans MS.ttf", 0)],
    # plain reference face
    "sans":         [(f"{_SUP}/Arial.ttf", 0),
                     (f"{_LIN}/dejavu/DejaVuSans.ttf", 0)],
}

DEFAULT_FONT = "script"

PAGE_SIZES = {
    "a4":     (595.2756, 841.8898),
    "letter": (612.0, 792.0),
    "legal":  (612.0, 1008.0),
    "a5":     (419.5276, 595.2756),
}

# Characters some handwriting faces lack; fall back to plain ASCII.
CHAR_FALLBACKS = {
    "‘": "'", "’": "'", "‚": ",", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    "…": "...", " ": " ", " ": " ", " ": " ",
    "•": "-", "·": ".", "­": "",
    "′": "'", "″": '"', "«": '"', "»": '"',
}

# --------------------------------------------------------------------------
# Standard-14 Helvetica metrics (AFM units/1000) - used for headers only, so
# the header never needs an embedded font.
# --------------------------------------------------------------------------

_HELV = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_HELV_B = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)
HELV_W = {"Helvetica": [int(v) for v in _HELV.split()],
          "Helvetica-Bold": [int(v) for v in _HELV_B.split()]}


def helv_width(text: str, size: float, bold: bool = False) -> float:
    table = HELV_W["Helvetica-Bold" if bold else "Helvetica"]
    total = 0
    for ch in text:
        o = ord(ch)
        total += table[o - 32] if 32 <= o <= 126 else 556
    return total * size / 1000.0


# --------------------------------------------------------------------------
# Minimal PDF writer
# --------------------------------------------------------------------------


def num(v: float) -> str:
    """Format a number the way PDF likes it: short, no exponent."""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def pdf_string(text: str) -> bytes:
    """Escape a literal PDF string, encoded as WinAnsi."""
    raw = text.encode("cp1252", "replace")
    out = bytearray(b"(")
    for b in raw:
        if b in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([b])
        elif b < 32 or b > 126:
            out += f"\\{b:03o}".encode()
        else:
            out.append(b)
    out += b")"
    return bytes(out)


class PDF:
    """Builds a flat, uncompressed-xref PDF file."""

    def __init__(self) -> None:
        self._objs: dict[int, bytes] = {}
        self._next = 1

    def reserve(self) -> int:
        n = self._next
        self._next += 1
        return n

    def put(self, n: int, body: bytes) -> int:
        self._objs[n] = body
        return n

    def add(self, body: bytes) -> int:
        return self.put(self.reserve(), body)

    def add_stream(self, extra: str, data: bytes, compress: bool = True) -> int:
        if compress:
            data = zlib.compress(data, 9)
            extra = "/Filter /FlateDecode " + extra
        head = f"<< {extra}/Length {len(data)} >>\nstream\n".encode("latin-1")
        return self.add(head + data + b"\nendstream")

    def build(self, root: int, info: int | None = None) -> bytes:
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict[int, int] = {}
        for n in sorted(self._objs):
            offsets[n] = len(out)
            out += f"{n} 0 obj\n".encode("latin-1") + self._objs[n] + b"\nendobj\n"
        size = self._next
        start = len(out)
        out += f"xref\n0 {size}\n".encode("latin-1")
        out += b"0000000000 65535 f \n"
        for n in range(1, size):
            if n in offsets:
                out += f"{offsets[n]:010d} 00000 n \n".encode("latin-1")
            else:
                out += b"0000000000 65535 f \n"
        trailer = f"trailer\n<< /Size {size} /Root {root} 0 R"
        if info:
            trailer += f" /Info {info} 0 R"
        trailer += f" >>\nstartxref\n{start}\n%%EOF\n"
        out += trailer.encode("latin-1")
        return bytes(out)


# --------------------------------------------------------------------------
# TrueType embedding (Identity-H / CIDFontType2)
# --------------------------------------------------------------------------


class ScriptFont:
    """Loads a TTF/OTF/TTC, measures it, and embeds it into a PDF."""

    ASC_PROBE = "bdfhklt"
    DESC_PROBE = "gjpqy"

    def __init__(self, path: str, index: int = 0) -> None:
        try:
            from fontTools.ttLib import TTFont
        except ImportError:  # pragma: no cover
            sys.exit("This program needs fontTools:  pip install fonttools")

        if not os.path.exists(path):
            sys.exit(f"Font not found: {path}")

        kwargs = {}
        if os.path.splitext(path)[1].lower() in (".ttc", ".otc"):
            kwargs["fontNumber"] = index
        try:
            self.tt = TTFont(path, **kwargs)
        except Exception as exc:  # pragma: no cover
            sys.exit(f"Could not read font {path}: {exc}")

        self.path = path
        self.upem = self.tt["head"].unitsPerEm
        self.cmap = self.tt.getBestCmap()
        self._hmtx = self.tt["hmtx"]
        self._order = self.tt.getGlyphOrder()
        self._glyphset = self.tt.getGlyphSet()
        self._bounds_cache: dict[str, tuple | None] = {}
        self._gid_cache: dict[str, int] = {}
        self._enc_cache: dict[str, list[int]] = {}
        self.used: set[int] = set()
        self.gid_to_char: dict[int, str] = {}
        self.missing: set[str] = set()

        names = self.tt["name"]
        ps = names.getDebugName(6) or names.getDebugName(4) or names.getDebugName(1)
        self.ps_name = re.sub(r"[^A-Za-z0-9-]", "", ps or "PracticeFont") or "PracticeFont"
        self.family = (names.getDebugName(4) or names.getDebugName(1)
                       or os.path.basename(path))

    # -- measuring ---------------------------------------------------------

    def _bounds(self, glyph_name: str):
        if glyph_name not in self._bounds_cache:
            from fontTools.pens.boundsPen import BoundsPen

            pen = BoundsPen(self._glyphset)
            try:
                self._glyphset[glyph_name].draw(pen)
            except Exception:
                pen.bounds = None
            self._bounds_cache[glyph_name] = pen.bounds
        return self._bounds_cache[glyph_name]

    def _probe_top(self, letters: str) -> float | None:
        tops = []
        for ch in letters:
            name = self.cmap.get(ord(ch))
            b = self._bounds(name) if name else None
            if b:
                tops.append(b[3])
        return max(tops) if tops else None

    def _probe_bottom(self, letters: str) -> float | None:
        bots = []
        for ch in letters:
            name = self.cmap.get(ord(ch))
            b = self._bounds(name) if name else None
            if b:
                bots.append(b[1])
        return min(bots) if bots else None

    @property
    def x_height(self) -> float:
        v = self._probe_top("x")
        if not v:
            os2 = self.tt.get("OS/2")
            v = getattr(os2, "sxHeight", 0) or 0
        return float(v) if v and v > 0 else self.upem * 0.5

    @property
    def asc_height(self) -> float:
        v = self._probe_top(self.ASC_PROBE)
        if not v:
            v = self.tt["hhea"].ascent
        return float(v)

    @property
    def desc_depth(self) -> float:
        """Positive distance below the baseline."""
        v = self._probe_bottom(self.DESC_PROBE)
        if v is None or v >= 0:
            v = self.tt["hhea"].descent
        return abs(float(v)) or self.upem * 0.2

    # -- text --------------------------------------------------------------

    def gid(self, ch: str) -> int | None:
        name = self.cmap.get(ord(ch))
        if name is None:
            return None
        if name not in self._gid_cache:
            self._gid_cache[name] = self.tt.getGlyphID(name)
        return self._gid_cache[name]

    def encode(self, text: str) -> list[int]:
        """Map text to glyph ids, substituting characters the font lacks."""
        if text in self._enc_cache:
            return self._enc_cache[text]
        gids: list[int] = []
        for ch in text:
            for cand, clean in self._candidates(ch):
                g = self.gid(cand)
                if g is None:
                    continue
                gids.append(g)
                self.used.add(g)
                self.gid_to_char.setdefault(g, cand)
                if not clean:
                    self.missing.add(ch)
                break
            else:
                self.missing.add(ch)
        self._enc_cache[text] = gids
        return gids

    def _candidates(self, ch: str):
        """(candidate, is_faithful) in order of preference."""
        yield ch, True
        for c in CHAR_FALLBACKS.get(ch, ""):
            yield c, True                       # deliberate typographic swap
        for c in unicodedata.normalize("NFKD", ch):
            if not unicodedata.combining(c):
                yield c, False                  # accent lost
        yield "?", False

    def advance(self, gid: int) -> float:
        try:
            return self._hmtx[self._order[gid]][0]
        except Exception:
            return self.upem * 0.5

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        gids = self.encode(text)
        w = sum(self.advance(g) for g in gids) * size / self.upem
        return w + tracking * max(len(gids) - 1, 0)

    def show(self, text: str) -> str:
        return "".join(f"{g:04X}" for g in self.encode(text))

    # -- embedding ---------------------------------------------------------

    def _subset_bytes(self) -> bytes:
        import io

        buf = io.BytesIO()
        try:
            from fontTools import subset

            opts = subset.Options()
            opts.retain_gids = True          # keeps our GID numbering valid
            opts.notdef_outline = True
            opts.recalc_bounds = False
            opts.drop_tables += ["DSIG"]
            opts.layout_features = []
            names = [self._order[g] for g in sorted(self.used) if g < len(self._order)]
            sub = subset.Subsetter(options=opts)
            sub.populate(glyphs=names or [".notdef"])
            sub.subset(self.tt)
            self.tt.save(buf)
        except Exception:
            buf = io.BytesIO()
            self.tt.save(buf)
        return buf.getvalue()

    def _w_array(self) -> str:
        items = sorted(self.used)
        parts: list[str] = []
        i = 0
        while i < len(items):
            j, run = i, []
            while j < len(items) and (j == i or items[j] == items[j - 1] + 1):
                run.append(num(self.advance(items[j]) * 1000.0 / self.upem))
                j += 1
            parts.append(f"{items[i]} [{' '.join(run)}]")
            i = j
        return "[" + " ".join(parts) + "]"

    def _to_unicode(self) -> bytes:
        pairs = [(g, self.gid_to_char[g]) for g in sorted(self.used) if g in self.gid_to_char]
        head = (
            "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        )
        body = []
        for k in range(0, len(pairs), 100):
            chunk = pairs[k:k + 100]
            body.append(f"{len(chunk)} beginbfchar")
            for g, ch in chunk:
                uni = "".join(f"{u:04X}" for u in [ord(c) for c in ch])
                body.append(f"<{g:04X}> <{uni}>")
            body.append("endbfchar")
        tail = "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
        return (head + "\n".join(body) + "\n" + tail).encode("latin-1")

    def embed(self, pdf: PDF) -> int:
        data = self._subset_bytes()
        file_obj = pdf.add_stream(f"/Length1 {len(data)} ", data)

        head, hhea, os2 = self.tt["head"], self.tt["hhea"], self.tt.get("OS/2")
        s = 1000.0 / self.upem
        bbox = " ".join(num(v * s) for v in (head.xMin, head.yMin, head.xMax, head.yMax))
        italic = self.tt["post"].italicAngle
        cap = getattr(os2, "sCapHeight", 0) if os2 else 0
        cap = cap if cap and cap > 0 else self.asc_height
        flags = 4 | (64 if italic else 0)

        desc = pdf.add(
            f"<< /Type /FontDescriptor /FontName /{self.ps_name} /Flags {flags} "
            f"/FontBBox [{bbox}] /ItalicAngle {num(italic)} "
            f"/Ascent {num(hhea.ascent * s)} /Descent {num(hhea.descent * s)} "
            f"/CapHeight {num(cap * s)} /StemV 80 /FontFile2 {file_obj} 0 R >>".encode("latin-1")
        )
        cid = pdf.add(
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{self.ps_name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {desc} 0 R /DW 1000 /W {self._w_array()} "
            f"/CIDToGIDMap /Identity >>".encode("latin-1")
        )
        touni = pdf.add_stream("", self._to_unicode())
        return pdf.add(
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{self.ps_name} "
            f"/Encoding /Identity-H /DescendantFonts [{cid} 0 R] "
            f"/ToUnicode {touni} 0 R >>".encode("latin-1")
        )


# --------------------------------------------------------------------------
# Page geometry
# --------------------------------------------------------------------------


class Sheet:
    """Works out where every rule on the page goes."""

    def __init__(self, opts) -> None:
        self.w, self.h = PAGE_SIZES[opts.page.lower()]
        self.left = opts.margin
        self.right = self.w - opts.margin
        self.opts = opts

        self.footer_y = 66.0 if opts.footer_rule else None
        if opts.header:
            self.title_y = self.h - 52
            self.sub_y = self.h - 68
            self.rule_y = self.h - 92
            self.field_y = self.h - 116 if opts.name_date else None
            top = self.h - (128 if opts.name_date else 112)
        else:
            self.title_y = self.sub_y = self.rule_y = self.field_y = None
            top = self.h - opts.margin

        bottom = (self.footer_y or 0) + 16 + (0 if self.footer_y else opts.margin)

        self.unit = opts.unit                 # midline<->baseline distance
        self.band = 3 * self.unit             # ascender line -> descender line
        self.rows = self._fit_rows(top, bottom, opts.rows)
        total = self.rows * self.band
        self.gap = ((top - bottom) - total) / (self.rows - 1) if self.rows > 1 else 0.0
        self.top = top

        self.content_rows = max(1, min(self.rows - 1, round(self.rows * opts.split)))
        if opts.content_rows:
            self.content_rows = max(1, min(self.rows, opts.content_rows))

    def _fit_rows(self, top: float, bottom: float, want: int) -> int:
        avail = top - bottom
        n = want
        while n > 2 and (n * self.band + (n - 1) * self.opts.min_gap) > avail:
            n -= 1
        return max(n, 2)

    def row(self, i: int) -> dict:
        """y positions of one ruled row, index 0 = top row."""
        asc = self.top - i * (self.band + self.gap)
        return {
            "asc": asc,
            "mid": asc - self.unit,
            "base": asc - 2 * self.unit,
            "desc": asc - 3 * self.unit,
        }


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


class Canvas:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def line(self, x1, y1, x2, y2, rgb, width, dash=None):
        r, g, b = rgb
        self.ops.append(f"{num(r)} {num(g)} {num(b)} RG {num(width)} w")
        self.ops.append(f"[{dash}] 0 d" if dash else "[] 0 d")
        self.ops.append(f"{num(x1)} {num(y1)} m {num(x2)} {num(y2)} l S")

    def hline(self, x1, x2, y, rgb, width, dash=None):
        self.line(x1, y, x2, y, rgb, width, dash)

    def helv(self, text, x, y, size, rgb=(0, 0, 0), bold=False):
        if not text:
            return
        r, g, b = rgb
        name = "/HB" if bold else "/HR"
        self.ops.append(
            f"BT {name} {num(size)} Tf {num(r)} {num(g)} {num(b)} rg "
            f"{num(x)} {num(y)} Td {pdf_string(text).decode('latin-1')} Tj ET"
        )

    def script(self, hexgids, x, y, size, rgb, tracking=0.0):
        if not hexgids:
            return
        r, g, b = rgb
        tc = f"{num(tracking)} Tc " if tracking else ""
        self.ops.append(
            f"BT /F1 {num(size)} Tf {num(r)} {num(g)} {num(b)} rg {tc}"
            f"{num(x)} {num(y)} Td <{hexgids}> Tj ET"
        )

    def data(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def parse_rgb(spec: str) -> tuple[float, float, float]:
    spec = spec.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", spec):
        return tuple(int(spec[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore
    parts = [float(p) for p in re.split(r"[,\s]+", spec) if p]
    if len(parts) == 1:
        return (parts[0],) * 3  # type: ignore
    if len(parts) == 3:
        return tuple(parts)  # type: ignore
    raise argparse.ArgumentTypeError(f"bad colour: {spec!r}")


# --------------------------------------------------------------------------
# Text flow
# --------------------------------------------------------------------------


def load_text(opts) -> str:
    if opts.file:
        with open(opts.file, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if opts.text:
        return " ".join(opts.text)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def paragraphs(text: str, keep_breaks: bool) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    if keep_breaks:
        return [ln.strip() for ln in text.split("\n")]
    out = []
    for block in re.split(r"\n\s*\n+", text):
        block = " ".join(block.split())
        if block:
            out.append(block)
    return out


def wrap(font: ScriptFont, text: str, size: float, max_w: float, tracking: float) -> list[str]:
    """Greedy word wrap, breaking words that are wider than the line."""
    if not text:
        return [""]
    lines, cur = [], ""
    for word in text.split(" "):
        if not word:
            continue
        trial = f"{cur} {word}".strip()
        if font.width(trial, size, tracking) <= max_w or not cur:
            if font.width(trial, size, tracking) <= max_w:
                cur = trial
                continue
            # single word too long: hard-break it
            if cur:
                lines.append(cur)
                cur = ""
            piece = ""
            for ch in word:
                if font.width(piece + ch, size, tracking) > max_w and piece:
                    lines.append(piece + "-")
                    piece = ch
                else:
                    piece += ch
            cur = piece
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def flow(font: ScriptFont, text: str, size: float, max_w: float, opts) -> list[str]:
    lines: list[str] = []
    for i, para in enumerate(paragraphs(text, opts.keep_linebreaks)):
        if i and opts.paragraph_gap:
            lines.extend([""] * opts.paragraph_gap)
        if not para:
            lines.append("")
            continue
        lines.extend(wrap(font, para, size, max_w, opts.tracking))
    while lines and not lines[-1]:
        lines.pop()
    return lines


def choose_size(font: ScriptFont, unit: float, opts) -> float:
    """Scale the face so it sits naturally inside the 4-line ruling."""
    zone_x, zone_asc, zone_desc = unit, 2 * unit, unit
    by_x = zone_x / (font.x_height / font.upem)
    by_asc = zone_asc / (font.asc_height / font.upem)
    by_desc = zone_desc / (font.desc_depth / font.upem)

    if opts.fit == "ascender":
        size = min(by_asc, by_desc * 1.2)
    elif opts.fit == "descender":
        size = by_desc
    else:  # xheight - the proportion the 4-line ruling is designed around
        size = min(by_x, by_asc * opts.overflow, by_desc * opts.overflow)
    return size * opts.font_scale


# --------------------------------------------------------------------------
# Worksheet
# --------------------------------------------------------------------------


def build_pdf(lines: list[str], font: ScriptFont, sheet: Sheet, opts) -> bytes:
    ink = opts.ink
    red, blue, guide = opts.rule_asc, opts.rule_mid, opts.guide_color
    size = opts.computed_size
    text_w = sheet.right - sheet.left

    chunks = [lines[i:i + sheet.content_rows]
              for i in range(0, len(lines), sheet.content_rows)] or [[]]

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

        # ---- ruling: every row on the page ----
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

        # ---- divider between the model half and the practice half ----
        if opts.divider and sheet.content_rows < sheet.rows:
            a = sheet.row(sheet.content_rows - 1)["desc"]
            b = sheet.row(sheet.content_rows)["asc"]
            y = (a + b) / 2
            c.hline(sheet.left, sheet.right, y, (0.72, 0.72, 0.75), 0.7, dash="2 3")
            if opts.divider_label:
                lw = helv_width(opts.divider_label, 7.5)
                c.helv(opts.divider_label, (sheet.left + sheet.right - lw) / 2,
                       y + 2.5, 7.5, (0.55, 0.55, 0.58))

        # ---- the content, on the top rows ----
        for i, line in enumerate(chunk):
            if not line:
                continue
            r = sheet.row(i)
            c.script(font.show(line), sheet.left + opts.text_indent, r["base"] + opts.baseline_shift,
                     size, ink, opts.tracking)

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
    info = pdf.add(b"<< /Title " + pdf_string(opts.title) +
                   b" /Producer (handwriting_practice.py) >>")
    return pdf.build(root, info)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def resolve_font(spec: str, index: int) -> tuple[str, int]:
    if spec in FONT_PRESETS:
        for path, idx in FONT_PRESETS[spec]:
            if os.path.exists(path):
                return path, (index if index else idx)
        sys.exit(f"None of the files for preset '{spec}' exist on this machine.\n"
                 "Try --list-fonts, or pass a path to a .ttf/.otf/.ttc file.")
    if os.path.exists(spec):
        return spec, index
    sys.exit(f"Unknown font preset or missing file: {spec!r}  (try --list-fonts)")


def list_fonts() -> None:
    print("Font presets (✓ = available here):\n")
    for name, cands in FONT_PRESETS.items():
        hit = next((p for p, _ in cands if os.path.exists(p)), None)
        mark = "✓" if hit else "✗"
        print(f"  {mark} {name:14s} {hit or cands[0][0]}")
    print("\nYou can also pass any .ttf/.otf/.ttc path to --font "
          "(use --font-index for .ttc collections).")


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(
        prog="handwriting_practice.py",
        description="Generate a 4-line handwriting practice PDF: model text on the "
                    "top half of each page, matching blank ruling underneath.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  ./handwriting_practice.py "The quick brown fox jumps over the lazy dog."
  ./handwriting_practice.py -f lesson.txt -o lesson.pdf --title "Module 8"
  pbpaste | ./handwriting_practice.py --font print --rows 10 --open
""",
    )
    p.add_argument("text", nargs="*", help="content to practise (or use -f / stdin)")
    p.add_argument("-f", "--file", help="read the content from a text file")
    p.add_argument("-o", "--output", help="output PDF path")
    p.add_argument("--open", dest="open_after", action="store_true",
                   help="open the PDF when it is finished")

    g = p.add_argument_group("layout")
    g.add_argument("--rows", type=int, default=12,
                   help="ruled rows per page, shrunk automatically if they will "
                        "not fit (default: 12)")
    g.add_argument("--split", type=float, default=0.5,
                   help="fraction of each page used for the model text "
                        "(default: 0.5 = top half)")
    g.add_argument("--content-rows", type=int, default=0,
                   help="exact number of model rows per page (overrides --split)")
    g.add_argument("--unit", type=float, default=11.25,
                   help="spacing between the four rules, in points (default: 11.25)")
    g.add_argument("--min-gap", type=float, default=8.0,
                   help="smallest allowed gap between ruled rows (default: 8)")
    g.add_argument("--page", default="a4", choices=sorted(PAGE_SIZES),
                   help="page size (default: a4)")
    g.add_argument("--margin", type=float, default=36.0, help="side margin (default: 36)")
    g.add_argument("--text-indent", type=float, default=4.0,
                   help="left inset for the model text (default: 4)")
    g.add_argument("--baseline-shift", type=float, default=0.0,
                   help="nudge the model text up/down, in points")

    g = p.add_argument_group("type")
    g.add_argument("--font", default=DEFAULT_FONT,
                   help=f"preset name or font file path (default: {DEFAULT_FONT})")
    g.add_argument("--font-index", type=int, default=0, help="face index inside a .ttc")
    g.add_argument("--fit", default="xheight", choices=["xheight", "ascender", "descender"],
                   help="how the face is scaled to the ruling (default: xheight)")
    g.add_argument("--font-scale", type=float, default=1.0,
                   help="extra multiplier on the computed size (default: 1.0)")
    g.add_argument("--overflow", type=float, default=1.25,
                   help="how far ascenders/descenders may pass their rule (default: 1.25)")
    g.add_argument("--tracking", type=float, default=0.0,
                   help="extra letter spacing in points")
    g.add_argument("--ink", type=parse_rgb, default=(0.3, 0.3, 0.3),
                   help="model text colour: grey level, r,g,b or #rrggbb (default: 0.3)")
    g.add_argument("--list-fonts", action="store_true", help="show the font presets and exit")

    g = p.add_argument_group("ruling")
    g.add_argument("--rule-asc", type=parse_rgb, default=(0.8, 0.1, 0.1),
                   help="ascender/descender rule colour (default: red)")
    g.add_argument("--rule-mid", type=parse_rgb, default=(0.12, 0.52, 0.95),
                   help="midline/baseline rule colour (default: blue)")
    g.add_argument("--midline-dash", default="", metavar="PATTERN",
                   help='dash the midline, e.g. --midline-dash "3 3"')
    g.add_argument("--no-guides", dest="guides", action="store_false",
                   help="drop the vertical slant guides")
    g.add_argument("--guide-step", type=float, default=22.5,
                   help="spacing of the slant guides (default: 22.5)")
    g.add_argument("--guide-color", type=parse_rgb, default=(0.92, 0.94, 0.97),
                   help="slant guide colour")
    g.add_argument("--slant", type=float, default=0.0,
                   help="slant guide angle in degrees (default: 0 = upright)")
    g.add_argument("--no-divider", dest="divider", action="store_false",
                   help="drop the dashed line between the two halves")
    g.add_argument("--divider-label", default="",
                   help='small caption on the divider, e.g. "now you try"')

    g = p.add_argument_group("page furniture")
    g.add_argument("--title", default="Handwriting Practice", help="header title")
    g.add_argument("--subtitle", default="", help="header subtitle")
    g.add_argument("--tag", default="", help="right-hand header label")
    g.add_argument("--footer", default="", help="centred footer text")
    g.add_argument("--title-color", type=parse_rgb, default=(0.07, 0.27, 0.49),
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
                   help="blank rows inserted between paragraphs (default: 0)")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)

    if opts.list_fonts:
        list_fonts()
        return 0

    text = load_text(opts)
    if not text.strip():
        print("No content given.\n", file=sys.stderr)
        print('  ./handwriting_practice.py "your text here"', file=sys.stderr)
        print("  ./handwriting_practice.py -f lesson.txt", file=sys.stderr)
        print("  cat lesson.txt | ./handwriting_practice.py", file=sys.stderr)
        return 2

    path, index = resolve_font(opts.font, opts.font_index)
    font = ScriptFont(path, index)
    sheet = Sheet(opts)

    opts.computed_size = choose_size(font, sheet.unit, opts)
    max_w = (sheet.right - sheet.left) - opts.text_indent
    lines = flow(font, text, opts.computed_size, max_w, opts)

    data = build_pdf(lines, font, sheet, opts)

    out = opts.output
    if not out:
        stem = os.path.splitext(os.path.basename(opts.file))[0] if opts.file else "handwriting-practice"
        out = f"{stem}-practice.pdf" if opts.file else "handwriting-practice.pdf"
    if not out.lower().endswith(".pdf"):
        out += ".pdf"
    with open(out, "wb") as fh:
        fh.write(data)

    pages = math.ceil(len(lines) / sheet.content_rows) if lines else 1
    face = font.family
    print(f"Wrote {out}")
    print(f"  {pages} page(s) - {sheet.rows} ruled rows each "
          f"({sheet.content_rows} model + {sheet.rows - sheet.content_rows} blank)")
    print(f"  {len(lines)} line(s) of content in {face} at {opts.computed_size:.1f}pt")
    if font.missing:
        shown = " ".join(f"{ch!r}" for ch in sorted(font.missing))
        print(f"  note: {face} has no glyph for {shown} - substituted",
              file=sys.stderr)

    if opts.open_after:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, out], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
