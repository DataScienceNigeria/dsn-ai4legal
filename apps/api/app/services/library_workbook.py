"""The legal team's playbook and clause library workbook, in and out.

Reading checks every row of both sheets before anything is written, and
reports each problem against the sheet and row it is on. What survives becomes
a plan: the clauses, their variants with wording and playbook positions, the
precedent wording, and one playbook per entity and agreement sub-type. The
plan is compared with the library as it stands, so a second upload of the same
workbook changes nothing, and an edited one proposes new drafts only where the
text moved.

Applying writes drafts. Publishing stays the separate, authorised step.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.library import (
    Clause,
    ClausePrecedent,
    ClauseVariant,
    ClauseVersion,
    LibraryImport,
    Playbook,
)
from app.domain import library_mapping as mapping
from app.domain.enums import VersionStatus

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PLAYBOOK_SHEET = "Legal Playbook"
LIBRARY_SHEET = "Clause Library"

PLAYBOOK_COLUMNS = [
    "Entity",
    "Agreement type",
    "Transaction role",
    "Clause category",
    "Clause title",
    "Standard position",
    "Acceptable negotiated position",
    "Fallback position",
    "Red line",
    "Clause ID",
    "Clause version ID",
]
LIBRARY_COLUMNS = [
    "Clause ID",
    "Clause version ID",
    "Entity",
    "Agreement type",
    "Transaction role",
    "Clause category",
    "Clause title",
    "Clause wording",
    "Wording status",
    "Source",
]
PLAYBOOK_KEYS = [
    "entity",
    "type",
    "role",
    "category",
    "title",
    "standard",
    "negotiated",
    "fallback",
    "red_line",
    "clause_id",
    "variant_id",
]
LIBRARY_KEYS = [
    "clause_id",
    "variant_id",
    "entity",
    "type",
    "role",
    "category",
    "title",
    "wording",
    "status",
    "source",
]

SUBTYPE_COLUMN = "Sub-type"
ALL_SUBTYPES = {"all sub-types", "all subtypes", "all"}
SUBTYPE_MAX = 128
MAX_ROWS = 5000
HEADER_SEARCH_ROWS = 15
TITLE_MAX = 255
ROLE_MAX = 64
POSITION_MAX = 4000
WORDING_MAX = 20000
URL_MAX = 2048

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
FORMULA_PREFIXES = ("=", "+", "-", "@")


class NotAWorkbook(ValueError):
    """The file is not an Excel workbook this importer can read."""


@dataclass
class Issue:
    sheet: str
    row: int | None
    column: str | None
    level: str
    message: str

    def as_dict(self) -> dict:
        return {
            "sheet": self.sheet,
            "row": self.row,
            "column": self.column,
            "level": self.level,
            "message": self.message,
        }


@dataclass
class Checked:
    """What a workbook would do, and everything wrong with it."""

    plan: dict
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.level == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.level == "warning")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return CONTROL_CHARACTERS.sub("", text).strip()


def _normal(text: str | None) -> str:
    return " ".join((text or "").split())


def _with_subtype(columns: list[str], keys: list[str]) -> tuple[list[str], list[str]]:
    """The same layout with a Sub-type column straight after Agreement type."""
    at = columns.index("Agreement type") + 1
    return (
        [*columns[:at], SUBTYPE_COLUMN, *columns[at:]],
        [*keys[:at], "subtype", *keys[at:]],
    )


def _rows(workbook, sheet: str, columns: list[str], keys: list[str], issues: list[Issue]):
    if sheet not in workbook.sheetnames:
        issues.append(
            Issue(sheet, None, None, "error", f'The workbook has no sheet named "{sheet}".')
        )
        return []

    layouts = [_with_subtype(columns, keys), (columns, keys)]
    header_row = None
    rows: list[tuple[int, dict]] = []
    for number, values in enumerate(workbook[sheet].iter_rows(values_only=True), start=1):
        cells = [_text(value) for value in values]
        if header_row is None:
            if number > HEADER_SEARCH_ROWS:
                break
            for layout, layout_keys in layouts:
                if [_normal(c).lower() for c in cells[: len(layout)]] == [
                    _normal(c).lower() for c in layout
                ]:
                    header_row, keys = number, layout_keys
                    break
            continue
        if not any(cells):
            continue
        if len(rows) >= MAX_ROWS:
            issues.append(
                Issue(
                    sheet,
                    None,
                    None,
                    "error",
                    f"The sheet has more than {MAX_ROWS} rows. Split it and import each part.",
                )
            )
            return []
        padded = cells[: len(keys)] + [""] * (len(keys) - len(cells[: len(keys)]))
        row = dict(zip(keys, padded, strict=True))
        row.setdefault("subtype", None)
        rows.append((number, row))

    if header_row is None:
        issues.append(
            Issue(
                sheet,
                None,
                None,
                "error",
                f"No header row was found in the first {HEADER_SEARCH_ROWS} rows. The columns "
                f"must read, in order: {', '.join(layouts[0][0])}. The Sub-type column may "
                "be left out.",
            )
        )
    return rows


def _required(value: str, limit: int, sheet: str, row: int, column: str, issues: list[Issue]):
    if not value:
        issues.append(Issue(sheet, row, column, "error", f"{column} is required."))
    elif len(value) > limit:
        issues.append(
            Issue(
                sheet,
                row,
                column,
                "error",
                f"{column} is {len(value)} characters; the limit is {limit}.",
            )
        )


def _optional(value: str, limit: int, sheet: str, row: int, column: str, issues: list[Issue]):
    if value and len(value) > limit:
        issues.append(
            Issue(
                sheet,
                row,
                column,
                "error",
                f"{column} is {len(value)} characters; the limit is {limit}.",
            )
        )


def _identifiers(row: dict, sheet: str, number: int, issues: list[Issue], variant_required: bool):
    if not mapping.CLAUSE_ID.fullmatch(row["clause_id"]):
        issues.append(
            Issue(
                sheet,
                number,
                "Clause ID",
                "error",
                f'"{row["clause_id"] or "(empty)"}" is not a clause ID such as CLS-TPL-007.',
            )
        )
    variant = row["variant_id"]
    if not variant:
        if variant_required:
            issues.append(
                Issue(sheet, number, "Clause version ID", "error", "Clause version ID is required.")
            )
        return
    if not mapping.VARIANT_ID.fullmatch(variant):
        issues.append(
            Issue(
                sheet,
                number,
                "Clause version ID",
                "error",
                f'"{variant}" is not a clause version ID such as CLV-DSN-SAG-001.',
            )
        )


def _scope_agrees(row: dict, scope: str | None, sheet: str, number: int, issues: list[Issue]):
    match = mapping.VARIANT_ID.fullmatch(row["variant_id"] or "")
    if match and scope and mapping.CODE_ENTITIES[match.group(1)] != scope:
        issues.append(
            Issue(
                sheet,
                number,
                "Clause version ID",
                "error",
                f"{row['variant_id']} is coded for {match.group(1)}, but the entity is "
                f"{row['entity']}.",
            )
        )


def _common(row: dict, sheet: str, number: int, issues: list[Issue]):
    scope = mapping.entity(row["entity"])
    if scope is None:
        issues.append(
            Issue(
                sheet,
                number,
                "Entity",
                "error",
                f'"{row["entity"] or "(empty)"}" is not an entity the platform knows. Use '
                f"{', '.join(mapping.ENTITY_CHOICES)}.",
            )
        )
    agreement = mapping.agreement_type(row["type"])
    if agreement is None:
        issues.append(
            Issue(
                sheet,
                number,
                "Agreement type",
                "error",
                f'"{row["type"] or "(empty)"}" is not a mapped agreement type.',
            )
        )
    elif row["subtype"] is not None:
        agreement = _subtype(row, agreement, sheet, number, issues)
    family = mapping.family(row["category"])
    if family is None:
        issues.append(
            Issue(
                sheet,
                number,
                "Clause category",
                "error",
                f'"{row["category"] or "(empty)"}" is not a mapped clause category.',
            )
        )
    _required(row["role"], ROLE_MAX, sheet, number, "Transaction role", issues)
    _required(row["title"], TITLE_MAX, sheet, number, "Clause title", issues)
    return scope, agreement, family


def _subtype(row: dict, agreement: tuple, sheet: str, number: int, issues: list[Issue]):
    """The Sub-type column, where the workbook has one."""
    code, named = agreement
    given = " ".join(row["subtype"].split())
    if _normal(given).lower() in ALL_SUBTYPES:
        given = ""
    if len(given) > SUBTYPE_MAX:
        issues.append(
            Issue(
                sheet,
                number,
                SUBTYPE_COLUMN,
                "error",
                f"{SUBTYPE_COLUMN} is {len(given)} characters; the limit is {SUBTYPE_MAX}.",
            )
        )
        return None
    if named and given and _normal(named).lower() != _normal(given).lower():
        issues.append(
            Issue(
                sheet,
                number,
                SUBTYPE_COLUMN,
                "error",
                f'Agreement type names the sub-type "{named}" but Sub-type says "{given}". '
                "Keep the sub-type in one place.",
            )
        )
        return None
    return code, given or named


def _library(rows, issues: list[Issue]):
    variants: dict[str, dict] = {}
    rejected: dict[str, int] = {}
    seen: dict[str, int] = {}
    precedents: list[dict] = []
    fingerprints: dict[str, int] = {}

    for number, row in rows:
        before = len(issues)
        status = mapping.wording_status(row["status"])
        if status is None:
            issues.append(
                Issue(
                    LIBRARY_SHEET,
                    number,
                    "Wording status",
                    "error",
                    f'"{row["status"] or "(empty)"}" is not a wording status. Use '
                    f"{', '.join(mapping.WORDING_STATUSES)}.",
                )
            )
        _identifiers(row, LIBRARY_SHEET, number, issues, variant_required=status == "approved")
        scope, agreement, family = _common(row, LIBRARY_SHEET, number, issues)
        if family:
            family = mapping.family_of_wording(row["category"], row["wording"])
        _scope_agrees(row, scope, LIBRARY_SHEET, number, issues)
        _required(row["wording"], WORDING_MAX, LIBRARY_SHEET, number, "Clause wording", issues)

        source = row["source"]
        if source:
            parsed = urlparse(source)
            if len(source) > URL_MAX or parsed.scheme != "https" or not parsed.netloc:
                issues.append(
                    Issue(
                        LIBRARY_SHEET,
                        number,
                        "Source",
                        "error",
                        "Source must be an https link of at most "
                        f"{URL_MAX} characters, or left empty.",
                    )
                )

        variant = row["variant_id"]
        if variant and variant in seen:
            issues.append(
                Issue(
                    LIBRARY_SHEET,
                    number,
                    "Clause version ID",
                    "error",
                    f"{variant} is already on row {seen[variant]}. Each clause version "
                    "ID appears once in the library.",
                )
            )
            if variant not in variants:
                rejected.setdefault(variant, number)
            continue
        if variant:
            seen[variant] = number
        if any(issue.level == "error" for issue in issues[before:]):
            if variant:
                rejected[variant] = number
            continue

        entry = {
            "row": number,
            "clause_id": row["clause_id"],
            "scope": scope,
            "agreement_type": agreement[0],
            "subtype": agreement[1],
            "role": row["role"],
            "family": family,
            "title": row["title"],
            "text": row["wording"],
            "source_url": source or None,
        }
        if status == "approved":
            variants[variant] = {**entry, "code": variant}
            continue

        entry.update(kind=status, reference=variant or None)
        fingerprint = hashlib.sha256(
            "|".join(
                str(entry[key])
                for key in (
                    "kind",
                    "reference",
                    "clause_id",
                    "scope",
                    "agreement_type",
                    "subtype",
                    "role",
                    "title",
                    "text",
                )
            ).encode()
        ).hexdigest()
        if fingerprint in fingerprints:
            issues.append(
                Issue(
                    LIBRARY_SHEET,
                    number,
                    None,
                    "warning",
                    f"The same wording is on row {fingerprints[fingerprint]}. It is kept once.",
                )
            )
            continue
        fingerprints[fingerprint] = number
        precedents.append({**entry, "fingerprint": fingerprint})

    return variants, precedents, rejected


def _compatible(variant: dict, code: str, subtype: str) -> bool:
    if variant["agreement_type"] == "all":
        return True
    return variant["agreement_type"] == code and variant["subtype"] in ("", subtype)


def _playbook(
    rows,
    variants: dict[str, dict],
    rejected: dict[str, int],
    issues: list[Issue],
    references: dict[str, dict],
):
    positions: dict[str, dict] = {}
    members: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    everywhere: list[tuple[str, str]] = []
    held: set[str] = set(rejected)
    scopes: set[tuple[str, str, str]] = set()

    for number, row in rows:
        before = len(issues)
        _identifiers(row, PLAYBOOK_SHEET, number, issues, variant_required=True)
        scope, agreement, _family = _common(row, PLAYBOOK_SHEET, number, issues)
        _required(
            row["standard"], POSITION_MAX, PLAYBOOK_SHEET, number, "Standard position", issues
        )
        for key, column in (
            ("negotiated", "Acceptable negotiated position"),
            ("fallback", "Fallback position"),
            ("red_line", "Red line"),
        ):
            _optional(row[key], POSITION_MAX, PLAYBOOK_SHEET, number, column, issues)

        code = row["variant_id"]
        variant = variants.get(code)
        precedent = references.get(code) if variant is None else None
        if code in rejected:
            issues.append(
                Issue(
                    PLAYBOOK_SHEET,
                    number,
                    "Clause version ID",
                    "error",
                    f"{code} has problems on {LIBRARY_SHEET} row {rejected[code]}. Fix that row "
                    "first.",
                )
            )
        elif code and mapping.VARIANT_ID.fullmatch(code) and variant is None and precedent is None:
            issues.append(
                Issue(
                    PLAYBOOK_SHEET,
                    number,
                    "Clause version ID",
                    "error",
                    f"{code} is not in the Clause Library sheet.",
                )
            )
        if precedent is not None:
            variant = precedent
        if variant is not None and scope and agreement:
            if variant["clause_id"] != row["clause_id"]:
                issues.append(
                    Issue(
                        PLAYBOOK_SHEET,
                        number,
                        "Clause ID",
                        "error",
                        f"{code} belongs to {variant['clause_id']} in the library, not "
                        f"{row['clause_id']}.",
                    )
                )
            if not (variant["scope"] == scope or variant["scope"] == "BOTH"):
                issues.append(
                    Issue(
                        PLAYBOOK_SHEET,
                        number,
                        "Entity",
                        "error",
                        f"{code} is library wording for "
                        f"{mapping.entity_label(variant['scope'])}, so it cannot be "
                        f"{row['entity']}'s position.",
                    )
                )
            if not _compatible(variant, *agreement):
                library_type = mapping.agreement_type_label(
                    variant["agreement_type"], variant["subtype"]
                )
                issues.append(
                    Issue(
                        PLAYBOOK_SHEET,
                        number,
                        "Agreement type",
                        "error",
                        f"{code} is library wording for {library_type}, not {row['type']}.",
                    )
                )
            if _normal(variant["title"]) != _normal(row["title"]):
                issues.append(
                    Issue(
                        PLAYBOOK_SHEET,
                        number,
                        "Clause title",
                        "warning",
                        f'The library calls {code} "{variant["title"]}". '
                        "The library title is used.",
                    )
                )

        stated = {key: row[key] for key in ("standard", "negotiated", "fallback", "red_line")}
        if code in positions:
            earlier = positions[code]
            if any(_normal(earlier[key]) != _normal(stated[key]) for key in stated):
                issues.append(
                    Issue(
                        PLAYBOOK_SHEET,
                        number,
                        None,
                        "error",
                        f"{code} has different positions on row {earlier['row']}. A clause "
                        "version holds one set of positions; reconcile the two rows.",
                    )
                )

        if any(issue.level == "error" for issue in issues[before:]):
            if code and precedent is None:
                held.add(code)
            continue

        if precedent is not None:
            if agreement[0] != "all":
                for entity in ("DSN", "EAI") if scope == "BOTH" else (scope,):
                    scopes.add((entity, agreement[0], agreement[1]))
            positions.setdefault(code, {**stated, "row": number})
            precedent.update(
                standard_position=row["standard"] or None,
                fallbacks=_fallbacks(stated),
                unacceptable_position=row["red_line"] or None,
                playbook_row=precedent.get("playbook_row") or number,
            )
            issues.append(
                Issue(
                    PLAYBOOK_SHEET,
                    number,
                    "Clause version ID",
                    "warning",
                    f"{code} is {precedent['kind']} wording. Its positions are kept with it, "
                    "outside every playbook, until the wording is approved.",
                )
            )
            continue

        if not (row["negotiated"] or row["fallback"] or row["red_line"]):
            issues.append(
                Issue(
                    PLAYBOOK_SHEET,
                    number,
                    None,
                    "warning",
                    "No negotiated position, fallback or red line. A departure from the "
                    "standard position needs Legal, or the legal lead and the executive "
                    "sponsor when it is critical.",
                )
            )

        positions.setdefault(code, {**stated, "row": number})
        if agreement[0] == "all":
            everywhere.append((scope, code))
            continue
        for entity in ("DSN", "EAI") if scope == "BOTH" else (scope,):
            key = (entity, agreement[0], agreement[1])
            if code not in members[key]:
                members[key].append(code)

    for scope, code in everywhere:
        for key, codes in members.items():
            if mapping.covers(scope, key[0]) and code not in codes:
                codes.append(code)

    for code, variant in variants.items():
        if code not in positions:
            issues.append(
                Issue(
                    LIBRARY_SHEET,
                    variant["row"],
                    "Clause version ID",
                    "warning",
                    f"{code} is approved template wording that no playbook row uses. It imports "
                    "with no standard position, fallback or red line.",
                )
            )

    for key in scopes:
        members.setdefault(key, [])
    return positions, members, held


def _fallbacks(position: dict | None) -> list[dict]:
    if not position:
        return []
    out = []
    if position["negotiated"]:
        out.append(
            {
                "rank": 1,
                "text": position["negotiated"],
                "required_authority": mapping.NEGOTIATED_AUTHORITY,
                "conditions": None,
            }
        )
    if position["fallback"]:
        out.append(
            {
                "rank": len(out) + 1,
                "text": position["fallback"],
                "required_authority": mapping.FALLBACK_AUTHORITY,
                "conditions": None,
            }
        )
    return out


def check(data: bytes) -> Checked:
    """Read both sheets and check every row. Raises NotAWorkbook."""
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError) as exc:
        raise NotAWorkbook(
            "This is not an Excel workbook (.xlsx) that can be read. Save it from Excel as "
            "an .xlsx file and upload it again."
        ) from exc

    issues: list[Issue] = []
    try:
        library_rows = _rows(workbook, LIBRARY_SHEET, LIBRARY_COLUMNS, LIBRARY_KEYS, issues)
        playbook_rows = _rows(workbook, PLAYBOOK_SHEET, PLAYBOOK_COLUMNS, PLAYBOOK_KEYS, issues)
    finally:
        workbook.close()

    if not library_rows and not any(i.sheet == LIBRARY_SHEET for i in issues):
        issues.append(Issue(LIBRARY_SHEET, None, None, "error", "The sheet has no rows."))
    if not playbook_rows and not any(i.sheet == PLAYBOOK_SHEET for i in issues):
        issues.append(Issue(PLAYBOOK_SHEET, None, None, "error", "The sheet has no rows."))

    if any(issue.row is None and issue.level == "error" for issue in issues):
        return Checked(
            plan={"clauses": {}, "variants": [], "precedents": [], "playbooks": []},
            issues=issues,
        )

    variants, precedents, rejected = _library(library_rows, issues)
    references = {p["reference"]: p for p in precedents if p["reference"]}
    positions, members, held = _playbook(playbook_rows, variants, rejected, issues, references)

    clauses: dict[str, dict] = {}
    titles: dict[str, Counter] = defaultdict(Counter)
    families: dict[str, Counter] = defaultdict(Counter)
    for entry in [*variants.values(), *precedents]:
        clause = clauses.setdefault(entry["clause_id"], {"entities": set(), "types": set()})
        clause["entities"].update(["DSN", "EAI"] if entry["scope"] == "BOTH" else [entry["scope"]])
        if entry["agreement_type"] != "all":
            clause["types"].add(entry["agreement_type"])
        families[entry["clause_id"]][entry["family"]] += 1
    for entry in variants.values():
        titles[entry["clause_id"]][entry["title"]] += 1
    for entry in precedents:
        titles[entry["clause_id"]].setdefault(entry["title"], 0)

    for clause_id, clause in clauses.items():
        clause["name"] = titles[clause_id].most_common(1)[0][0]
        clause["family"] = families[clause_id].most_common(1)[0][0]
        clause["entities"] = sorted(clause["entities"])
        clause["types"] = sorted(clause["types"])

    plan_variants = []
    for code, variant in sorted(variants.items()):
        position = positions.get(code)
        plan_variants.append(
            {
                **variant,
                "standard_position": position["standard"] if position else None,
                "fallbacks": _fallbacks(position),
                "unacceptable_position": (position["red_line"] or None) if position else None,
                "playbook_row": position["row"] if position else None,
            }
        )

    playbooks = []
    for (entity, code, subtype), codes in sorted(members.items()):
        playbooks.append(
            {
                "entity": entity,
                "agreement_type": code,
                "subtype": subtype,
                "name": f"{'DSN' if entity == 'DSN' else 'EqualyzAI'}, "
                f"{mapping.type_label(code, subtype)}",
                "required_clauses": [
                    {
                        "category": variants[c]["clause_id"],
                        "variant": c,
                        "name": variants[c]["title"],
                        "family": variants[c]["family"],
                        "absent_severity": mapping.ABSENT_SEVERITY[variants[c]["family"]],
                    }
                    for c in codes
                ],
            }
        )

    issues.sort(key=lambda i: (i.sheet != PLAYBOOK_SHEET, i.row or 0, i.level != "error"))
    return Checked(
        plan={
            "clauses": clauses,
            "variants": plan_variants,
            "precedents": precedents,
            "playbooks": playbooks,
            "held": sorted(held),
        },
        issues=issues,
    )


def structural(issues: list[dict]) -> bool:
    """A problem with the workbook itself rather than one of its rows."""
    return any(issue["level"] == "error" and issue["row"] is None for issue in issues)


def excluded_rows(issues: list[dict]) -> list[tuple[str, int]]:
    return sorted(
        {(i["sheet"], i["row"]) for i in issues if i["level"] == "error" and i["row"] is not None}
    )


def playbook_key(planned: dict) -> str:
    return f"{planned['entity']}|{planned['agreement_type']}|{planned['subtype']}"


def only_playbook(plan: dict, key: str) -> dict | None:
    """The part of the plan one playbook needs, for a pilot load.

    Its clause versions, the clauses they belong to, and the precedent for its
    entity and agreement type, so review behaves as it will with everything
    loaded.
    """
    chosen = next((p for p in plan["playbooks"] if playbook_key(p) == key), None)
    if chosen is None:
        return None
    codes = {r["variant"] for r in chosen["required_clauses"]}
    variants = [v for v in plan["variants"] if v["code"] in codes]
    precedents = [
        p
        for p in plan["precedents"]
        if p["agreement_type"] in (chosen["agreement_type"], "all")
        and mapping.covers(p["scope"], chosen["entity"])
    ]
    clause_ids = {v["clause_id"] for v in variants} | {p["clause_id"] for p in precedents}
    return {
        "clauses": {k: v for k, v in plan["clauses"].items() if k in clause_ids},
        "variants": variants,
        "precedents": precedents,
        "playbooks": [chosen],
        "held": plan.get("held", []),
    }


def next_number(versions, current: ClauseVersion | None) -> tuple[int, int]:
    """The next free minor number on the current major.

    A withdrawn draft keeps its reference, so the number after the current
    version may already be taken.
    """
    if current is None:
        used = [v.minor for v in versions if v.major == 1]
        return 1, (max(used) + 1) if used else 0
    used = [v.minor for v in versions if v.major == current.major]
    return current.major, max(used) + 1


def _latest(variant: ClauseVariant) -> ClauseVersion | None:
    live = [
        v
        for v in variant.versions
        if v.status in (VersionStatus.DRAFT.value, VersionStatus.APPROVED.value)
    ]
    drafts = [v for v in live if v.status == VersionStatus.DRAFT.value]
    if drafts:
        return drafts[0]
    return max(live, key=lambda v: (v.major, v.minor), default=None)


def _same_version(version: ClauseVersion, planned: dict) -> bool:
    return (
        _normal(version.house_position) == _normal(planned["text"])
        and _normal(version.standard_position) == _normal(planned["standard_position"])
        and _normal(version.unacceptable_position) == _normal(planned["unacceptable_position"])
        and [
            (f.get("rank"), _normal(f.get("text")), f.get("required_authority"))
            for f in version.fallbacks or []
        ]
        == [(f["rank"], _normal(f["text"]), f["required_authority"]) for f in planned["fallbacks"]]
    )


def _same_variant(variant: ClauseVariant, planned: dict) -> bool:
    return (
        variant.title == planned["title"]
        and variant.entity_scope == planned["scope"]
        and variant.agreement_type == planned["agreement_type"]
        and variant.subtype == planned["subtype"]
        and variant.transaction_role == planned["role"]
        and (variant.source_url or None) == planned["source_url"]
    )


def compare(db: Session, plan: dict) -> tuple[dict, list[Issue]]:
    """What applying the plan would change in the library as it is now."""
    issues: list[Issue] = []
    counts: Counter = Counter()
    outcomes: dict[str, str] = {}

    existing = {
        v.code: v
        for v in db.execute(
            select(ClauseVariant).where(
                ClauseVariant.code.in_([p["code"] for p in plan["variants"]])
            )
        ).scalars()
    }
    clause_ids = set(
        db.execute(
            select(Clause.category).where(Clause.category.in_(list(plan["clauses"])))
        ).scalars()
    )
    counts["clauses_new"] = len(set(plan["clauses"]) - clause_ids)

    for planned in plan["variants"]:
        variant = existing.get(planned["code"])
        if variant is None:
            outcome = "new"
        else:
            if variant.clause.category != planned["clause_id"]:
                issues.append(
                    Issue(
                        LIBRARY_SHEET,
                        planned["row"],
                        "Clause ID",
                        "error",
                        f"{planned['code']} is already in the library under "
                        f"{variant.clause.category}, not {planned['clause_id']}.",
                    )
                )
                outcome = "blocked"
            else:
                latest = _latest(variant)
                if latest is not None and _same_version(latest, planned):
                    outcome = "unchanged" if _same_variant(variant, planned) else "relabelled"
                elif (
                    latest is not None
                    and latest.status == VersionStatus.DRAFT.value
                    and latest.library_import_id is None
                ):
                    issues.append(
                        Issue(
                            LIBRARY_SHEET,
                            planned["row"],
                            "Clause wording",
                            "error",
                            f"{latest.reference} is an open draft somebody wrote in the platform. "
                            "Publish or withdraw it before the workbook can change this clause.",
                        )
                    )
                    outcome = "blocked"
                else:
                    outcome = "changed"
        outcomes[planned["code"]] = outcome
        counts[f"variants_{outcome}"] += 1

    known = _known_precedents(db, plan)
    for planned in plan["precedents"]:
        held = known.get(planned["fingerprint"])
        if held is None:
            counts["precedents_new"] += 1
        elif _precedent_moved(held, planned):
            counts["precedents_changed"] += 1
        else:
            counts["precedents_unchanged"] += 1

    for planned in plan["playbooks"]:
        playbook = _find_playbook(db, planned)
        if playbook is None:
            counts["playbooks_new"] += 1
        elif _required_codes(playbook.required_clauses) == _required_codes(
            _merged(playbook, planned, plan)
        ):
            counts["playbooks_unchanged"] += 1
        else:
            counts["playbooks_changed"] += 1

    summary = {
        "clauses": len(plan["clauses"]),
        "variants": len(plan["variants"]),
        "precedents": len(plan["precedents"]),
        "prohibited": sum(1 for p in plan["precedents"] if p["kind"] == "prohibited"),
        "playbooks": len(plan["playbooks"]),
        "without_fallbacks": sum(1 for v in plan["variants"] if not v["fallbacks"]),
        "variants_without_source": sum(1 for v in plan["variants"] if not v["source_url"]),
        "precedents_without_source": sum(1 for p in plan["precedents"] if not p["source_url"]),
        **dict(counts),
        "outcomes": outcomes,
    }
    return summary, issues


def _known_precedents(db: Session, plan: dict) -> dict[str, ClausePrecedent]:
    return {
        p.fingerprint: p
        for p in db.execute(
            select(ClausePrecedent).where(
                ClausePrecedent.fingerprint.in_([p["fingerprint"] for p in plan["precedents"]])
            )
        ).scalars()
    }


def _precedent_fields(planned: dict) -> dict:
    """What can change on a precedent without it becoming different wording."""
    return {
        "source_url": planned["source_url"],
        "family": planned["family"],
        "standard_position": planned.get("standard_position"),
        "fallbacks": planned.get("fallbacks") or [],
        "unacceptable_position": planned.get("unacceptable_position"),
        "playbook_row": planned.get("playbook_row"),
    }


def _precedent_moved(held: ClausePrecedent, planned: dict) -> bool:
    wanted = _precedent_fields(planned)
    wanted.pop("playbook_row")
    return any((getattr(held, key) or None) != (value or None) for key, value in wanted.items())


def _required_codes(required: list[dict]) -> list[tuple]:
    return sorted((r.get("variant") or "", r.get("absent_severity") or "") for r in required or [])


def _merged(playbook: Playbook, planned: dict, plan: dict) -> list[dict]:
    """The planned clause list, keeping what a row left out by an error held.

    A row with an error is left out of the load, not out of the library: a
    playbook that already requires that clause goes on requiring it.
    """
    held = set(plan.get("held", []))
    planned_codes = {r["variant"] for r in planned["required_clauses"]}
    kept = [
        r
        for r in playbook.required_clauses or []
        if r.get("variant") in held and r.get("variant") not in planned_codes
    ]
    return [*planned["required_clauses"], *kept]


def _find_playbook(db: Session, planned: dict) -> Playbook | None:
    return db.execute(
        select(Playbook).where(
            Playbook.agreement_type == planned["agreement_type"],
            Playbook.entity == planned["entity"],
            Playbook.subtype == planned["subtype"],
        )
    ).scalar_one_or_none()


def apply(
    db: Session, record: LibraryImport, plan: dict, outcomes: dict, user_id: uuid.UUID
) -> dict:
    """Write the plan as drafts.

    Rows with errors are not in the plan. A clause version the library already
    holds a draft of, written in the platform, is left alone.
    """
    provenance_base = f"Imported from {record.filename}, source hash {record.source_hash[:12]}"
    written: Counter = Counter()

    clauses: dict[str, Clause] = {
        c.category: c
        for c in db.execute(
            select(Clause).where(Clause.category.in_(list(plan["clauses"])))
        ).scalars()
    }
    for clause_id, planned in plan["clauses"].items():
        clause = clauses.get(clause_id)
        if clause is None:
            clause = Clause(
                category=clause_id,
                name=planned["name"][:255],
                family=planned["family"],
                owner_id=user_id,
                entity_applicability=planned["entities"],
                required_for_types=planned["types"],
            )
            db.add(clause)
            clauses[clause_id] = clause
            written["clauses_created"] += 1
        else:
            clause.family = clause.family or planned["family"]
            clause.entity_applicability = sorted(
                set(clause.entity_applicability or []) | set(planned["entities"])
            )
            clause.required_for_types = sorted(
                set(clause.required_for_types or []) | set(planned["types"])
            )
    db.flush()

    variants = {
        v.code: v
        for v in db.execute(
            select(ClauseVariant).where(
                ClauseVariant.code.in_([p["code"] for p in plan["variants"]])
            )
        ).scalars()
    }
    for planned in plan["variants"]:
        outcome = outcomes.get(planned["code"])
        if outcome == "blocked":
            written["variants_left_alone"] += 1
            continue
        variant = variants.get(planned["code"])
        if variant is None:
            variant = ClauseVariant(
                clause_id=clauses[planned["clause_id"]].id, code=planned["code"]
            )
            db.add(variant)
        variant.title = planned["title"]
        variant.entity_scope = planned["scope"]
        variant.agreement_type = planned["agreement_type"]
        variant.subtype = planned["subtype"]
        variant.transaction_role = planned["role"]
        variant.source_url = planned["source_url"]
        db.flush()

        if outcome in ("unchanged", "relabelled"):
            written[f"variants_{outcome}"] += 1
            continue

        provenance = (
            f"{provenance_base}, {LIBRARY_SHEET} row {planned['row']}"
            + (
                f", {PLAYBOOK_SHEET} row {planned['playbook_row']}"
                if planned["playbook_row"]
                else ""
            )
            + "."
        )
        fields = {
            "house_position": planned["text"],
            "standard_position": planned["standard_position"],
            "fallbacks": planned["fallbacks"],
            "unacceptable_position": planned["unacceptable_position"],
            "provenance": provenance,
            "library_import_id": record.id,
        }

        latest = _latest(variant) if outcome == "changed" else None
        if latest is not None and latest.status == VersionStatus.DRAFT.value:
            for key, value in fields.items():
                setattr(latest, key, value)
            written["drafts_updated"] += 1
            continue

        major, minor = next_number(variant.versions, latest)
        db.add(
            ClauseVersion(
                clause_id=variant.clause_id,
                variant_id=variant.id,
                reference=f"{variant.code}-v{major}.{minor}",
                major=major,
                minor=minor,
                status=VersionStatus.DRAFT.value,
                supersedes_id=latest.id if latest else None,
                **fields,
            )
        )
        written["drafts_created"] += 1
    db.flush()

    known = _known_precedents(db, plan)
    added: list[ClausePrecedent] = []
    for planned in plan["precedents"]:
        held = known.get(planned["fingerprint"])
        if held is not None:
            if _precedent_moved(held, planned):
                for key, value in _precedent_fields(planned).items():
                    setattr(held, key, value)
                added.append(held)
                written["precedents_updated"] += 1
            continue
        precedent = ClausePrecedent(
            clause_id=clauses[planned["clause_id"]].id,
            fingerprint=planned["fingerprint"],
            reference=planned["reference"],
            kind=planned["kind"],
            entity_scope=planned["scope"],
            agreement_type=planned["agreement_type"],
            subtype=planned["subtype"],
            transaction_role=planned["role"],
            title=planned["title"],
            text=planned["text"],
            library_import_id=record.id,
            source_row=planned["row"],
            **_precedent_fields(planned),
        )
        db.add(precedent)
        added.append(precedent)
        written["precedents_created"] += 1
    db.flush()

    for planned in plan["playbooks"]:
        playbook = _find_playbook(db, planned)
        if playbook is None:
            db.add(
                Playbook(
                    agreement_type=planned["agreement_type"],
                    entity=planned["entity"],
                    subtype=planned["subtype"],
                    name=planned["name"],
                    version=1,
                    required_clauses=planned["required_clauses"],
                    active=False,
                    library_import_id=record.id,
                )
            )
            written["playbooks_created"] += 1
        elif _required_codes(playbook.required_clauses) != _required_codes(
            _merged(playbook, planned, plan)
        ):
            playbook.required_clauses = _merged(playbook, planned, plan)
            playbook.version += 1
            playbook.library_import_id = record.id
            written["playbooks_changed"] += 1
    db.flush()

    record.status = "applied"
    record.applied_by_id = user_id
    record.applied_at = datetime.now(UTC)
    return {"written": dict(written), "precedents": added}


def _set(sheet, row: int, column: int, value) -> None:
    cell = sheet.cell(row=row, column=column, value=value)
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        cell.data_type = "s"
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def _sheet(workbook, title: str, heading: str, columns: list[str]):
    sheet = workbook.create_sheet(title)
    sheet.cell(row=2, column=1, value=heading).font = Font(bold=True, size=14)
    for index, column in enumerate(columns, start=1):
        sheet.cell(row=5, column=index, value=column).font = Font(bold=True)
        sheet.column_dimensions[sheet.cell(row=5, column=index).column_letter].width = 28
    return sheet


def _type_and_subtype(code: str, subtype: str) -> list[str]:
    """Agreement type and Sub-type as the two columns of the current layout."""
    if code == "all":
        return [mapping.agreement_type_label("all", ""), "All sub-types"]
    return [mapping.agreement_type_label(code, ""), subtype]


def export(db: Session) -> bytes:
    """The library as the workbook, so the legal team edits from what is live.

    One trailing column, Platform status, says which version each row is.
    The importer reads only the columns it knows, so the file goes back in
    unchanged.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    playbook_sheet = _sheet(
        workbook,
        PLAYBOOK_SHEET,
        "DSN and EqualyzAI Legal Playbook",
        [*_with_subtype(PLAYBOOK_COLUMNS, PLAYBOOK_KEYS)[0], "Platform status"],
    )
    library_sheet = _sheet(
        workbook,
        LIBRARY_SHEET,
        "DSN and EqualyzAI Clause Library",
        [*_with_subtype(LIBRARY_COLUMNS, LIBRARY_KEYS)[0], "Platform status"],
    )

    variants = {
        v.code: v for v in db.execute(select(ClauseVariant).order_by(ClauseVariant.code)).scalars()
    }

    row = 6
    written_everywhere: set[str] = set()
    for playbook in db.execute(
        select(Playbook)
        .where(Playbook.entity.is_not(None))
        .order_by(Playbook.entity, Playbook.agreement_type, Playbook.subtype)
    ).scalars():
        for required in playbook.required_clauses or []:
            variant = variants.get(required.get("variant"))
            latest = _latest(variant) if variant else None
            if variant is None or latest is None:
                continue
            fallbacks = {f.get("required_authority"): f.get("text") for f in latest.fallbacks or []}
            if variant.agreement_type == "all":
                if variant.code in written_everywhere:
                    continue
                written_everywhere.add(variant.code)
                entity, agreement = variant.entity_scope, ("all", "")
            else:
                entity, agreement = playbook.entity, (playbook.agreement_type, playbook.subtype)
            values = [
                mapping.entity_label(entity),
                *_type_and_subtype(*agreement),
                variant.transaction_role,
                variant.clause.family or required.get("family") or "",
                variant.title,
                latest.standard_position or "",
                fallbacks.get(mapping.NEGOTIATED_AUTHORITY, ""),
                fallbacks.get(mapping.FALLBACK_AUTHORITY, ""),
                latest.unacceptable_position or "",
                variant.clause.category,
                variant.code,
                f"{latest.reference}, {latest.status}",
            ]
            for column, value in enumerate(values, start=1):
                _set(playbook_sheet, row, column, value)
            row += 1

    for precedent in db.execute(
        select(ClausePrecedent)
        .where(ClausePrecedent.standard_position.is_not(None))
        .order_by(ClausePrecedent.playbook_row, ClausePrecedent.source_row)
    ).scalars():
        fallbacks = {f.get("required_authority"): f.get("text") for f in precedent.fallbacks or []}
        values = [
            mapping.entity_label(precedent.entity_scope),
            *_type_and_subtype(precedent.agreement_type, precedent.subtype),
            precedent.transaction_role,
            precedent.family,
            precedent.title,
            precedent.standard_position,
            fallbacks.get(mapping.NEGOTIATED_AUTHORITY, ""),
            fallbacks.get(mapping.FALLBACK_AUTHORITY, ""),
            precedent.unacceptable_position or "",
            precedent.clause.category,
            precedent.reference or "",
            f"{mapping.wording_status_label(precedent.kind)}, not in any playbook",
        ]
        for column, value in enumerate(values, start=1):
            _set(playbook_sheet, row, column, value)
        row += 1

    row = 6
    for variant in variants.values():
        latest = _latest(variant)
        if latest is None:
            continue
        values = [
            variant.clause.category,
            variant.code,
            mapping.entity_label(variant.entity_scope),
            *_type_and_subtype(variant.agreement_type, variant.subtype),
            variant.transaction_role,
            variant.clause.family or "",
            variant.title,
            latest.house_position,
            mapping.wording_status_label("approved"),
            variant.source_url or "",
            f"{latest.reference}, {latest.status}",
        ]
        for column, value in enumerate(values, start=1):
            _set(library_sheet, row, column, value)
        row += 1

    for precedent in db.execute(
        select(ClausePrecedent).order_by(ClausePrecedent.source_row, ClausePrecedent.created_at)
    ).scalars():
        values = [
            precedent.clause.category,
            precedent.reference or "",
            mapping.entity_label(precedent.entity_scope),
            *_type_and_subtype(precedent.agreement_type, precedent.subtype),
            precedent.transaction_role,
            precedent.family,
            precedent.title,
            precedent.text,
            mapping.wording_status_label(precedent.kind),
            precedent.source_url or "",
            "precedent",
        ]
        for column, value in enumerate(values, start=1):
            _set(library_sheet, row, column, value)
        row += 1

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
