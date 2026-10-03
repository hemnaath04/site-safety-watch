---
name: Site Safety Watch Console
description: A local-first evidence docket for workplace safety events.
colors:
  canvas: "#080b0f"
  surface: "#0e1319"
  surface-raised: "#141a21"
  rule: "#27313c"
  rule-strong: "#3b4856"
  text: "#f3f0e9"
  muted: "#aab6c3"
  faint: "#82909f"
  hazard: "#ff6a32"
  hazard-soft: "#3d1d12"
  resolved: "#57d6b1"
  resolved-soft: "#12362f"
  posted: "#f0bd55"
  focus: "#9dc6ff"
typography:
  display:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "clamp(1.35rem, 2.6vw, 2rem)"
    fontWeight: 900
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.83rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.67rem"
    fontWeight: 800
    letterSpacing: "0.11em"
rounded:
  surface: "10px"
  control: "6px"
  stamp: "7px"
spacing:
  tight: "8px"
  standard: "16px"
  shell: "18px"
components:
  status-chip:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "3px 8px"
  hazard-stamp:
    backgroundColor: "{colors.hazard}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.stamp}"
    padding: "13px 16px 12px"
---

# Design System: Site Safety Watch Console

## Overview

**Creative North Star: "The Evidence Docket"**

The console treats each detection as a record with evidence, time, status and human custody.
It is dense without becoming analytical theater: one camera dominates, one chronological ledger
organizes the events, and the selected record exposes exactly what the system stored.

The visual language is industrial and factual. Matte carbon surfaces reduce glare in a control
room, while a single safety orange mark pulls the active hazard forward. The design rejects the
generic grid of equal metric cards because the job is to inspect and disposition evidence.

**Key Characteristics:**
- Evidence occupies the most space.
- Status is written as text and reinforced with color.
- Fine rules create chain-of-custody sections.
- New data moves once; unchanged data remains still.

## Colors

The palette uses one urgent orange, one resolved teal and a layered carbon neutral scale.

### Primary
- **Safety Orange:** Marks the active hazard, unresolved event selection and urgent state.

### Secondary
- **Resolved Teal:** Marks approved events and verified online state.
- **Alert Amber:** Marks events posted to the response workflow.

### Neutral
- **Carbon Canvas:** The low-glare page ground.
- **Evidence Surfaces:** Tonal layers that separate the camera, detail record and event ledger.
- **Paper White:** Primary text and data.
- **Blue Grey:** Secondary metadata and quiet labels.

**The Earned Color Rule.** Orange, amber and teal appear only when a real event state earns them.

## Typography

**Display Font:** System UI sans
**Body Font:** System UI sans
**Label Font:** System UI sans with tabular figures for measurements

**Character:** Direct, compact and familiar across the offline box. Weight and case establish
hierarchy without loading a web font.

### Hierarchy
- **Display** (900, responsive up to 2rem, 1.1): The active hazard stamp.
- **Headline** (700, up to 1.65rem): Product identity.
- **Title** (700, 1.08rem): Panel and selected-record titles.
- **Body** (400, 0.83rem, 1.45): Model observation, rule and proposed fix.
- **Label** (800, 0.67rem, 0.11em tracking): Uppercase evidence and state labels.

**The Five-Second Rule.** Product name, active hazard, zone and event status remain readable
before any supporting copy.

## Layout

At desktop recording sizes, the console splits into a wide evidence column and a narrow event
ledger. The evidence column divides vertically between the dominant camera and selected record.
At 1100px and below, the ledger follows the evidence column in document order. The 18px shell
rhythm and 14px internal gap keep evidence groups tight while retaining visible separation.

## Elevation & Depth

The system is flat by default. Tonal layering and fine rules establish depth. The active hazard
stamp alone receives a soft, offset shadow because it floats over video evidence.

**The Flat Record Rule.** Evidence rows and detail fields use rules, never generic card shadows.

## Shapes

Large evidence surfaces use gently squared 10px corners. Compact state controls use 5px to 7px
corners. Pills are reserved for system state and update time. The recurring silhouette is a
ruled docket: header, evidence body and chronological ledger.

## Components

### Status chips
- Carry explicit state text in uppercase.
- Use state-specific foreground, background and border colors.
- Never rely on color alone.

### Event rows
- Use time, event name, zone, confidence and status in one compact row.
- The selected row receives a 3px inset state marker.
- A new row gets one clipped reveal, then becomes still.

### Hazard stamp
- Uses safety orange with dark text and the largest type on the screen.
- Contains the hazard name and zone only.

### Evidence record
- Divides frame, model observation, stored rule and timeline with one-pixel rules.
- Remains read-only because the disposition action occurs in Slack.

## Do's and Don'ts

### Do:
- **Do** make the newest unresolved evidence immediately visible.
- **Do** show honest loading, empty, unavailable and offline states.
- **Do** use tabular figures for time, confidence and measured values.
- **Do** preserve the camera, ledger and selected record at recording breakpoints.

### Don't:
- **Don't** invent metrics, status or evidence.
- **Don't** add decorative gradients, glows or stock imagery.
- **Don't** turn the console into a grid of equal metric cards.
- **Don't** animate unchanged polling results.
