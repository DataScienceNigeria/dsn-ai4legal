"""How the legal team's workbook labels become the platform's vocabulary.

Every label the workbook uses is listed here, and a label that is not listed
is an error on its row rather than a guess. The mappings are proposals the
legal team signs off; changing one is a change to this file, reviewed like
code, so the reading of the workbook is never decided silently at import.
"""

from __future__ import annotations

import re

#: Entity column to the scope a variant or precedent applies in. The first
#: label for each scope is the one an export writes.
ENTITIES: dict[str, str] = {
    "Data Scientists Network Foundation (Data Science Nigeria)": "DSN",
    "EqualyzAI": "EAI",
    "Both entities": "BOTH",
    "Data Science Nigeria": "DSN",
    "DSN": "DSN",
    "EAI": "EAI",
}

#: The entity part of a ``CLV`` code, which must agree with the entity column.
ENTITY_CHOICES = [
    "Data Scientists Network Foundation (Data Science Nigeria)",
    "EqualyzAI",
    "Both entities",
]

CODE_ENTITIES: dict[str, str] = {"DSN": "DSN", "EQL": "EAI", "BOTH": "BOTH"}

#: The playbook's own families. Every clause category lands on one.
FAMILIES: list[str] = [
    "Scope and performance",
    "Payment",
    "Confidentiality",
    "Data protection",
    "Intellectual property",
    "Warranties",
    "Liability and insurance",
    "Compliance and audit",
    "AI and technology",
    "Term and exit",
    "Disputes and standard terms",
]

#: Clause category label to its family. Matched without regard to case.
CATEGORIES: dict[str, str] = {
    **{family: family for family in FAMILIES},
    "Standard terms": "Disputes and standard terms",
    "Commercial and payment": "Payment",
    "Termination": "Term and exit",
    "Information security": "Data protection",
    "Dispute resolution": "Disputes and standard terms",
    "Personnel and subcontracting": "Scope and performance",
    "Compliance": "Compliance and audit",
    "Limitation of liability": "Liability and insurance",
    "Force majeure": "Disputes and standard terms",
    "Assignment": "Disputes and standard terms",
    "Indemnity": "Liability and insurance",
    "Governing law": "Disputes and standard terms",
    "Partnerships and grants": "Scope and performance",
    "Insurance": "Liability and insurance",
    "Restrictive covenants": "Term and exit",
}

