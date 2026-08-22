# Interface conventions

Colour and brand live in [DESIGN_TOKENS.md](DESIGN_TOKENS.md). This file covers everything
else the interface has to get right, and the constraints DESIGN_TOKENS.md sets.

## Constraints carried from DESIGN_TOKENS.md

1. Blue `#1B8FE0` fails WCAG AA for normal text at 3.1:1. Use it for links,
   large text, borders and chart fills, never for body copy.
2. Green and red alone fail for red-green colour blindness. Every status carries
   an icon or a text label as well as a colour, and amber and indigo provide a
   second status axis rather than more red.

## Dark mode

Required. Colour is expressed only as CSS custom properties on `:root`, with a
dark set under `.dark`. No component hardcodes a hex value. The brand green
holds in both themes; surfaces, borders and text invert.

## Component system

shadcn component anatomy: zinc borders, 8px and 11px radii, Geist for text and
Geist Mono for identifiers such as matter numbers and clause references.

## Screens

Portal, 6: request type selection, guided form, data involvement declaration,
confirmation, generation preview, AI first draft.

Workspace, 14: delivery, triage, triage detail, matters, matter, document,
templates, review, archive, obligations, inbox, memory, assessment, capabilities.

## Rules the interface must make visible

These are platform rules, not decoration. Each one has a visual consequence.

| Rule | What the interface must show |
| --- | --- |
| AI may recommend, a human must confirm | Every AI output is labelled a draft and carries accept, edit and reject |
| An output without sources is a failed call | A refusal is shown as a refusal, never as an empty answer |
| Only approved clauses are house position | Novel text is marked novel and unapproved wherever it appears |
| Approval binds to a document hash | An edit after approval shows the approval as invalidated |
| A capability below its gate does not run | The capability appears disabled, with its score against its gate |
| Restricted matters are genuinely restricted | No title, snippet or citation appears, and the refusal says so |

## Document surfaces

Viewing, suggesting and editing modes, tracked changes, comments and version
history, following the SuperDoc model. Implemented directly rather than
embedding SuperDoc, which is AGPLv3.
