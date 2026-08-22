# DSN Design Tokens

Design token reference for products built under the Data Science Nigeria (DSN) brand.
This file is written to be read directly by an AI coding agent. Follow the rules in
[Agent Rules](#agent-rules) without exception unless a human overrides them in writing.

**Provenance:** the six brand colours were sampled pixel-by-pixel from the official DSN
logo (`dsn-logo.png`). Every other value in this file is *derived*, not official, and is
marked as such. Derived values require brand-team sign-off before external publication.

**Last updated:** 21 August 2026

---

## 1. Brand colours (sampled, do not alter)

| Token | Hex | Source in logo |
|---|---|---|
| `--dsn-red` | `#ED3237` | "DSN" wordmark, dominant colour |
| `--dsn-green` | `#00A859` | Nigeria map silhouette |
| `--dsn-indigo` | `#3E4095` | "Data Science Nigeria" text |
| `--dsn-blue` | `#0487F0` | Mosaic arc, median tone |
| `--dsn-blue-deep` | `#014DBD` | Mosaic arc, darkest stop |
| `--dsn-blue-light` | `#87D5F6` | Mosaic arc, lightest stop |

The arc is a gradient, not a flat colour. Reproduce it as:

```css
--dsn-arc: linear-gradient(90deg, #014DBD 0%, #0487F0 55%, #87D5F6 100%);
```

## 2. Full token set

```css
:root {
  /* Brand (sampled from logo, do not alter) */
  --dsn-red:        #ED3237;
  --dsn-green:      #00A859;
  --dsn-indigo:     #3E4095;
  --dsn-blue:       #0487F0;
  --dsn-blue-deep:  #014DBD;
  --dsn-blue-light: #87D5F6;
  --dsn-arc: linear-gradient(90deg, #014DBD 0%, #0487F0 55%, #87D5F6 100%);

  /* Semantic: fills, icons, borders, large type only */
  --success:  #00A859;   /* brand green */
  --info:     #0487F0;   /* brand blue */
  --danger:   #ED3237;   /* brand red */
  --warning:  #F5A623;   /* DERIVED: amber, no logo source */

  /* Semantic text: safe for small type on white, all >= 4.5:1 */
  --success-text: #00713B;   /* DERIVED */
  --info-text:    #014DBD;   /* brand blue-deep, 7.4:1 */
  --danger-text:  #B21F23;   /* DERIVED */
  --warning-text: #8A5300;   /* DERIVED */

  /* Tinted surfaces for banners, chips, alert rows (DERIVED) */
  --success-bg: #E6F6EE;  --success-border: #99DDBF;
  --info-bg:    #E6F3FE;  --info-border:    #9CD0FB;
  --danger-bg:  #FDECEC;  --danger-border:  #F8B3B5;
  --warning-bg: #FEF5E6;  --warning-border: #FBDCA1;

  /* Neutrals: indigo-tinted greys (DERIVED) */
  --n-900: #16172B;   /* body text */
  --n-700: #3A3C55;   /* secondary text, outline buttons */
  --n-500: #6E7089;   /* muted text, placeholders */
  --n-300: #C8CAD8;   /* borders, dividers */
  --n-100: #EEEFF4;   /* subtle fills */
  --n-050: #F7F8FB;   /* page background */
  --white: #FFFFFF;   /* card and surface background */
}

/* Dark mode: brand hues lifted for contrast on --n-900 (DERIVED) */
[data-theme="dark"] {
  --surface:  #16172B;
  --surface-2:#1F2138;
  --success:  #3FCC8B;
  --info:     #5AB3F7;
  --danger:   #FF7377;
  --warning:  #FFC55C;
  --dsn-indigo-on-dark: #8C8EDB;
  --text:     #EEEFF4;
  --text-muted: #A8AABE;
}
```

## 3. Contrast reference (on `#FFFFFF`)

| Token | Ratio | Verdict |
|---|---|---|
| `--dsn-indigo` `#3E4095` | 8.6:1 | Passes AA and AAA for all text |
| `--dsn-blue-deep` `#014DBD` | 7.4:1 | Passes AA and AAA for all text |
| `--n-900` `#16172B` | 16.9:1 | Default body text |
| `--dsn-red` `#ED3237` | 4.0:1 | Fails AA for small text. Fills and large type only |
| `--dsn-blue` `#0487F0` | 3.3:1 | Fails AA for small text. Fills and large type only |
| `--dsn-green` `#00A859` | 2.8:1 | Fails AA for small text. Fills and icons only |
| `--warning` `#F5A623` | 1.9:1 | Fills only. Never text on white |
| `--dsn-blue-light` `#87D5F6` | 1.6:1 | Backgrounds and accents only |

"Large type" means 24px regular or 18.66px bold and above.

## 4. Usage map

| Surface | Token |
|---|---|
| Page background | `--n-050` |
| Card and modal background | `--white` |
| Body text | `--n-900` |
| Secondary text | `--n-700` |
| Muted text and placeholders | `--n-500` |
| Borders and dividers | `--n-300` |
| Primary action (fill) | `--dsn-indigo` on `--white` text |
| Primary action (hover) | `#33357E` (DERIVED) |
| Secondary action | `--n-700` outline on `--white` |
| Destructive action | `--danger` fill, `--white` text |
| Links | `--info-text` |
| Focus ring | `--dsn-blue` at 3px, 2px offset |
| Hero and header banding | `--dsn-arc` |

## 5. Chart palette

Ordered for maximum pairwise distinguishability, including under deuteranopia and
protanopia. Use in sequence. Do not reorder to lead with red.

1. `#3E4095` indigo
2. `#0487F0` blue
3. `#00A859` green
4. `#F5A623` amber (DERIVED)
5. `#ED3237` red
6. `#87D5F6` light blue

For sequential (single-hue) scales use the arc ramp: `#87D5F6` to `#0487F0` to `#014DBD`.
For diverging scales use `#ED3237` to `#EEEFF4` to `#3E4095`, never red to green.

## 6. Agent rules

1. **Never invent a brand colour.** If a needed hue is absent from this file, use the
   nearest neutral and leave a `TODO(brand):` comment. Do not sample or guess a new hex.
2. **Text contrast.** For any text under 18px, or under 14px bold, use only `--n-900`,
   `--n-700`, `--dsn-indigo`, `--dsn-blue-deep`, or a `*-text` token. Plain `--success`,
   `--info`, `--danger`, and `--warning` are for fills, icons, borders, and large display
   type only.
3. **Never signal state with hue alone.** Every status must carry an icon or a text label.
   Red and green are the two primary brand colours and read alike under red-green colour
   blindness.
4. **Red is both brand and danger.** Do not place a destructive red button in the same
   visual block as the DSN wordmark. Use a `--n-700` outline button in logo-adjacent
   regions instead.
5. **The arc gradient is a hero device.** Use it in headers, hero bands, and splash
   surfaces. Never place body text on top of it.
6. **Brand indigo fails on dark backgrounds.** In dark mode swap to
   `--dsn-indigo-on-dark`. Do not tint `#3E4095` inline.
7. **Flag derived values.** Amber, all neutrals, all `*-text` values, all tinted
   backgrounds, and all dark-mode values are derived and not official DSN brand colours.
   Surface this to the user before any externally published artefact ships.
8. **Reference tokens, never literals.** Emit `var(--dsn-indigo)`, not `#3E4095`, in all
   application code. Raw hex belongs only in this file and the generated token files.
9. **Focus states are mandatory.** Every interactive element gets a visible
   `--dsn-blue` focus ring. Never set `outline: none` without a replacement.
10. **Do not restyle the logo.** The DSN mark is used as supplied. No recolouring,
    no monochrome variant, no gradient overlay, no rotation.

## 7. Open items

- Confirm the official amber, if one exists, with the DSN brand team. `#F5A623` is a
  placeholder.
- Confirm the neutral ramp. The indigo tint is a design choice, not a brand mandate.
- Obtain the official typeface. This file covers colour only.
- Obtain vector logo assets (SVG) and clear-space rules for production use.
