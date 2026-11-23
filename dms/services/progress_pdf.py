from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .project_control import collect_project_control


NAVY = colors.HexColor("#07192E")
CYAN = colors.HexColor("#00A9BD")
TEAL = colors.HexColor("#31D2C4")
GREEN = colors.HexColor("#16875A")
AMBER = colors.HexColor("#B66C08")
RED = colors.HexColor("#BD3944")
BLUE = colors.HexColor("#3157D5")
INK = colors.HexColor("#172337")
MUTED = colors.HexColor("#687386")
LINE = colors.HexColor("#DCE3EA")
LIGHT = colors.HexColor("#F3F6F8")
WHITE = colors.white


def _text(value):
    return str(value or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_color(status):
    return {
        "APPROVED": GREEN,
        "UNDER_REVIEW": BLUE,
        "REVISION_REQUIRED": AMBER,
        "REJECTED": RED,
        "PENDING_INSTALLATION": AMBER,
        "IN_PROGRESS": CYAN,
    }.get(status, MUTED)


def _draw_page(canvas, document):
    canvas.saveState()
    width, _ = landscape(A4)
    canvas.setStrokeColor(LINE)
    canvas.line(14 * mm, 11 * mm, width - 14 * mm, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(14 * mm, 6.8 * mm, "Triple E DWDM Document Control")
    canvas.drawRightString(
        width - 14 * mm,
        6.8 * mm,
        f"Page {document.page}",
    )
    canvas.restoreState()


def _progress_bar(value, width=54 * mm):
    value = max(0, min(int(value), 100))
    filled = max(width * value / 100, 0.2 * mm)
    remaining = max(width - filled, 0.2 * mm)
    return Table(
        [["", ""]],
        colWidths=[filled, remaining],
        rowHeights=[4 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), CYAN),
                ("BACKGROUND", (1, 0), (1, 0), LINE),
                ("BOX", (0, 0), (-1, -1), 0.25, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def build_progress_pdf(snapshot=None):
    snapshot = snapshot or collect_project_control()
    generated_at = snapshot["generated_at"]
    metrics = snapshot["metrics"]
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Triple E DWDM Project Progress",
        author="PT Triple E",
        subject="QC, ATP, and FATP document progress",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ProjectTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=WHITE,
        alignment=TA_LEFT,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ProjectSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#B7CAD9"),
    )
    heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=INK,
        spaceBefore=3 * mm,
        spaceAfter=3 * mm,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.4,
        leading=9.5,
        textColor=INK,
    )
    body_muted = ParagraphStyle(
        "BodyMuted",
        parent=body,
        textColor=MUTED,
    )
    body_center = ParagraphStyle(
        "BodyCenter",
        parent=body,
        alignment=TA_CENTER,
    )
    batch_body = ParagraphStyle(
        "BatchBody",
        parent=body,
        fontSize=6.2,
        leading=7.4,
    )
    batch_center = ParagraphStyle(
        "BatchCenter",
        parent=batch_body,
        alignment=TA_CENTER,
    )

    story = []
    hero = Table(
        [[
            Paragraph("TRIPLE E - DWDM PROJECT CONTROL", title_style),
            Paragraph(
                f"Snapshot<br/><b>{generated_at:%d %B %Y, %H:%M} WIB</b>",
                ParagraphStyle(
                    "HeroDate",
                    parent=subtitle_style,
                    alignment=TA_CENTER,
                ),
            ),
        ], [
            Paragraph(
                "QC, ATP, and FATP progress by physical site and installation batch.",
                subtitle_style,
            ),
            "",
        ]],
        colWidths=[220 * mm, 45 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("SPAN", (1, 0), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 7 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
                ("LINEBELOW", (0, 1), (-1, 1), 2, CYAN),
            ]
        ),
    )
    story.extend([hero, Spacer(1, 6 * mm)])

    kpis = [
        ("Overall", f"{metrics['progress']}%", TEAL),
        ("Approved", f"{metrics['approved']}/{metrics['documents']}", GREEN),
        ("Under Review", metrics["under_review"], BLUE),
        ("Overdue Review", metrics["overdue_review"], AMBER),
        ("Perlu Revisi", metrics["revision_required"], RED),
        ("Pending Instalasi", metrics["pending_installation"], AMBER),
    ]
    kpi_cells = []
    for label, value, color in kpis:
        kpi_cells.append(
            Table(
                [[Paragraph(_text(label), body_muted)], [Paragraph(f"<b>{_text(value)}</b>", ParagraphStyle("Kpi", parent=body, fontSize=16, leading=18, textColor=color))]],
                colWidths=[42 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                    ]
                ),
            )
        )
    story.extend([
        Table([kpi_cells], colWidths=[44.1 * mm] * 6),
        Spacer(1, 6 * mm),
    ])

    type_rows = []
    for item in snapshot["type_summary"]:
        type_rows.append(
            [
                Paragraph(f"<b>{_text(item['type'])}</b>", body),
                _progress_bar(item["progress"], 48 * mm),
                Paragraph(f"<b>{item['progress']}%</b>", body_center),
                Paragraph(f"{item['approved']} / {item['total']}", body_center),
                Paragraph(str(item["under_review"]), body_center),
                Paragraph(str(item["revision"]), body_center),
            ]
        )
    type_table = Table(
        [["Document", "Progress", "%", "Approved", "Review", "Revision"], *type_rows],
        colWidths=[35 * mm, 55 * mm, 18 * mm, 25 * mm, 23 * mm, 23 * mm],
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), CYAN),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
            ]
        ),
    )
    story.extend([
        KeepTogether([Paragraph("Document Readiness", heading), type_table]),
        Spacer(1, 4 * mm),
    ])

    if snapshot["attention"]:
        attention_rows = [["Priority", "Site / Document", "Status", "Age"]]
        for item in snapshot["attention"][:3]:
            attention_rows.append(
                [
                    Paragraph("HIGH" if item["priority"] >= 75 else "FOLLOW UP", body_center),
                    Paragraph(f"<b>{_text(item['title'])}</b><br/><font color='#687386'>{_text(item['detail'])}</font>", body),
                    Paragraph(_text(item["style"]).upper(), body_center),
                    Paragraph(_text(item["age"]), body_center),
                ]
            )
        attention_table = Table(
            attention_rows,
            colWidths=[27 * mm, 115 * mm, 32 * mm, 30 * mm],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
                ]
            ),
        )
        story.extend([Paragraph("Attention Required", heading), attention_table])

    story.extend([PageBreak(), Paragraph("Installation Batch Register", heading)])
    batch_rows = [["Site / ID", "Batch", "PIC", "QC", "ATP", "FATP", "Progress", "Status", "Updated"]]
    for row in snapshot["batch_rows"]:
        values = [row["qc"], row["atp"], row["fatp"]]
        batch_rows.append(
            [
                Paragraph(f"<b>{_text(row['site'].name)}</b><br/><font color='#687386'>{_text(row['site'].tower_id)}</font>", batch_body),
                Paragraph(_text(row["batch"].label), batch_body),
                Paragraph(_text(row["batch"].pic_name), batch_body),
                *[
                    Paragraph(_text(item.get_status_display() if item else "-"), batch_center)
                    for item in values
                ],
                Paragraph(f"<b>{row['progress']}%</b><br/>{row['approved']}/{row['total']}", batch_center),
                Paragraph(f"<b>{_text(row['summary']['label'])}</b>", batch_center),
                Paragraph(row["last_updated"].strftime("%d %b %Y"), batch_center),
            ]
        )
    batch_table = Table(
        batch_rows,
        colWidths=[44 * mm, 22 * mm, 26 * mm, 27 * mm, 27 * mm, 27 * mm, 24 * mm, 34 * mm, 25 * mm],
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 6.4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.6 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.6 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0.8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8 * mm),
            ]
        ),
    )
    for row_index, row in enumerate(snapshot["batch_rows"], start=1):
        for column_index, item in enumerate([row["qc"], row["atp"], row["fatp"]], start=3):
            if item:
                batch_table.setStyle(
                    TableStyle(
                        [
                            (
                                "TEXTCOLOR",
                                (column_index, row_index),
                                (column_index, row_index),
                                _status_color(item.status),
                            )
                        ]
                    )
                )
    story.append(batch_table)

    document.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    buffer.seek(0)
    filename = f"TripleE_DWDM_Progress_{generated_at:%Y%m%d_%H%M}.pdf"
    return buffer, filename
