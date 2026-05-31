---
name: Nexus Geo-Intelligence
colors:
  surface: '#11131b'
  surface-dim: '#11131b'
  surface-bright: '#373942'
  surface-container-lowest: '#0c0e16'
  surface-container-low: '#191b24'
  surface-container: '#1c1f27'
  surface-container-high: '#282a32'
  surface-container-highest: '#32343e'
  on-surface: '#e1e1ee'
  on-surface-variant: '#c3c5d8'
  inverse-surface: '#e1e1ee'
  inverse-on-surface: '#2e3039'
  outline: '#8d90a1'
  outline-variant: '#434655'
  surface-tint: '#b4c5ff'
  primary: '#b4c5ff'
  on-primary: '#00297a'
  primary-container: '#135bec'
  on-primary-container: '#e2e6ff'
  inverse-primary: '#0052de'
  secondary: '#4cd7f6'
  on-secondary: '#003640'
  secondary-container: '#03b5d3'
  on-secondary-container: '#00424e'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#925c00'
  on-tertiary-container: '#ffe3c6'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174c'
  on-primary-fixed-variant: '#003daa'
  secondary-fixed: '#acedff'
  secondary-fixed-dim: '#4cd7f6'
  on-secondary-fixed: '#001f26'
  on-secondary-fixed-variant: '#004e5c'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#11131b'
  on-background: '#e1e1ee'
  surface-variant: '#32343e'
  background-deep: '#0a0c10'
  surface-panel: '#111318'
  surface-elevated: '#282e39'
  border-muted: '#282e39'
  status-success: '#22c55e'
  status-warning: '#f59e0b'
  status-error: '#ef4444'
  ai-accent: '#a855f7'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 120%
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 140%
  body-md:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 150%
  body-sm:
    fontFamily: Noto Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 140%
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 100%
    letterSpacing: 0.1em
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 100%
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  sidebar-width: 440px
  header-height: 64px
---

## Brand & Style
Nexus Geo-Intelligence is a sophisticated, data-driven platform designed for urban developers, civil engineers, and real estate analysts. The brand personality is technical, authoritative, and futuristic, emphasizing precision and interconnected data.

The visual style is a refined mix of **Glassmorphism** and **Corporate Modern**. It utilizes high-transparency surfaces with heavy backdrop blurs to overlay complex information on top of interactive map environments without losing context. The interface feels like a "heads-up display" (HUD), using glowing accents and crisp typography to guide the user through high-density spatial data.

## Colors
The palette is rooted in a "Deep Space" dark mode, providing a high-contrast foundation for luminous data visualization. 

- **Primary Blue (#135bec):** Used for core actions, branding, and "Consolidated" state highlights. It represents connectivity and stability.
- **Support Accents:** Cyan and Amber are used for technical infrastructure overlays (Utility lines, High Pressure Gas), providing immediate visual categorization.
- **Functional Grays:** The background scales from `#0a0c10` (Map void) to `#1c1f27` (Side panels), creating a hierarchy of information density.
- **Glass Effects:** Semi-transparent panels use an 85% opacity of `#161920` with a 12px blur to maintain legibility over the map's grid.

## Typography
The system uses a dual-font strategy to balance technical aesthetics with readability.

- **Space Grotesk (Headlines/Labels):** Chosen for its geometric, futuristic qualities. It is used for all uppercase labels, headers, and branding to evoke a high-tech engineering feel.
- **Noto Sans (Body):** Used for all data-heavy descriptions and UI controls. It provides neutral, high-legibility support for complex feasibility reports.
- **JetBrains Mono (Data):** For APN numbers, coordinates, and area measurements, a monospaced font ensures numerical alignment and a "coded" aesthetic.

## Layout & Spacing
The layout follows a **Fixed Sidebar + Fluid Map** model. The primary workspace is a full-screen canvas (the Map), while detailed analysis and controls are housed in a robust 440px right-hand sidebar.

- **Floating UI:** Controls on the map are detached and use a floating glass-panel approach with 24px (6 units) of padding from screen edges.
- **Sidebar Density:** The sidebar uses a strict vertical rhythm with 24px section spacing. Internal card padding is set to 16px to maximize information density without clutter.
- **Grids:** A 40px square grid overlay on the map serves as a visual guide for spatial alignment.

## Elevation & Depth
Depth is created through transparency and "Glow-Shadows" rather than traditional ambient occlusion.

- **Level 0 (Base):** The map layer with a dark grayscale filter.
- **Level 1 (Panels):** Glass-morphic panels with `backdrop-filter: blur(12px)` and a subtle `1px` border in `#282e39`.
- **Level 2 (Interaction):** Active tools and buttons utilize a primary color glow (`shadow-primary/20`) to indicate "active" or "hover" states.
- **Level 3 (Popovers/Alerts):** High-contrast panels (like the BIM-GIS Conflict warning) use 90% opacity and a 24px blur to float prominently above all other layers.

## Shapes
The shape language is "Technical-Soft." It uses small border radii to maintain a structured, professional appearance while avoiding the harshness of sharp corners.

- **Standard Buttons/Inputs:** 4px (rounded) radius.
- **Glass Panels/Cards:** 8px or 12px (rounded-lg/xl) radius for larger structural elements.
- **Pills:** Full rounding is reserved for user avatars and notification badges only.

## Components
- **Buttons:** Primary buttons use the brand blue with a subtle upward translate on hover. "Glass" buttons use a white-overlay hover state (`bg-white/10`).
- **Input Fields:** Search bars are integrated into the header with a dark background (`#1c1f27`) and a primary-colored border on focus.
- **Status Chips:** Use a low-opacity background of the status color (e.g., Green 10%) with a high-contrast text and border for accessibility.
- **Map Overlays:** Use dashed strokes for proposed boundaries and glowing circles for specific points of interest.
- **Layer Toggles:** Checkboxes use a custom primary color fill with a "dot" style layer indicator (e.g., orange circle next to Utility Lines) to bridge the UI control with the map's visual key.
- **Metric Cards:** Use large Space Grotesk display numbers with small Noto Sans unit labels for clear hierarchical reading of data.
