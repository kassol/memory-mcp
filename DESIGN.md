---
name: 记忆登记簿 (Memory Registry)
description: Web console for reviewing findings and correcting or archiving memories, built as a records registry and docket.
colors:
  ledger-ground: "oklch(97.5% 0.003 250)"
  ledger-sheet: "oklch(99.5% 0.002 250)"
  rule: "oklch(89% 0.005 250)"
  rule-strong: "oklch(78% 0.008 250)"
  ink: "oklch(24% 0.012 250)"
  ink-secondary: "oklch(45% 0.012 250)"
  ink-tertiary: "oklch(50% 0.01 250)"
  registry-blue: "oklch(47% 0.13 255)"
  registry-blue-ink: "oklch(99% 0 0)"
  registry-blue-wash: "oklch(94% 0.03 255)"
  conflict-amber: "oklch(52% 0.13 55)"
  archive-red: "oklch(50% 0.16 27)"
  archive-red-fill: "oklch(50% 0.16 27)"
  current-green: "oklch(48% 0.1 155)"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
  title:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
  registry-name:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    letterSpacing: "0.02em"
  body:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  record-text:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.7
  body-small:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  label:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
  stamp:
    fontFamily: "system-ui, -apple-system, \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", \"Noto Sans CJK SC\", sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.04em"
  identifier:
    fontFamily: "ui-monospace, \"SF Mono\", \"JetBrains Mono\", Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.4
  meta-mono:
    fontFamily: "ui-monospace, \"SF Mono\", \"JetBrains Mono\", Menlo, Consolas, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\""
  count:
    fontFamily: "ui-monospace, \"SF Mono\", \"JetBrains Mono\", Menlo, Consolas, monospace"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1
    fontFeature: "\"tnum\""
rounded:
  stamp: "3px"
  control: "6px"
spacing:
  xxs: "0.25rem"
  xs: "0.5rem"
  sm: "0.75rem"
  card: "0.875rem"
  md: "1rem"
  lg: "1.25rem"
  xl: "1.5rem"
  xxl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.registry-blue}"
    textColor: "{colors.registry-blue-ink}"
    rounded: "{rounded.control}"
    padding: "0.4375rem 0.875rem"
  button-secondary:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0.4375rem 0.875rem"
  button-quiet:
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.control}"
    padding: "0.4375rem 0.875rem"
  button-quiet-hover:
    backgroundColor: "{colors.ledger-ground}"
    textColor: "{colors.ink}"
  button-quiet-danger:
    textColor: "{colors.archive-red}"
    rounded: "{rounded.control}"
    padding: "0.4375rem 0.875rem"
  input:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.625rem"
  tab:
    textColor: "{colors.ink-secondary}"
    padding: "0 0.75rem"
    height: "3.25rem"
  tab-active:
    textColor: "{colors.ink}"
  top-bar:
    backgroundColor: "{colors.ledger-sheet}"
    height: "3.25rem"
    padding: "0 1.25rem"
  ledger-row:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink}"
    padding: "0.625rem 1rem"
  ledger-row-hover:
    backgroundColor: "{colors.ledger-ground}"
  ledger-row-selected:
    backgroundColor: "{colors.registry-blue-wash}"
  record-card:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  stamp-current:
    textColor: "{colors.current-green}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "0.25rem 0.4375rem"
  stamp-archived:
    textColor: "{colors.ink-tertiary}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "0.25rem 0.4375rem"
  stamp-correction:
    textColor: "{colors.registry-blue}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "0.25rem 0.4375rem"
  stamp-conflict:
    textColor: "{colors.conflict-amber}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "0.25rem 0.4375rem"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ledger-sheet}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.875rem"
  toast-error:
    backgroundColor: "{colors.archive-red-fill}"
    textColor: "{colors.registry-blue-ink}"
---

# Design System: 记忆登记簿 (Memory Registry)

Source of truth: `src/memory_mcp/ui/style.css`, `src/memory_mcp/ui/index.html`, `src/memory_mcp/ui/app.js`. Frontmatter color values are the light scheme; dark-scheme values live in `.impeccable/design.json` (`colorMeta.<token>.dark`) and in the `prefers-color-scheme: dark` block of the stylesheet.

## Overview

**Creative North Star: "The Records Registry"**

The console is a registry office, not a dashboard. Every memory is a filed record with an identifier, and the findings queue is a docket of cases waiting for a ruling. The screen is a neutral grey ledger: thin ruled rows, a white sheet for the list and for each record, and plain system text. Nothing decorates; structure comes from rules (1px lines) and from the split between the ledger on the left and the case file on the right.

Density is moderate and reading-first. Records show their full text, never truncated, at a generous line height (1.7) so long Chinese passages with dates and version strings stay readable. Monospace appears only where something is an identifier, a date or a count. Status is a small outlined stamp, the way a clerk marks a paper file. One blue accent marks where the reader is and what the main action is.

The system follows the operating system's light or dark scheme with the same roles in both; it has no theme switch.

