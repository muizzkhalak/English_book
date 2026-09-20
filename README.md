# Handwriting practice generator

Turns any text into a printable 4-line handwriting worksheet.

Every page carries the classic four-rule ruling — **red ascender / blue midline /
blue baseline / red descender** — from the top of the page to the bottom, on the
blank lines as much as the written ones. Text that runs past the end of a page
continues on the next.

There are two scripts, identical apart from where the blank lines go. They share
all the same options, fonts and ruling.

| script | layout |
| --- | --- |
| `handwriting_practice.py` | **half and half** — the top half of the page is the model, the bottom half is blank |
| `handwriting_alternating.py` | **every other line** — a model line, then a blank line to copy it onto, all the way down |

Use `handwriting_alternating.py` when you want what you are copying to sit
directly above where you write it. It always puts an even number of ruled lines
on a page, so no model line is ever left without its blank line underneath, and
an odd `--rows` is rounded down.

```sh
./handwriting_alternating.py -f lesson.txt --font kid-simple --italic
```

## Setup

Python 3.8+ and `fontTools` — already present in Anaconda and most Python
installs.

```sh
./handwriting_practice.py --fetch-fonts     # once: downloads the school cursive fonts
pip install uharfbuzz                       # once: makes cursive letters join up
```

Neither step is strictly required — the program runs on the macOS system fonts
alone — but both matter if you want proper joined-up cursive. School cursive
faces build their joins from separate connector glyphs that only appear when the
text is shaped, and `uharfbuzz` is what does the shaping. Without it those fonts
print as disconnected letters, and the program warns you.

## Use

```sh
./handwriting_practice.py "The quick brown fox jumps over the lazy dog."
```

That writes `handwriting-practice.pdf` next to you. The three ways to hand it
content:

```sh
./handwriting_practice.py "text straight on the command line"
./handwriting_practice.py -f lesson.txt                 # -> lesson-practice.pdf
pbpaste | ./handwriting_practice.py                     # anything on stdin
```

Add `--open` to have the finished PDF open as soon as it is written.

A fuller example:

```sh
./handwriting_practice.py -f module8.txt \
    -o module8-practice.pdf \
    --title "Handwriting Practice" --subtitle "Module 8" --tag "Dutch B2" \
    --font kid --open
```

Blank lines in the input start a new paragraph; everything else is reflowed to
fit the line width. Use `--keep-linebreaks` if you want each input line to stay
on its own ruled line.

## Fonts

`--list-fonts` shows what is ready to use.

### For a child learning cursive

These are teaching fonts — plain letterforms, no flourishes, real joins. They
live in `fonts/` after `--fetch-fonts`, and all are SIL Open Font Licensed.

| preset | face | style |
| --- | --- | --- |
| `kid` | Playwrite US Trad | joined school cursive, US traditional — **good first choice** |
| `kid-modern` | Playwrite US Modern | joined, simpler and more upright |
| `kid-uk` | Playwrite GB J | joined, upright, UK school model |
| `kid-simple` | Edu NSW ACT Cursive | joined, very plain and light |
| `kid-print` | Edu NSW ACT Foundation | **unjoined** pre-cursive — letter shapes before joining |

A sensible order for a beginner is `kid-print` first (get the letter shapes
right), then `kid-uk` or `kid-modern` (upright joins), then `kid` (slanted
joined cursive).

### Already on macOS

| preset | face | style |
| --- | --- | --- |
| `cursive` *(default)* | Snell Roundhand | elegant, ornate capitals |
| `cursive-bold` | Snell Roundhand Bold | the same, heavier strokes |
| `chancery` | Apple Chancery | slanted calligraphic |
| `script` | Savoye LET | ornate script |
| `print` | Bradley Hand | unjoined handwriting |
| `note` | Noteworthy | casual print |
| `chalk` | Chalkboard SE | round, very legible print |
| `comic` | Comic Sans MS | round print |
| `sans` | Arial | plain reference face |

You can also point `--font` at any `.ttf` / `.otf` / `.ttc` file — another
Playwrite variant for a different country's school model, for instance. Drop the
file in `fonts/` and use `--font fonts/YourFont.ttf`. For a `.ttc` collection,
pick the face inside it with `--font-index`.

The face is scaled automatically so its x-height fills the midline-to-baseline
zone, which is what the four-rule ruling is built around. If a particular font
sits too small or too large for your taste, nudge it with `--font-scale 1.1`, or
switch the rule it is fitted to with `--fit ascender`.

## Common adjustments

| | |
| --- | --- |
| more/fewer lines per page | `--rows 10` (default 12; shrinks automatically if they will not fit) |
| change the split | `--split 0.33` (a third model, two thirds blank) |
| exact model lines per page | `--content-rows 4` |
| bigger writing | `--unit 14` (spacing between the four rules, in points) |
| letter paper | `--page letter` |
| darker or lighter model text | `--ink 0.15` or `--ink "#3366aa"` |
| plain black-and-white ruling | `--rule-asc 0.45 --rule-mid 0.65` |
| dashed midline | `--midline-dash "3 3"` |
| italic / slanted model text | `--italic` (12 degrees), or `--italic 15` |
| guide-tick angle | `--slant 15` — defaults to whatever `--italic` is |
| no vertical guides | `--no-guides` |
| caption on the divider | `--divider-label "now you try"` |
| bare page, no header | `--no-header --no-name-date` |
| language-specific letterforms | `--lang nl` |

`./handwriting_practice.py --help` lists everything. `handwriting_alternating.py` takes the same options, minus `--split`, `--content-rows` and the divider flags, which have no meaning when the blank lines are interleaved.

## Notes

- The page is A4 by default, with the same margins and rule colours as the
  worksheet this was modelled on.
- The handwriting font is subsetted into the PDF, so the file stays small (three
  pages is roughly 25–60 KB) and prints identically anywhere.
- Text stays selectable and searchable, joined cursive included.
- Characters the chosen face has no glyph for are substituted, and the program
  tells you which ones on stderr.
- `--italic` shears the text about its baseline, so it works on any face,
  including the school cursive fonts, none of which ship an italic cut. The
  vertical guide ticks lean by the same angle, which is what you actually
  copy when practising a consistent slant.
- Playwrite NL was deliberately left out: its loops descend so far that they
  cannot fit a standard four-rule band at a size where the x-height still
  reaches the midline. Fetch it by hand into `fonts/` if you want it anyway.
