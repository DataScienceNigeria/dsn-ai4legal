"""Domain vocabulary.

The values here are the contract between the database, the API and the user
interface. They are taken directly from the PRD so that a reader can trace any
value back to a numbered section.
"""

from enum import StrEnum


class Entity(StrEnum):
    """PRD section 8.3, entity prefixes."""

    DSN = "DSN"
    EAI = "EAI"

class Role(StrEnum):
    """PRD section 5.2, roles and permissions model."""

    REQUESTER = "requester"
    MANAGEMENT = "management"
    LEGAL_OPS = "legal_ops"
    COUNSEL = "counsel"
    HEAD_OF_LEGAL = "head_of_legal"
    PRIVACY = "privacy"
    ADMIN = "admin"
    AUDITOR = "auditor"
    COUNTERPARTY = "counterparty"

LEGAL_ROLES: frozenset[Role] = frozenset(
    {Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN}
)

class MatterState(StrEnum):
    """PRD section 8.2, matter state model."""

    SUBMITTED = "submitted"
    RETURNED_FOR_INFORMATION = "returned_for_information"
    IN_TRIAGE = "in_triage"
    ACCEPTED = "accepted"
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    IN_APPROVAL = "in_approval"
    AWAITING_SIGNATURE = "awaiting_signature"
    EXECUTED = "executed"
    ACTIVE = "active"
    AMENDED = "amended"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    ARCHIVED = "archived"
    ON_HOLD = "on_hold"
    CLOSED_WITHOUT_MATTER = "closed_without_matter"

class RiskTier(StrEnum):
    """PRD section 14.1. Ordering matters: the highest triggered tier wins."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"

TIER_RANK: dict[RiskTier, int] = {
    RiskTier.TIER_1: 1,
    RiskTier.TIER_2: 2,
    RiskTier.TIER_3: 3,
    RiskTier.TIER_4: 4,
}

RANK_TIER: dict[int, RiskTier] = {v: k for k, v in TIER_RANK.items()}

class DataClass(StrEnum):
    """PRD section 9.2, data classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

CLASS_RANK: dict[DataClass, int] = {
    DataClass.PUBLIC: 0,
    DataClass.INTERNAL: 1,
    DataClass.CONFIDENTIAL: 2,
    DataClass.RESTRICTED: 3,
}

class VersionStatus(StrEnum):
    """PRD section 7.3, template and clause version lifecycle."""

    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"

class Severity(StrEnum):
    """PRD section 7.6, deviation severity."""

    CRITICAL = "critical"
    MATERIAL = "material"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"

class AuthorityLevel(StrEnum):
    """PRD section 14.3, authority to concede."""

    HOUSE = "house"
    FALLBACK_1 = "fallback_1"
    FALLBACK_2 = "fallback_2"
    FALLBACK_3 = "fallback_3"
    OUTSIDE = "outside"

AUTHORITY_MATRIX: dict[AuthorityLevel, dict[str, object]] = {
    AuthorityLevel.HOUSE: {
        "roles": [Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL],
        "decision_record": False,
        "residual_risk": False,
        "library_review": False,
        "label": "Any authorised user on the matter",
    },
    AuthorityLevel.FALLBACK_1: {
        "roles": [Role.COUNSEL, Role.HEAD_OF_LEGAL],
        "decision_record": True,
        "residual_risk": False,
        "library_review": False,
        "label": "Counsel",
    },
    AuthorityLevel.FALLBACK_2: {
        "roles": [Role.HEAD_OF_LEGAL],
        "decision_record": True,
        "residual_risk": False,
        "library_review": False,
        "label": "Head of Legal",
    },
    AuthorityLevel.FALLBACK_3: {
        "roles": [Role.HEAD_OF_LEGAL],
        "decision_record": True,
        "residual_risk": True,
        "library_review": False,
        "label": "Head of Legal plus accountable business owner",
    },
    AuthorityLevel.OUTSIDE: {
        "roles": [Role.HEAD_OF_LEGAL],
        "decision_record": True,
        "residual_risk": True,
        "library_review": True,
        "label": "Head of Legal plus executive sponsor",
    },
}

class ApprovalDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    #: The requester wants something different, not something refused. It goes
    #: back to drafting with their comment attached and their step stays open,
    #: because they have not decided yet. Rejection is a different act and says
    #: a different thing to everyone reading the matter afterwards.
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"

class ObligationStatus(StrEnum):
    PROPOSED = "proposed"
    OPEN = "open"
    COMPLETED = "completed"
    WAIVED = "waived"
    REJECTED = "rejected"

class DocumentType(StrEnum):
    DRAFT = "draft"
    #: Their paper, not ours. Kept apart from every other type because nothing
    #: in it came from an approved clause, so it may never be approved, signed
    #: or presented as house position.
    COUNTERPARTY = "counterparty"
    REDLINE = "redline"
    EXECUTED = "executed"
    EVIDENCE = "evidence"
    CORRESPONDENCE = "correspondence"

class CommunicationClass(StrEnum):
    """PRD section 7.9, the fixed inbox classification set."""

    ACTION_REQUIRED = "action_required"
    DEADLINE_PRESENT = "deadline_present"
    AWARENESS_ONLY = "awareness_only"
    POSSIBLE_CONTRACT = "possible_contract"
    PRIVACY_ISSUE = "privacy_issue"
    VENDOR_ISSUE = "vendor_issue"
    UNCLEAR = "unclear"

class AssessmentType(StrEnum):
    DPIA = "dpia"
    AI_ASSESSMENT = "ai_assessment"

class AssessmentStage(StrEnum):
    """PRD section 7.11, assessments are workflows rather than forms."""

    INITIATED = "initiated"
    PRODUCT = "product"
    ENGINEERING = "engineering"
    LEGAL = "legal"
    BUSINESS_OWNER = "business_owner"
    CLOSED = "closed"

ASSESSMENT_STAGE_ORDER: list[AssessmentStage] = [
    AssessmentStage.INITIATED,
    AssessmentStage.PRODUCT,
    AssessmentStage.ENGINEERING,
    AssessmentStage.LEGAL,
    AssessmentStage.BUSINESS_OWNER,
    AssessmentStage.CLOSED,
]

class CapabilityState(StrEnum):
    """PRD section 13.2 and 16.3. A capability below its gate does not run."""

    ENABLED = "enabled"
    SHADOW = "shadow"
    DISABLED = "disabled"

class HumanDecision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
