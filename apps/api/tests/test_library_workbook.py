import io

from openpyxl import Workbook

from app.services import library_workbook as wb

SERVICE = "Service Agreement - General"
DSN = "Data Scientists Network Foundation (Data Science Nigeria)"
APPROVED = "Approved template wording"


def _workbook(library: list[list], playbook: list[list]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for title, columns, rows in (
        (wb.PLAYBOOK_SHEET, wb.PLAYBOOK_COLUMNS, playbook),
        (wb.LIBRARY_SHEET, wb.LIBRARY_COLUMNS, library),
    ):
        sheet = book.create_sheet(title)
        sheet.append([])
        sheet.append([title])
        sheet.append([])
        sheet.append([])
        sheet.append(columns)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_rows_become_a_plan_and_every_problem_is_reported_on_its_row():
    library = [
        [
            "CLS-TPL-001",
            "CLV-DSN-SAG-001",
            DSN,
            SERVICE,
            "Organisation",
            "Confidentiality",
            "Confidentiality",
            "Each party keeps the other's information confidential.",
            APPROVED,
            "https://example.sharepoint.com/a.docx",
        ],
        [
            "CLS-TPL-002",
            "CLV-BOTH-SAG-002",
            "Both entities",
            "All agreements",
            "All roles",
            "Standard terms",
            "Assignment",
            "Neither party may assign.",
            APPROVED,
            "",
        ],
        [
            "CLS-TPL-003",
            "",
            "Not classified",
            "Other",
            "Organisation",
            "Payment",
            "Fees",
            "Fees are payable.",
            "Reference wording",
            "",
        ],
        [
            "CLS-TPL-001",
            "CLV-DSN-SAG-001",
            DSN,
            SERVICE,
            "Organisation",
            "Confidentiality",
            "Confidentiality",
            "A second copy.",
            APPROVED,
            "http://insecure.example",
        ],
    ]
    playbook = [
        [
            DSN,
            SERVICE,
            "Organisation",
            "Confidentiality",
            "Confidentiality",
            "Keep it confidential.",
            "Three years.",
            "Two years.",
            "Perpetual one-way duty.",
            "CLS-TPL-001",
            "CLV-DSN-SAG-001",
        ],
        [
            DSN,
            SERVICE,
            "Organisation",
            "Confidentiality",
            "Confidentiality",
            "Keep it confidential.",
            "Five years.",
            "Two years.",
            "Perpetual one-way duty.",
            "CLS-TPL-001",
            "CLV-DSN-SAG-001",
        ],
        [
            "Both entities",
            "All agreements",
            "All roles",
            "Standard terms",
            "Assignment",
            "No assignment without consent.",
            "",
            "",
            "",
            "CLS-TPL-002",
            "CLV-BOTH-SAG-002",
        ],
    ]

    checked = wb.check(_workbook(library, playbook))
    errors = {(i.sheet, i.row, i.column) for i in checked.issues if i.level == "error"}

    assert errors == {
        (wb.LIBRARY_SHEET, 8, "Entity"),
        (wb.LIBRARY_SHEET, 9, "Clause version ID"),
        (wb.LIBRARY_SHEET, 9, "Source"),
        (wb.PLAYBOOK_SHEET, 7, None),
    }
    assert any(
        i.level == "warning" and i.row == 8 for i in checked.issues if i.sheet == wb.PLAYBOOK_SHEET
    )

    plan = checked.plan
    confidentiality = next(v for v in plan["variants"] if v["code"] == "CLV-DSN-SAG-001")
    assert confidentiality["standard_position"] == "Keep it confidential."
    assert [f["required_authority"] for f in confidentiality["fallbacks"]] == [
        "fallback_1",
        "fallback_2",
    ]
    assert confidentiality["unacceptable_position"] == "Perpetual one-way duty."

    (service,) = plan["playbooks"]
    assert (service["entity"], service["agreement_type"], service["subtype"]) == (
        "DSN",
        "service_agreement",
        "General",
    )
    assert [r["variant"] for r in service["required_clauses"]] == [
        "CLV-DSN-SAG-001",
        "CLV-BOTH-SAG-002",
    ]
    assert service["required_clauses"][0]["absent_severity"] == "critical"


def test_a_sub_type_column_names_the_playbook():
    book = Workbook()
    book.remove(book.active)
    for title, columns, keys, rows in (
        (
            wb.PLAYBOOK_SHEET,
            wb.PLAYBOOK_COLUMNS,
            wb.PLAYBOOK_KEYS,
            [
                [
                    DSN,
                    "Service Agreement",
                    "AI Compute Access",
                    "Service provider",
                    "Confidentiality",
                    "Confidentiality",
                    "Keep it confidential.",
                    "",
                    "",
                    "",
                    "CLS-TPL-001",
                    "CLV-DSN-SAACA-001",
                ],
            ],
        ),
        (
            wb.LIBRARY_SHEET,
            wb.LIBRARY_COLUMNS,
            wb.LIBRARY_KEYS,
            [
                [
                    "CLS-TPL-001",
                    "CLV-DSN-SAACA-001",
                    DSN,
                    "Service Agreement",
                    "AI Compute Access",
                    "Service provider",
                    "Confidentiality",
                    "Confidentiality",
                    "Each party keeps it confidential.",
                    APPROVED,
                    "https://example.com/a",
                ],
                [
                    "CLS-TPL-002",
                    "",
                    DSN,
                    "Service Agreement - General",
                    "AI Compute Access",
                    "Service provider",
                    "Payment",
                    "Fees",
                    "Fees are payable.",
                    "Reference wording",
                    "",
                ],
            ],
        ),
    ):
        sheet = book.create_sheet(title)
        sheet.append([title])
        sheet.append([])
        sheet.append([])
        sheet.append(wb._with_subtype(columns, keys)[0])
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)

    checked = wb.check(buffer.getvalue())

    (playbook,) = checked.plan["playbooks"]
    assert (playbook["agreement_type"], playbook["subtype"]) == (
        "service_agreement",
        "AI Compute Access",
    )
    assert {(i.row, i.column) for i in checked.issues if i.level == "error"} == {(6, "Sub-type")}
