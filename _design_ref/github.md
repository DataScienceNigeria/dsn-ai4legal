repo: superdoc/docx-editor
branch: main
role: reference only, not vendored into this project

## Last sync
date: 2026-08-21T15:41:03Z

### Updated in this project
- Read README and package.json to ground the document surfaces on SuperDoc's real capabilities.
- Added a Document screen (M04/M06) with viewing / suggesting / editing modes, tracked changes and version history.
- Added a Templates screen (M03) with merge fields, conditional sections, change proposals and atomic publication.
- Noted the AGPLv3 licence, which the external product path (M16) would need a commercial licence for.

## Screen map
| Screen | Built from |
| --- | --- |
| Document, Sahel Cloud MSA draft 4 | README.md (DOCX-native model, suggesting mode, track changes, version history) |
| Templates, TPL-MSA-v2.4 | README.md (Document API, editing modes), PRD section 7.3 |

## Notes
No SuperDoc code was copied into this project. It requires a build step, so the prototype
designs the UI around the editor rather than embedding it. Integration points assumed:
`new SuperDoc({ selector, toolbar, document, documentMode })` with documentMode driving the
viewing / suggesting / editing switch.