**Key Characteristics:**
- Neutral cool-grey ledger ground with white sheets, separated by 1px rules.
- One accent hue (registry blue) for the current row, the active tab, focus and the primary action.
- System sans for prose; tabular monospace for identifiers, dates and counts.
- Outlined status stamps in currentColor; no filled badges.
- Flat surfaces; the only shadow belongs to the transient toast.

## Colors

A near-achromatic cool-grey ledger (hue 250, chroma at or below 0.012) with one saturated blue and three semantic stamp colors.

### Primary
- **Registry Blue** (`registry-blue`): the only accent. Primary button fill, active tab underline and tab count, the 2px bar on the selected ledger row, the focus outline, and the correction stamp.
- **Registry Blue Ink** (`registry-blue-ink`): text on a Registry Blue fill, and text on the error toast.
- **Registry Blue Wash** (`registry-blue-wash`): background of the selected ledger row and of text selection.

### Tertiary
- **Current Green** (`current-green`): the "current" stamp only.
- **Conflict Amber** (`conflict-amber`): the "conflict merge" stamp and the finding-kind stamp at the head of a case file.
- **Archive Red** (`archive-red`): the archive action text and the login error message. **Archive Red Fill** (`archive-red-fill`) is the error toast background; it equals Archive Red in light and is darker in dark (oklch(44% 0.14 27)) so white text keeps contrast.

### Neutral
- **Ledger Ground** (`ledger-ground`): page background, case-file background, hover fill for rows and quiet buttons.
- **Ledger Sheet** (`ledger-sheet`): top bar, ledger column, record cards, inputs, secondary buttons.
- **Rule** (`rule`): hairlines inside a component (between rows, inside record cards, version list rows) and the skeleton bar.
- **Rule Strong** (`rule-strong`): structural lines (under the top bar, ledger column edge, record card border, ruling divider) and input and secondary-button borders.
- **Ink** (`ink`): primary text; toast background.
- **Ink Secondary** (`ink-secondary`): inactive tabs, hints, labels, row keys, history text.
- **Ink Tertiary** (`ink-tertiary`): metadata, row numbers, counts, archived stamp, hover border for inputs.

### Named Rules
**The One Blue Rule.** Registry Blue marks position and the main action: the selected row, the active tab, focus, the primary button. Status colors never borrow it except for the correction stamp.

**The Two Rules Rule.** Lines come in two weights of color only: `rule` inside a component, `rule-strong` between structural regions. All lines are 1px, except the 2px active-tab underline and selected-row bar.

## Typography

**Body Font:** system UI sans with Chinese fallbacks (PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC).
**Label/Mono Font:** ui-monospace stack (SF Mono, JetBrains Mono, Menlo, Consolas).

**Character:** plain office type. The sans carries all prose; the monospace is a clerk's stamp for entity keys, timestamps, version numbers and counts, always with tabular figures.

### Hierarchy
- **Headline** (700, 1.25rem): login card heading only.
- **Title** (650, 1.125rem): case file and record heading ("卷宗 02").
- **Registry Name** (650, 1rem, 0.02em tracking): the top bar title; 0.9375rem on phones.
- **Body** (400, 15px, line-height 1.6): base text. Case detail paragraphs cap at 72ch.
- **Record Text** (400, 15px, line-height 1.7): full memory text in record cards and the correction editor; preserves line breaks; caps at 80ch in a single record, unbounded inside a side-by-side pair.
- **Body Small** (0.875rem): row gist (clamped to two lines in the ledger), hints, version text, toast, errors.
- **Label** (0.8125rem): form labels, ledger meta, footers, ruling note.
- **Stamp** (600, 0.6875rem, 0.04em tracking): status stamps.
- **Identifier** (mono 500, 0.8125rem): entity keys in record heads and in the records list.
- **Meta Mono** (mono 400, 0.75rem, tabular): record meta line and version timestamps.
- **Count** (mono 600, 0.75rem, tabular): tab counts and row numbers (row numbers use weight 500).

### Named Rules
**The Identifier Rule.** Monospace is for identifiers, dates and counts only. Prose, finding kinds and labels stay in the sans.

## Layout

A full-height column: a 3.25rem top bar, then a two-column workspace. The ledger column is `minmax(18rem, 26rem)`; the case file takes the rest and scrolls on its own (padding 1.5rem 2rem 3rem). The ledger has a head (search and filters, or a docket note), a scrolling ordered list, and a foot with the count or "load more".

In a case file, two records sit side by side in equal columns with a 1.25rem gap, aligned to the top; the ruling bar sits under them. Between 761px and 1100px the pair stacks into one column. At 760px and below the ledger and the case file become separate views: the list shows first, selecting a row opens the case file with a quiet "返回列表" button, and the version history collapses to a single column.

Spacing is rem-based: 0.25 / 0.5 / 0.75 / 0.875 / 1 / 1.25 / 1.5 / 2rem. Record cards use 0.875rem horizontal padding; ledger rows use 0.625rem by 1rem.

## Elevation & Depth

Flat. Depth comes from tone (sheet on ground) and 1px rules. The toast is the only element with a shadow, because it floats over content for a moment.

