"""Seed the platform with a working demonstration dataset.

The people, counterparties, matters and findings mirror the scenario in the
design canvases, so the running platform shows the same story the design does.
Run with --if-empty to make it idempotent on container start.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, text

from app.ai.retrieval import embed
from app.core.security import hash_password
from app.db.models.ai import Baseline, Capability
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty, Vendor
from app.db.models.document import Document, ReviewFinding
from app.db.models.evaluation import GoldenCase, GoldenSet
from app.db.models.governance import (
    Assessment,
    Communication,
    ComplianceItem,
    ExtractedValue,
    Mailbox,
    Product,
)
from app.db.models.intake import Request, RequestType
from app.db.models.library import Clause, ClauseVersion, Playbook, Template, TemplateVersion
from app.db.models.matter import DecisionRecord, Matter, MatterTransition
from app.db.models.organisation import Organisation, User, UserEntity
from app.db.models.platform import Connector, MemoryChunk, RetentionPolicy
from app.db.session import owner_session
from app.domain.enums import (
    AssessmentStage,
    AssessmentType,
    CapabilityState,
    CommunicationClass,
    DataClass,
    DocumentType,
    MatterState,
    ObligationStatus,
    RiskTier,
    Role,
    Severity,
    VersionStatus,
)

TODAY = date(2026, 8, 21)
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


def _counter(session, scope: str, value: int) -> None:
    session.execute(
        text(
            "INSERT INTO identifier_counter (scope, value) VALUES (:s, :v) "
            "ON CONFLICT (scope) DO UPDATE SET value = GREATEST(identifier_counter.value, :v)"
        ),
        {"s": scope, "v": value},
    )


def seed_organisations(session) -> None:
    session.add_all(
        [
            Organisation(
                entity_code="DSN",
                legal_name="Data Science Nigeria",
                registration_number="RC-1442907",
                default_jurisdiction="Nigeria",
                branding={"primary": "#0A7A0A", "secondary": "#3E4095"},
            ),
            Organisation(
                entity_code="EAI",
                legal_name="EqualyzAI Limited",
                registration_number="RC-1783402",
                default_jurisdiction="Nigeria",
                branding={"primary": "#0A7A0A", "secondary": "#3E4095"},
            ),
        ]
    )
    session.flush()


PEOPLE = [
    (
        "Adaeze Okafor",
        "adaeze.okafor@dsn.example",
        [Role.HEAD_OF_LEGAL, Role.COUNSEL],
        ["DSN", "EAI"],
        ["dpr", "com", "crp"],
        5,
    ),
    (
        "Ifeoma Chukwu",
        "ifeoma.chukwu@dsn.example",
        [Role.COUNSEL],
        ["EAI", "DSN"],
        ["com", "ipr"],
        6,
    ),
    ("Chidi Nwosu", "chidi.nwosu@dsn.example", [Role.COUNSEL], ["DSN"], ["emp"], 4),
    ("Amaka Eze", "amaka.eze@dsn.example", [Role.COUNSEL], ["DSN", "EAI"], ["com"], 3),
    ("Tunde Bakare", "tunde.bakare@dsn.example", [Role.REQUESTER], ["DSN"], [], 0),
    ("Ngozi Adeyemi", "ngozi.adeyemi@dsn.example", [Role.REQUESTER], ["EAI"], [], 0),
    ("Segun Lawal", "segun.lawal@dsn.example", [Role.REQUESTER, Role.MANAGEMENT], ["DSN"], [], 0),
    ("Fatima Bello", "fatima.bello@dsn.example", [Role.PRIVACY], ["DSN", "EAI"], ["dpr"], 2),
    ("Emeka Obi", "emeka.obi@dsn.example", [Role.ADMIN], ["DSN", "EAI"], [], 0),
    ("Yusuf Danjuma", "yusuf.danjuma@dsn.example", [Role.AUDITOR], ["DSN", "EAI"], [], 0),
]


def seed_users(session) -> dict[str, User]:
    users: dict[str, User] = {}
    for name, email, roles, entities, specialisms, workload in PEOPLE:
        user = User(
            subject=email,
            name=name,
            work_email=email,
            password_hash=hash_password("Lop-Demo-2026"),
            roles=[r.value for r in roles],
            specialisms=specialisms,
            workload=workload,
            active=True,
        )
        session.add(user)
        session.flush()
        for entity in entities:
            session.add(UserEntity(user_id=user.id, entity_code=entity))
        users[name] = user
    session.flush()
    return users


def seed_request_types(session) -> dict[str, RequestType]:
    definitions = [
        {
            "code": "nda_mutual",
            "business_label": "We want to sign an NDA",
            "description": "A mutual confidentiality agreement before sharing information.",
            "agreement_type": "nda_mutual",
            "practice_code": "COM",
            "sla_hours": 8,
            "value_threshold": 5_000_000,
            "sort_order": 1,
            "drafting_enabled": False,
            "tier_1_auto_issue": True,
            "fields": [
                {
                    "name": "counterparty",
                    "label": "Who is it with",
                    "type": "string",
                    "mandatory": True,
                },
                {
                    "name": "purpose",
                    "label": "What will you share",
                    "type": "text",
                    "mandatory": True,
                },
                {
                    "name": "required_date",
                    "label": "When do you need it",
                    "type": "date",
                    "mandatory": True,
                },
                {
                    "name": "term_months",
                    "label": "How long should it run, in months",
                    "type": "number",
                    "unit": "months",
                    "help_text": (
                        "A whole number of months. 12 for a year, 36 for three years. "
                        "Leave it blank if it should run until either side ends it."
                    ),
                    "mandatory": False,
                    "progressive": True,
                },
            ],
            "mandatory_fields": ["counterparty", "purpose", "required_date"],
        },
        {
            "code": "consultant_engagement",
            "business_label": "We are engaging a consultant",
            "description": "An individual or firm doing defined work for a fee.",
            "agreement_type": "consultant_engagement",
            "practice_code": "EMP",
            "sla_hours": 48,
            "value_threshold": 5_000_000,
            "sort_order": 2,
            "fields": [
                {
                    "name": "counterparty",
                    "label": "Who are you engaging",
                    "type": "string",
                    "mandatory": True,
                },
                {"name": "scope", "label": "What will they do", "type": "text", "mandatory": True},
                {
                    "name": "value_amount",
                    "label": "Fee",
                    "type": "number",
                    "unit": "NGN",
                    "help_text": "The total fee, in naira, excluding VAT.",
                    "mandatory": True,
                },
                {"name": "required_date", "label": "Start date", "type": "date", "mandatory": True},
                {
                    "name": "exclusivity",
                    "label": "Is the engagement exclusive",
                    "type": "boolean",
                    "mandatory": False,
                },
            ],
            "mandatory_fields": ["counterparty", "scope", "value_amount", "required_date"],
        },
        {
            "code": "their_paper",
            "business_label": "A partner sent us their contract",
            "description": "Review a document the other side drafted.",
            "agreement_type": "master_services_agreement",
            "practice_code": "COM",
            "sla_hours": 72,
            "sort_order": 3,
            "fields": [
                {
                    "name": "counterparty",
                    "label": "Who sent it",
                    "type": "string",
                    "mandatory": True,
                },
                {"name": "purpose", "label": "What is it for", "type": "text", "mandatory": True},
                {
                    "name": "required_date",
                    "label": "When do they need a response",
                    "type": "date",
                    "mandatory": True,
                },
                {
                    "name": "their_paper",
                    "label": "Their paper",
                    "type": "boolean",
                    "mandatory": False,
                    "default": True,
                },
            ],
            "mandatory_fields": ["counterparty", "purpose", "required_date"],
        },
        {
            "code": "data_sharing",
            "business_label": "We are sharing or receiving data",
            "description": "A data-sharing or data-processing arrangement.",
            "agreement_type": "data_sharing_agreement",
            "practice_code": "DPR",
            "sla_hours": 72,
            "sort_order": 4,
            "drafting_enabled": True,
            "fields": [
                {
                    "name": "counterparty",
                    "label": "Who is the other party",
                    "type": "string",
                    "mandatory": True,
                },
                {
                    "name": "purpose",
                    "label": "What is the data for",
                    "type": "text",
                    "mandatory": True,
                },
                {
                    "name": "data_categories",
                    "label": "What data is involved",
                    "type": "text",
                    "mandatory": True,
                },
                {
                    "name": "required_date",
                    "label": "When do you need it",
                    "type": "date",
                    "mandatory": True,
                },
            ],
            "mandatory_fields": ["counterparty", "purpose", "data_categories", "required_date"],
        },
        {
            "code": "partnership",
            "business_label": "We are entering a partnership",
            "description": "A collaboration or partnership agreement.",
            "agreement_type": "partnership_agreement",
            "practice_code": "COM",
            "sla_hours": 72,
            "sort_order": 5,
            "drafting_enabled": True,
            "fields": [
                {
                    "name": "counterparty",
                    "label": "Who is the partner",
                    "type": "string",
                    "mandatory": True,
                },
                {
                    "name": "purpose",
                    "label": "What will you do together",
                    "type": "text",
                    "mandatory": True,
                },
                {
                    "name": "value_amount",
                    "label": "Value, if any",
                    "type": "number",
                    "unit": "NGN",
                    "mandatory": False,
                },
                {
                    "name": "required_date",
                    "label": "Target date",
                    "type": "date",
                    "mandatory": True,
                },
            ],
            "mandatory_fields": ["counterparty", "purpose", "required_date"],
        },
        {
            "code": "something_else",
            "business_label": "Something else",
            "description": "Describe it in your own words and Legal will route it.",
            "agreement_type": "unknown",
            "practice_code": "COM",
            "sla_hours": 48,
            "sort_order": 9,
            "fields": [
                {"name": "purpose", "label": "What do you need", "type": "text", "mandatory": True},
                {
                    "name": "required_date",
                    "label": "When do you need it",
                    "type": "date",
                    "mandatory": False,
                },
            ],
            "mandatory_fields": ["purpose"],
        },
    ]

    types: dict[str, RequestType] = {}
    for definition in definitions:
        record = RequestType(**definition)
        session.add(record)
        types[record.code] = record
    session.flush()
    return types


CLAUSES = [
    {
        "category": "CONF",
        "name": "Confidentiality",
        "house": (
            "Each party shall keep confidential all Confidential Information disclosed by "
            "the other party, shall use it only for the Purpose, and shall not disclose it "
            "to any third party except to those of its personnel and professional advisers "
            "who need to know it and who are bound by equivalent obligations. This "
            "obligation survives termination for five years."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": "Survival reduced to three years from termination.",
                "required_authority": "fallback_1",
                "conditions": (
                    "Where the counterparty is a public body operating a fixed retention rule."
                ),
            },
            {
                "rank": 2,
                "text": (
                    "Survival reduced to two years, with trade secrets carved out and held "
                    "indefinitely."
                ),
                "required_authority": "fallback_2",
                "conditions": "Only where no personal data is in scope.",
            },
        ],
        "unacceptable": (
            "A survival period under two years, or a definition that excludes orally disclosed "
            "information."
        ),
        "required_for": [
            "nda_mutual",
            "master_services_agreement",
            "partnership_agreement",
            "data_sharing_agreement",
            "consultant_engagement",
        ],
        "review": date(2027, 3, 1),
    },
    {
        "category": "LIAB",
        "name": "Limitation of liability",
        "house": (
            "Each party's aggregate liability under this agreement is limited to the greater "
            "of the fees paid in the twelve months preceding the claim and twenty-five "
            "million Naira. Neither party is liable for indirect or consequential loss. "
            "Nothing limits liability for death or personal injury, fraud, or a breach of "
            "confidentiality or data protection obligations."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": "Cap raised to one and a half times the annual fees.",
                "required_authority": "fallback_1",
                "conditions": "Where the counterparty carries dedicated delivery staffing.",
            },
            {
                "rank": 2,
                "text": (
                    "Cap raised to two times the annual fees, with the data protection carve-out "
                    "retained."
                ),
                "required_authority": "fallback_2",
                "conditions": "Strategic partners only.",
            },
            {
                "rank": 3,
                "text": (
                    "Cap set at the contract value, with a separate higher cap for data protection "
                    "breaches."
                ),
                "required_authority": "fallback_3",
                "conditions": "Funder agreements where the funder mandates it.",
            },
        ],
        "unacceptable": (
            "Uncapped liability of any kind, or a cap that includes the data protection carve-out."
        ),
        "required_for": [
            "master_services_agreement",
            "partnership_agreement",
            "consultant_engagement",
        ],
        "review": date(2026, 11, 30),
    },
    {
        "category": "DPR",
        "name": "Data protection",
        "house": (
            "Where a party processes personal data on behalf of the other, it does so only "
            "on documented instructions, maintains appropriate technical and organisational "
            "measures, engages no subprocessor without prior written consent, notifies any "
            "personal data breach within forty-eight hours, permits audit on reasonable "
            "notice, and returns or deletes the data on termination. Transfers outside "
            "Nigeria require a documented transfer mechanism approved in advance."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": "Breach notification extended to seventy-two hours.",
                "required_authority": "fallback_1",
                "conditions": (
                    "Where the counterparty is subject to an equivalent statutory regime."
                ),
            },
        ],
        "unacceptable": (
            "Silence on subprocessors, no breach notification period, or an unrestricted "
            "right to transfer personal data outside Nigeria."
        ),
        "required_for": [
            "master_services_agreement",
            "data_sharing_agreement",
            "partnership_agreement",
        ],
        "review": date(2026, 10, 15),
    },
    {
        "category": "IPR",
        "name": "Intellectual property",
        "house": (
            "Each party retains its pre-existing intellectual property. All models, weights, "
            "derived datasets and outputs created from our data are our exclusive property, "
            "with a limited, revocable licence back to the counterparty for the sole purpose "
            "of delivering the services."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": (
                    "Joint ownership of derived models, with each party free to exploit "
                    "independently."
                ),
                "required_authority": "fallback_2",
                "conditions": "Research collaborations where both parties contribute data.",
            },
        ],
        "unacceptable": (
            "Silence on models or outputs derived from our data, or counterparty ownership of them."
        ),
        "required_for": [
            "master_services_agreement",
            "partnership_agreement",
            "consultant_engagement",
        ],
        "review": date(2027, 1, 20),
    },
    {
        "category": "TERM",
        "name": "Termination",
        "house": (
            "Either party may terminate for convenience on thirty days written notice, with "
            "a pro-rata refund of prepaid fees. Either party may terminate immediately on a "
            "material breach that is not remedied within fifteen days of notice, or on the "
            "other party's insolvency."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": "Notice period extended to sixty days.",
                "required_authority": "fallback_1",
                "conditions": (
                    "Where the counterparty carries dedicated staffing for the engagement."
                ),
            },
        ],
        "unacceptable": (
            "A notice period over ninety days, or no right to terminate for convenience at all."
        ),
        "required_for": [
            "master_services_agreement",
            "partnership_agreement",
            "consultant_engagement",
        ],
        "review": date(2027, 2, 1),
    },
    {
        "category": "GOV",
        "name": "Governing law and disputes",
        "house": (
            "This agreement is governed by the laws of the Federal Republic of Nigeria. The "
            "parties submit to the exclusive jurisdiction of the courts of Lagos State, "
            "having first attempted resolution by arbitration under the rules of the Lagos "
            "Court of Arbitration."
        ),
        "fallbacks": [
            {
                "rank": 1,
                "text": (
                    "Arbitration seated in Lagos under UNCITRAL rules, courts retained for interim "
                    "relief."
                ),
                "required_authority": "fallback_1",
                "conditions": "International counterparties.",
            },
        ],
        "unacceptable": (
            "A foreign governing law, or a forum outside Nigeria for a wholly domestic arrangement."
        ),
        "required_for": [
            "nda_mutual",
            "master_services_agreement",
            "partnership_agreement",
            "data_sharing_agreement",
            "consultant_engagement",
        ],
        "review": date(2027, 6, 1),
    },
]


CLAUSE_VERSIONS = {
    "CONF": (3, 1),
    "LIAB": (2, 0),
    "DPR": (1, 4),
    "IPR": (1, 2),
    "TERM": (2, 2),
    "GOV": (3, 0),
}


def seed_library(session, users: dict[str, User]) -> dict[str, ClauseVersion]:
    head = users["Adaeze Okafor"]
    versions: dict[str, ClauseVersion] = {}

    for definition in CLAUSES:
        clause = Clause(
            category=definition["category"],
            name=definition["name"],
            owner_id=head.id,
            entity_applicability=["DSN", "EAI"],
            required_for_types=definition["required_for"],
        )
        session.add(clause)
        session.flush()

        # Version numbers are declared per category rather than derived from
        # position, because the templates and the playbooks reference them by
        # name. Deriving them let three references point at versions that were
        # never created, and neither template could generate as a result.
        major, minor = CLAUSE_VERSIONS[definition["category"]]
        version = ClauseVersion(
            clause_id=clause.id,
            reference=f"CLS-{clause.category}-v{major}.{minor}",
            major=major,
            minor=minor,
            status=VersionStatus.APPROVED.value,
            house_position=definition["house"],
            fallbacks=definition["fallbacks"],
            unacceptable_position=definition["unacceptable"],
            approved_by_id=head.id,
            approval_date=date(2026, 1, 15),
            effective_date=date(2026, 2, 1),
            review_date=definition["review"],
        )
        session.add(version)
        session.flush()
        versions[clause.category] = version

    return versions


NDA_BODY = [
    {
        "key": "parties",
        "number": "1",
        "heading": "Parties and purpose",
        "text": "This mutual non-disclosure agreement is made on {{effective_date}} between "
        "{{our_entity}} and {{counterparty}} of {{counterparty_jurisdiction}}, for the "
        "purpose of {{purpose}}.",
    },
    {
        "key": "definitions",
        "number": "2",
        "heading": "Definitions",
        "text": 'In this agreement, "Confidential Information" means all information disclosed '
        "by one party to the other, in any form, whether or not marked as confidential, "
        'and "Purpose" means the purpose stated in clause 1.',
    },
    {"key": "conf", "number": "3", "heading": "Confidentiality", "clause": "CLS-CONF-v3.1"},
    {
        "key": "dpr",
        "number": "4",
        "heading": "Data protection",
        "clause": "CLS-DPR-v1.4",
        "condition": "privacy_flag",
    },
    {
        "key": "term",
        "number": "5",
        "heading": "Term and termination",
        "text": "This agreement runs for {{term_months}} months from {{effective_date}}, and "
        "either party may end it on thirty days written notice. The confidentiality "
        "obligation in clause 3 survives that end.",
    },
    {
        "key": "gov",
        "number": "6",
        "heading": "Governing law and disputes",
        "clause": "CLS-GOV-v3.0",
    },
]

MSA_BODY = [
    {
        "key": "parties",
        "number": "1",
        "heading": "Parties",
        "text": "This master services agreement is made on {{effective_date}} between "
        "{{our_entity}} and {{counterparty}}.",
    },
    {
        "key": "services",
        "number": "2",
        "heading": "Services",
        "text": "The supplier shall provide the services described in each statement of work "
        "agreed under this agreement.",
    },
    {
        "key": "fees",
        "number": "3",
        "heading": "Fees",
        "text": "The fees are {{value_currency}} {{value_amount}}, payable in accordance with "
        "each statement of work.",
    },
    {"key": "conf", "number": "4", "heading": "Confidentiality", "clause": "CLS-CONF-v3.1"},
    {"key": "dpr", "number": "5", "heading": "Data protection", "clause": "CLS-DPR-v1.4"},
    {"key": "ipr", "number": "6", "heading": "Intellectual property", "clause": "CLS-IPR-v1.2"},
    {"key": "liab", "number": "7", "heading": "Limitation of liability", "clause": "CLS-LIAB-v2.0"},
    {"key": "term", "number": "8", "heading": "Termination", "clause": "CLS-TERM-v2.2"},
    {
        "key": "gov",
        "number": "9",
        "heading": "Governing law and disputes",
        "clause": "CLS-GOV-v3.0",
    },
    {
        "key": "deliverable",
        "number": "10",
        "heading": "Deliverable",
        "text": "Deliverable {{index}}: {{name}}, due {{due}}.",
        "repeat_over": "deliverables",
    },
]

NDA_VARIABLES = [
    {"name": "our_entity", "label": "Our entity", "type": "string", "mandatory": True},
    {
        "name": "counterparty",
        "label": "Counterparty legal name",
        "type": "string",
        "mandatory": True,
    },
    {
        "name": "counterparty_jurisdiction",
        "label": "Counterparty jurisdiction",
        "type": "string",
        "mandatory": True,
    },
    {"name": "purpose", "label": "Purpose", "type": "string", "mandatory": True},
    {"name": "effective_date", "label": "Effective date", "type": "date", "mandatory": True},
    {
        "name": "term_months",
        "label": "Term in months",
        "type": "string",
        "mandatory": False,
        "default": "24",
    },
]

MSA_VARIABLES = [
    {"name": "our_entity", "label": "Our entity", "type": "string", "mandatory": True},
    {
        "name": "counterparty",
        "label": "Counterparty legal name",
        "type": "string",
        "mandatory": True,
    },
    {"name": "effective_date", "label": "Effective date", "type": "date", "mandatory": True},
    {"name": "value_amount", "label": "Contract value", "type": "currency", "mandatory": True},
    {"name": "value_currency", "label": "Currency", "type": "string", "mandatory": True},
]


def seed_templates(session, users: dict[str, User]) -> dict[str, TemplateVersion]:
    head = users["Adaeze Okafor"]
    out: dict[str, TemplateVersion] = {}

    for code, name, agreement_type, body, variables, clauses, major, minor, review in [
        (
            "TPL-NDA",
            "Mutual non-disclosure agreement",
            "nda_mutual",
            NDA_BODY,
            NDA_VARIABLES,
            ["CLS-CONF-v3.1", "CLS-DPR-v1.4", "CLS-GOV-v3.0"],
            3,
            1,
            date(2027, 3, 1),
        ),
        (
            "TPL-MSA",
            "Master services agreement",
            "master_services_agreement",
            MSA_BODY,
            MSA_VARIABLES,
            [
                "CLS-CONF-v3.1",
                "CLS-DPR-v1.4",
                "CLS-IPR-v1.2",
                "CLS-LIAB-v2.0",
                "CLS-TERM-v2.2",
                "CLS-GOV-v3.0",
            ],
            2,
            4,
            date(2026, 9, 30),
        ),
    ]:
        template = Template(
            code=code,
            name=name,
            agreement_type=agreement_type,
            owner_id=head.id,
            entity_applicability=["DSN", "EAI"],
        )
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id,
            reference=f"{code}-v{major}.{minor}",
            major=major,
            minor=minor,
            status=VersionStatus.APPROVED.value,
            body=body,
            variables=variables,
            clause_references=clauses,
            approved_by_id=head.id,
            approval_date=date(2026, 1, 20),
            effective_date=date(2026, 2, 1),
            review_date=review,
        )
        session.add(version)
        session.flush()
        out[code] = version

    session.add_all(
        [
            Playbook(
                agreement_type="master_services_agreement",
                name="Master services agreement playbook",
                version=4,
                required_clauses=[
                    {
                        "category": "LIAB",
                        "name": "Limitation of liability",
                        "absent_severity": "critical",
                    },
                    {"category": "CONF", "name": "Confidentiality", "absent_severity": "critical"},
                    {"category": "DPR", "name": "Data protection", "absent_severity": "critical"},
                    {
                        "category": "IPR",
                        "name": "Intellectual property",
                        "absent_severity": "material",
                    },
                    {"category": "TERM", "name": "Termination", "absent_severity": "material"},
                    {"category": "GOV", "name": "Governing law", "absent_severity": "minor"},
                ],
            ),
            Playbook(
                agreement_type="nda_mutual",
                name="Mutual NDA playbook",
                version=2,
                required_clauses=[
                    {"category": "CONF", "name": "Confidentiality", "absent_severity": "critical"},
                    {"category": "GOV", "name": "Governing law", "absent_severity": "minor"},
                ],
            ),
        ]
    )
    session.flush()
    return out


def seed_counterparties(session, users: dict[str, User]) -> dict[str, Counterparty]:
    definitions = [
        (
            "CPT-0031",
            "Sahel Cloud Services Limited",
            "commercial",
            "sahelcloud.example",
            "RC-993201",
        ),
        (
            "CPT-0047",
            "Harmattan Analytics Limited",
            "commercial",
            "harmattan.example",
            "RC-1120384",
        ),
        (
            "CPT-0052",
            "Kano Partners Limited",
            "strategic_partner",
            "kanopartners.example",
            "RC-889120",
        ),
        ("CPT-0019", "Lagos Data Institute", "funder", "lagosdata.example", "RC-772013"),
        ("CPT-0064", "Federal Ministry of Health", "government", "health.gov.example", None),
        ("CPT-0071", "Zamfara Agritech Limited", "commercial", "zamfaraagri.example", "RC-1330922"),
        ("CPT-0080", "Olamide Bello", "individual", None, None),
    ]
    out: dict[str, Counterparty] = {}
    for reference, name, relationship, domain, registration in definitions:
        record = Counterparty(
            reference=reference,
            legal_name=name,
            counterparty_type="individual" if relationship == "individual" else "company",
            registration_number=registration,
            domain=domain,
            relationship_class="commercial" if relationship == "individual" else relationship,
        )
        session.add(record)
        session.flush()
        out[reference] = record

    session.add(
        Vendor(
            counterparty_id=out["CPT-0031"].id,
            service_owner_id=users["Amaka Eze"].id,
            security_review_status="findings_open",
            security_review_date=date(2026, 4, 12),
            open_security_findings=2,
            subprocessors=[
                {"name": "Northwind Hosting", "location": "Ireland"},
                {"name": "Cedar Backup", "location": "South Africa"},
            ],
            hosting_locations=["Ireland", "Nigeria"],
            renewal_date=date(2027, 6, 18),
            spend_band="25m to 50m",
            performance_notes="Two missed reporting deadlines in the last quarter.",
            assessment_expired=True,
        )
    )
    _counter(session, "counterparty", 80)
    session.flush()
    return out


# Every matter but the restricted investigation began as a request from a
# colleague. Seeding matters without one left the platform unable to show where
# any of its work came from, and the "what was asked for" panel blank on every
# screen but the one request raised by hand.
#
# The investigation is deliberately absent. A restricted internal matter is
# opened by Legal, not raised through the portal, and a fabricated request
# behind it would misrepresent how that work starts.
MATTER_ORIGINS: dict[str, dict] = {
    "EAI-COM-2026-0011": {
        "reference": "REQ-2026-01170",
        "type_code": "nda_mutual",
        "requester": "Ngozi Adeyemi",
        "subject": "Mutual NDA with Harmattan Analytics",
        "purpose": (
            "We are scoping a joint bid with Harmattan and need to exchange model "
            "performance figures and client names before either side commits."
        ),
        "answers": {
            "counterparty": "Harmattan Analytics Limited",
            "purpose": ("Model performance figures, client names and our pricing bands."),
            "term_months": 24,
        },
        "raised_hours": 30,
    },
    "EAI-COM-2026-0009": {
        "reference": "REQ-2026-01171",
        "type_code": "their_paper",
        "requester": "Ngozi Adeyemi",
        "subject": "Sahel Cloud sent us their master services agreement",
        "purpose": (
            "Sahel Cloud will host the inference workloads. They have sent their own "
            "master services agreement and will not start until it is signed."
        ),
        "answers": {
            "counterparty": "Sahel Cloud Services Limited",
            "purpose": "Hosting and inference for the production models.",
            "their_paper": True,
        },
        "personal_data": True,
        "leaves_nigeria": True,
        "raised_hours": 240,
    },
    "EAI-CON-2026-0038": {
        "reference": "REQ-2026-01172",
        "type_code": "partnership",
        "requester": "Ngozi Adeyemi",
        "subject": "Partnership agreement with Kano Partners",
        "purpose": (
            "A joint delivery arrangement for the northern programme. They bring the "
            "field teams, we bring the platform, and revenue is shared."
        ),
        "answers": {
            "counterparty": "Kano Partners Limited",
            "purpose": "Joint delivery of the northern programme, revenue shared.",
            "value_amount": 18_000_000,
        },
        "value_amount": 18_000_000,
        "raised_hours": 44,
    },
    "DSN-EMP-2026-0104": {
        "reference": "REQ-2026-01173",
        "type_code": "consultant_engagement",
        "requester": "Tunde Bakare",
        "subject": "Consultant engagement, Olamide Bello",
        "purpose": (
            "Olamide is writing the curriculum for the schools programme. Six weeks, "
            "paid on delivery of each module."
        ),
        "answers": {
            "counterparty": "Olamide Bello",
            "scope": "Write and review the six curriculum modules for the schools programme.",
            "value_amount": 4_200_000,
            "exclusivity": False,
        },
        "value_amount": 4_200_000,
        "raised_hours": 160,
    },
    "DSN-COM-2026-0087": {
        "reference": "REQ-2026-01174",
        "type_code": "data_sharing",
        "requester": "Segun Lawal",
        "subject": "Data-sharing agreement with the Lagos Data Institute",
        "purpose": (
            "The Institute holds the anonymised health cohort we need to train the "
            "triage model. They want a data-sharing agreement before releasing it."
        ),
        "answers": {
            "counterparty": "Lagos Data Institute",
            "purpose": "Training the triage model on the anonymised health cohort.",
            "data_categories": (
                "Anonymised patient records: age band, presenting condition, outcome."
            ),
        },
        "personal_data": True,
        "special_category_data": True,
        "raised_hours": 90,
    },
    "EAI-COM-2026-0004": {
        "reference": "REQ-2026-01175",
        "type_code": "partnership",
        "requester": "Ngozi Adeyemi",
        "subject": "Reseller agreement with Zamfara Agritech",
        "purpose": (
            "Zamfara Agritech want to resell the advisory product to their cooperative "
            "members. They asked for exclusivity in the north west; we said no."
        ),
        "answers": {
            "counterparty": "Zamfara Agritech Limited",
            "purpose": "Reselling the advisory product to cooperative members.",
            "value_amount": 9_500_000,
        },
        "value_amount": 9_500_000,
        "raised_hours": 4_400,
    },
}


def build_origin_request(number: str, matter, users, types, counterparty) -> Request | None:
    """The request a seeded matter was accepted from.

    Accepted rather than open: it has already become a matter, so it belongs in
    no triage queue.
    """
    origin = MATTER_ORIGINS.get(number)
    if origin is None:
        return None

    raised = NOW - timedelta(hours=origin["raised_hours"])
    return Request(
        reference=origin["reference"],
        entity=matter.entity,
        request_type_id=types[origin["type_code"]].id,
        requester_id=users[origin["requester"]].id,
        subject=origin["subject"],
        purpose=origin["purpose"],
        proposed_counterparty=counterparty.legal_name if counterparty else None,
        counterparty_id=matter.counterparty_id,
        required_date=(raised + timedelta(days=7)).date(),
        value_amount=origin.get("value_amount"),
        personal_data=origin.get("personal_data", False),
        special_category_data=origin.get("special_category_data", False),
        third_party_confidential=origin.get("third_party_confidential", False),
        leaves_nigeria=origin.get("leaves_nigeria", False),
        privacy_flag=matter.privacy_flag,
        answers=dict(origin["answers"]),
        status=MatterState.ACCEPTED.value,
        triage_notes="Accepted at triage and opened as a matter.",
        acknowledged_at=raised + timedelta(minutes=1),
        created_at=raised,
    )


def seed_matters(session, users, counterparties, types, templates, clauses) -> dict[str, Matter]:
    ifeoma = users["Ifeoma Chukwu"]
    adaeze = users["Adaeze Okafor"]
    chidi = users["Chidi Nwosu"]

    definitions = [
        (
            "EAI-COM-2026-0011",
            "EAI",
            "Mutual NDA, Harmattan Analytics",
            "CPT-0047",
            ifeoma,
            RiskTier.TIER_1,
            MatterState.AWAITING_SIGNATURE,
            "Counterparty to sign",
            8,
            4,
            False,
            None,
        ),
        (
            "EAI-COM-2026-0009",
            "EAI",
            "Master services agreement, Sahel Cloud",
            "CPT-0031",
            adaeze,
            RiskTier.TIER_3,
            MatterState.IN_REVIEW,
            "14 findings to clear",
            72,
            216,
            True,
            18_000_000,
        ),
        (
            "EAI-CON-2026-0038",
            "EAI",
            "Partnership agreement, Kano Partners",
            "CPT-0052",
            ifeoma,
            RiskTier.TIER_2,
            MatterState.IN_APPROVAL,
            "Signatory approval overdue",
            24,
            20,
            False,
            18_000_000,
        ),
        (
            "DSN-EMP-2026-0104",
            "DSN",
            "Consultant engagement, Olamide Bello",
            "CPT-0080",
            chidi,
            RiskTier.TIER_2,
            MatterState.RETURNED_FOR_INFORMATION,
            "Awaiting requester",
            48,
            140,
            False,
            4_200_000,
        ),
        (
            "DSN-COM-2026-0087",
            "DSN",
            "Data-sharing agreement, Lagos Data Institute",
            "CPT-0019",
            adaeze,
            RiskTier.TIER_3,
            MatterState.ESCALATED,
            "Outside playbook, liability",
            72,
            62,
            True,
            None,
        ),
        (
            "EAI-COM-2026-0004",
            "EAI",
            "Reseller agreement, Zamfara Agritech",
            "CPT-0071",
            ifeoma,
            RiskTier.TIER_2,
            MatterState.ACTIVE,
            "Renewal notice 18 Jun 2027",
            None,
            4320,
            False,
            9_500_000,
        ),
        (
            "DSN-CRP-2026-0002",
            "DSN",
            "Anambra investigation",
            None,
            adaeze,
            RiskTier.TIER_4,
            MatterState.DRAFTING,
            "Counsel only",
            None,
            30,
            False,
            None,
        ),
    ]

    out: dict[str, Matter] = {}
    for (
        number,
        entity,
        title,
        cpt,
        owner,
        tier,
        state,
        next_action,
        sla,
        age_hours,
        privacy,
        value,
    ) in definitions:
        restricted = number == "DSN-CRP-2026-0002"
        created = datetime.now(UTC) - timedelta(hours=age_hours)
        matter = Matter(
            number=number,
            entity=entity,
            practice_code=number.split("-")[1],
            title=title,
            counterparty_id=counterparties[cpt].id if cpt else None,
            requester_id=users["Ngozi Adeyemi"].id if entity == "EAI" else users["Tunde Bakare"].id,
            responsible_lawyer_id=owner.id,
            risk_tier=tier.value,
            tier_rationale=[f"Derived at triage on {created:%d %B %Y}."],
            classification=DataClass.RESTRICTED.value
            if restricted
            else DataClass.CONFIDENTIAL.value,
            status=state.value,
            next_action=next_action,
            sla_target_hours=sla,
            sla_started_at=created,
            privacy_flag=privacy,
            value_amount=value,
            restricted=restricted,
            created_at=created,
            updated_at=datetime.now(UTC) - timedelta(hours=3),
        )
        if state is MatterState.ESCALATED:
            matter.blocker = "Awaiting the legal lead on the liability position"
        session.add(matter)
        session.flush()

        origin = build_origin_request(
            number, matter, users, types, counterparties[cpt] if cpt else None
        )
        if origin is not None:
            session.add(origin)
            session.flush()
            matter.request_id = origin.id

        session.add(
            MatterTransition(
                matter_id=matter.id,
                to_state=MatterState.ACCEPTED.value,
                actor_id=owner.id,
                occurred_at=created,
                clock_running=True,
            )
        )
        if state is not MatterState.ACCEPTED:
            session.add(
                MatterTransition(
                    matter_id=matter.id,
                    from_state=MatterState.ACCEPTED.value,
                    to_state=state.value,
                    actor_id=owner.id,
                    occurred_at=created + timedelta(hours=min(6, age_hours / 2)),
                    clock_running=state is not MatterState.RETURNED_FOR_INFORMATION,
                )
            )
        if restricted:
            from app.db.models.matter import MatterAccess

            session.add(
                MatterAccess(matter_id=matter.id, user_id=adaeze.id, granted_by_id=adaeze.id)
            )

        out[number] = matter

    _counter(session, "matter:EAI:COM:2026", 11)
    _counter(session, "matter:EAI:CON:2026", 38)
    _counter(session, "matter:DSN:EMP:2026", 104)
    _counter(session, "matter:DSN:COM:2026", 87)
    _counter(session, "matter:DSN:CRP:2026", 2)
    session.flush()
    return out


DECISIONS = [
    (
        44,
        "EAI",
        "Accepted an uncapped indemnity for third-party intellectual property claims.",
        "The funder made it a condition of the research collaboration and the exposure was "
        "bounded by the scope of the dataset.",
        "Capped indemnity at contract value, refused.",
        ["CLS-LIAB-v2.0"],
        "outside",
        True,
        "CPT-0019",
        date(2024, 11, 14),
    ),
    (
        58,
        "EAI",
        "Accepted a sixty-day termination notice period.",
        "The counterparty carries dedicated delivery staffing for this engagement, which is the "
        "condition attached to fallback 1.",
        "Held at thirty days, refused by the counterparty.",
        ["CLS-TERM-v2.2"],
        "fallback_1",
        False,
        "CPT-0071",
        date(2026, 2, 4),
    ),
    (
        61,
        "EAI",
        "Conceded a liability cap of one and a half times annual fees.",
        "Granted to the parent company in 2024 to close a stalled negotiation. The counterparty "
        "has cited this concession in correspondence since.",
        "Held at the standard cap, refused.",
        ["CLS-LIAB-v2.0"],
        "fallback_2",
        False,
        "CPT-0031",
        date(2024, 6, 2),
    ),
    (
        66,
        "DSN",
        "Refused a ninety-day termination notice period.",
        "Ninety days sits on the unacceptable list. The counterparty settled at sixty.",
        "Sixty days under fallback 1.",
        ["CLS-TERM-v2.2"],
        "fallback_1",
        False,
        None,
        date(2025, 9, 18),
    ),
    (
        71,
        "EAI",
        "Refused a ninety-day termination notice period.",
        "Same position as decision 66. The counterparty settled at sixty.",
        "Sixty days under fallback 1.",
        ["CLS-TERM-v2.2"],
        "fallback_1",
        False,
        None,
        date(2026, 1, 30),
    ),
    (
        73,
        "EAI",
        "Refused uncapped liability on counterparty paper.",
        "Uncapped exposure sits on the unacceptable list rather than among the fallbacks. "
        "Settled at fallback 1.",
        "Accept the counterparty position, refused.",
        ["CLS-LIAB-v2.0"],
        "fallback_1",
        False,
        "CPT-0031",
        date(2026, 5, 12),
    ),
]


def seed_decisions(session, users, counterparties, matters) -> None:
    adaeze = users["Adaeze Okafor"]
    ifeoma = users["Ifeoma Chukwu"]

    for (
        sequence,
        entity,
        decision,
        reason,
        alternatives,
        refs,
        authority,
        residual,
        cpt,
        decided_on,
    ) in DECISIONS:
        session.add(
            DecisionRecord(
                sequence=sequence,
                entity=entity,
                decision=decision,
                reason=reason,
                alternatives_considered=alternatives,
                clause_references=refs,
                authority_level=authority,
                residual_risk_accepted=residual,
                commercial_rationale="Recorded at the time of the concession."
                if authority in {"fallback_2", "fallback_3", "outside"}
                else None,
                decided_by_id=adaeze.id if authority != "fallback_1" else ifeoma.id,
                decided_at=datetime.combine(decided_on, datetime.min.time(), tzinfo=UTC),
                counterparty_id=counterparties[cpt].id if cpt else None,
            )
        )
    _counter(session, "decision", 73)
    session.flush()


FINDINGS = [
    (
        "Liability uncapped",
        "Their clause 11.2",
        False,
        Severity.CRITICAL,
        "LIAB",
        "CLS-LIAB-v2.0",
        "Neither party limits its liability under this agreement, and each party is liable for all "
        "direct, indirect and consequential losses without cap.",
        "Aggregate liability capped at the greater of fees paid in the preceding twelve months or "
        "twenty-five million Naira, with indirect and consequential loss excluded on both sides.",
        "Replace clause 11.2 in full with the house wording. Fallback 1, a cap at one and a half "
        "times annual fees, is available to legal staff if they refuse the base cap.",
        "outside",
        False,
    ),
    (
        "Data protection clause absent",
        "Required, not present",
        True,
        Severity.CRITICAL,
        "DPR",
        "CLS-DPR-v1.4",
        "No data protection or processing terms appear anywhere in the draft, although the "
        "services"
        "involve hosting our personal data outside Nigeria.",
        "Full data-processing terms with named subprocessors, a transfer mechanism, breach "
        "notification within forty-eight hours and audit rights.",
        "Insert the approved data-processing annex as Schedule 3 and add a cross-reference at "
        "clause 4.1. The privacy flag on this matter requires it.",
        "outside",
        False,
    ),
    (
        "Notice period ninety days, we accept thirty",
        "Their clause 14.1",
        False,
        Severity.MATERIAL,
        "TERM",
        "CLS-TERM-v2.2",
        "Either party may terminate for convenience on ninety days written notice to the other "
        "party.",
        "Termination for convenience on thirty days written notice, with a pro-rata refund of "
        "prepaid fees.",
        "Amend to thirty days. Fallback 1 permits sixty days where the counterparty carries "
        "dedicated staffing, which appears to apply here.",
        "fallback_1",
        False,
    ),
    (
        "Intellectual property silent on derived models",
        "Their clause 8",
        False,
        Severity.MATERIAL,
        "IPR",
        "CLS-IPR-v1.2",
        "Each party retains ownership of its pre-existing intellectual property. No provision "
        "addresses models or outputs derived from our data.",
        "All models, weights and outputs derived from our data are our exclusive property, with a "
        "limited licence back for service delivery only.",
        "Add house clause 8.4. This is the position recorded in decision 61, conceded once, in "
        "2024, at legal lead level.",
        "fallback_2",
        False,
    ),
    (
        "Governing law drafting non-standard",
        "Their clause 19",
        False,
        Severity.MINOR,
        "GOV",
        "CLS-GOV-v3.0",
        "This agreement shall be construed in accordance with Nigerian law and the parties submit "
        "to the courts of Lagos State.",
        "Governed by the laws of the Federal Republic of Nigeria, exclusive jurisdiction of the "
        "courts of Lagos State, arbitration first under the Lagos Court of Arbitration rules.",
        "Apply approved fallback 1 wording. It matches a pre-approved fallback, so legal "
        "staff may clear it without escalating.",
        "fallback_1",
        True,
    ),
]


def seed_review(session, users, matters, templates) -> Document:
    matter = matters["EAI-COM-2026-0009"]

    document = Document(
        matter_id=matter.id,
        entity=matter.entity,
        name="Sahel Cloud master services agreement, their draft 4",
        document_type=DocumentType.DRAFT.value,
        version=4,
        blocks=[
            {
                "key": "b11",
                "number": "11.2",
                "heading": "Liability",
                "text": FINDINGS[0][6],
                "provenance": "novel",
                "source_reference": None,
                "novel": True,
            },
            {
                "key": "b14",
                "number": "14.1",
                "heading": "Termination",
                "text": FINDINGS[2][6],
                "provenance": "novel",
                "source_reference": None,
                "novel": True,
            },
            {
                "key": "b8",
                "number": "8",
                "heading": "Intellectual property",
                "text": FINDINGS[3][6],
                "provenance": "novel",
                "source_reference": None,
                "novel": True,
            },
            {
                "key": "b19",
                "number": "19",
                "heading": "Governing law",
                "text": FINDINGS[4][6],
                "provenance": "novel",
                "source_reference": None,
                "novel": True,
            },
        ],
        content_hash="counterpartypaper" + "0" * 46,
        classification=DataClass.CONFIDENTIAL.value,
        generated_by_id=users["Adaeze Okafor"].id,
        generated_at=NOW - timedelta(days=2),
        novel_clause_count=4,
    )
    session.add(document)
    session.flush()

    for index, (
        title,
        ref,
        absent,
        severity,
        category,
        clause_ref,
        theirs,
        house,
        suggestion,
        authority,
        preapproved,
    ) in enumerate(FINDINGS, start=1):
        session.add(
            ReviewFinding(
                matter_id=matter.id,
                document_id=document.id,
                sequence=index,
                title=title,
                their_reference=ref,
                clause_absent=absent,
                severity=severity.value,
                clause_category=category,
                clause_version_ref=clause_ref,
                their_text=theirs,
                house_position=house,
                suggested_redline=suggestion,
                required_authority=authority,
                matches_preapproved_fallback=preapproved,
            )
        )
    session.flush()
    return document


def seed_archive(session, users, counterparties, matters) -> Contract:
    matter = matters["EAI-CON-2026-0038"]
    executed = Document(
        matter_id=matter.id,
        entity="EAI",
        name="Partnership agreement, Kano Partners, executed",
        document_type=DocumentType.EXECUTED.value,
        version=1,
        template_version_ref="TPL-MSA-v2.4",
        clause_versions=["CLS-CONF-v3.1", "CLS-DPR-v1.4", "CLS-LIAB-v2.0", "CLS-TERM-v2.2"],
        blocks=[],
        content_hash="e3b0c44298fc1c149afbf4c8996fb924" + "27ae41e4649b934c",
        classification=DataClass.CONFIDENTIAL.value,
        immutable=True,
        generated_at=NOW - timedelta(days=3),
    )
    session.add(executed)
    session.flush()

    contract = Contract(
        reference="EAI-CON-2026-0038",
        matter_id=matter.id,
        entity="EAI",
        counterparty_id=counterparties["CPT-0052"].id,
        agreement_type="partnership_agreement",
        effective_date=date(2026, 8, 18),
        term_months=24,
        end_date=date(2028, 8, 17),
        renewal_type="automatic",
        notice_period_days=90,
        value_amount=18_000_000,
        governing_law="Nigeria",
        signature_status="executed",
        executed_document_id=executed.id,
        executed_at=NOW - timedelta(days=3),
        content_hash=executed.content_hash,
        authoritative=True,
        signature_certificate={
            "provider": "internal",
            "signers": [
                {
                    "name": "Adaeze Obi",
                    "organisation": "Kano Partners Limited",
                    "signed_at": "2026-08-18T14:22:00Z",
                    "ip": "102.89.44.17",
                },
                {
                    "name": "Adaeze Okafor",
                    "organisation": "EqualyzAI Limited",
                    "signed_at": "2026-08-18T15:04:00Z",
                    "ip": "102.89.12.4",
                },
            ],
        },
    )
    session.add(contract)
    session.flush()
    _counter(session, "contract:EAI:2026", 38)

    obligations = [
        (
            "Renewal notice, Sahel Cloud",
            "renewal",
            "cl. 14.1",
            TODAY - timedelta(days=4),
            "Amaka Eze",
            True,
            ObligationStatus.OPEN,
            "none",
            "Either party may terminate on ninety days notice before the renewal date.",
        ),
        (
            "Quarterly data-processing report",
            "reporting",
            "cl. 6.3",
            TODAY + timedelta(days=11),
            "Tunde Bakare",
            True,
            ObligationStatus.OPEN,
            "quarterly",
            "The supplier shall report on processing activity each quarter.",
        ),
        (
            "Insurance certificate",
            "deliverable",
            "cl. 9.2",
            TODAY + timedelta(days=41),
            "Amaka Eze",
            True,
            ObligationStatus.OPEN,
            "annual",
            "The supplier shall maintain insurance and produce a certificate on request.",
        ),
        (
            "Milestone 2 payment certificate",
            "payment_milestone",
            "cl. 5.2",
            TODAY - timedelta(days=2),
            "Segun Lawal",
            True,
            ObligationStatus.OPEN,
            "none",
            "Payment falls due on certification of milestone 2.",
        ),
        (
            "Subprocessor change notification",
            "reporting",
            "cl. 7.4",
            None,
            "Amaka Eze",
            False,
            ObligationStatus.PROPOSED,
            "none",
            "The supplier shall notify any change of subprocessor before it takes effect.",
        ),
        (
            "Renewal notice window opens",
            "renewal",
            "cl. 14.1",
            date(2027, 4, 19),
            "Ifeoma Chukwu",
            False,
            ObligationStatus.PROPOSED,
            "none",
            "Notice deadline minus a sixty day lead time.",
        ),
    ]

    for index, (name, kind, clause, due, owner, evidence, status, recurrence, quote) in enumerate(
        obligations, start=1
    ):
        session.add(
            Obligation(
                reference=f"OBL-0038-{index:02d}",
                contract_id=contract.id,
                matter_id=matter.id,
                entity="EAI",
                name=name,
                obligation_type=kind,
                source_clause=clause,
                source_quote=quote,
                owner_id=users[owner].id,
                due_date=due,
                recurrence=recurrence,
                lead_time_days=60 if kind == "renewal" else 14,
                evidence_required=evidence,
                status=status.value,
                escalation_rule={
                    "levels": [
                        {"after_days": 0, "notify": "owner"},
                        {"after_days": 7, "notify": "head_of_legal"},
                    ]
                },
                decision_options=["renew", "renegotiate", "terminate", "allow_to_lapse"]
                if kind == "renewal"
                else [],
            )
        )
    _counter(session, "obligation:38", len(obligations))
    session.flush()
    return contract


INBOX = [
    (
        "adaeze.obi@kanopartners.example",
        "Partnership, next steps before the summit",
        "Dear Legal,\n\nFollowing our conversation last week with Ngozi and the programme team, "
        "please conclude the partnership before 18 August so we can announce at the summit. The "
        "figure we discussed, eighteen million naira over two years, still stands.\n\n"
        "Kind regards,\nAdaeze Obi\nDirector of Partnerships, Kano Partners Ltd",
        CommunicationClass.ACTION_REQUIRED,
        0.94,
        False,
        None,
        1,
    ),
    (
        "procurement@sahelcloud.example",
        "Revised MSA attached",
        "Hello,\n\nPlease find our revised master services agreement. We have kept our standard "
        "liability and termination positions. Let us know if you need anything else.\n\n"
        "Sahel Cloud Procurement",
        CommunicationClass.POSSIBLE_CONTRACT,
        0.88,
        False,
        None,
        2,
    ),
    (
        "programme@dsn.example",
        "Update on the Kaduna rollout",
        "Team,\n\nThe Kaduna rollout is on track. Once the pilot closes we will probably need "
        "something in writing with the state ministry before we can share the household dataset "
        "with them.\n\nSegun",
        CommunicationClass.AWARENESS_ONLY,
        0.71,
        True,
        "we will probably need something in writing with the state ministry",
        6,
    ),
    (
        "no-reply@nitda.gov.example",
        "Reminder, annual data controller filing",
        "This is a reminder that annual data controller filings are due by 30 September.\n\n"
        "Nigeria Data Protection Commission",
        CommunicationClass.DEADLINE_PRESENT,
        0.96,
        False,
        None,
        3,
    ),
]


def seed_inbox(session, users, matters) -> None:
    mailbox = Mailbox(
        address="legal@dsn.example",
        entity="DSN",
        provider="microsoft_graph",
        scopes=["Mail.Read"],
        owner_id=users["Amaka Eze"].id,
        last_polled_at=NOW - timedelta(minutes=12),
    )
    session.add(mailbox)
    session.flush()

    for index, (
        sender,
        subject,
        body,
        classification,
        confidence,
        implied,
        phrase,
        age,
    ) in enumerate(INBOX):
        record = Communication(
            mailbox_id=mailbox.id,
            entity="EAI" if index < 2 else "DSN",
            external_id=f"msg-{index:04d}",
            direction="inbound",
            sender=sender,
            subject=subject,
            body=body,
            received_at=NOW - timedelta(days=age),
            classification=classification.value,
            classification_confidence=confidence,
            implied_work=implied,
            implied_work_phrase=phrase,
            proposed_matter_type="partnership" if index == 0 else None,
            proposed_priority="high" if index == 0 else "normal",
            proposed_owner_id=users["Ifeoma Chukwu"].id if index == 0 else None,
            proposed_acknowledgment=(
                "Thank you for your message. We have logged it as a legal request and a "
                "member of the legal team will come back to you with next steps and a "
                "timeline. This acknowledgment is administrative and does not constitute "
                "agreement to any term."
            )
            if index == 0
            else None,
        )
        session.add(record)
        session.flush()

        if index == 0:
            for field, value, sentence in [
                (
                    "deadline",
                    "2026-08-18",
                    "please conclude the partnership before 18 August so we can announce at the "
                    "summit",
                ),
                (
                    "counterparty",
                    "Kano Partners Ltd",
                    "Adaeze Obi, Director of Partnerships, Kano Partners Ltd",
                ),
                (
                    "apparent_requester",
                    "Ngozi Adeyemi, programme",
                    "Following our conversation last week with Ngozi and the programme team",
                ),
                (
                    "monetary_value",
                    "NGN 18,000,000",
                    "the figure we discussed, eighteen million naira over two years",
                ),
            ]:
                session.add(
                    ExtractedValue(
                        communication_id=record.id,
                        field_name=field,
                        value=value,
                        source_sentence=sentence,
                        confidence=0.92,
                    )
                )
    session.flush()


"""The capability register.

