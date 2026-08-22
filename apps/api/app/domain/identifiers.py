"""Identifier scheme, PRD section 8.3.

Identifiers are system-generated, permanent and never reused. A matter
identifier must not depend on a counterparty name, because names and spellings
change while identity should not.
"""

import re

from app.domain.enums import Entity

DEFAULT_PRACTICE_CODES: dict[str, str] = {
    "COM": "Commercial",
    "EMP": "Employment",
    "IPR": "Intellectual property",
    "DPR": "Data protection",
    "CRP": "Corporate",
}

PATTERNS: dict[str, re.Pattern[str]] = {
    "counterparty": re.compile(r"^CPT-\d{4,}$"),
    "matter": re.compile(r"^(DSN|EAI)-[A-Z]{3}-\d{4}-\d{4}$"),
    "contract": re.compile(r"^(DSN|EAI)-CON-\d{4}-\d{4}$"),
    "request": re.compile(r"^REQ-\d{4}-\d{5}$"),
    "template": re.compile(r"^TPL-[A-Z0-9]+-v\d+\.\d+$"),
    "clause": re.compile(r"^CLS-[A-Z0-9]+-v\d+\.\d+$"),
    "obligation": re.compile(r"^OBL-\d{4}-\d{2}$"),
    "assessment": re.compile(r"^ASM-\d{4}-\d{4}$"),
}

def counterparty_id(sequence: int) -> str:
    return f"CPT-{sequence:04d}"

def matter_number(entity: Entity | str, practice: str, year: int, sequence: int) -> str:
    practice = practice.upper()
    if not re.fullmatch(r"[A-Z]{3}", practice):
        raise ValueError(f"Practice code must be three letters, got {practice!r}")
    return f"{Entity(entity).value}-{practice}-{year}-{sequence:04d}"

def contract_id(entity: Entity | str, year: int, sequence: int) -> str:
    return f"{Entity(entity).value}-CON-{year}-{sequence:04d}"

def request_reference(year: int, sequence: int) -> str:
    return f"REQ-{year}-{sequence:05d}"

def template_version_id(agreement_type: str, major: int, minor: int) -> str:
    return f"TPL-{agreement_type.upper()}-v{major}.{minor}"

def clause_version_id(category: str, major: int, minor: int) -> str:
    return f"CLS-{category.upper()}-v{major}.{minor}"

def obligation_id(contract_sequence: int, sequence: int) -> str:
    return f"OBL-{contract_sequence:04d}-{sequence:02d}"

def assessment_id(year: int, sequence: int) -> str:
    return f"ASM-{year}-{sequence:04d}"

def validate(kind: str, value: str) -> bool:
    pattern = PATTERNS.get(kind)
    if pattern is None:
        raise KeyError(f"Unknown identifier kind {kind!r}")
    return bool(pattern.fullmatch(value))
