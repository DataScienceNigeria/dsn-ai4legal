"""Contracts, approvals, signature and obligations, M07 and M08."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain import lifecycle
from app.domain.enums import ApprovalDecision, ObligationStatus

if TYPE_CHECKING:
    from app.db.models.counterparty import Counterparty
    from app.db.models.matter import Matter


class Contract(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A proposed or executed agreement. One matter may hold several."""

    __tablename__ = "contract"

    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("matter.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL"), index=True
    )
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int | None] = mapped_column(Integer)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    renewal_type: Mapped[str] = mapped_column(String(32), default="none")
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    value_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    value_currency: Mapped[str] = mapped_column(String(3), default="NGN")
    governing_law: Mapped[str] = mapped_column(String(64), default="Nigeria")
    signature_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    executed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("document.id", ondelete="SET NULL", use_alter=True),
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    signature_certificate: Mapped[dict] = mapped_column(JSONB, default=dict)
    executed_outside_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_reason: Mapped[str | None] = mapped_column(Text)
    amends_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    """The agreement this one changes.

    The column existed and nothing wrote it, because there was no way to raise a
    variation. There is now: an approved change request opens its own matter,
    which drafts, approves, signs and executes like any other, and the contract
    it produces points here. The original is not edited. A varied agreement is
    two documents and the register has to show both, because what was true last
    March was true under the paper that existed last March.
    """

    authoritative: Mapped[bool] = mapped_column(Boolean, default=False)

    # The register, section 14 of the guide.
    #
    # The columns above are the deal. These are how the organisation finds and
    # runs it afterwards, and their absence is why the register lived in a
    # spreadsheet: a contract with no named owner and no recorded department is
    # one nobody can be asked about.
    status: Mapped[str] = mapped_column(String(24), default="executed", nullable=False, index=True)
    user_department: Mapped[str | None] = mapped_column(String(128))
    contract_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    payment_terms: Mapped[str | None] = mapped_column(Text)
    key_deliverables: Mapped[str | None] = mapped_column(Text)
    milestones: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    termination_deadline: Mapped[date | None] = mapped_column(Date)
    """The last day notice can be given. Derived from the end date and the
    notice period when both are known, and overridable, because a contract that
    names a specific date in words beats the arithmetic."""

    remarks: Mapped[str | None] = mapped_column(Text)

    closure_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_note: Mapped[str | None] = mapped_column(Text)

    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )

    # Read-only, and viewonly for that reason: an agreement belongs to its
    # matter and its counterparty, and neither is edited from this side. The
    # renewal task already assumed contract.matter existed and raised an
    # AttributeError on every contract instead.
    matter: Mapped["Matter"] = relationship("Matter", viewonly=True)
    counterparty: Mapped["Counterparty | None"] = relationship("Counterparty", viewonly=True)
    contract_owner: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[contract_owner_id], lazy="joined", viewonly=True
    )

    issues: Mapped[list["ContractIssue"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    change_requests: Mapped[list["ContractChangeRequest"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    closure_items: Mapped[list["ContractClosureItem"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )

    @property
    def contract_owner_name(self) -> str | None:
        return self.contract_owner.name if self.contract_owner else None

    @property
    def open_issue_count(self) -> int:
        return sum(1 for issue in self.issues if issue.status not in lifecycle.ISSUE_SETTLED)

    @property
    def open_change_count(self) -> int:
        return sum(
            1 for change in self.change_requests if change.decision in lifecycle.CHANGE_OPEN
        )

class Approval(UUIDPrimaryKey, Timestamped, Base):
    """Approval binds to a document content hash (PRD LOP-M07-US-03)."""

    __tablename__ = "approval"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("matter.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("approval_chain_definition.id", ondelete="SET NULL")
    )
    chain_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_mode: Mapped[str] = mapped_column(String(16), default="sequential")
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    approver_role: Mapped[str | None] = mapped_column(String(32))
    delegate_used_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decision: Mapped[str] = mapped_column(
        String(16), default=ApprovalDecision.PENDING.value, nullable=False, index=True
    )
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_by_event: Mapped[str | None] = mapped_column(String(255))

class SignatureRequest(UUIDPrimaryKey, Timestamped, Base):
    """Controlled execution. Cannot be issued for an unapproved hash."""

    __tablename__ = "signature_request"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="RESTRICT"), nullable=False
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="internal")
    external_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    signers: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="sent", index=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_certificate: Mapped[dict] = mapped_column(JSONB, default=dict)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

class Obligation(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A tracked duty arising from a contract or a statutory requirement.

    Proposals show the clause they came from and become tasks only when Legal
    confirms them (PRD LOP-M08-US-02).
    """

    __tablename__ = "obligation"

    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), index=True
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE")
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("assessment.id", ondelete="CASCADE")
    )
    compliance_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("compliance_item.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    obligation_type: Mapped[str] = mapped_column(String(32), default="deliverable")
    source_clause: Mapped[str | None] = mapped_column(String(64))
    source_quote: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    recurrence: Mapped[str] = mapped_column(String(24), default="none")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14)
    escalation_rule: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(512))
    evidence_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=ObligationStatus.PROPOSED.value, nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decision_options: Mapped[list[str]] = mapped_column(JSONB, default=list)
    decision_taken: Mapped[str | None] = mapped_column(String(32))
    interaction_id: Mapped[str | None] = mapped_column(String(64))

    contract: Mapped[Contract | None] = relationship(back_populates="obligations")


class ContractIssue(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """Something has gone wrong, or looks like it is about to.

    Section 15 of the guide: the user department runs the contract day to day
    and tells Legal promptly about potential breaches, disputes, material
    changes, early termination, renewal and significant performance concerns.
    Before this there was no channel for any of it. The department that noticed
    a problem had an email address and Legal had a memory.

    Raised by whoever noticed, categorised so a pattern is visible across a
    portfolio, assigned to somebody in Legal, and settled only when a written
    resolution says what was done. Evidence is a file rather than a paragraph,
    because a missed milestone is proved by the delivery note.
    """

    __tablename__ = "contract_issue"

    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_on: Mapped[date | None] = mapped_column(Date)

    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    """The file that proves it. A delivery note, a bank statement, the email
    thread. Kept as a document so it inherits retention, the legal hold and the
    access rules rather than sitting in an attachment nobody can find."""

    evidence_note: Mapped[str | None] = mapped_column(Text)

    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)

    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract_change_request.id", ondelete="SET NULL",
                                        use_alter=True)
    )
    """Where the answer to the issue was to change the paper. A dispute about
    scope is often resolved by varying the scope, and the two records should say
    so to each other rather than being reconstructed later from dates."""

    contract: Mapped[Contract] = relationship(back_populates="issues")
    raised_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[raised_by_id], lazy="joined", viewonly=True
    )
    assignee: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[assignee_id], lazy="joined", viewonly=True
    )

    @property
    def raised_by_name(self) -> str | None:
        return self.raised_by.name if self.raised_by else None

    @property
    def assignee_name(self) -> str | None:
        return self.assignee.name if self.assignee else None

    @property
    def settled(self) -> bool:
        return self.status in lifecycle.ISSUE_SETTLED


class ContractChangeRequest(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A request to change an executed agreement.

    Section 16: no material change is implemented informally. The department
    submits the change and its rationale, Legal determines which instrument
    carries it, and the executed change is archived with the original and
    reflected in the register.

    The important decision here is that an approved change **opens a new
    matter** rather than editing the contract. A variation is a document that
    has to be drafted, approved, signed and executed like any other, and the
    agreement that governed last March has to keep saying what it said. So the
    original is untouched, the new matter runs the ordinary pipeline, and the
    contract it produces points back through ``amends_contract_id``.
    """

    __tablename__ = "contract_change_request"

    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_changes: Mapped[str] = mapped_column(Text, nullable=False)

    # What it costs and what it moves. Both optional, because a change of
    # registered address costs nothing and moves nothing, and both structured,
    # because "there is a financial impact" in a paragraph cannot be totalled.
    financial_effect: Mapped[str | None] = mapped_column(String(16))
    """increase, decrease, none, or unknown."""

    value_delta: Mapped[float | None] = mapped_column(Numeric(18, 2))
    value_currency: Mapped[str | None] = mapped_column(String(3))
    financial_note: Mapped[str | None] = mapped_column(Text)

    timeline_effect: Mapped[str | None] = mapped_column(String(16))
    """extends, shortens, none, or unknown."""

    proposed_end_date: Mapped[date | None] = mapped_column(Date)
    timeline_note: Mapped[str | None] = mapped_column(Text)

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )

    instrument: Mapped[str | None] = mapped_column(String(24))
    """Legal's determination: amendment, addendum, variation, restatement, or
    none. The requester says what they want to happen; which paper carries it is
    a legal question and is answered here."""

    decision: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False, index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resulting_matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL"), index=True
    )
    """The matter opened to carry the change. Present once Legal approves and an
    instrument is required; absent where the determination was that no paper is
    needed, which is a real outcome and not an unfinished one."""

    contract: Mapped[Contract] = relationship(back_populates="change_requests")
    requested_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[requested_by_id], lazy="joined", viewonly=True
    )

    @property
    def requested_by_name(self) -> str | None:
        return self.requested_by.name if self.requested_by else None


class ContractClosureItem(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """One line of the closure checklist, for one contract.

    Section 17. The checklist is defined once in ``domain/lifecycle.py`` and
    materialised per contract when closure opens, the same way the DPIA form is
    defined once and answered per assessment. Rows rather than a JSON blob
    because each line is confirmed by a named person on a date with a file
    attached, and that is a record, not a field.

    A contract does not reach ``closed`` while a required line is outstanding.
    The line that matters most is the return or deletion of personal data: the
    Act requires it, the agreement will have said so, and it is the one item on
    the list that is a legal duty rather than housekeeping.
    """

    __tablename__ = "contract_closure_item"
    __table_args__ = (UniqueConstraint("contract_id", "item_key", name="uq_closure_item"),)

    contract_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    group_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24), default="outstanding", nullable=False, index=True
    )

    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    evidence_reference: Mapped[str | None] = mapped_column(String(512))
    note: Mapped[str | None] = mapped_column(Text)
    """On a confirmed item, what was done. On an inapplicable one, why it does
    not apply, which is required: a line dismissed without a reason is a line
    nobody read."""

    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contract: Mapped[Contract] = relationship(back_populates="closure_items")
    confirmed_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[confirmed_by_id], lazy="joined", viewonly=True
    )

    @property
    def confirmed_by_name(self) -> str | None:
        return self.confirmed_by.name if self.confirmed_by else None

    @property
    def definition(self) -> lifecycle.ClosureItem | None:
        return lifecycle.ITEMS_BY_KEY.get(self.item_key)
