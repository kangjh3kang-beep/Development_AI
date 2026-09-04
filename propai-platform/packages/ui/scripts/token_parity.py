#!/usr/bin/env python3
"""Token parity gate for tokens.css.

Asserts the @tokens:light region and @tokens:dark region declare the *same set*
of CSS custom-property keys. A color/theme token present in only one theme block
causes a transparent/black collapse on theme switch — this gate blocks that.

The @tokens:common region (theme-invariant: fonts, radii, weights, motion,
glass-blur, paper, saas marketing palette) is intentionally excluded.

Usage:  python3 packages/ui/scripts/token_parity.py
Exit 0 = parity (diff 0); exit 1 = mismatch.
"""
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "src" / "styles" / "tokens.css"


def region(text: str, name: str) -> str:
    m = re.search(rf"@tokens:{name}:start(.*?)@tokens:{name}:end", text, re.S)
    if not m:
        sys.exit(f"FAIL: region @tokens:{name} not found")
    return m.group(1)


def keys(block: str) -> set[str]:
    # Only left-hand-side declarations `--x:` (ignore var() usages in values).
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", block, re.I))


def main() -> int:
    text = CSS.read_text(encoding="utf-8")
    light = keys(region(text, "light"))
    dark = keys(region(text, "dark"))
    only_light = sorted(light - dark)
    only_dark = sorted(dark - light)

    print(f"tokens.css: {CSS}")
    print(f"light keys: {len(light)}   dark keys: {len(dark)}")
    if not only_light and not only_dark:
        print(f"PASS: key-set diff = 0 ({len(light)} theme-varying tokens in both blocks)")
        return 0
    print("FAIL: theme-varying key sets differ")
    if only_light:
        print("  light-only:", ", ".join(only_light))
    if only_dark:
        print("  dark-only :", ", ".join(only_dark))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
