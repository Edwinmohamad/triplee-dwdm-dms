"""Professional PDF progress report for the Triple E DWDM document register."""

from collections import Counter
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models import Document, InstallationBatch, Site


NAVY = colors.HexColor("#122033")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#657184")
LINE = colors.HexColor("#DCE2E8")
SURFACE = colors.HexColor("#F5F7F9")
TEAL = colors.HexColor("#087F8C")
GREEN = colors.HexColor("#18794E")
BLUE = colors.HexColor("#2F5FD0")
AMBER = colors.HexColor("#A96207")
RED = colors.HexColor("#B93843")
WHITE = colors.white

STATUS_COLORS = {
    Document.Status.APPROVED: GREEN,
    Document.Status.UNDER_REVIEW: BLUE,
    Document.Status.REVISION_REQUIRED: AMBER,
    Document.Status.REJECTED: RED,
    Document.Status.UPLOADED: TEAL,
    Document.Status.DRAFT: MUTED,
    Document.Status.NOT_STARTED: MUTED,
    Document.Status.NOT_APPLICABLE: MUTED,
}


def _text(value, fallback="-"):
    value = str(value or "").strip()
    return value if value else fallback


def _short(value, length=92):
    value = _text(value)
    return value if len(value) <= length else f"{value[: length - 1].rstrip()}."


def _local(value, with_time=False):
    if not value:
        return "-"
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d %b %Y, %H:%M") if with_time else value.strftime("%d %b %Y")


def _summary_status(documents):
    documents = list(documents)
    statuses = {item.status for item in documents}
    if not documents or statuses <= {Document.Status.NOT_STARTED, Document.Status.NOT_APPLICABLE}:
        return "Not Started"
    if statuses & {Document.Status.REVISION_REQUIRED, Document.Status.REJECTED}:
        return "Perlu Revisi"
    if statuses <= {Document.Status.APPROVED, Document.Status.NOT_APPLICABLE}:
        return "Approved"
    if Document.Status.UNDER_REVIEW in statuses:
        return "Under Review"
    return "In Progress"


def _paragraph(value, style):
    from xml.sax.saxutils import escape

    return Paragraph(escape(_text(value)), style)


def _table(data, widths, styles, header=True, row_height=None):
    table = LongTable(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1 if header else 0), (-1, -1), 0.35, LINE),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, colors.HexColor("#FAFBFC")]),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]
        )
    table.setStyle(TableStyle(commands + styles))
    return table


