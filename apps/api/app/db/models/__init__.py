"""Every mapped class, imported so that metadata is complete for Alembic."""

from app.db.models.ai import AIInteraction, Baseline, Capability, EvaluationRun
from app.db.models.contract import (
    Approval,
    Contract,
    Obligation,
    SignatureRequest,
)
from app.db.models.conversation import Conversation, ConversationTurn
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
from app.db.models.intake import Attachment, Request, RequestType
from app.db.models.library import Clause, ClauseVersion, Playbook, Template, TemplateVersion
from app.db.models.matter import (
    DecisionRecord,
    Matter,
    MatterAccess,
    MatterLink,
    MatterTransition,
)
from app.db.models.organisation import ConfigSetting, Organisation, User, UserEntity
from app.db.models.platform import (
    AuditEvent,
    Connector,
    EgressLog,
    IdempotencyKey,
    MemoryChunk,
    OutboxEvent,
    RetentionPolicy,
)

__all__ = [
    "AIInteraction",
    "Approval",
    "Assessment",
    "Attachment",
    "AuditEvent",
    "Baseline",
    "Capability",
    "Clause",
    "ClauseVersion",
    "Communication",
    "ComplianceItem",
    "ConfigSetting",
    "Connector",
    "Contract",
    "Conversation",
    "ConversationTurn",
    "Counterparty",
    "DecisionRecord",
    "Document",
    "EgressLog",
    "GoldenCase",
    "GoldenSet",
    "EvaluationRun",
    "ExtractedValue",
    "IdempotencyKey",
    "Mailbox",
    "Matter",
    "MatterAccess",
    "MatterLink",
    "MatterTransition",
    "MemoryChunk",
    "Obligation",
    "Organisation",
    "OutboxEvent",
    "Playbook",
    "Product",
    "Request",
    "RequestType",
    "RetentionPolicy",
    "ReviewFinding",
    "SignatureRequest",
    "Template",
    "TemplateVersion",
    "User",
    "UserEntity",
    "Vendor",
]
