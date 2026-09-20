# Handwriting practice generator

Turns any text into a printable 4-line handwriting worksheet.

Every page carries the classic four-rule ruling — **red ascender / blue midline /
blue baseline / red descender** — from the top of the page to the bottom. The
**top half** of each page is set in a handwriting face so you have a model to
look at; the **bottom half** is the same ruling left blank so you can copy it.
When the text runs past the bottom half of one page, it simply continues on the
next.

## Requirements

Python 3.8+ and `fontTools` — already present in Anaconda and most Python
installs. Nothing else; the PDF is written directly.

```sh
python3 -c "import fontTools; print('ok')"    # if this fails: pip install fonttools
```

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
    --font cursive --open
```

Blank lines in the input start a new paragraph; everything else is reflowed to
fit the line width. Use `--keep-linebreaks` if you want each input line to stay
on its own ruled line.

## Fonts

`--list-fonts` shows what is installed. On macOS all of these are present:

| preset | face | style |
| --- | --- | --- |
| `cursive` *(default)* | Snell Roundhand | flowing joined-up script |
| `cursive-bold` | Snell Roundhand Bold | the same, heavier strokes |
| `chancery` | Apple Chancery | slanted calligraphic |
| `script` | Savoye LET | ornate script |
| `print` | Bradley Hand | unjoined "manuscript" handwriting |
| `note` | Noteworthy | casual print |
| `chalk` | Chalkboard SE | round, very legible print |
| `comic` | Comic Sans MS | round print |
| `sans` | Arial | plain reference face |

You can also point `--font` at any `.ttf` / `.otf` / `.ttc` file — a school
cursive font you have downloaded, for instance. For a `.ttc` collection, pick
the face inside it with `--font-index`.

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
| slanted guides for italic | `--slant 15` |
| no vertical guides | `--no-guides` |
| caption on the divider | `--divider-label "now you try"` |
| bare page, no header | `--no-header --no-name-date` |

`./handwriting_practice.py --help` lists everything.

## Notes

- The page is A4 by default, with the same margins and rule colours as the
  worksheet this was modelled on.
- The handwriting font is subsetted into the PDF, so the file is small (a few
  pages is roughly 25 KB) and prints identically anywhere.
- Text stays selectable and searchable in the PDF.
- Characters the chosen face has no glyph for are substituted, and the program
  tells you which ones on stderr.
