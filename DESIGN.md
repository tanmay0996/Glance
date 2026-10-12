---
name: Glance
description: Webcam attendance for one operator; being seen gets a student stamped present.
colors:
  ground: "#F4F6F8"
  card: "#FFFFFF"
  well: "#EEF1F4"
  sidebar-well: "#E9EDF1"
  line: "#D5DBE1"
  line-soft: "#E3E8ED"
  miss-dash: "#B9C1CB"
  ink: "#15191F"
  ink-2: "#3D4552"
  muted: "#687387"
  stamp: "#6E2B8F"
  stamp-soft: "#F3ECF7"
  stamp-line: "#D9C4E6"
  danger: "#B42318"
  success: "#2F7D4F"
typography:
  display: { fontFamily: "Schibsted Grotesk, system-ui, sans-serif", fontSize: "2rem", fontWeight: 700, lineHeight: 1.1, letterSpacing: "-0.02em" }
  headline: { fontFamily: "Schibsted Grotesk, system-ui, sans-serif", fontSize: "1.125rem", fontWeight: 400 }
  title: { fontFamily: "Schibsted Grotesk, system-ui, sans-serif", fontSize: "1rem", fontWeight: 600 }
  body: { fontFamily: "Schibsted Grotesk, system-ui, sans-serif", fontSize: "15px", fontWeight: 400 }
  label: { fontFamily: "Schibsted Grotesk, system-ui, sans-serif", fontSize: "0.85rem", fontWeight: 400 }
  data: { fontFamily: "Courier Prime, ui-monospace, monospace", fontSize: "0.85rem", fontWeight: 400, fontFeature: "tnum" }
  stamp: { fontFamily: "Courier Prime, ui-monospace, monospace", fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.14em" }
rounded: { tick: "2px", mark: "3px", stamp: "4px", row: "8px", card: "12px" }
spacing: { xs: "4px", sm: "8px", md: "12px", lg: "16px" }
components:
  catalog-list: { backgroundColor: "{colors.card}", rounded: "{rounded.card}" }
  catalog-row: { padding: "10px 14px", height: "56px" }
  catalog-row-fresh: { backgroundColor: "{colors.stamp-soft}" }
  avatar: { backgroundColor: "{colors.well}", textColor: "{colors.ink-2}", rounded: "{rounded.row}", size: "36px" }
  stamp: { textColor: "{colors.stamp}", typography: "{typography.stamp}", rounded: "{rounded.stamp}", padding: "3px 9px 2px" }
  slip-mark: { textColor: "{colors.stamp}", rounded: "{rounded.mark}", size: "18px" }
  tally-cell: { backgroundColor: "{colors.line}", rounded: "{rounded.tick}", height: "14px" }
  tally-cell-on: { backgroundColor: "{colors.stamp}" }
---

# Design System: Glance

## Overview

**Creative North Star: "The Date-Due Slip"**

A library card catalog on cool card stock: white index cards with slate hairlines on a pale ground, catalog-ink text, and one plum ink that only ever appears as a stamp. The screen answers one question at a glance: who is stamped present today, and who is not. Density is moderate (56px rows, 1180px max content width); depth comes from surface steps and 1px lines, never shadows.

Built entirely in Streamlit. Tokens live in three places that must agree: `.streamlit/config.toml` (theme), `styles.css` `:root` variables, and the hex constants in `app.py` (`STAMP_HEX`, `MUTED_HEX`, `LINE_HEX`, `INK_HEX`, `STAMP_BGR`, `UNKNOWN_BGR`). Custom markup is emitted by `app.py` helpers through `st.html` with `g-` class names.

**Key Characteristics:**
- One reserved hue, one meaning: stamp ink = present.
- Grotesk for UI; typewriter face for IDs, dates, times, counts and the stamp.
- Flat: card on ground, hairline borders, 12px card / 8px row radii.
- Icons are Material Symbols Rounded via Streamlit's `":material/name:"` strings only.

## Colors

Cool slate neutrals carry everything; plum ink is the only chroma in normal use.

### Primary
- **Stamp Ink** (stamp): the stamp border and text, the slip-grid mark, the "on" tally cells, the roll count numeral, the bars in the 14-day chart (each bar counts present students), and the webcam box once a face is recognised (`STAMP_BGR` 143,43,110).
- **Stamp Wash** (stamp-soft): background of a catalog row stamped since the last refresh.
- **Stamp Rule** (stamp-line): reserved pale ink line; defined, not yet used.

### Neutral
- **Card-Stock Ground** (ground): app background, header at 92% opacity.
- **Index Card** (card): lists, bordered containers, slip grid, sticky name column.
- **Well** (well): avatar and empty-photo fill, dataframe header, sidebar. **Sidebar Well** (sidebar-well) is Streamlit's secondary background (inputs).
- **Hairline** (line): list/card borders, header rule, empty tally cells, chart domain/ticks. **Soft Hairline** (line-soft): row dividers, chart gridlines.
- **Catalog Ink** (ink): names, headings, body. **Ink 2** (ink-2): date in heading, meta values, rate column. **Slate** (muted): IDs, counts, "Not yet marked", axis labels, hints.
- **Miss Dash** (miss-dash): the "not marked" dash in the slip grid and scrollbar thumb.

### Status
- **Signal Red** (danger): "Not recognised" dot and webcam box (`UNKNOWN_BGR` 24,35,180), Streamlit errors. **Green** (success) is Streamlit's success alert colour only.

### Named Rules
**The One Ink Rule.** `#6E2B8F` means "present" and nothing else. Anything not about a student being marked present uses ink, ink-2, muted or line.
Known drift, not a rule: `primaryColor = "#6E2B8F"` in `config.toml` also inks primary buttons, links, text selection, caret and the focus outline, and the logo mark is drawn in stamp ink. These break the One Ink Rule and are not to be copied.
**The Quiet Absence Rule.** Not-yet-marked is slate text and a grey dash, never red. Red is reserved for recognition failure and errors.

## Typography

**UI Font:** Schibsted Grotesk 400/500/600/700 (system-ui fallback). **Data Font:** Courier Prime 400/700 (ui-monospace fallback), both from Google Fonts, loaded in `config.toml` and `@import` in `styles.css`. Base size 15px.

### Hierarchy
- **Display** (700, 2rem, 1.1, -0.02em; 1.6rem under 640px): page title in `.g-head`.
- **Headline** (400, 1.125rem): roll line "N of M stamped present"; the count numeral is Courier Prime 700 1.5rem in stamp ink.
- **Title** (600, 1rem): section labels ("Stamped present", "Not yet marked"). Streamlit h2 1.5rem/600, h3 1.125rem/600.
- **Body** (400, 15px; subtitles 0.95rem muted, max 62ch, `text-wrap: pretty`). Names 600; card name 1.05rem.
- **Label** (400, 0.85–0.9rem, muted): hints, legend, "Not yet marked".
- **Data** (Courier Prime 400, 0.85rem, tabular-nums): student IDs, heading date (0.95rem, 0.02em), section counts, slip-grid date heads (0.75rem), rate column, chart axis labels (11px).

### Named Rules
**The Typewriter Rule.** Courier Prime sets only machine-recorded facts: IDs, dates, times, counts, the stamp. Never prose, buttons or headings.

## Layout

4px base grid; observed steps 4/8/12/16px, with 10px/14px row insets. Content max-width 1180px, top padding 4.5rem (4rem under 640px). Top navigation (`st.navigation(position="top")`): Today, Take attendance, Students, Add student, Records; wordmark logo at size large. Today: roll line + primary button in a 3:1 column pair, then two equal columns (present / not yet marked) with gap large. Take attendance: camera 3 : feed 2. Students: 3-column card grid. Add student: form 3 : tips 2. Single breakpoint at 640px (heading stacks, row padding 10px 12px).

## Elevation & Depth

No shadows anywhere. Depth is ground (#F4F6F8) → white card with a 1px hairline. The only translucency is the sticky header at 92% ground over content.

## Shapes

Cards and lists 12px; rows, buttons, avatars and photos 8px; stamp 4px; slip mark 3px; tally cells 2px; status dots round. Borders are 1px hairlines; the stamp alone uses a 1.5px border plus a 1px outline offset 2px (a double rule) and a −3° rotation.

## Components

### Stamp (signature)
`stamp_html(day, time)`: inline column, "PRESENT" (Courier Prime 700, 0.72rem, 0.14em) over "12 OCT · 09:14" (400, 0.7rem, 0.04em), uppercase, stamp ink at 0.92 opacity, rotated −3°, `role="img"` with an aria-label. Large variant `.lg` (padding 8px 18px 6px, 2px border, 1.15rem key) is defined but not yet rendered. On a fresh row it lands with `g-press`: 180ms `cubic-bezier(0.23, 1, 0.32, 1)`, scale 1.08→1, opacity 0→0.92; reduced motion swaps to a 120ms opacity fade.

### Catalog row
Grid `36px | 1fr | auto`, gap 12px, padding 10px 14px, min-height 56px, soft-hairline dividers inside a 12px white list. Avatar 36px photo or initials on well. Name 600 ink, ID Courier Prime muted. Right slot: stamp (present) or "Not yet marked" (muted). `.fresh` = stamp-wash background, held until the 2s live fragment refresh. Empty state: muted 0.95rem line with a bold ink lead.

### Roll tally
CSS grid of `--n` equal cells, gap 3px, height 14px; on cells stamp ink, rest hairline. Decorative (`aria-hidden`); the sentence carries the count.

### Slip grid (Records)
HTML table in a 12px bordered white wrapper with horizontal scroll. Rows 34px; date heads Courier Prime (weekday muted 0.75rem over bold day 0.85rem). Sticky left name column (min 180px, 500 weight + ID). Present cell: 18px square mark, 1.5px stamp border, "P" Courier Prime 700, rotated −6°. Missed cell: 6×1.5px miss-dash. Trailing rate column in Courier Prime. Legend underneath.

### Student card
Bordered Streamlit container. Grid `72px | 1fr`, photo 72×88 8px radius; name, ID, meta list (key muted, value ink-2, 0.875rem); today line shows the stamp or muted text. Edit / delete buttons below; delete confirms with a primary button.

### Buttons, inputs, alerts
Streamlit widgets themed by `config.toml` (8px radius, widget borders on). One primary button per view (Take attendance, Save, Add student, confirm delete); everything else secondary. Press feedback: `scale(0.97)` on `:active`, 140ms ease-out transform; background/border 140ms ease. Focus: 2px outline offset 2px. Toasts and alerts always carry a Material icon.

### Live check-in
Webcam box 2px + Hershey label: stamp ink "Name | Verifying..." then "Name | Stamped present" after 5 matches; red "Not recognised". Legend dots 8px (stamp ink / red). Feed beside camera = present catalog rows refreshed every 2s.

### Icons
Material Symbols Rounded through `":material/name:"` only: today, photo_camera, badge, person_add, history, search, search_off, event_busy, edit, delete, check, check_circle, download. No SVG or glyph icons in custom HTML.

## Do's and Don'ts

### Do:
- **Do** keep `config.toml`, `:root` and `app.py` hex constants identical when a colour changes.
- **Do** render every "present" fact as the stamp, the slip mark, an on tally cell or stamp-ink text, and nothing else in ink.
- **Do** set IDs, dates, times and counts in Courier Prime with tabular figures.
- **Do** build new containers as white 12px cards with a 1px #D5DBE1 line on the ground.
- **Do** gate any new motion behind `prefers-reduced-motion` and keep it ≤180ms ease-out.

### Don't:
- **Don't** use stamp ink #6E2B8F for decoration, emphasis, links, selection, focus, headings or brand accents; it means present and nothing else.
- **Don't** colour absence red or add a second accent hue.
- **Don't** add box-shadows, gradients or glows.
- **Don't** rotate or ink anything except the stamp and slip mark.
- **Don't** add icons other than Material Symbols via `":material/name:"`.
