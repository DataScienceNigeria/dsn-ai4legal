"""The agreement types the organisation actually signs.

Until now an agreement type was a free string, written independently on the
contract, the request type, the template, the playbook and the template import.
Five places invented their own vocabulary, so the library held a
``lease_agreement`` nothing could request, requests named a
``master_services_agreement`` no playbook covered, and a matter could be typed
``unknown`` and stay that way.

The list here is the one in the Guide to Engaging the Legal Team, section 3C,
and nothing else is offered. A type nobody in the organisation can name is a
type nobody can hold a position on.
"""

from __future__ import annotations

#: Code to the words the legal team uses, in the order the guide lists them.
AGREEMENT_TYPES: dict[str, str] = {
    "service_agreement": "Service Agreement",
    "consultancy_agreement": "Consultancy Agreement",
    "vendor_supplier_agreement": "Vendor or Supplier Agreement",
    "partnership_agreement": "Partnership Agreement",
    "research_collaboration_agreement": "Research or Collaboration Agreement",
    "nda_mutual": "Non-disclosure Agreement, mutual",
    "nda_one_sided": "Non-disclosure Agreement, one-sided",
    "data_sharing_agreement": "Data Sharing or Data Processing Agreement",
    "memorandum_of_understanding": "Memorandum of Understanding",
    "grant_agreement": "Grant Agreement",
    "other": "Other",
}

#: What the platform used to call things, and what each becomes.
#:
#: ``master_services_agreement`` is the guide's Service Agreement. The two NDAs
#: were one type that only ever meant the mutual one. ``consultant_engagement``
#: was the same thing as consultancy with a different noun. The rest were
#: templates somebody imported: a lease, an IP assignment and a cease and
#: desist, none of which the guide recognises, and the last of which is a letter
#: rather than an agreement at all. They land on ``other``, which is a real
#: answer, rather than being deleted along with the paper.
RENAMED: dict[str, str] = {
    "master_services_agreement": "service_agreement",
    "consultant_engagement": "consultancy_agreement",
    "lease_agreement": "other",
    "ip_assignment": "other",
    "cease_and_desist": "other",
    "unknown": "other",
}


def label(code: str | None) -> str:
    """The words for a code, falling back to the code so nothing renders blank."""
    if not code:
        return "Not yet typed"
    return AGREEMENT_TYPES.get(code, code.replace("_", " ").capitalize())


def is_known(code: str) -> bool:
    return code in AGREEMENT_TYPES


#: Grant agreements and research collaborations are how a non-profit takes money
#: in rather than pays it out, and both carry reporting duties the commercial
#: types do not. Named here so the tier rules and the playbook gap are visible
#: rather than discovered.
INBOUND_FUNDING = frozenset({"grant_agreement", "research_collaboration_agreement"})