No score is seeded. A score is a measurement, and a measurement that nobody
took is not one: the register used to ship with figures typed by hand, which
is how obligation extraction came to tell a user it had failed an evaluation
that never ran. Every capability starts unmeasured, and the first real number
comes from running its golden set.
"""
CAPABILITIES = [
    (
        "inbox_classification",
        "Inbox classification",
        "M09",
        DataClass.CONFIDENTIAL,
        "tier_3",
        "Legal confirms or corrects before any matter or action is created.",
        "counsel",
        "Macro F1",
        "at least 0.90, recall at least 0.95 for action required",
        0.90,
        "inbox_classification",
        True,
    ),
    (
        "fact_extraction",
        "Deadline and fact extraction",
        "M09",
        DataClass.CONFIDENTIAL,
        "tier_3",
        "Extracted values are suggestions until confirmed field by field.",
        "counsel",
        "Precision and recall",
        "precision at least 0.95, recall at least 0.90",
        0.95,
        "extraction",
        True,
    ),
    (
        "clause_retrieval_answer",
        "Clause retrieval and grounded answer",
        "M10",
        DataClass.CONFIDENTIAL,
        "tier_4",
        "The answer must cite its sources. Counsel judges applicability.",
        "counsel",
        "Recall at 5",
        "at least 0.92",
        0.92,
        "clause_retrieval",
        True,
    ),
    (
        "ai_first_draft",
        "AI first draft",
        "M04",
        DataClass.CONFIDENTIAL,
        "tier_3",
        "Counsel reviews every clause before the draft leaves the platform.",
        "counsel",
        "Unsupported statement rate",
        "under 0.02 of clauses",
        0.98,
        "drafting",
        True,
    ),
    (
        "deviation_detection",
        "Playbook deviation detection",
        "M05",
        DataClass.CONFIDENTIAL,
        "tier_3",
        "Counsel reviews all critical and material findings. Legal staff may clear minor "
        "findings matching pre-approved fallbacks.",
        "counsel",
        "Recall on critical deviations",
        "at least 0.95, false positives under 0.20",
        0.95,
        "deviation_detection",
        True,
    ),
    (
        "obligation_extraction",
        "Obligation extraction",
        "M08",
        DataClass.CONFIDENTIAL,
        "tier_3",
        "Legal confirms before obligations become tracked tasks.",
        "counsel",
        "Recall on dated obligations",
        "at least 0.93",
        0.93,
        "obligation_extraction",
        False,
    ),
    (
        "conversation_title",
        "Conversation title",
        "M10",
        DataClass.CONFIDENTIAL,
        "tier_4",
        "Naming a saved thread. Anyone may rename it, and nothing depends on the name.",
        "counsel",
        "Not measured",
        "no gate, the output makes no claim about the record",
        None,
        None,
        False,
    ),
    (
        "management_summary",
        "Management summary",
        "M12",
        DataClass.INTERNAL,
        "tier_4",
        "The legal lead signs off the summary before it is issued.",
        "head_of_legal",
        "Groundedness",
        "at least 0.95 attributable",
        0.95,
        "summary",
        True,
    ),
]


def seed_capabilities(session, users) -> None:
    admin = users["Emeka Obi"]
    for (
        code,
        name,
        module,
        data_class,
        tier,
        requirement,
        role,
        metric,
        gate_text,
        threshold,
        golden_set,
        enforced,
    ) in CAPABILITIES:
        session.add(
            Capability(
                code=code,
                name=name,
                module=module,
                purpose=requirement,
                owner_id=admin.id,
                max_data_class=data_class.value,
                tier_ceiling=tier,
                human_requirement=requirement,
                confirming_role=role,
                state=CapabilityState.ENABLED.value,
                disabled_reason=None,
                metric_name=metric,
                gate_expression=gate_text,
                gate_threshold=threshold,
                last_score=None,
                last_score_label=None,
                last_evaluated_at=None,
                golden_set=golden_set,
                gate_enforced=enforced,
                prompt_reference=f"prompts/{code}@v1",
                tools_allowed=[],
            )
        )
    session.flush()


GOLDEN_SETS = [
    (
        "inbox_classification",
        "inbox_classification",
        "Correspondence drawn from the shared legal mailbox, classified by "
        "legal staff and reviewed by the legal lead.",
        [
            (
                "GC-INB-001",
                "From: procurement@dsn.example\nSubject: Signed MSA back from Kairos\n\n"
                "Attached is the countersigned master services agreement. Please file it.",
                {"classification": "possible_contract"},
            ),
            (
                "GC-INB-002",
                "From: regulator@ndpc.gov.ng\nSubject: Response required by 14 March\n\n"
                "We require your response to the enquiry below no later than 14 March.",
                {"classification": "deadline_present"},
            ),
            (
                "GC-INB-003",
                "From: people@dsn.example\nSubject: Office closed on Monday\n\n"
                "For information only. The office is closed for the public holiday.",
                {"classification": "awareness_only"},
            ),
            (
                "GC-INB-004",
                "From: cto@eai.example\nSubject: Data leaving Nigeria\n\n"
                "The new vendor stores training data in Frankfurt. Is that a problem "
                "for the participants whose CVs we processed?",
                {"classification": "privacy_issue"},
            ),
            (
                "GC-INB-005",
                "From: finance@dsn.example\nSubject: Please review before Friday\n\n"
                "Can Legal look at the attached statement of work and tell us whether "
                "we can sign it.",
                {"classification": "action_required"},
            ),
            (
                "GC-INB-006",
                "From: ops@dsn.example\nSubject: Kairos support is degrading\n\n"
                "Third outage this quarter and their response times are outside what "
                "we agreed. Renewal is in May.",
                {"classification": "vendor_issue"},
            ),
            (
                "GC-INB-007",
                "From: unknown@example.com\nSubject: FW: FW: re\n\nSee below.",
                {"classification": "unclear"},
            ),
            (
                "GC-INB-008",
                "From: programme@dsn.example\nSubject: Grant reporting deadline\n\n"
                "The funder needs the compliance certificate by 30 April at the latest.",
                {"classification": "deadline_present"},
            ),
        ],
    ),
    (
        "extraction",
        "fact_extraction",
        "Messages with the facts a person confirmed afterwards, field by field.",
        [
            (
                "GC-EXT-001",
                "From: procurement@dsn.example\n\nKairos Technologies Limited have come "
                "back on the MSA. They need it signed by 12 May 2026. The annual value "
                "is 45,000,000 naira.",
                {
                    "values": [
                        {"field_name": "counterparty", "value": "Kairos Technologies Limited"},
                        {"field_name": "deadline", "value": "2026-05-12"},
                        {"field_name": "monetary_value", "value": "45,000,000 naira"},
                    ]
                },
            ),
            (
                "GC-EXT-002",
                "From: adaeze.okafor@dsn.example\n\nThe data processing agreement with "
                "Lumen Analytics has to be in place before the pilot starts on "
                "1 June 2026.",
                {
                    "values": [
                        {"field_name": "counterparty", "value": "Lumen Analytics"},
                        {"field_name": "deadline", "value": "2026-06-01"},
                    ]
                },
            ),
            (
                "GC-EXT-003",
                "From: finance@eai.example\n\nWe owe Bright Path Consulting the second "
                "milestone of 8,500,000 naira once the model card is delivered.",
                {
                    "values": [
                        {"field_name": "counterparty", "value": "Bright Path Consulting"},
                        {"field_name": "monetary_value", "value": "8,500,000 naira"},
                        {"field_name": "deliverable", "value": "model card"},
                    ]
                },
            ),
            (
                "GC-EXT-004",
                "From: legal@dsn.example\n\nNothing is due yet. I will confirm the date "
                "once the sponsor replies.",
                {"values": []},
            ),
            (
                "GC-EXT-005",
                "From: partnerships@dsn.example\n\nThe memorandum of understanding with "
                "Federal University of Technology Minna needs review. No deadline.",
                {
                    "values": [
                        {
                            "field_name": "counterparty",
                            "value": "Federal University of Technology Minna",
                        }
                    ]
                },
            ),
        ],
    ),
    (
        "clause_retrieval",
        "clause_retrieval_answer",
        "Questions counsel has asked of the record, with the clauses that actually answer them.",
        [
            (
                "GC-RET-001",
                "What is our house position on limitation of liability?",
                {"references": ["CLS-LIABILITY-v2.0"]},
            ),
            (
                "GC-RET-002",
                "How long do we allow for payment, and what have we conceded before?",
                {"references": ["CLS-PAYMENT-v1.0"]},
            ),
            (
                "GC-RET-003",
                "What do we require on data protection when personal data leaves Nigeria?",
                {"references": ["CLS-DATA-v1.0"]},
            ),
            (
                "GC-RET-004",
                "What is our position on intellectual property in a research collaboration?",
                {"references": ["CLS-IP-v1.0"]},
            ),
        ],
    ),
    (
        "drafting",
        "ai_first_draft",
        "Briefs with the approved clause library available, measuring how much "
        "of the draft is attributable to it.",
        [
            (
                "GC-DFT-001",
                "Draft a mutual non-disclosure agreement for a three-month evaluation "
                "with a Nigerian technology vendor. Nothing unusual.",
                {"maximum_unsupported": 0.02},
            ),
            (
                "GC-DFT-002",
                "Draft a services agreement for data annotation work, twelve months, "
                "monthly invoicing, no personal data involved.",
                {"maximum_unsupported": 0.02},
            ),
            (
                "GC-DFT-003",
                "Draft a data processing agreement for a vendor hosting participant "
                "records in Nigeria.",
                {"maximum_unsupported": 0.02},
            ),
        ],
    ),
    (
        "deviation_detection",
        "deviation_detection",
        "Counterparty paper with the critical deviations a reviewer confirmed.",
        [
            (
                "GC-DEV-001",
                "Clause 9. Liability. Neither party limits its liability under this "
                "agreement. Clause 12. Payment. Payment falls due 90 days after invoice.",
                {"critical_categories": ["LIABILITY"]},
            ),
            (
                "GC-DEV-002",
                "Clause 4. Data. The Supplier may transfer personal data to any "
                "jurisdiction it selects without notice. Clause 5. Term. Twelve months.",
                {"critical_categories": ["DATA"]},
            ),
            (
                "GC-DEV-003",
                "Clause 2. Fees. Payment within 30 days of invoice. Clause 7. Liability. "
                "Each party's liability is capped at the fees paid in the preceding "
                "twelve months.",
                {"critical_categories": []},
            ),
        ],
    ),
    (
        "obligation_extraction",
        "obligation_extraction",
        "Executed agreements with the dated obligations Legal confirmed.",
        [
            (
                "GC-OBL-001",
                "Clause 6. The Supplier shall deliver the quarterly service report "
                "within ten business days of each quarter end. Clause 11. Either party "
                "may terminate on 60 days written notice before 31 December 2026.",
                {
                    "dated_obligations": [
                        "quarterly service report",
                        "termination notice",
                    ]
                },
            ),
            (
                "GC-OBL-002",
                "Clause 3. The first milestone payment of 5,000,000 naira falls due on "
                "15 July 2026. Clause 8. The Supplier shall provide evidence of "
                "insurance annually on the anniversary of the effective date.",
                {
                    "dated_obligations": [
                        "first milestone payment",
                        "evidence of insurance",
                    ]
                },
            ),
        ],
    ),
    (
        "summary",
        "management_summary",
        "Reporting periods with the figures the summary is allowed to state.",
        [
            (
                "GC-SUM-001",
                "Requests received 42. Matters opened 31. Median acknowledgement "
                "3 hours. Matters past their target 4. Deviations accepted 7.",
                {"figures": ["42", "31", "3", "4", "7"]},
            ),
            (
                "GC-SUM-002",
                "Requests received 18. Matters opened 15. Median acknowledgement "
                "2 hours. Matters past their target 0. Deviations accepted 1.",
                {"figures": ["18", "15", "2", "0", "1"]},
            ),
        ],
    ),
]


def seed_golden_sets(session, users) -> None:
    """The sets the capability gates are measured against.

    Without these the register's thresholds are a declaration. With them the
    harness can disable a capability that stops meeting its own standard.
    """
    owner = users["Emeka Obi"]
    for name, capability_code, description, cases in GOLDEN_SETS:
        golden = GoldenSet(
            name=name,
            version=1,
            capability_code=capability_code,
            description=description,
            owner_id=owner.id,
            active=True,
        )
        session.add(golden)
        session.flush()
        for reference, prompt, expected in cases:
            session.add(
                GoldenCase(
                    set_id=golden.id,
                    reference=reference,
                    prompt=prompt,
                    context=[],
                    expected=expected,
                    source="Seeded from the demonstration scenario.",
                    active=True,
                )
            )
    session.flush()


KPIS = [
    (
        "LOP-KPI-01",
        "Median time to acknowledge a legal request",
        "hours",
        "Time from request submission to the acceptance transition, median over the period.",
        None,
        4,
        1,
        "down",
    ),
    (
        "LOP-KPI-02",
        "Median time from complete instructions to first draft",
        "minutes",
        "Time from acceptance to the first drafting transition, median over the period.",
        None,
        60,
        10,
        "down",
    ),
    (
        "LOP-KPI-03",
        "Median end-to-end turnaround, tier 1",
        "hours",
        "Running clock time from acceptance to execution on tier 1 matters.",
        None,
        8,
        2,
        "down",
    ),
    (
        "LOP-KPI-04",
        "Median end-to-end turnaround, tier 2",
        "days",
        "Running clock time from acceptance to execution on tier 2 matters.",
        None,
        5,
        3,
        "down",
    ),
    (
        "LOP-KPI-05",
        "Requests arriving with all mandatory fields complete",
        "per cent",
        "Share of submissions that passed validation without a returned-for-information step.",
        None,
        80,
        95,
        "up",
    ),
    (
        "LOP-KPI-06",
        "Executed contracts with complete metadata and linked obligations",
        "per cent",
        "Share of authoritative contracts with all metadata and at least one confirmed obligation.",
        None,
        85,
        98,
        "up",
    ),
    (
        "LOP-KPI-07",
        "Overdue legal tasks and obligations",
        "count",
        "Count of open obligations past their due date.",
        None,
        0,
        0,
        "down",
    ),
    (
        "LOP-KPI-08",
        "Time to produce a management update",
        "minutes",
        "Wall-clock time to generate the weekly update.",
        120,
        15,
        0,
        "down",
    ),
    (
        "LOP-KPI-09",
        "Share of legal requests entering through the portal",
        "per cent",
        "Requests created through the portal, over all matters created.",
        None,
        70,
        95,
        "up",
    ),
    (
        "LOP-KPI-10",
        "Counsel hours reclaimed per month",
        "hours",
        "Estimated from drafting and review time saved against the captured baseline.",
        0,
        30,
        80,
        "up",
    ),
]


def seed_kpis(session) -> None:
    for code, name, unit, method, baseline, phase1, phase3, direction in KPIS:
        session.add(
            Baseline(
                kpi_code=code,
                name=name,
                unit=unit,
                measurement_method=method,
                baseline_value=baseline,
                baseline_captured_on=date(2026, 2, 1) if baseline is not None else None,
                phase_1_target=phase1,
                phase_3_target=phase3,
                target_direction=direction,
            )
        )
    session.flush()


def seed_platform_config(session, users) -> None:
    admin = users["Emeka Obi"]
    session.add_all(
        [
            Connector(
                code="mail_administrative",
                name="Administrative mail",
                purpose="Acknowledgments and status notices. No substantive content.",
                direction="outbound",
                permitted_data_classes=[DataClass.PUBLIC.value, DataClass.INTERNAL.value],
                scopes=["Mail.Send on legal@dsn.example"],
                owner_id=admin.id,
                review_date=NOW + timedelta(days=90),
            ),
            Connector(
                code="notification_channel",
                name="Teams and Google Chat notification",
                purpose="Approval requests, reminders and escalations with an action link.",
                direction="outbound",
                permitted_data_classes=[
                    DataClass.PUBLIC.value,
                    DataClass.INTERNAL.value,
                    DataClass.CONFIDENTIAL.value,
                ],
                scopes=["ChannelMessage.Send"],
                owner_id=admin.id,
                review_date=NOW + timedelta(days=90),
            ),
            Connector(
                code="mailbox_ingest",
                name="Approved mailbox ingest",
                purpose="Read named mailboxes only. Personal mailboxes are never ingested.",
                direction="inbound",
                permitted_data_classes=[DataClass.CONFIDENTIAL.value],
                scopes=["Mail.Read on legal@dsn.example"],
                owner_id=admin.id,
                review_date=NOW + timedelta(days=90),
            ),
            Connector(
                code="calendar_write",
                name="Calendar write",
                purpose="Obligation and filing deadlines written as events.",
                direction="outbound",
                permitted_data_classes=[DataClass.INTERNAL.value],
                scopes=["Calendars.ReadWrite"],
                owner_id=admin.id,
                review_date=NOW + timedelta(days=90),
            ),
        ]
    )

    session.add_all(
        [
            RetentionPolicy(
                record_class="audit_event",
                retain_years=7,
                deletion_requires_approval=True,
                description="Signed, immutable, retained for at least seven years.",
            ),
            RetentionPolicy(
                record_class="executed_contract",
                retain_years=12,
                deletion_requires_approval=True,
                description="Executed agreements and their signature certificates.",
            ),
            RetentionPolicy(
                record_class="ai_interaction",
                retain_years=3,
                deletion_requires_approval=True,
                description="Interaction records, subject to minimisation.",
            ),
            RetentionPolicy(
                record_class="communication",
                retain_years=3,
                deletion_requires_approval=True,
                description="Ingested messages from approved mailboxes.",
            ),
        ]
    )

    session.flush()


def seed_governance(session, users, counterparties, matters) -> None:
    product = Product(
        entity="EAI",
        name="Triage classifier",
        purpose="Classify messages in the shared legal mailbox and propose a next step.",
        owner_id=users["Emeka Obi"].id,
        intended_users="Legal staff and counsel.",
        datasets=["legal mailbox, de-identified"],
        models=["hosted classifier"],
        approval_status="in_assessment",
    )
    session.add(product)
    session.flush()

    session.add(
        Assessment(
            reference="ASM-2026-0022",
            assessment_type=AssessmentType.AI_ASSESSMENT.value,
            title="Triage classifier, pre-release assessment",
            entity="EAI",
            product_id=product.id,
            stage=AssessmentStage.LEGAL.value,
            stage_records=[
                {
                    "stage": "product",
                    "status": "complete",
                    "owner_label": "Product",
                    "completed_at": "2026-08-04T10:00:00Z",
                    "completed_by": "Emeka Obi",
                },
                {
                    "stage": "engineering",
                    "status": "complete",
                    "owner_label": "Engineering",
                    "completed_at": "2026-08-11T14:30:00Z",
                    "completed_by": "Emeka Obi",
                },
                {"stage": "legal", "status": "in_progress", "owner_label": "Legal"},
                {
                    "stage": "business_owner",
                    "status": "not_started",
                    "owner_label": "Accountable business owner",
                },
            ],
            captured={
                "purpose": "Reduce time to identify legal work arriving by email.",
                "intended_users": "Legal staff and counsel.",
                "affected_persons": "Staff and counterparty contacts who write to the mailbox.",
                "business_owner": "legal lead",
                "data_categories": "Names, work contact details, message content.",
                "data_sources": "One named mailbox, legal@dsn.example.",
                "legal_basis": "Legitimate interest in operating the legal function.",
                "retention": "Three years, then deletion.",
                "hosting_locations": "Nigeria and Ireland.",
                "transfers": "Processing by an approved provider under contractual protections.",
                "models": "Hosted classifier through the approved route.",
                "vendors": "One approved provider.",
                "subprocessors": "None beyond the provider.",
                "connectors": "mailbox_ingest, read only, one mailbox.",
                "datasets": "De-identified message set for evaluation.",
                "material_contractual_terms": "No training on our content, zero retention.",
                "potential_harms": "A missed urgent request, or a message misrouted.",
                "bias": "Evaluated across senders and message types on the golden set.",
                "security_threats": "Prompt injection through message content.",
                "performance_limits": "Macro F1 of 0.93, recall 0.96 on action required.",
                "human_oversight": "Legal confirms or corrects every classification.",
            },
            risks=[
                {
                    "risk": "A message implying legal work is classified as awareness only.",
                    "likelihood": "medium",
                    "impact": "high",
                    "control": (
                        "Implied-work watch view with an ageing clock, separate from the queue."
                    ),
                },
                {
                    "risk": "Instruction-like content in a message is treated as an instruction.",
                    "likelihood": "medium",
                    "impact": "high",
                    "control": "Untrusted material is wrapped and neutralised, and the model layer "
                    "has no tool that can act.",
                },
            ],
            controls=[
                {
                    "control": "Human confirmation before any matter is created.",
                    "status": "in_place",
                },
                {"control": "Named mailbox only, read scope only.", "status": "in_place"},
                {
                    "control": "Monthly golden-set evaluation with an automatic kill switch.",
                    "status": "in_place",
                },
            ],
            testing_evidence=[
                {
                    "test": "Golden set, 400 messages",
                    "result": "Macro F1 0.93",
                    "date": "2026-08-12",
                },
                {
                    "test": "Adversarial set, 100 cases",
                    "result": "No successful instruction follow",
                    "date": "2026-08-12",
                },
            ],
            conditions=[
                {
                    "name": "Re-run the adversarial set before any new mailbox is added",
                    "detail": "The module cannot expand to new mailboxes until this is repeated.",
                    "satisfied": False,
                    "due_date": "2026-11-30",
                },
            ],
            review_date=date(2027, 2, 12),
        )
    )
    _counter(session, "assessment:2026", 22)

    session.add_all(
        [
            ComplianceItem(
                entity="DSN",
                requirement="Annual return to the Corporate Affairs Commission",
                statutory_reference="CAMA 2020, section 417",
                filing_date=date(2026, 9, 28),
                recurrence="annual",
                accountable_owner_id=users["Amaka Eze"].id,
                next_due_date=date(2026, 9, 28),
                lead_time_days=30,
            ),
            ComplianceItem(
                entity="DSN",
                requirement="Annual data controller filing with the NDPC",
                statutory_reference="Nigeria Data Protection Act 2023",
                filing_date=date(2026, 9, 30),
                recurrence="annual",
                accountable_owner_id=users["Fatima Bello"].id,
                next_due_date=date(2026, 9, 30),
                lead_time_days=30,
            ),
            ComplianceItem(
                entity="EAI",
                requirement="Annual return to the Corporate Affairs Commission",
                statutory_reference="CAMA 2020, section 417",
                filing_date=date(2026, 11, 14),
                recurrence="annual",
                accountable_owner_id=users["Amaka Eze"].id,
                next_due_date=date(2026, 11, 14),
                lead_time_days=30,
            ),
        ]
    )
    session.flush()


def seed_memory(session, clauses, templates, matters, contract) -> None:
    """The corpus builds itself from normal work, so this mirrors what the
    platform would have indexed by now."""
    chunks: list[MemoryChunk] = []

    for category, version in clauses.items():
        chunks.append(
            MemoryChunk(
                entity="EAI",
                source_type="clause",
                source_reference=version.reference,
                source_detail="Approved clause, house position and ranked fallbacks",
                title=f"{category}, house position",
                body=version.house_position
                + "\n\nFallbacks: "
                + " ".join(
                    f"Fallback {f['rank']}, requires {f['required_authority']}: {f['text']}"
                    for f in version.fallbacks
                )
                + f"\n\nUnacceptable: {version.unacceptable_position}",
                weight=1.4,
            )
        )
        chunks.append(
            MemoryChunk(
                entity="DSN",
                source_type="clause",
                source_reference=version.reference,
                source_detail="Approved clause, house position and ranked fallbacks",
                title=f"{category}, house position",
                body=version.house_position,
                weight=1.4,
            )
        )

    for sequence, entity, decision, reason, _alt, refs, authority, _res, _cpt, decided in DECISIONS:
        chunks.append(
            MemoryChunk(
                entity=entity,
                source_type="decision",
                source_reference=f"Decision {sequence}",
                source_detail=f"Decision record, {decided:%d %B %Y}, authority {authority}",
                title=decision,
                body=f"{decision} {reason} Clause references: {', '.join(refs)}.",
                weight=1.2,
            )
        )

    chunks.append(
        MemoryChunk(
            entity="EAI",
            source_type="contract",
            source_reference=contract.reference,
            source_detail="Executed partnership agreement, Kano Partners",
            title="Partnership agreement, Kano Partners",
            body=(
                "Executed 18 August 2026, two-year term with automatic renewal and ninety "
                "days notice. Value eighteen million Naira. Liability capped at the house "
                "position."
            ),
        )
    )
    chunks.append(
        MemoryChunk(
            entity="EAI",
            source_type="contract",
            source_reference="EAI-CON-2024-0019",
            source_detail="Research collaboration, Lagos Data Institute, clause 12.4",
            title="Research collaboration, Lagos Data Institute",
            body=(
                "Executed November 2024. Carries an uncapped indemnity for third-party "
                "intellectual property claims, accepted as an express exception by the Head "
                "of Legal and recorded in decision 44."
            ),
        )
    )
    chunks.append(
        MemoryChunk(
            entity="DSN",
            source_type="matter_paper",
            source_reference="DSN-CRP-2026-0002",
            source_detail="Restricted matter working paper",
            title="Anambra investigation working note",
            body="Restricted content. Visible only to users named on the matter.",
            restricted=True,
            matter_id=matters["DSN-CRP-2026-0002"].id,
        )
    )

    vectors = embed([f"{c.title}\n{c.body}" for c in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
    session.add_all(chunks)
    session.flush()


def seed_requests(session, users, types, counterparties) -> None:
    definitions = [
        (
            "REQ-2026-01184",
            "EAI",
            "nda_mutual",
            "Ngozi Adeyemi",
            "Mutual NDA with Harmattan Analytics",
            "CPT-0047",
            2,
            False,
        ),
        (
            "REQ-2026-01183",
            "DSN",
            "consultant_engagement",
            "Tunde Bakare",
            "Consultant engagement, Olamide Bello",
            "CPT-0080",
            5,
            False,
        ),
        (
            "REQ-2026-01181",
            "EAI",
            "their_paper",
            "Ngozi Adeyemi",
            "Sahel Cloud sent us their master services agreement",
            "CPT-0031",
            26,
            True,
        ),
        (
            "REQ-2026-01179",
            "DSN",
            "data_sharing",
            "Segun Lawal",
            "Data-sharing agreement with the Federal Ministry of Health",
            "CPT-0064",
            50,
            True,
        ),
    ]
    for reference, entity, type_code, requester, subject, cpt, age_hours, privacy in definitions:
        request_type = types[type_code]
        session.add(
            Request(
                reference=reference,
                entity=entity,
                request_type_id=request_type.id,
                requester_id=users[requester].id,
                subject=subject,
                purpose=subject,
                proposed_counterparty=counterparties[cpt].legal_name,
                counterparty_id=counterparties[cpt].id,
                required_date=TODAY + timedelta(days=7),
                value_amount=4_200_000 if type_code == "consultant_engagement" else None,
                personal_data=privacy,
                leaves_nigeria=privacy and type_code == "their_paper",
                special_category_data=privacy and type_code == "data_sharing",
                privacy_flag=privacy,
                answers={"their_paper": type_code == "their_paper"},
                status=MatterState.SUBMITTED.value,
                acknowledged_at=NOW - timedelta(hours=age_hours),
                created_at=NOW - timedelta(hours=age_hours),
            )
        )
    _counter(session, "request:2026", 1184)
    session.flush()


def run(if_empty: bool = False) -> None:
    with owner_session() as session:
        existing = session.execute(select(func.count()).select_from(Organisation)).scalar_one()
        if existing and if_empty:
            print("Seed data is already present.")
            return
        if existing:
            raise SystemExit("The database already holds data. Drop it, or run with --if-empty.")

        seed_organisations(session)
        users = seed_users(session)
        types = seed_request_types(session)
        clauses = seed_library(session, users)
        templates = seed_templates(session, users)
        counterparties = seed_counterparties(session, users)
        seed_platform_config(session, users)
        seed_capabilities(session, users)
        seed_golden_sets(session, users)
        seed_kpis(session)
        matters = seed_matters(session, users, counterparties, types, templates, clauses)
        seed_decisions(session, users, counterparties, matters)
        seed_review(session, users, matters, templates)
        contract = seed_archive(session, users, counterparties, matters)
        seed_inbox(session, users, matters)
        seed_governance(session, users, counterparties, matters)
        seed_memory(session, clauses, templates, matters, contract)
        seed_requests(session, users, types, counterparties)

        print(
            "Seeded 2 entities, "
            f"{len(users)} users, {len(types)} request types, {len(clauses)} clauses, "
            f"{len(templates)} templates, {len(counterparties)} counterparties, "
            f"{len(matters)} matters."
        )
        print("Sign in with adaeze.okafor@dsn.example and the password Lop-Demo-2026.")


if __name__ == "__main__":
    run(if_empty="--if-empty" in sys.argv)
