#!/usr/bin/env python3
"""WCAG 2.1 relative-luminance contrast ratios for accent-strong dual-use decision."""

def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def lum(hexs):
    hexs = hexs.lstrip('#')
    r, g, b = (int(hexs[i:i+2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

def ratio(fg, bg):
    l1, l2 = lum(fg), lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)

WHITE = "#FFFFFF"
LIGHT_BG = "#F6F7FB"   # light page background
DARK_BG  = "#11131b"   # dark page/surface background

def row(name, cand, bg_for_text):
    r_btn = ratio(WHITE, cand)          # (a) white text ON accent-strong button
    r_txt = ratio(cand, bg_for_text)    # (b) accent-strong AS text on page bg
    ok = "PASS" if (r_btn >= 4.5 and r_txt >= 4.5) else ("btn-ok" if r_btn>=4.5 else ("txt-ok" if r_txt>=4.5 else "FAIL"))
    print(f"  {name:<10} {cand}  white-on-btn={r_btn:5.2f}  as-text-on-bg={r_txt:5.2f}  -> both>=4.5? {r_btn>=4.5 and r_txt>=4.5}  [{ok}]")

print("=== accent-strong dual-use (button-bg w/ white text  &  as-text on page bg) ===")
print("LIGHT candidates (text bg = #F6F7FB):")
for n, c in [("#5570DE", "#5570DE"), ("#1d5fd1(cur)", "#1d5fd1"), ("#7C98F2", "#7C98F2"), ("#3f63d6","#3f63d6")]:
    row(n, c, LIGHT_BG)
print("DARK candidates (text bg = #11131b):")
for n, c in [("#3b82f6(cur)", "#3b82f6"), ("#135bec", "#135bec"), ("#b4c5ff", "#b4c5ff"), ("#4b8dfa","#4b8dfa"), ("#5a93f5","#5a93f5")]:
    row(n, c, DARK_BG)

print()
print("=== core pairs (on-surface text on surface) ===")
pairs = [
    ("LIGHT on-surface/surface", "#2A2E3B", "#FFFFFF"),
    ("LIGHT on-surface/bg",      "#2A2E3B", "#F6F7FB"),
    ("LIGHT on-surf-var/surface","#555B6E", "#FFFFFF"),
    ("LIGHT on-surf-muted/surf", "#8A90A4", "#FFFFFF"),
    ("LIGHT text-hint#9AA0B2/bg","#9AA0B2", "#F6F7FB"),
    ("LIGHT text-hint#A0A5B6/bg","#A0A5B6", "#F6F7FB"),
    ("DARK  on-surface/surface", "#e1e1ee", "#11131b"),
    ("DARK  on-surface/panel",   "#e1e1ee", "#111318"),
    ("DARK  on-surf-var/surface", "#c3c5d8", "#11131b"),
    ("DARK  on-surf-muted/surf", "#8d90a1", "#11131b"),
]
for n, fg, bg in pairs:
    print(f"  {n:<28} {fg} on {bg}  ratio={ratio(fg,bg):5.2f}  AA-body(4.5)? {ratio(fg,bg)>=4.5}")

print()
print("=== primary button (on-primary text on primary bg) ===")
for n, fg, bg in [
    ("LIGHT on-primary/primary", "#FFFFFF", "#7C98F2"),
    ("LIGHT white/primary-dim",  "#FFFFFF", "#5570DE"),
    ("DARK  on-primary/primary", "#e2e6ff", "#135bec"),
    ("DARK  white/primary",      "#FFFFFF", "#135bec"),
]:
    print(f"  {n:<26} {fg} on {bg}  ratio={ratio(fg,bg):5.2f}  AA(4.5)? {ratio(fg,bg)>=4.5}  AA-large(3.0)? {ratio(fg,bg)>=3.0}")