def _draw_brand(canvas, document):
    canvas.saveState()
    page_width, page_height = landscape(A4)
    logo_path = Path(settings.BRAND_LOGO_PATH)
    logo_drawn = False
    if logo_path.is_file():
        try:
            from reportlab.lib.utils import ImageReader

            image = ImageReader(str(logo_path))
            image_width, image_height = image.getSize()
            draw_height = 10 * mm
            draw_width = min(draw_height * image_width / image_height, 28 * mm)
            canvas.drawImage(
                image,
                15 * mm,
                page_height - 17 * mm,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        canvas.setFillColor(TEAL)
        canvas.roundRect(15 * mm, page_height - 17 * mm, 11 * mm, 10 * mm, 2 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawCentredString(20.5 * mm, page_height - 13.5 * mm, "3E")

    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(47 * mm, page_height - 10.5 * mm, "PT TRIPLE E GLOBAL TRANSFORMASI")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(47 * mm, page_height - 14.5 * mm, "DWDM Project � Document Management System")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(15 * mm, page_height - 21 * mm, page_width - 15 * mm, page_height - 21 * mm)

    canvas.line(15 * mm, 13 * mm, page_width - 15 * mm, 13 * mm)
    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 8.5 * mm, "Internal project document � Generated from Triple E DWDM DMS")
    page_label = f"Page {document.page}"
    canvas.drawRightString(page_width - 15 * mm, 8.5 * mm, page_label)
    canvas.restoreState()


def build_progress_pdf():
    """Return a complete, paginated progress PDF and its filename."""
    generated_at = timezone.localtime()
    sites = list(
        Site.objects.select_related("project").prefetch_related(
            "batches__documents__versions__uploaded_by",
            "batches__documents__versions__attachments",
        )
    )
    batches = [batch for site in sites for batch in site.batches.all()]
    documents = [document for batch in batches for document in batch.documents.all()]
    applicable = [document for document in documents if document.status != Document.Status.NOT_APPLICABLE]
    counts = Counter(document.status for document in applicable)
    total = len(applicable)
    approved = counts[Document.Status.APPROVED]
    progress = round((approved / total) * 100) if total else 0

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=27 * mm,
        bottomMargin=18 * mm,
        title="Triple E DWDM Total Progress Report",
        author="PT Triple E Global Transformasi",
        subject="QC, ATP, and FATP document progress",
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle("ReportTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3 * mm)
    subtitle = ParagraphStyle("ReportSubtitle", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=5 * mm)
    section = ParagraphStyle("Section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=2 * mm, spaceAfter=3 * mm)
    body = ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=7, leading=9, textColor=INK)
    small = ParagraphStyle("Small", parent=body, fontSize=6.4, leading=8)
    center = ParagraphStyle("Center", parent=small, alignment=TA_CENTER)
    right = ParagraphStyle("Right", parent=small, alignment=TA_RIGHT)
    kpi_label = ParagraphStyle("KpiLabel", parent=small, textColor=MUTED, fontName="Helvetica-Bold", leading=9)
    kpi_value = ParagraphStyle("KpiValue", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=NAVY)

    story = [
        Paragraph("TOTAL DOCUMENT PROGRESS REPORT", title),
        Paragraph(
            f"QC, ATP, and FATP document readiness across all DWDM installation batches. Reporting cut-off: {generated_at:%d %B %Y, %H:%M} WIB.",
            subtitle,
        ),
    ]

    pending_installation = sum(batch.status == InstallationBatch.Status.PENDING_INSTALLATION for batch in batches)
    revision_count = counts[Document.Status.REVISION_REQUIRED] + counts[Document.Status.REJECTED]
    kpis = [
        ("OVERALL PROGRESS", f"{progress}%"),
        ("PHYSICAL SITES", str(len(sites))),
        ("INSTALLATION BATCHES", str(len(batches))),
        ("APPLICABLE DOCUMENTS", str(total)),
        ("APPROVED", str(approved)),
        ("REQUIRE ATTENTION", str(revision_count)),
    ]
    # Render KPI cards as three columns without decorative chart effects.
    cards = []
    for index in range(0, len(kpis), 3):
        row = []
        for label, value in kpis[index : index + 3]:
            card = Table([[Paragraph(label, kpi_label)], [Paragraph(value, kpi_value)]], colWidths=[82 * mm])
            card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SURFACE), ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, -1), 8)]))
            row.append(card)
        cards.append(row)
    cards_table = Table(cards, colWidths=[84 * mm, 84 * mm, 84 * mm], hAlign="LEFT")
    cards_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm)]))
    story.extend([cards_table, Spacer(1, 5 * mm)])

    status_rows = [
        ["No", "Document Status", "Total", "Percentage", "Operational Note"],
        ["1", "Approved", approved, f"{(approved / total * 100) if total else 0:.1f}%", "Accepted and ready for reporting"],
        ["2", "Under Review", counts[Document.Status.UNDER_REVIEW], f"{(counts[Document.Status.UNDER_REVIEW] / total * 100) if total else 0:.1f}%", "Awaiting reviewer decision"],
        ["3", "Revision / Rejected", revision_count, f"{(revision_count / total * 100) if total else 0:.1f}%", "Action required by document owner"],
        ["4", "In Progress / Not Started", max(total - approved - counts[Document.Status.UNDER_REVIEW] - revision_count, 0), f"{(max(total - approved - counts[Document.Status.UNDER_REVIEW] - revision_count, 0) / total * 100) if total else 0:.1f}%", "Preparation or upload pending"],
    ]
    story.extend([
        Paragraph("Executive Summary", section),
        _table([[ _paragraph(cell, small) for cell in row] for row in status_rows], [12 * mm, 47 * mm, 22 * mm, 28 * mm, 142 * mm], [], row_height=8 * mm),
        Spacer(1, 4 * mm),
    ])

    type_rows = [["No", "Document Type", "Applicable", "Approved", "Under Review", "Revision", "Progress"]]
    for number, (document_type, label) in enumerate(Document.Type.choices, 1):
        subset = [document for document in applicable if document.document_type == document_type]
        type_approved = sum(document.status == Document.Status.APPROVED for document in subset)
        type_review = sum(document.status == Document.Status.UNDER_REVIEW for document in subset)
        type_revision = sum(document.status in {Document.Status.REVISION_REQUIRED, Document.Status.REJECTED} for document in subset)
        type_rows.append([str(number), label, str(len(subset)), str(type_approved), str(type_review), str(type_revision), f"{round(type_approved / len(subset) * 100) if subset else 0}%"])
    story.extend([
        Paragraph("Progress by Document Type", section),
        _table([[ _paragraph(cell, center if col != 1 else small) for col, cell in enumerate(row)] for row in type_rows], [12 * mm, 55 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm], [("ALIGN", (2, 1), (-1, -1), "CENTER")]),
        Spacer(1, 3 * mm),
        Paragraph(f"Pending installation batches: <b>{pending_installation}</b>. These batches remain visible in the detailed register and are excluded only when a document is marked not applicable.", subtitle),
        PageBreak(),
    ])

    site_rows = [["No", "Site", "Tower ID", "Region", "Batch", "Applicable", "Approved", "Progress", "QC", "ATP", "FATP", "Overall Status"]]
    for number, site in enumerate(sites, 1):
        site_documents = [document for batch in site.batches.all() for document in batch.documents.all() if document.status != Document.Status.NOT_APPLICABLE]
        site_approved = sum(document.status == Document.Status.APPROVED for document in site_documents)
        values = [
            str(number), _text(site.name), _text(site.tower_id), _text(site.region), str(len(site.batches.all())), str(len(site_documents)), str(site_approved), f"{round(site_approved / len(site_documents) * 100) if site_documents else 0}%",
            _summary_status(item for item in site_documents if item.document_type == Document.Type.QC),
            _summary_status(item for item in site_documents if item.document_type == Document.Type.ATP),
            _summary_status(item for item in site_documents if item.document_type == Document.Type.FATP),
            _summary_status(site_documents),
        ]
        site_rows.append(values)
    story.extend([
        Paragraph("1. Total Progress by Site", title),
        Paragraph("Numbered register of physical sites with document completion and status by document type.", subtitle),
        _table([[ _paragraph(cell, center if col in {0, 4, 5, 6, 7} else small) for col, cell in enumerate(row)] for row in site_rows], [10 * mm, 34 * mm, 26 * mm, 25 * mm, 15 * mm, 19 * mm, 18 * mm, 19 * mm, 25 * mm, 25 * mm, 25 * mm, 30 * mm], [("ALIGN", (4, 1), (7, -1), "CENTER")]),
        PageBreak(),
    ])

    batch_rows = [["No", "Site / Tower ID", "Installation Batch", "Installation Status", "Schedule", "Installed", "PIC", "Docs", "Approved", "Progress", "QC", "ATP", "FATP", "Last Update"]]
    for number, batch in enumerate(batches, 1):
        batch_documents = [document for document in batch.documents.all() if document.status != Document.Status.NOT_APPLICABLE]
        by_type = {document.document_type: document for document in batch_documents}
        batch_approved = sum(document.status == Document.Status.APPROVED for document in batch_documents)
        batch_rows.append([
            str(number), f"{_text(batch.site.name)}\n{_text(batch.site.tower_id)}", _text(batch.label), batch.get_status_display(), _local(batch.scheduled_date), _local(batch.installed_at), _text(batch.pic_name), str(len(batch_documents)), str(batch_approved), f"{round(batch_approved / len(batch_documents) * 100) if batch_documents else 0}%",
            by_type[Document.Type.QC].get_status_display() if Document.Type.QC in by_type else "N/A",
            by_type[Document.Type.ATP].get_status_display() if Document.Type.ATP in by_type else "N/A",
            by_type[Document.Type.FATP].get_status_display() if Document.Type.FATP in by_type else "N/A",
            _local(batch.updated_at, with_time=True),
        ])
    story.extend([
        Paragraph("2. Detailed Progress by Installation Batch", title),
        Paragraph("Each installation batch is listed independently to preserve the project execution trail.", subtitle),
        _table([[ _paragraph(cell, center if col in {0, 7, 8, 9} else small) for col, cell in enumerate(row)] for row in batch_rows], [9 * mm, 34 * mm, 26 * mm, 28 * mm, 22 * mm, 22 * mm, 25 * mm, 14 * mm, 16 * mm, 18 * mm, 24 * mm, 24 * mm, 24 * mm, 30 * mm], [("ALIGN", (7, 1), (9, -1), "CENTER")]),
        PageBreak(),
    ])

    document_rows = [["No", "Site / Batch", "Type", "Status", "Revision", "Files", "Uploader", "Uploaded", "Submitted", "Approved", "Revision Note / Description", "Last Update"]]
    status_commands = []
    for number, document_item in enumerate(documents, 1):
        versions = list(document_item.versions.all())
        latest = versions[0] if versions else None
        file_count = len(latest.attachments.all()) if latest else 0
        if latest and file_count == 0 and latest.has_file:
            file_count = 1
        document_rows.append([
            str(number), f"{_text(document_item.batch.site.name)}\n{_text(document_item.batch.label)}", document_item.get_document_type_display(), document_item.get_status_display(), f"Rev {latest.revision_no}" if latest else "-", str(file_count), _text(latest.uploaded_by.full_name) if latest else "-", _local(latest.uploaded_at, with_time=True) if latest else "-", _local(document_item.submitted_at, with_time=True), _local(document_item.approved_at, with_time=True), _short(latest.change_summary if latest else document_item.legacy_note, 120), _local(document_item.updated_at, with_time=True),
        ])
        status_commands.extend([("TEXTCOLOR", (3, number), (3, number), STATUS_COLORS.get(document_item.status, MUTED)), ("FONTNAME", (3, number), (3, number), "Helvetica-Bold")])
    story.extend([
        Paragraph("3. Document Register and Revision History", title),
        Paragraph("Complete numbered register of QC, ATP, and FATP records including latest revision and audit timestamps.", subtitle),
        _table([[ _paragraph(cell, center if col in {0, 2, 4, 5} else small) for col, cell in enumerate(row)] for row in document_rows], [9 * mm, 31 * mm, 13 * mm, 25 * mm, 15 * mm, 11 * mm, 25 * mm, 27 * mm, 27 * mm, 27 * mm, 47 * mm, 27 * mm], status_commands),
    ])

    doc.build(story, onFirstPage=_draw_brand, onLaterPages=_draw_brand)
    output.seek(0)
    filename = f"TripleE_DWDM_Total_Progress_{generated_at:%Y%m%d_%H%M}.pdf"
    return output, filename

