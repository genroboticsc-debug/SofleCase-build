"""Install the recovered lowercase first glyph in F012 engraving."""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

old = 'ENGRAVING_TEXT = "V4_17"'
new = 'ENGRAVING_TEXT = "v4_17"'

if new in text:
    print(f"Recovered lowercase F012 text already present in {PATH}")
    raise SystemExit(0)
if text.count(old) != 1:
    raise RuntimeError(
        f"Expected one legacy F012 text constant, found {text.count(old)}"
    )

PATH.write_text(text.replace(old, new), encoding="utf-8")
print(f"Installed recovered lowercase F012 first glyph in {PATH}")
