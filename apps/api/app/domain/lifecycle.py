"""What happens to a contract after it is signed.

The platform stopped at execution. An executed agreement was archived, and
nothing in the product acknowledged that most of a contract's life happens
afterwards: it is performed, it goes wrong, it is varied, and eventually it
ends and somebody has to give the data back.

Three vocabularies here, one per thing the guide asks for. Sections 15, 16 and
17 of the Guide to Engaging the Legal Team.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Section 15. What the user department has to tell Legal about.
# ---------------------------------------------------------------------------

#: The guide lists what Legal must be told about promptly: potential breaches,
#: disputes, material changes, early termination, renewal and significant
#: performance concerns. Each is a kind of issue rather than a free-text note,
#: because a category is what makes a pattern visible across a portfolio.
ISSUE_TYPES: dict[str, str] = {
    "breach": "Potential breach",
    "dispute": "Dispute",
    "performance_concern": "Performance concern",
    "delay": "Delay or missed milestone",
    "payment_issue": "Payment issue",
    "data_incident": "Data or confidentiality incident",
    "material_change": "Material change in circumstances",
    "other": "Something else",
}

#: An issue is open until somebody writes down what was done about it.
ISSUE_STATUSES: dict[str, str] = {
    "open": "Open",
    "investigating": "Being looked at",
    "escalated": "Escalated",
    "resolved": "Resolved",
    "closed_no_action": "Closed, no action needed",
}

#: Which statuses mean nobody is waiting.
ISSUE_SETTLED = frozenset({"resolved", "closed_no_action"})

#: A resolution has to say what was done. Anything shorter than this is a tick
#: rather than a record, and a tick is what the register already has.
#: What an issue turned into. Section 15 says the department reports and Legal
#: decides; it does not say what a decision produces, and an issue that ends at
#: a paragraph is a record of a problem rather than an account of what was done
#: about it. These are the four things a contract problem actually becomes,
#: plus the honest fifth.
ISSUE_OUTCOMES: dict[str, str] = {
    "none": "Nothing further, settled between the parties",
    "change_request": "A change to the paper",
    "matter": "Reopen the matter behind this agreement",
    "termination": "Termination of the agreement",
    "obligation": "A dated obligation on the other side",
}

#: Outcomes that need something more than a sentence before they can be made.
OUTCOMES_NEEDING_DETAIL: frozenset[str] = frozenset(
    {"change_request", "matter", "obligation"}
)

MIN_RESOLUTION = 15


# ---------------------------------------------------------------------------
# Section 16. Amendments and variations.
# ---------------------------------------------------------------------------

#: What the change is. Legal decides which instrument carries it; the requester
#: says what they want to happen. These are the requester's words.
CHANGE_TYPES: dict[str, str] = {
    "scope_change": "Change what is being delivered",
    "value_change": "Change the money",
    "timeline_change": "Change the dates",
    "extension": "Extend the term",
    "renewal": "Renew it",
    "early_termination": "End it early",
    "party_change": "Change a party's details",
    "other": "Something else",
}

#: The formal document Legal decides is required. The guide names the first
#: three; ``none`` is the honest fourth, because a change that turns out not to
#: touch contractual rights needs no paper and saying so is a determination.
INSTRUMENTS: dict[str, str] = {
    "amendment": "Amendment",
    "addendum": "Addendum",
    "variation": "Variation Agreement",
    "restatement": "Amended and restated agreement",
    "none": "No formal document required",
}

CHANGE_DECISIONS: dict[str, str] = {
    "pending": "With Legal",
    "approved": "Approved, paper to follow",
    "no_paper_needed": "Approved, no paper needed",
    "declined": "Declined",
    "withdrawn": "Withdrawn by the requester",
}

CHANGE_OPEN = frozenset({"pending"})

#: A rationale of three words is not a rationale. The guide requires the change
#: and its reason, and the reason is the half that survives into the amendment's
#: recitals.
MIN_RATIONALE = 20


# ---------------------------------------------------------------------------
# Section 17. Closure.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosureItem:
    """One thing that has to be true before a contract is closed."""

    key: str
    group: str
    label: str
    intent: str
    #: Whether evidence is required to confirm it. Where it is, confirming with
    #: nothing attached is refused: the whole point of the checklist is that it
    #: can be shown to somebody afterwards.
    evidence_required: bool = True
    #: Items that can honestly not apply. A contract with no personal data has
    #: no data to return, and forcing a confirmation would teach the team to
    #: tick things.
    may_not_apply: bool = True


@dataclass(frozen=True)
class ClosureGroup:
    key: str
    title: str
    intent: str
    items: list[ClosureItem] = field(default_factory=list)


CLOSURE_GROUPS: list[ClosureGroup] = [
    ClosureGroup(
        key="deliverables",
        title="Deliverables and performance",
        intent="Everything the agreement required has been produced and accepted.",
        items=[
            ClosureItem(
                key="deliverables_received",
                group="deliverables",
                label="Every deliverable has been received",
                intent="Against the scope in the executed agreement, not against memory.",
            ),
            ClosureItem(
                key="acceptance_recorded",
                group="deliverables",
                label="Acceptance has been recorded where the agreement required it",
                intent="An acceptance condition nobody signed off is an unpaid dispute waiting.",
            ),
            ClosureItem(
                key="outstanding_obligations",
                group="deliverables",
                label="No obligation is outstanding on either side",
                intent=(
                    "Read the obligations on the agreement. Anything still open is "
                    "either done or a claim."
                ),
                evidence_required=False,
                may_not_apply=False,
            ),
        ],
    ),
    ClosureGroup(
        key="payment",
        title="Payment",
        intent="The money is settled in both directions.",
        items=[
            ClosureItem(
                key="final_invoice",
                group="payment",
                label="The final invoice has been raised or received",
                intent="Whichever direction the money runs.",
            ),
            ClosureItem(
                key="payments_settled",
                group="payment",
                label="All payments due have been made",
                intent="Finance confirms. A closed contract with money owing is not closed.",
            ),
            ClosureItem(
                key="retentions_released",
                group="payment",
                label="Retentions, deposits and guarantees have been released",
                intent="Money held as security has to come back when the security ends.",
            ),
        ],
    ),
    ClosureGroup(
        key="property",
        title="Property and access",
        intent="Nothing of ours is with them, and nothing of theirs is with us.",
        items=[
            ClosureItem(
                key="assets_returned",
                group="property",
                label="Equipment, materials and assets have been returned",
                intent="Both directions. A laptop with a consultant is an asset off the register.",
            ),
            ClosureItem(
                key="access_revoked",
                group="property",
                label="System access, accounts and credentials have been revoked",
                intent=(
                    "The single most commonly missed item at closure, and the one an "
                    "auditor asks about first."
                ),
            ),
            ClosureItem(
                key="ip_handover",
                group="property",
                label="Intellectual property and deliverable handover is complete",
                intent="Source, working files and assignments, not just the finished artefact.",
            ),
        ],
    ),
    ClosureGroup(
        key="data",
        title="Data and confidential information",
        intent=(
            "Personal data returned or deleted, and confidential information "
            "accounted for. This group is a legal duty, not housekeeping."
        ),
        items=[
            ClosureItem(
                key="personal_data",
                group="data",
                label="Personal data has been returned or deleted, and it is certified",
                intent=(
                    "The Nigeria Data Protection Act requires it and the agreement will "
                    "have said so. A certificate of deletion is the evidence; an assurance "
                    "over the phone is not."
                ),
            ),
            ClosureItem(
                key="confidential_information",
                group="data",
                label="Confidential information has been returned or destroyed",
                intent="Including copies held by their subcontractors.",
            ),
            ClosureItem(
                key="subprocessors",
                group="data",
                label="Their subprocessors have done the same",
                intent="A deletion that stops at the counterparty stops short of the data.",
            ),
        ],
    ),
    ClosureGroup(
        key="surviving",
        title="Surviving obligations",
        intent=(
            "What continues after the agreement ends, so somebody knows it is "
            "still running rather than discovering it in three years."
        ),
        items=[
            ClosureItem(
                key="surviving_recorded",
                group="surviving",
                label="Surviving obligations have been identified and recorded",
                intent=(
                    "Confidentiality, non-solicitation, indemnities, audit rights and "
                    "warranty periods typically outlive the term."
                ),
                evidence_required=False,
                may_not_apply=False,
            ),
            ClosureItem(
                key="survival_owner",
                group="surviving",
                label="Somebody owns each surviving obligation",
                intent="An obligation that outlives the contract and has no owner has no owner.",
                evidence_required=False,
            ),
        ],
    ),
]

ITEMS: list[ClosureItem] = [item for group in CLOSURE_GROUPS for item in group.items]
ITEMS_BY_KEY: dict[str, ClosureItem] = {item.key: item for item in ITEMS}
GROUPS_BY_KEY: dict[str, ClosureGroup] = {group.key: group for group in CLOSURE_GROUPS}

CLOSURE_STATUSES: dict[str, str] = {
    "outstanding": "Outstanding",
    "confirmed": "Confirmed",
    "not_applicable": "Does not apply",
}


#: What a contract is doing now. The guide's register carries a status column and
#: the platform had only ``authoritative`` and a signature state, which between
#: them cannot say that an agreement is live, being varied, or winding down.
CONTRACT_STATUSES: dict[str, str] = {
    "executed": "Executed",
    "active": "Active",
    "in_closure": "Closing",
    "closed": "Closed",
    "terminated": "Terminated early",
    "lapsed": "Allowed to lapse",
    "superseded": "Superseded by a later agreement",
}

CONTRACT_LIVE = frozenset({"executed", "active", "in_closure"})


def not_applicable_needs_reason(status: str, reason: str | None) -> bool:
    """Marking something inapplicable is a judgement and has to say why."""
    return status == "not_applicable" and not (reason or "").strip()


def outstanding(rows: list) -> list:
    """Which required items are still open, for the refusal message."""
    return [
        row
        for row in rows
        if row.status == "outstanding" and ITEMS_BY_KEY.get(row.item_key) is not None
    ]
