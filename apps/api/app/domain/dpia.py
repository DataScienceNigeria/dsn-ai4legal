"""The Data Protection Impact Assessment, as a form, M11.

One definition, held here and served to the interface, so the questions a
department lead answers and the questions the record stores are the same
questions. A form written twice is a form that disagrees with itself the first
time either copy is edited.

Two people fill this in and they are never the same person. A team lead who is
building something describes what it does with personal data; the data
protection officer reads that and says whether it is adequate, scores it, and
recommends. Keeping those apart in the structure is what lets the portal show a
lead only their part, and what makes the DPO's assessment a record of a
judgement rather than another field on a form.

The wording follows the DSN template. Where the template offers a tip, the tip
is kept as help text rather than dropped: it is what tells somebody who has not
written a DPIA before what a good answer looks like.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FieldKind = Literal["text", "long_text", "choice", "multi_choice", "boolean", "date"]


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    kind: FieldKind = "long_text"
    help_text: str | None = None
    options: tuple[str, ...] = ()
    required: bool = True
    #: Shown only when another answer makes it relevant, as "key=value".
    depends_on: str | None = None


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    intent: str
    """What this section is for, in one line. A lead filling it in should not
    have to infer why they are being asked."""

    questions: tuple[Question, ...] = ()
    #: Whether the DPO assesses this section. Document control is a fact sheet
    #: and needs no judgement; every substantive section gets one.
    assessed: bool = True


ROLE_OPTIONS = (
    "Data Controller",
    "Data Processor",
    "Sub Processor",
    "Joint Controller",
)

LAWFUL_BASIS_OPTIONS = (
    "Consent",
    "Contractual obligation",
    "Legal obligation",
    "Vital interest",
    "Public interest",
    "Legitimate interest",
)

TRANSFER_BASIS_OPTIONS = (
    "Adequacy decision, on the NDPC whitelist",
    "Standard Contractual Clauses",
    "Binding Corporate Rules",
    "Code of conduct or certification",
    "Consent of the data subject",
    "Necessary for a contract",
    "Public interest",
    "Legal claims",
    "Vital interest",
    "Benefit of the data subject",
)

RISK_GRADES = ("Low", "Medium", "High")

FINAL_DECISIONS = {
    "go_ahead": (
        "Go ahead. The processing may be carried out: the risk is remote and the "
        "recommendations are adequate."
    ),
    "modify": (
        "Modify the processing. It may be carried out subject to the fundamental "
        "modifications recommended."
    ),
    "stop": (
        "Stop the processing. It should not be carried out: the general nature of the "
        "processing presents risks that cannot be mitigated."
    ),
}

SECTIONS: tuple[Section, ...] = (
    Section(
        key="document_control",
        title="Document control",
        intent="What this assessment is about and who is answerable for it.",
        assessed=False,
        questions=(
            Question("project_name", "Project or product name", kind="text",
                     help_text="The software or AI system this assessment covers."),
            Question("project_description", "Project description",
                     help_text="A summary of the system or new process, and its purpose."),
            Question("organisation_context", "Business context",
                     help_text="Why the organisation is doing this, and for whom."),
            Question("author", "Author", kind="text",
                     help_text="The person responsible for this assessment."),
            Question("dpo_contact", "Data protection officer, name and contact", kind="text",
                     required=False),
        ),
    ),
    Section(
        key="background",
        title="General background",
        intent="Why this needs an assessment at all, and what could go wrong.",
        questions=(
            Question("why_required", "Why is a DPIA required for this process or product?",
                     help_text=(
                         "Are there high-risk indicators: large-scale processing, profiling, "
                         "automated decisions with legal effect, sensitive categories, "
                         "systematic monitoring, or vulnerable data subjects?"
                     )),
            Question("risks", "What risks does this present? Grade each one.",
                     help_text="Identify each risk separately and grade it low, medium or high."),
            Question("mitigations", "What has been done to mitigate each of those risks?"),
            Question("processing_activities", "Explain the processing activities",
                     help_text=(
                         "A systematic description, from the point the data is first "
                         "collected through to its deletion. Say who touches it and where "
                         "it goes."
                     )),
        ),
    ),
    Section(
        key="nature",
        title="Nature of the envisaged processing",
        intent="What data, from where, handled how, and in what role.",
        questions=(
            Question("our_role", "What is the organisation's role?", kind="multi_choice",
                     options=ROLE_OPTIONS,
                     help_text=(
                         "Controller determines the purposes and means. Processor acts for a "
                         "controller. Sub processor acts under a processor's instructions. "
                         "Joint controller decides purposes and means with another."
                     )),
            Question("role_rationale", "Explain the rationale for that choice"),
            Question("data_types", "What types of personal data will be collected?",
                     help_text=(
                         "For example name, address, gender, NIN, email, designation, IP "
                         "address, location data, biometric or voice data."
                     )),
            Question("data_sources", "How will the data be sourced?",
                     help_text=(
                         "From a third party's API, entered directly by the data subject, "
                         "observed by the system, or inferred."
                     )),
            Question("processing_method", "Processed automatically, manually, or both?",
                     kind="choice", options=("Automatically", "Manually", "Both")),
            Question("third_party_data", "Will data be processed from any third party?",
                     help_text="If yes, say under what contractual arrangement."),
            Question("secondary_use",
                     "Is there a risk the data is used beyond its primary purpose?",
                     help_text=(
                         "For example, using data gathered for one product to train a model "
                         "for another. If yes, say what and why."
                     )),
        ),
    ),
    Section(
        key="lawful_basis",
        title="Lawful basis",
        intent="The legal ground for processing, and the relationship it rests on.",
        questions=(
            Question("bases", "What is the lawful basis for processing?", kind="multi_choice",
                     options=LAWFUL_BASIS_OPTIONS,
                     help_text="Identify every basis that applies, not only the strongest."),
            Question("basis_rationale", "Explain why each basis applies"),
            Question("prior_relationship", "Explain any prior relationship with the data subjects",
                     required=False),
        ),
    ),
    Section(
        key="purpose",
        title="Purpose and transparency",
        intent="Why this processing is necessary, and how people are told about it.",
        questions=(
            Question("purpose", "What is the purpose of the processing, and why is it necessary?"),
            Question("alternatives", "Did you consider alternatives with less privacy risk?"),
            Question("alternatives_rejected",
                     "Why would those alternatives not achieve the purpose?"),
            Question("privacy_notice", "Will the privacy notice need updating?", kind="boolean"),
            Question("notice_alternative",
                     "If not, how will the processing be communicated to data subjects?",
                     required=False),
            Question("consent_mechanism", "If consent is the basis, how is it obtained?",
                     required=False),
            Question("consent_records", "Are records of consent kept?", kind="boolean",
                     required=False),
            Question("consent_withdrawal", "Is there a process to withdraw consent?",
                     required=False),
            Question("lia_completed",
                     "If legitimate interest is the basis, has a Legitimate Interest "
                     "Assessment been completed?", kind="boolean", required=False),
        ),
    ),
    Section(
        key="accuracy",
        title="Accuracy",
        intent="Whether the data is right, and how that is kept true.",
        questions=(
            Question("accuracy_confidence", "Are you satisfied the personal data is accurate?"),
            Question("verification",
                     "Where the data does not come from the data subject, what steps verify it?",
                     required=False),
        ),
    ),
    Section(
        key="minimisation",
        title="Data minimisation and retention",
        intent="How little is held, for how long, and how it leaves.",
        questions=(
            Question("minimisation", "What has been done to minimise the personal data processed?"),
            Question("retention_period", "How long will the data be kept, and why?"),
            Question("deletion",
                     "How will deletion at the end of the retention period be ensured?"),
            Question("schedule_update", "Does the retention and disposal schedule need updating?",
                     kind="boolean"),
        ),
    ),
    Section(
        key="security",
        title="Integrity and confidentiality",
        intent="Where the data lives and what protects it.",
        questions=(
            Question("storage_location", "Where will the personal data be stored?"),
            Question("security_measures", "What measures keep the personal data secure?"),
            Question("cyber_assessment", "Has a cybersecurity assessment been carried out?",
                     kind="boolean"),
            Question("staff_measures",
                     "What policies, training or instructions will enable staff to operate "
                     "the system safely?"),
        ),
    ),
    Section(
        key="accountability",
        title="Accountability",
        intent="Who answers for this data inside the organisation.",
        questions=(
            Question("responsible_person", "Who is responsible for the personal data?",
                     kind="text",
                     help_text="Somebody on the executing team, named."),
            Question("ropa_updated",
                     "Has the Record of Processing Activities been updated for this?",
                     kind="boolean"),
            Question("dpa_signed",
                     "Where a processor or third party is involved, is a written data "
                     "processing agreement in place?",
                     help_text=(
                         "It may be a separate agreement or a schedule inside the commercial "
                         "contract. Say which, and name the counterparty."
                     )),
        ),
    ),
    Section(
        key="rights",
        title="Individual rights",
        intent="What a data subject can actually make happen, and how.",
        questions=(
            Question("access", "How can data subjects get access to their personal data?"),
            Question("rectification", "How can they update or correct inaccurate data?"),
            Question("restriction", "Can processing be restricted on request? Explain how."),
            Question("objection", "Can processing be stopped on request? Explain how."),
            Question("portability",
                     "Can the data be extracted and transmitted in a structured, commonly "
                     "used, machine-readable format?"),
            Question("erasure", "Can the data be erased on request? Explain how."),
        ),
    ),
    Section(
        key="transfers",
        title="Cross-border data transfers",
        intent="Whether the data leaves Nigeria, and what makes that lawful.",
        questions=(
            Question("transfers_abroad", "Will data be transferred outside Nigeria?",
                     kind="boolean"),
            Question("destination_countries", "Which countries?", kind="text",
                     required=False, depends_on="transfers_abroad=true"),
            Question("transfer_basis", "Legal justification for the transfer", kind="multi_choice",
                     options=TRANSFER_BASIS_OPTIONS, required=False,
                     depends_on="transfers_abroad=true"),
            Question("non_whitelist_measures",
                     "If the destination is not on the NDPC whitelist, what legal and "
                     "technical measures protect the data there?",
                     required=False, depends_on="transfers_abroad=true",
                     help_text=(
                         "Name the country's data protection law if it has one, and the "
                         "contractual measures in place."
                     )),
            Question("transfer_risks",
                     "What are the potential risks to data subjects from the transfer?",
                     required=False, depends_on="transfers_abroad=true",
                     help_text="For example unauthorised access, misuse, or loss of redress."),
            Question("grievance_mechanism",
                     "How can data subjects raise a grievance in the destination country?",
                     required=False, depends_on="transfers_abroad=true"),
            Question("retain_locally",
                     "How practical would it be to keep the data in Nigeria?",
                     required=False, depends_on="transfers_abroad=true"),
            Question("public_function",
                     "Is the processing for a public service or an inherently governmental "
                     "function?", kind="boolean", required=False),
            Question("breach_risk",
                     "What is the risk of a breach in the destination country, considering "
                     "state and non-state actors?",
                     required=False, depends_on="transfers_abroad=true"),
        ),
    ),
    Section(
        key="vulnerabilities",
        title="Identified vulnerabilities",
        intent="Whether these particular people are at more risk than most.",
        questions=(
            Question("vulnerability_index",
                     "Describe the data subjects' vulnerability",
                     help_text=(
                         "Are any of them at peculiar risk by reason of age, health, "
                         "literacy, income, immigration status, or any other circumstance?"
                     )),
        ),
    ),
    Section(
        key="disparate_outcome",
        title="Potential disparate outcome",
        intent="Whether the processing could land differently on different groups.",
        questions=(
            Question("rights_impact",
                     "Is the processing likely to affect the fundamental rights of data "
                     "subjects?", kind="boolean"),
            Question("disparate_mitigation",
                     "If so, what is being done to mitigate that?",
                     required=False,
                     help_text=(
                         "A survey of a disadvantaged group for a good cause can still "
                         "expose that group if the data is later linked back to them."
                     )),
        ),
    ),
)

SECTIONS_BY_KEY: dict[str, Section] = {section.key: section for section in SECTIONS}

ASSESSED_SECTIONS: tuple[str, ...] = tuple(s.key for s in SECTIONS if s.assessed)


@dataclass
class Completeness:
    answered: int
    required: int
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def _visible(question: Question, answers: dict) -> bool:
    """Whether a conditional question is being asked at all."""
    if not question.depends_on:
        return True
    key, _, expected = question.depends_on.partition("=")
    given = answers.get(key)
    if expected == "true":
        return given is True or str(given).lower() == "true"
    return str(given).lower() == expected.lower()


def completeness(answers: dict) -> Completeness:
    """What is still missing, by question label.

    Counted by label rather than key because the answer to it is read by a
    person: "Where will the personal data be stored?" tells them what to go
    and write, and "security.storage_location" does not.
    """
    answered = 0
    required = 0
    missing: list[str] = []

    for section in SECTIONS:
        for question in section.questions:
            if not question.required or not _visible(question, answers):
                continue
            required += 1
            value = answers.get(question.key)
            if value in (None, "", [], {}):
                missing.append(f"{section.title}: {question.label}")
            else:
                answered += 1

    return Completeness(answered=answered, required=required, missing=missing)