#: The clause-level labels the revised workbook of 6 November 2026 uses, each
#: proposed onto a family for the legal team to confirm.
REVISED_CATEGORIES: dict[str, str] = {
    "Acceptance": "Scope and performance",
    "Research scope": "Scope and performance",
    "Permitted use": "Scope and performance",
    "Quality and acceptance": "Scope and performance",
    "Contribution": "Scope and performance",
    "Scope and delivery": "Scope and performance",
    "Technical standards": "Scope and performance",
    "Service levels": "Scope and performance",
    "Personnel and third parties": "Scope and performance",
    "Programme scope": "Scope and performance",
    "Participation obligations": "Scope and performance",
    "Facilities and acceptable use": "Scope and performance",
    "Introductions and relationships": "Scope and performance",
    "Change control": "Scope and performance",
    "Scope and governance": "Scope and performance",
    "Roles and responsibilities": "Scope and performance",
    "Business continuity": "Scope and performance",
    "Appointment": "Scope and performance",
    "Orders and supply": "Scope and performance",
    "Delivery and returns": "Scope and performance",
    "Personnel": "Scope and performance",
    "Programme delivery": "Scope and performance",
    "Scheduling": "Scope and performance",
    "Scope and brief": "Scope and performance",
    "Scope and language": "Scope and performance",
    "Quality and accuracy": "Scope and performance",
    "Documentation": "Scope and performance",
    "Dataset scope": "Scope and performance",
    "Prohibited use": "Scope and performance",
    "Purpose and status": "Scope and performance",
    "Roles and governance": "Scope and performance",
    "Projects and changes": "Scope and performance",
    "Purpose": "Scope and performance",
    "Participation": "Scope and performance",
    "Scope and authority": "Scope and performance",
    "Deliverables": "Scope and performance",
    "Product scope": "Scope and performance",
    "Roles": "Scope and performance",
    "Quality and support": "Scope and performance",
    "Customer contracting": "Scope and performance",
    "Leads and opportunities": "Scope and performance",
    "Scope and plan": "Scope and performance",
    "Editorial standards": "Scope and performance",
    "Measurement": "Scope and performance",
    "Role": "Scope and performance",
    "Fees and payment": "Payment",
    "Funding and investment": "Payment",
    "Costs and expenses": "Payment",
    "Pricing and payment": "Payment",
    "Sponsor benefits": "Payment",
    "Compensation": "Payment",
    "Funding and resources": "Payment",
    "Support and expenses": "Payment",
    "Purpose and budget": "Payment",
    "Disbursement": "Payment",
    "Unused funds": "Payment",
    "Revenue share": "Payment",
    "Commercial terms": "Payment",
    "Use restrictions": "Confidentiality",
    "Publicity": "Confidentiality",
    "Remedies": "Disputes and standard terms",
    "Fees and exit": "Payment",
    "Expenses and support": "Payment",
    "Data and confidentiality": "Confidentiality",
    "Confidentiality and publicity": "Confidentiality",
    "Confidentiality and access": "Confidentiality",
    "Confidential information": "Confidentiality",
    "Exclusions": "Confidentiality",
    "Recipients": "Confidentiality",
    "Required disclosure": "Confidentiality",
    "Ownership and remedies": "Confidentiality",
    "Confidentiality and data": "Confidentiality",
    "Data governance": "Data protection",
    "Processing details": "Data protection",
    "Security": "Data protection",
    "Processing instructions": "Data protection",
    "Data breach": "Data protection",
    "Data subject rights": "Data protection",
    "Subprocessors": "Data protection",
    "Sub-processors": "Data protection",
    "International transfers": "Data protection",
    "Transfers": "Data protection",
    "Privacy and publicity": "Data protection",
    "Publicity and data": "Data protection",
    "Methods and security": "Data protection",
    "Consent and privacy": "Data protection",
    "Security and retention": "Data protection",
    "Security and incidents": "Data protection",
    "Privacy": "Data protection",
    "Data and security": "Data protection",
    "Instructions": "Data protection",
    "Rights and assessments": "Data protection",
    "Breach": "Data protection",
    "Accounts and security": "Data protection",
    "Publication and attribution": "Intellectual property",
    "Rights clearances": "Intellectual property",
    "Branding and communications": "Intellectual property",
    "Sponsor content": "Intellectual property",
    "Branding": "Intellectual property",
    "Performance and intellectual property": "Intellectual property",
    "Originality and tools": "Intellectual property",
    "Ownership and rights": "Intellectual property",
    "Third-party materials": "Intellectual property",
    "Media": "Intellectual property",
    "Brand and claims": "Intellectual property",
    "User content": "Intellectual property",
    "Rights and releases": "Intellectual property",
    "Warranties and indemnity": "Warranties",
    "Marketing and representations": "Warranties",
    "Warranties and permissions": "Warranties",
    "Research and accuracy": "Warranties",
    "Liability and indemnity": "Liability and insurance",
    "Risk": "Liability and insurance",
    "Ethics and consent": "Compliance and audit",
    "Eligibility and conduct": "Compliance and audit",
    "Training and conduct": "Compliance and audit",
    "Incident and complaints": "Compliance and audit",
    "Status and taxes": "Compliance and audit",
    "Fair treatment and grievance": "Compliance and audit",
    "Facilities and safety": "Compliance and audit",
    "Reporting and audit": "Compliance and audit",
    "Compliance and permits": "Compliance and audit",
    "Safeguarding and facilities": "Compliance and audit",
    "Consents and approvals": "Compliance and audit",
    "Supervision and conduct": "Compliance and audit",
    "Compliance and reputation": "Compliance and audit",
    "Transparency and records": "Compliance and audit",
    "Health and safety": "Compliance and audit",
    "Emergency assistance": "Compliance and audit",
    "Integrity": "Compliance and audit",
    "Records and audit": "Compliance and audit",
    "Procurement and conflicts": "Compliance and audit",
    "Audit and liability": "Compliance and audit",
    "Conduct and conflicts": "Compliance and audit",
    "AI and secondary use": "AI and technology",
    "AI and synthetic voice": "AI and technology",
    "Term and termination": "Term and exit",
    "Exit": "Term and exit",
    "Return and deletion": "Term and exit",
    "Change and cancellation": "Term and exit",
    "Termination and handover": "Term and exit",
    "Termination and rights": "Term and exit",
    "Handover": "Term and exit",
    "Removal": "Term and exit",
    "Suspension and exit": "Term and exit",
    "Termination and customers": "Term and exit",
    "Leaving": "Term and exit",
    "Status": "Disputes and standard terms",
    "Contract structure": "Disputes and standard terms",
}

