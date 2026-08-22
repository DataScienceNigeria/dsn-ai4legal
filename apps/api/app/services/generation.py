"""Document generation, M04.

Generation is deterministic. Given the same structured facts and the same
template version, the output is byte-identical. Nothing generative happens
here, which is what makes tier 1 auto-issue defensible.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.errors import Refused
from app.services.checks import CheckResult, run_all
from app.services.checks import Clause as CheckClause
from app.services.hashing import content_hash

VARIABLE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")

FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

@dataclass
class GeneratedBlock:
    """One assembled unit, carrying where its text came from."""

    key: str
    number: str
    heading: str
    text: str
    provenance: str
    source_reference: str | None = None

    @property
    def novel(self) -> bool:
        return self.provenance == "novel"

@dataclass
class GenerationResult:
    blocks: list[GeneratedBlock]
    values: dict[str, Any]
    checks: list[CheckResult]
    content_hash: str
    template_reference: str
    clause_references: list[str]
    novel_count: int = 0
    open_items: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        for block in self.blocks:
            heading = f"{block.number} {block.heading}".strip()
            lines.append(heading)
            lines.append(block.text)
            lines.append("")
        return "\n".join(lines).strip() + "\n"

def _coerce(value: Any, declared_type: str) -> Any:
    if value is None:
        return None
    if declared_type == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if declared_type == "number":
        return float(value)
    if declared_type == "boolean":
        return bool(value)
    return value

def _format(value: Any, declared_type: str, fmt: str | None) -> str:
    """Rendering is fixed by declared type, so the same value always reads the
    same way in every document (house style, LOP-M05-US-03)."""
    if value is None:
        return ""
    if declared_type == "date":
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
        return parsed.strftime(fmt or "%d %B %Y")
    if declared_type == "number":
        return f"{float(value):,.2f}"
    if declared_type == "currency":
        return f"{float(value):,.2f}"
    return str(value)

def validate_variables(
    declared: list[dict], supplied: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Resolve declared variables against supplied facts.

    Generation fails safely and reports the missing variable rather than
    emitting a placeholder into a document (LOP-M03-US-04).
    """
    resolved: dict[str, Any] = {}
    missing: list[str] = []

    for declaration in declared:
        name = declaration["name"]
        declared_type = declaration.get("type", "string")
        raw = supplied.get(name, declaration.get("default"))
        if raw in (None, ""):
            if declaration.get("mandatory", True):
                missing.append(
                    f"{declaration.get('label', name)} is required by this template "
                    f"and is not present on the matter record."
                )
            resolved[name] = None
            continue

        value = _coerce(raw, declared_type)
        pattern = declaration.get("pattern")
        if pattern and not re.fullmatch(pattern, str(raw)):
            missing.append(
                f"{declaration.get('label', name)} does not satisfy the validation rule "
                f"declared by the template."
            )
        resolved[name] = _format(value, declared_type, declaration.get("format"))

    return resolved, missing

def evaluate_condition(expression: str | None, facts: dict[str, Any]) -> bool:
    """Evaluate a template section condition.

    Conditions are deliberately a tiny language rather than Python, so a
    template cannot execute anything. Supported forms are ``name``,
    ``not name``, ``name == value`` and ``name != value``.
    """
    if not expression:
        return True
    expression = expression.strip()

    negate = expression.startswith("not ")
    if negate:
        expression = expression[4:].strip()

    for operator in ("==", "!="):
        if operator in expression:
            left, right = (part.strip().strip("'\"") for part in expression.split(operator, 1))
            actual = str(facts.get(left, "")).strip()
            result = actual == right if operator == "==" else actual != right
            return not result if negate else result

    value = facts.get(expression)
    truthy = bool(value) and str(value).lower() not in {"false", "no", "0", ""}
    return not truthy if negate else truthy

