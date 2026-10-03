---
name: Site Safety Watch Command Wall
description: A local incident command wall for live evidence, spatial verification and human response.
colors:
  zinc-black: "#090b0c"
  shell-black: "#101416"
  panel-zinc: "#151b1e"
  raised-zinc: "#1d2529"
  rule-strong: "#39444a"
  rule-soft: "#293238"
  paper-white: "#f1f2ec"
  text-muted: "#b3bec3"
  text-dim: "#849198"
  safety-lime: "#d8ff3f"
  signal-red: "#ff5838"
  clear-teal: "#5bd6c0"
  response-amber: "#efbd56"
typography:
  display:
    fontFamily: "Barlow Condensed, Arial Narrow, ui-sans-serif, sans-serif"
    fontSize: "clamp(2.2rem, 5vw, 4.4rem)"
    fontWeight: 900
    lineHeight: 0.86
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Barlow Condensed, Arial Narrow, ui-sans-serif, sans-serif"
    fontSize: "clamp(1.45rem, 2.4vw, 2rem)"
    fontWeight: 900
    lineHeight: 0.95
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Barlow Condensed, Arial Narrow, ui-sans-serif, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Barlow Condensed, Arial Narrow, ui-sans-serif, sans-serif"
    fontSize: "0.76rem"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Barlow Condensed, Arial Narrow, ui-sans-serif, sans-serif"
    fontSize: "0.65rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.08em"
rounded:
  square: "0"
  indicator: "50%"
spacing:
  micro: "4px"
  tight: "8px"
  compact: "12px"
  standard: "16px"
  command: "18px"
  stage: "20px"
components:
  hazard-new:
    backgroundColor: "{colors.safety-lime}"
    textColor: "{colors.zinc-black}"
    rounded: "{rounded.square}"
    padding: "18px 20px"
  hazard-approved:
    backgroundColor: "{colors.response-amber}"
    textColor: "{colors.zinc-black}"
    rounded: "{rounded.square}"
    padding: "18px 20px"
  hazard-resolved:
    backgroundColor: "{colors.clear-teal}"
    textColor: "{colors.zinc-black}"
    rounded: "{rounded.square}"
    padding: "18px 20px"
  incident-selected:
    backgroundColor: "{colors.safety-lime}"
    textColor: "{colors.zinc-black}"
    rounded: "{rounded.square}"
    padding: "12px 14px"
  rule-block:
    backgroundColor: "{colors.raised-zinc}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.square}"
    padding: "9px 10px"
---

# Design System: Site Safety Watch Command Wall

## Overview

**Creative North Star: "The Incident Command Wall"**

Site Safety Watch is a fixed-lane operational wallboard, not a dashboard assembled from cards.
One live or recorded camera owns the field, while spatial reconstruction and the human response
record form a compact verification stack at the right. The incident tape runs below both so the
whole detection and disposition story reads in one sweep.

The world is industrial, flat and decisive. Zinc-black surfaces reduce glare, paper-white type
stays legible at a distance, and high-visibility color appears as an earned field tied to a real
state. Barlow Condensed gives the wall the density and authority of site signage without adding
ornament. Rules, fixed lanes and hard edges create structure instead of floating containers.

**Key Characteristics:**
- The camera is the dominant source of truth.
- Spatial evidence and response stay in a fixed right-hand stack.
- The incident tape preserves chronology across the full lower edge.
- Status is always stated in text and reinforced by color.
- Every runtime claim and measurement comes from the local Dell Pro Max GB10.

## Colors

The palette pairs low-glare zinc neutrals with four high-visibility operational signals.

### Primary
- **Safety Lime:** Owns active evidence, selected incidents, keyboard focus and the wallboard index. It is the strongest field and appears only where immediate attention is required.

### Secondary
- **Signal Red:** Identifies the live camera source and offline or newly detected states.
- **Clear Teal:** Marks confirmed clearance, resolved incidents and healthy local services.

### Tertiary
- **Response Amber:** Marks approved work and response in progress without implying clearance.

### Neutral
- **Zinc Black:** The page ground and deepest evidence stage.
- **Shell Black:** The masthead, footer and right-side command structure.
- **Panel Zinc:** Empty camera and supporting module surfaces.
- **Raised Zinc:** Rule blocks, hover states and the incident tape.
- **Strong and Soft Rules:** Separate lanes, headings and evidence fields without simulating cards.
- **Paper White:** Primary labels, findings and measured values.
- **Muted and Dim Text:** Supporting descriptions, timestamps and inactive states.

**The Earned Signal Rule.** Lime, red, teal and amber always communicate a named operational state. Never use them as decoration.

**The Text Before Color Rule.** Every status remains understandable when the signal color is unavailable.

## Typography

**Display Font:** Barlow Condensed, self-hosted, with Arial Narrow and system sans fallbacks

**Body Font:** Barlow Condensed, self-hosted, with Arial Narrow and system sans fallbacks

**Label Font:** Barlow Condensed with tabular figures for time, confidence and measured values

**Character:** Condensed, forceful and economical. Heavy uppercase display type behaves like
industrial site signage, while compact regular text keeps dense evidence readable without
introducing a second family.