#: Agreement type label to the platform's code and a sub-type. An empty
#: sub-type means the wording applies across the whole type. The first label
#: for each pair is the one an export writes.
AGREEMENT_TYPES: dict[str, tuple[str, str]] = {
    "All agreements": ("all", ""),
    "Service Agreement": ("service_agreement", ""),
    "Service Agreement - General": ("service_agreement", "General"),
    "Service Agreement - AI Compute Access": ("service_agreement", "AI Compute Access"),
    "Consultancy Agreement": ("consultancy_agreement", ""),
    "Consultancy Agreement - General Individual": ("consultancy_agreement", "General Individual"),
    "Consultancy Agreement - Technical Individual": (
        "consultancy_agreement",
        "Technical Individual",
    ),
    "Consultancy Agreement - Pre-Project": ("consultancy_agreement", "Pre-Project"),
    "Consultancy Agreement - Frontend Engineer": ("consultancy_agreement", "Frontend Engineer"),
    "Consultancy Agreement - Technical Lead": ("consultancy_agreement", "Technical Lead"),
    "Partnership Agreement": ("partnership_agreement", ""),
    "Partnership Agreement - Community Hub": ("partnership_agreement", "Community Hub"),
    "Partnership Agreement - Product": ("partnership_agreement", "Product"),
    "Memorandum of Understanding": ("memorandum_of_understanding", ""),
    "Memorandum of Understanding - General": ("memorandum_of_understanding", "General"),
    "Memorandum of Understanding - Training Host": (
        "memorandum_of_understanding",
        "Training Host",
    ),
    "Mutual NDA": ("nda_mutual", ""),
    "One-sided NDA": ("nda_one_sided", ""),
    "Grant Agreement": ("grant_agreement", ""),
    "Employment and Workforce": ("other", "Employment and Workforce"),
    "Other": ("other", ""),
}

#: What it costs the platform when a draft leaves out a clause of the family.
ABSENT_SEVERITY: dict[str, str] = {
    "Confidentiality": "critical",
    "Data protection": "critical",
    "Liability and insurance": "critical",
    "Intellectual property": "critical",
    "Scope and performance": "material",
    "Payment": "material",
    "Warranties": "material",
    "Compliance and audit": "material",
    "AI and technology": "material",
    "Term and exit": "material",
    "Disputes and standard terms": "minor",
}

#: Who may concede each playbook position, in the library's authority codes.
NEGOTIATED_AUTHORITY = "fallback_1"
FALLBACK_AUTHORITY = "fallback_2"

#: Months from publication to the review date, when the version names none.
REVIEW_MONTHS = 12

WORDING_STATUSES: dict[str, str] = {
    "Approved template wording": "approved",
    "Reference wording": "reference",
    "Prohibited wording": "prohibited",
}

CLAUSE_ID = re.compile(r"CLS-[A-Z]{3}-\d{3}")
VARIANT_ID = re.compile(r"CLV-(DSN|EQL|BOTH)-[A-Z]{2,6}-\d{3}")


def _key(label: str | None) -> str:
    return " ".join((label or "").split()).lower()


def _lookup(table: dict) -> dict:
    return {_key(label): value for label, value in table.items()}


_ENTITIES = _lookup(ENTITIES)
_CATEGORIES = _lookup({**REVISED_CATEGORIES, **CATEGORIES})
def _platform_types() -> dict[str, tuple[str, str]]:
    from app.domain.agreements import AGREEMENT_TYPES as PLATFORM

    return {label: (code, "") for code, label in PLATFORM.items()}


_AGREEMENT_TYPES = {**_lookup(_platform_types()), **_lookup(AGREEMENT_TYPES)}
_WORDING_STATUSES = _lookup(WORDING_STATUSES)


def _first_label(table: dict, value) -> str:
    return next(label for label, mapped in table.items() if mapped == value)


def entity(label: str | None) -> str | None:
    return _ENTITIES.get(_key(label))


def family(label: str | None) -> str | None:
    return _CATEGORIES.get(_key(label))


#: A remedies clause that allocates liability or an indemnity stays with
#: Liability and insurance, whatever its label, as the legal team directed.
LIABILITY_WORDING = re.compile(r"\bindemn|\bliabilit|\bliable\b", re.IGNORECASE)


def family_of_wording(label: str | None, wording: str | None) -> str | None:
    found = family(label)
    if _key(label) == "remedies" and LIABILITY_WORDING.search(wording or ""):
        return "Liability and insurance"
    return found


def agreement_type(label: str | None) -> tuple[str, str] | None:
    return _AGREEMENT_TYPES.get(_key(label))


def wording_status(label: str | None) -> str | None:
    return _WORDING_STATUSES.get(_key(label))


def entity_label(scope: str) -> str:
    return _first_label(ENTITIES, scope)


def agreement_type_label(code: str, subtype: str) -> str:
    """The workbook's words for a type, or a readable fallback for one it lacks."""
    try:
        return _first_label(AGREEMENT_TYPES, (code, subtype))
    except StopIteration:
        return type_label(code, subtype)


def wording_status_label(status: str) -> str:
    return _first_label(WORDING_STATUSES, status)


def covers(scope: str, entity_code: str) -> bool:
    """Whether wording scoped to one entity, or both, applies to another."""
    return scope == "BOTH" or scope == entity_code


def type_label(code: str, subtype: str) -> str:
    from app.domain.agreements import label

    if code == "all":
        return "All agreements"
    return f"{label(code)}, {subtype}" if subtype else label(code)