### Shadow Vocabulary
- **Toast float** (`box-shadow: 0 6px 20px oklch(0% 0 0 / 0.18)`): transient status messages only.

### Named Rules
**The Flat Ledger Rule.** Cards, rows, bars and inputs never cast shadows. Separate them with tone and rules.

## Shapes

Small, plain corners. Controls, inputs, record cards and the toast use 6px; stamps and skeleton bars use 3px. Rows, bars and columns are square and bounded by rules. The registry mark in the top bar is a small outlined file shape (2px stroke, 5px top edge, 1px corner) drawn in CSS.

## Components

### Buttons
Restrained and compact; weight 550; background and border transition 150ms ease-out.
- **Shape:** gently rounded (6px), padding 0.4375rem 0.875rem, 1px transparent border.
- **Primary:** Registry Blue fill, Registry Blue Ink text. Hover mixes 12% ink into the blue. One per context: "进入", "保存为新版本", "确认归档".
- **Secondary:** sheet fill, Rule Strong border; hover darkens the border to Ink Tertiary. Used for "改正" and "判为误报".
- **Quiet:** no fill, Ink Secondary text; hover fills with Ledger Ground and darkens text. Used for cancel, load more, back.
- **Quiet danger:** quiet button with Archive Red text, for "归档".
- **Disabled:** 50% opacity, progress cursor, while a request runs.
- **Text link:** the logout control in the top bar; underlines on hover (3px offset).

### Chips
Status stamps (see Signature Component).

### Cards / Containers
- **Corner Style:** 6px.
- **Background:** Ledger Sheet on Ledger Ground.
- **Shadow Strategy:** none (Flat Ledger Rule).
- **Border:** 1px Rule Strong outside; 1px Rule between head, body, editor and actions.
- **Internal Padding:** head 0.625rem 0.875rem; meta line 0.5rem 0.875rem 0; body 0.75rem 0.875rem 1rem; actions 0.625rem 0.875rem.
- **Record card anatomy:** monospace key with stamps pushed to the right; a monospace meta line (written, valid from, version); full text; archive reason if any; actions. Correct and archive open an inline editor inside the card with a hint, a textarea (min 12rem, line-height 1.7) and right-aligned cancel and confirm.

### Inputs / Fields
- **Style:** sheet fill, 1px Rule Strong border, 6px corners, padding 0.5rem 0.625rem, full width. Selects in the ledger head are auto width and smaller (0.875rem).
- **Hover:** border darkens to Ink Tertiary.
- **Focus:** 2px Registry Blue outline at offset 0 and the border turns transparent. Other focusable elements get the same outline at offset 2px.
- **Error:** message in Archive Red under the field, with a reserved 1.5rem height so layout does not jump.

### Navigation
Top bar on Ledger Sheet with a Rule Strong bottom line: mark, registry name, two tabs, logout pushed right. Tabs are full bar height, Ink Secondary; hover goes to Ink. The active tab (`aria-current="page"`) is Ink, weight 600, with a 2px Registry Blue underline, and its monospace count turns blue.

### Ledger Row (signature)
A two-column grid: a right-aligned monospace number spanning two lines, then the key (finding kind in sans on the docket, entity key in monospace on the records list) over a two-line clamped gist. 1px Rule under each row. Hover fills with Ledger Ground; the selected row fills with Registry Blue Wash and carries a 2px Registry Blue bar on its left edge. Loading rows show pulsing skeleton bars (1.2s; no animation under reduced motion).

### Status Stamp (signature)
An outlined mark: 1px border in currentColor, 3px corners, 0.6875rem weight 600 text with 0.04em tracking, no fill. Color carries the status: current (green), archived (Ink Tertiary), correction (blue), conflict merge and finding kind (amber).

### Ruling Bar
Under the records of a case: a Rule Strong top line, a tertiary note on the left, and the dismiss action on the right.

### Version History
A list under a single record: a Rule Strong top line, rows split into an 11rem monospace column (timestamp plus stamps) and the version text. The current version's text is Ink; older versions are Ink Secondary; archive reasons appear in Ink Tertiary.

### Toast
Centered at the bottom (1.25rem), Ink background with Sheet text, 6px corners, the toast float shadow. The error variant uses Archive Red Fill with near-white text.

## Do's and Don'ts

### Do:
- **Do** show the full memory text in records, with line breaks kept and line-height 1.7.
- **Do** put entity keys, timestamps, version numbers and counts in the monospace stack with tabular figures.
- **Do** show status with outlined stamps in currentColor (3px corners, 1px border).
- **Do** separate regions with 1px rules: `rule` inside a component, `rule-strong` between regions.
- **Do** keep one primary (Registry Blue) button per decision point; use secondary and quiet buttons for the rest.
- **Do** give destructive actions the quiet danger style and confirm them in an inline editor that states what will change.

### Don't:
- **Don't** add metric cards, charts or dashboard tiles; the console is a registry and docket.
- **Don't** truncate memory text in a record or case file; clamping is for ledger gists only.
- **Don't** use Registry Blue for decoration or for status other than correction.
- **Don't** give cards, rows or bars a shadow; only the toast floats.
- **Don't** fill stamps with solid color.
