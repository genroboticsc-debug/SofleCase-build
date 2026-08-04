"""Install the F012 Arial size recovered from four unclipped glyph bounds."""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

old = "ENGRAVING_FONT_SIZE = 5.00000000"
new = "ENGRAVING_FONT_SIZE = 4.88949692"

if new in text:
    print(f"Recovered F012 font size already present in {PATH}")
    raise SystemExit(0)
if text.count(old) != 1:
    raise RuntimeError(
        f"Expected one legacy F012 font-size constant, found {text.count(old)}"
    )

PATH.write_text(text.replace(old, new), encoding="utf-8")
print(f"Installed recovered F012 font size in {PATH}")