### Hierarchy
- **Display** (900, responsive to 4.4rem, 0.86): Camera identity and the dominant monitored zone.
- **Headline** (900, responsive to 2rem, 0.95): Product identity in the masthead.
- **Title** (900, 0.95rem): Spatial, response and incident-tape module headings.
- **Body** (400, 0.76rem, 1.4): Findings, rule text, captions and empty-state guidance.
- **Label** (800, 0.65rem, 0.08em tracking): Uppercase operational status, metadata and controls.

**The Distance Read Rule.** The product name, camera identity, hazard, zone and status must read before supporting evidence at wallboard distance.

**The Condensed Voice Rule.** Barlow Condensed is the only interface family. Hierarchy comes from weight, scale and case, not font mixing.

## Layout

The desktop command wall uses two columns and two rows. The camera fills the flexible left
column. The right rail is at least 330px wide and holds the spatial reconstruction above the
response record. A 92px incident tape spans both columns beneath them. The masthead is 72px
high, and the command area fills the remaining viewport above the 34px footer.

At 1040px and below, the right rail narrows to at least 295px while the same lane hierarchy is
preserved. At 760px and below, document order becomes the layout: camera first, spatial
reconstruction second, response record third and incident tape fourth. At 420px and below, the
system board compresses to two columns and hides only the secondary live-twin link.

Spacing is dense and repeatable. Outer identity and camera overlays use 18px. Module headings
and evidence interiors use 11px to 13px. One-pixel rules carry nearly every major boundary.

**The Fixed Lane Rule.** Camera, spatial evidence, response and incident tape keep their rank at every width, even when the lanes stack.

## Elevation & Depth

The system is flat by default. Adjacent zinc tones and one-pixel rules distinguish regions.
There are no card shadows, floating panels or decorative glows. The only structural shadow is
the strong dark lift beneath the hazard field when it overlays camera evidence. Camera labels
use a restrained text shadow solely to remain readable over changing footage.

### Shadow Vocabulary
- **Hazard overlay** (`0 18px 38px rgba(0, 0, 0, 0.45)`): Separates the full-width state field from moving camera evidence.
- **Evidence legibility** (`0 2px 8px #000`): Keeps camera identity and source labels readable over footage.

**The Ruled Surface Rule.** Establish hierarchy with tone and rules. Shadow is reserved for information physically overlaid on camera evidence.

## Shapes

The command wall uses square surfaces and hard lane boundaries. Panels, status fields, rule
blocks, toolbar controls and incident rows have no corner radius. Circles are reserved for the
live camera dot and timeline markers. This narrow exception makes the indicators feel like
equipment signals instead of decorative badges.

**The No Card Silhouette Rule.** Never wrap modules in rounded rectangles. A module is a lane bounded by rules.

## Components

### Masthead and system board
- The lime SW index anchors the brand at the far left.
- Three ruled status cells carry the live-twin link, event API state and last update.
- State values use explicit words, with teal for online and red for offline.

### Camera stage
- Live or recorded footage fills the entire left lane with cover cropping.
- The camera identity sits at the upper left, while the source state and replay caption sit at the upper right.
- The honest empty state uses ruled scan corners and explains when evidence will appear.

### Hazard field
- A full-width square field attaches to the bottom of the camera.
- New evidence uses safety lime, approved work uses amber, resolved evidence uses teal and false alarms use strong neutral zinc.
- Hazard name, event detail and confidence remain text-first and use tabular figures where measured.

### Spatial reconstruction
- The point-cloud stage sits between a ruled module heading and a measured depth caption.
- Ordinary points preserve source color; hazard points use safety lime.
- Orbit controls are square, compact and text-labeled. The active tool becomes a lime field.

### Response record
- Finding, zone, confidence, stored rule, proposed fix and timeline appear in one continuous lane.
- The rule block uses raised zinc, not a card treatment.
- Status labels use amber for approved, teal for resolved, red for new and explicit neutral text for other states.

### Incident tape
- Incident rows flow horizontally at desktop widths and vertically on mobile.
- The selected incident becomes a full signal-color field with dark text.
- A new incident receives one clipped reveal, then remains still. Reduced-motion preference collapses the reveal.

### Footer truth bar
- The footer states **100% local on Dell Pro Max GB10** and **Raw video and inference remain on this box**.
- Optional measured metrics appear only when supplied by the local runtime.
- Never substitute Cosmos or any other platform name for the Dell Pro Max GB10.

## Do's and Don'ts

### Do:
- **Do** let the live or recorded camera dominate the wall.
- **Do** preserve the camera, spatial reconstruction, response and incident-tape order on mobile.
- **Do** use safety lime for active evidence and focus, red for the camera source, amber for approved work and teal only for confirmed clearance.
- **Do** pair every color state with direct text.
- **Do** show honest loading, empty, unavailable and offline states.
- **Do** keep the local-runtime truth visible in the footer.

### Don't:
- **Don't** introduce rounded cards, floating tiles, decorative gradients or ambient glows.
- **Don't** turn the wall into a grid of equal metrics.
- **Don't** invent measurements, confidence, status or evidence.
- **Don't** animate unchanged polling results.
- **Don't** use a cloud platform name or imply that inference leaves the Dell Pro Max GB10.
- **Don't** add a second typeface, emoji or decorative stock imagery.