def generate(
    *,
    template_reference: str,
    body: list[dict],
    declared_variables: list[dict],
    facts: dict[str, Any],
    clause_texts: dict[str, dict],
    expected_parties: list[str] | None = None,
) -> GenerationResult:
    """Assemble a document from a published template version.

    ``clause_texts`` maps a clause reference to its approved record, so the
    assembled document can state where each clause came from.
    """
    values, missing = validate_variables(declared_variables, facts)
    if missing:
        raise Refused(
            "This document cannot be generated from the record as it stands.", missing
        )

    condition_facts = {**facts, **{k: v for k, v in values.items() if v not in (None, "")}}

    blocks: list[GeneratedBlock] = []
    used_clauses: list[str] = []
    counter = 0

    for section in body:
        if not evaluate_condition(section.get("condition"), condition_facts):
            continue

        repeat_over = section.get("repeat_over")
        iterations: list[dict[str, Any]] = [{}]
        if repeat_over:
            rows = facts.get(repeat_over) or []
            if not isinstance(rows, list):
                rows = []
            iterations = [dict(row) for row in rows]
            if not iterations:
                continue

        for index, row in enumerate(iterations, start=1):
            counter += 1
            scope = {**values, **row, "index": index}

            clause_reference = section.get("clause")
            if clause_reference:
                record = clause_texts.get(clause_reference)
                if record is None:
                    raise Refused(
                        "This document cannot be generated.",
                        [
                            f"Clause {clause_reference} is referenced by the template but "
                            "is not an approved, effective version."
                        ],
                    )
                raw_text = record["text"]
                provenance = record.get("provenance", "approved_clause")
                source_reference = clause_reference
                used_clauses.append(clause_reference)
            else:
                raw_text = section.get("text", "")
                provenance = "template_text"
                source_reference = template_reference

            # scope is bound as a default so the substitution cannot pick up a
            # later iteration's values. It is applied immediately here, but a
            # lambda that closes over a loop variable is a bug waiting for
            # someone to move the call.
            def substitute(text: str, scope: dict = scope) -> str:
                return VARIABLE.sub(lambda m: str(scope.get(m.group(1), "")), text)

            rendered = substitute(raw_text)
            heading = substitute(section.get("heading", ""))
            number = section.get("number") or str(counter)
            if repeat_over:
                number = f"{number}.{index}"

            blocks.append(
                GeneratedBlock(
                    key=section.get("key", f"b{counter}"),
                    number=number,
                    heading=heading,
                    text=rendered.strip(),
                    provenance=provenance,
                    source_reference=source_reference,
                )
            )

    checks = run_all(
        [CheckClause(number=b.number, heading=b.heading, text=b.text) for b in blocks],
        expected_parties,
    )

    digest = content_hash(
        template_reference,
        sorted(set(used_clauses)),
        [{"n": b.number, "h": b.heading, "t": b.text} for b in blocks],
    )

    return GenerationResult(
        blocks=blocks,
        values=values,
        checks=checks,
        content_hash=digest,
        template_reference=template_reference,
        clause_references=sorted(set(used_clauses)),
        novel_count=sum(1 for b in blocks if b.novel),
        open_items=[
            f"{c.name.replace('_', ' ')}: {item}"
            for c in checks
            if not c.passed
            for item in c.items
        ],
    )

def render_docx(result: GenerationResult, title: str) -> bytes:
    """Produce a .docx.

    The archive is written with a fixed timestamp and a fixed member order so
    that regeneration from identical inputs produces an identical file, which
    is what LOP-M04-US-03 requires.
    """
    paragraphs = [f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>{_run(title)}</w:p>']
    for block in result.blocks:
        heading = f"{block.number} {block.heading}".strip()
        paragraphs.append(
            f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>{_run(heading)}</w:p>'
        )
        for line in block.text.split("\n"):
            paragraphs.append(f"<w:p>{_run(line)}</w:p>")

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(paragraphs)}</w:body></w:document>"
    )

    members = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
            'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
        ),
        "word/document.xml": document,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, members[name])
    return buffer.getvalue()

def _run(value: str) -> str:
    escaped = (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f'<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r>'
