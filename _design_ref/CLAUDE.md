# Project conventions

## Writing
- Never use em dashes (—). Use commas, colons, full stops, or restructure the sentence.

## Brand: Data Science Nigeria
Logo at `dsn-logo.png` (project root). Palette, as supplied:

| Role | Hex | Use |
| --- | --- | --- |
| Primary green | `#0A7A0A` | Primary actions, active states, logo mark |
| Primary green 600 | `#086508` | Hover on primary |
| Indigo | `#3E4095` | Headings, nav bars, secondary surfaces |
| Blue | `#1B8FE0` | Links, info states, data-viz primary |
| Accent red | `#E01B1B` | Alerts, destructive actions, sparing emphasis |
| Neutral dark | `#1A1A1A` | Body text |
| Neutral light | `#F5F7F5` | Page background, cards |
| Surface | `#FFFFFF` | Cards, paper |

Applied convention: green for primary buttons and confirm actions, indigo for page
headings and the active nav item, blue for links, red for refusals and overdue states.

## Design system
- shadcn component anatomy (zinc borders, 8px/11px radii, Geist + Geist Mono) over the DSN palette.

## Files
- Avoid em dashes and other non-ASCII punctuation in filenames; the tooling rejects those paths.

## Stack notes
- Document viewing, editing and version history are designed around SuperDoc
  (github.com/superdoc/docx-editor): DOCX-native, mounts into a selector plus toolbar,
  supports viewing / suggesting / editing modes, comments, track changes and Yjs collaboration.
  AGPLv3, so the external product path (M16) needs the commercial licence.
