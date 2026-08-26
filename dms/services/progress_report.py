"""Excel progress report generator for the Triple E DWDM document register."""

from collections import Counter
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import Document, InstallationBatch, Site


NAVY = "0B1F35"
CYAN = "00A9BD"
TEAL = "31D2C4"
GREEN = "16875A"
AMBER = "D28A1B"
RED = "BD3944"
BLUE = "3157D5"
WHITE = "FFFFFF"
LIGHT = "F3F6F8"
LINE = "DCE3EA"
MUTED = "687386"
STATUS_COLORS = {
    Document.Status.APPROVED: GREEN,
    Document.Status.UNDER_REVIEW: BLUE,
    Document.Status.REVISION_REQUIRED: AMBER,
    Document.Status.REJECTED: RED,
    Document.Status.UPLOADED: CYAN,
    Document.Status.DRAFT: "6B7C93",
    Document.Status.NOT_STARTED: "AAB4C0",
    Document.Status.NOT_APPLICABLE: "D7DCE2",
}
STATUS_SOFT_COLORS = {
    Document.Status.APPROVED: "E2F3EA",
    Document.Status.UNDER_REVIEW: "E8EDFF",
    Document.Status.REVISION_REQUIRED: "FFF1D6",
    Document.Status.REJECTED: "FDE8EA",
    Document.Status.UPLOADED: "DFF7F9",
    Document.Status.DRAFT: "EBEFF4",
    Document.Status.NOT_STARTED: "F0F2F5",
    Document.Status.NOT_APPLICABLE: "F3F4F6",
}


def _safe(value):
    """Prevent spreadsheet formula injection for user-controlled text."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _local_datetime(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.replace(tzinfo=None)


def _date(value):
    return value or ""


def _latest_version(document):
    versions = list(document.versions.all())
    return versions[0] if versions else None


def _summary_status(documents):
    documents = list(documents)
    statuses = {document.status for document in documents}
    if not documents or statuses <= {
        Document.Status.NOT_STARTED,
        Document.Status.NOT_APPLICABLE,
    }:
        return "Not Started"
    if statuses & {Document.Status.REVISION_REQUIRED, Document.Status.REJECTED}:
        return "Perlu Revisi"
    if statuses <= {Document.Status.APPROVED, Document.Status.NOT_APPLICABLE}:
        return "Approved"
    if Document.Status.UNDER_REVIEW in statuses:
        return "Under Review"
    return "In Progress"


def _overall_site_status(site, documents):
    documents = list(documents)
    if (
        any(
            batch.status == InstallationBatch.Status.PENDING_INSTALLATION
            for batch in site.batches.all()
        )
        and not any(document.status == Document.Status.APPROVED for document in documents)
    ):
        return "Pending Instalasi"
    return _summary_status(documents)


def _title(ws, title, subtitle, last_column):
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=last_column)
    cell = ws.cell(1, 1, title)
    cell.font = Font(name="Aptos Display", size=20, bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.alignment = Alignment(vertical="center")
    for row in ws.iter_rows(min_row=1, max_row=2, min_col=1, max_col=last_column):
        for item in row:
            item.fill = PatternFill("solid", fgColor=NAVY)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_column)
    sub = ws.cell(3, 1, subtitle)
    sub.font = Font(name="Aptos", size=10, color=MUTED, italic=True)
    sub.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 24


def _header_row(ws, row, columns):
    thin = Side(style="thin", color=LINE)
    for column, label in enumerate(columns, 1):
        cell = ws.cell(row, column, label)
        cell.font = Font(name="Aptos", size=10, bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=CYAN)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(bottom=thin)
    ws.row_dimensions[row].height = 30


def _style_table(ws, start_row, end_row, end_column):
    thin = Side(style="thin", color=LINE)
    for row in ws.iter_rows(
        min_row=start_row,
        max_row=end_row,
        min_col=1,
        max_col=end_column,
    ):
        for cell in row:
            cell.font = Font(name="Aptos", size=10, color="172337")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
        if row[0].row % 2 == 0:
            for cell in row:
                cell.fill = PatternFill("solid", fgColor="F8FAFB")


def _auto_width(ws, minimum=10, maximum=42):
    for column in range(1, ws.max_column + 1):
        letter = get_column_letter(column)
        width = max(
            (
                len(str(ws.cell(row, column).value or ""))
                for row in range(1, ws.max_row + 1)
            ),
            default=minimum,
        )
        ws.column_dimensions[letter].width = min(max(width + 2, minimum), maximum)


def _style_status_cell(cell, status_code):
    color = STATUS_COLORS.get(status_code, "6B7C93")
    cell.fill = PatternFill(
        "solid", fgColor=STATUS_SOFT_COLORS.get(status_code, LIGHT)
    )
    cell.font = Font(name="Aptos", size=10, bold=True, color=color)


def build_progress_report():
    """Return a formatted XLSX workbook in memory and its generated filename."""
    generated_at = timezone.localtime()
    sites = list(
        Site.objects.select_related("project").prefetch_related(
            "batches__documents__versions__uploaded_by",
            "batches__documents__versions__attachments",
        )
    )
    batches = [batch for site in sites for batch in site.batches.all()]
    documents = [document for batch in batches for document in batch.documents.all()]
    applicable = [
        document
        for document in documents
        if document.status != Document.Status.NOT_APPLICABLE
    ]
    counts = Counter(document.status for document in applicable)
    approved = counts[Document.Status.APPROVED]
    total = len(applicable)
    progress = round((approved / total) * 100) if total else 0

    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Triple E DWDM DMS"
    workbook.properties.title = "DWDM Document Progress Report"
    workbook.properties.subject = "Progress QC, ATP, dan FATP per installation batch"
    workbook.properties.description = "Generated automatically from Triple E DWDM DMS"
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True

    summary = workbook.create_sheet("Ringkasan")
    _title(
        summary,
        "TRIPLE E · DWDM DOCUMENT PROGRESS",
        f"Snapshot otomatis {generated_at:%d %B %Y, %H:%M} WIB",
        9,
    )
    summary.sheet_view.showGridLines = False
    summary.freeze_panes = "A5"
    kpis = [
        ("Site Fisik", len(sites), CYAN),
        ("Installation Batch", len(batches), BLUE),
        ("Dokumen Berlaku", total, "6B7C93"),
        ("Approved", approved, GREEN),
        ("Overall Progress", progress / 100, TEAL),
        (
            "Pending Instalasi",
            sum(
                batch.status == InstallationBatch.Status.PENDING_INSTALLATION
                for batch in batches
            ),
            AMBER,
        ),
    ]
    for index, (label, value, color) in enumerate(kpis):
        start_col = 1 + (index % 3) * 3
        start_row = 5 + (index // 3) * 3
        summary.merge_cells(
            start_row=start_row,
            start_column=start_col,
            end_row=start_row,
            end_column=start_col + 1,
        )
        label_cell = summary.cell(start_row, start_col, label)
        label_cell.font = Font(name="Aptos", size=9, bold=True, color=MUTED)
        summary.merge_cells(
            start_row=start_row + 1,
            start_column=start_col,
            end_row=start_row + 1,
            end_column=start_col + 1,
        )
        value_cell = summary.cell(start_row + 1, start_col, value)
        value_cell.font = Font(name="Aptos Display", size=18, bold=True, color=color)
        value_cell.number_format = "0%" if label == "Overall Progress" else "0"
        for row in range(start_row, start_row + 2):
            for column in range(start_col, start_col + 2):
                summary.cell(row, column).fill = PatternFill("solid", fgColor="F5F8FA")
        summary.cell(start_row, start_col).fill = PatternFill("solid", fgColor="F5F8FA")

    status_start = 12
    _header_row(summary, status_start, ["Status", "Jumlah", "Persentase"])
    status_rows = [
        ("Approved", approved, GREEN),
        ("Under Review", counts[Document.Status.UNDER_REVIEW], BLUE),
        (
            "Perlu Revisi",
            counts[Document.Status.REVISION_REQUIRED] + counts[Document.Status.REJECTED],
            AMBER,
        ),
        (
            "Dalam Proses / Belum Mulai",
            total
            - approved
            - counts[Document.Status.UNDER_REVIEW]
            - counts[Document.Status.REVISION_REQUIRED]
            - counts[Document.Status.REJECTED],
            "7C8A9B",
        ),
    ]
    for offset, (label, count, color) in enumerate(status_rows, 1):
        row = status_start + offset
        summary.cell(row, 1, label)
        summary.cell(row, 2, count)
        summary.cell(row, 3, (count / total) if total else 0)
        summary.cell(row, 3).number_format = "0%"
        summary.cell(row, 1).font = Font(name="Aptos", size=10, bold=True, color=color)
    _style_table(summary, status_start + 1, status_start + len(status_rows), 3)

    doughnut = DoughnutChart()
    doughnut.title = "Komposisi Status Dokumen"
    doughnut.holeSize = 58
    doughnut.height = 7.2
    doughnut.width = 10.5
    doughnut.add_data(
        Reference(summary, min_col=2, min_row=status_start, max_row=status_start + len(status_rows)),
        titles_from_data=True,
    )
    doughnut.set_categories(
        Reference(summary, min_col=1, min_row=status_start + 1, max_row=status_start + len(status_rows))
    )
    doughnut.series[0].data_points = [
        DataPoint(idx=index, spPr=GraphicalProperties(solidFill=color))
        for index, color in enumerate((GREEN, BLUE, AMBER, "9CA7B5"))
    ]
    summary.add_chart(doughnut, "E12")

    type_start = 19
    _header_row(summary, type_start, ["Tipe Dokumen", "Total", "Approved", "Progress"])
    for offset, (document_type, label) in enumerate(Document.Type.choices, 1):
        subset = [document for document in applicable if document.document_type == document_type]
        type_approved = sum(
            document.status == Document.Status.APPROVED for document in subset
        )
        row = type_start + offset
        summary.cell(row, 1, label)
        summary.cell(row, 2, len(subset))
        summary.cell(row, 3, type_approved)
        summary.cell(row, 4, (type_approved / len(subset)) if subset else 0)
        summary.cell(row, 4).number_format = "0%"
    _style_table(summary, type_start + 1, type_start + len(Document.Type.choices), 4)

    bar = BarChart()
    bar.type = "col"
    bar.style = 10
    bar.title = "Progress per Jenis Dokumen"
    bar.y_axis.title = "Persentase"
    bar.y_axis.scaling.max = 1
    bar.y_axis.numFmt = "0%"
    bar.height = 7
    bar.width = 10.5
    bar.add_data(
        Reference(
            summary,
            min_col=4,
            min_row=type_start,
            max_row=type_start + len(Document.Type.choices),
        ),
        titles_from_data=True,
    )
    bar.set_categories(
        Reference(
            summary,
            min_col=1,
            min_row=type_start + 1,
            max_row=type_start + len(Document.Type.choices),
        )
    )
    bar.series[0].graphicalProperties.solidFill = CYAN
    bar.series[0].graphicalProperties.line.solidFill = CYAN
    summary.add_chart(bar, "E27")
    summary.column_dimensions["A"].width = 29
    summary.column_dimensions["B"].width = 15
    summary.column_dimensions["C"].width = 15
    summary.column_dimensions["D"].width = 15
    for letter in "EFGHI":
        summary.column_dimensions[letter].width = 13

    site_sheet = workbook.create_sheet("Progress Site")
    site_columns = [
        "No",
        "Site",
        "Tower ID",
        "Region",
        "Jumlah Batch",
        "Dokumen Berlaku",
        "Approved",
        "Progress",
        "QC",
        "ATP",
        "FATP",
        "Status Keseluruhan",
    ]
    _title(
        site_sheet,
        "PROGRESS DOKUMEN PER SITE",
        "Persentase dihitung dari dokumen Approved dibanding dokumen yang berlaku.",
        len(site_columns),
    )
    _header_row(site_sheet, 5, site_columns)
    for index, site in enumerate(sites, 1):
        row = 5 + index
        site_documents = [
            document
            for batch in site.batches.all()
            for document in batch.documents.all()
            if document.status != Document.Status.NOT_APPLICABLE
        ]
        site_approved = sum(
            document.status == Document.Status.APPROVED for document in site_documents
        )
        values = [
            index,
            _safe(site.name),
            _safe(site.tower_id),
            _safe(site.region),
            len(site.batches.all()),
            len(site_documents),
            site_approved,
            f'=IF(F{row}=0,0,G{row}/F{row})',
            _summary_status(
                document
                for document in site_documents
                if document.document_type == Document.Type.QC
            ),
            _summary_status(
                document
                for document in site_documents
                if document.document_type == Document.Type.ATP
            ),
            _summary_status(
                document
                for document in site_documents
                if document.document_type == Document.Type.FATP
            ),
            _overall_site_status(site, site_documents),
        ]
        for column, value in enumerate(values, 1):
            site_sheet.cell(row, column, value)
        site_sheet.cell(row, 8).number_format = "0%"
    _style_table(site_sheet, 6, site_sheet.max_row, len(site_columns))
    if site_sheet.max_row >= 6:
        site_sheet.conditional_formatting.add(
            f"H6:H{site_sheet.max_row}",
            ColorScaleRule(
                start_type="num",
                start_value=0,
                start_color=RED,
                mid_type="num",
                mid_value=0.6,
                mid_color=AMBER,
                end_type="num",
                end_value=1,
                end_color=GREEN,
            ),
        )
    site_sheet.freeze_panes = "A6"
    site_sheet.auto_filter.ref = f"A5:L{site_sheet.max_row}"
    _auto_width(site_sheet)

    batch_sheet = workbook.create_sheet("Detail Batch")
    batch_columns = [
        "No",
        "Site",
        "Tower ID",
        "Region",
        "Installation Batch",
        "Status Instalasi",
        "Jadwal",
        "Tanggal Instalasi",
        "PIC",
        "Dokumen Berlaku",
        "Approved",
        "Progress",
        "QC",
        "ATP",
        "FATP",
        "Catatan Batch",
        "Update Terakhir",
    ]
    _title(
        batch_sheet,
        "DETAIL PROGRESS PER INSTALLATION BATCH",
        "Mentigi Batch 1/2 dan site multi-batch tetap ditampilkan sebagai baris terpisah.",
        len(batch_columns),
    )
    _header_row(batch_sheet, 5, batch_columns)
    for index, batch in enumerate(batches, 1):
        row = 5 + index
        batch_documents = [
            document
            for document in batch.documents.all()
            if document.status != Document.Status.NOT_APPLICABLE
        ]
        document_by_type = {
            document.document_type: document for document in batch_documents
        }
        batch_approved = sum(
            document.status == Document.Status.APPROVED for document in batch_documents
        )
        values = [
            index,
            _safe(batch.site.name),
            _safe(batch.site.tower_id),
            _safe(batch.site.region),
            _safe(batch.label),
            batch.get_status_display(),
            _date(batch.scheduled_date),
            _date(batch.installed_at),
            _safe(batch.pic_name),
            len(batch_documents),
            batch_approved,
            f'=IF(J{row}=0,0,K{row}/J{row})',
            document_by_type.get(Document.Type.QC).get_status_display()
            if document_by_type.get(Document.Type.QC)
            else "N/A",
            document_by_type.get(Document.Type.ATP).get_status_display()
            if document_by_type.get(Document.Type.ATP)
            else "N/A",
            document_by_type.get(Document.Type.FATP).get_status_display()
            if document_by_type.get(Document.Type.FATP)
            else "N/A",
            _safe(batch.notes),
            _local_datetime(batch.updated_at),
        ]
        for column, value in enumerate(values, 1):
            batch_sheet.cell(row, column, value)
        batch_sheet.cell(row, 12).number_format = "0%"
        batch_sheet.cell(row, 7).number_format = "dd-mm-yyyy"
        batch_sheet.cell(row, 8).number_format = "dd-mm-yyyy"
        batch_sheet.cell(row, 17).number_format = "dd-mm-yyyy hh:mm"
    _style_table(batch_sheet, 6, batch_sheet.max_row, len(batch_columns))
    if batch_sheet.max_row >= 6:
        batch_sheet.conditional_formatting.add(
            f"L6:L{batch_sheet.max_row}",
            ColorScaleRule(
                start_type="num",
                start_value=0,
                start_color=RED,
                mid_type="num",
                mid_value=0.6,
                mid_color=AMBER,
                end_type="num",
                end_value=1,
                end_color=GREEN,
            ),
        )
    batch_sheet.freeze_panes = "A6"
    batch_sheet.auto_filter.ref = f"A5:Q{batch_sheet.max_row}"
    _auto_width(batch_sheet)

    history_sheet = workbook.create_sheet("Riwayat Dokumen")
    history_columns = [
        "No",
        "Site",
        "Tower ID",
        "Installation Batch",
        "Tipe",
        "Status",
        "Revisi Terakhir",
        "Jumlah File",
        "Uploader",
        "Waktu Upload",
        "Waktu Submit",
        "Waktu Approved",
        "Catatan Revisi",
        "Update Dokumen",
    ]
    _title(
        history_sheet,
        "REGISTER & RIWAYAT DOKUMEN",
        "Daftar QC, ATP, dan FATP beserta revisi terakhir yang tersedia.",
        len(history_columns),
    )
    _header_row(history_sheet, 5, history_columns)
    for index, document in enumerate(documents, 1):
        row = 5 + index
        latest = _latest_version(document)
        file_count = len(latest.attachments.all()) if latest else 0
        if latest and file_count == 0 and latest.storage_key:
            file_count = 1
        values = [
            index,
            _safe(document.batch.site.name),
            _safe(document.batch.site.tower_id),
            _safe(document.batch.label),
            document.get_document_type_display(),
            document.get_status_display(),
            f"Rev {latest.revision_no}" if latest else "-",
            file_count,
            _safe(latest.uploaded_by.full_name) if latest else "-",
            _local_datetime(latest.uploaded_at) if latest else "",
            _local_datetime(document.submitted_at),
            _local_datetime(document.approved_at),
            _safe(latest.change_summary) if latest else _safe(document.legacy_note),
            _local_datetime(document.updated_at),
        ]
        for column, value in enumerate(values, 1):
            history_sheet.cell(row, column, value)
        for column in (10, 11, 12, 14):
            history_sheet.cell(row, column).number_format = "dd-mm-yyyy hh:mm"
        _style_status_cell(history_sheet.cell(row, 6), document.status)
    _style_table(history_sheet, 6, history_sheet.max_row, len(history_columns))
    # Re-apply status styling because table striping intentionally comes first.
    for index, document in enumerate(documents, 1):
        _style_status_cell(history_sheet.cell(5 + index, 6), document.status)
    history_sheet.freeze_panes = "A6"
    history_sheet.auto_filter.ref = f"A5:N{history_sheet.max_row}"
    _auto_width(history_sheet)

    for worksheet in workbook.worksheets:
        worksheet.sheet_view.showGridLines = False
        worksheet.sheet_view.zoomScale = 90
        worksheet.sheet_properties.pageSetUpPr.fitToPage = True
        worksheet.page_setup.fitToWidth = 1
        worksheet.page_setup.fitToHeight = 0
        worksheet.page_margins.left = 0.25
        worksheet.page_margins.right = 0.25
        worksheet.page_margins.top = 0.5
        worksheet.page_margins.bottom = 0.5

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"TripleE_DWDM_Progress_{generated_at:%Y%m%d_%H%M}.xlsx"
    return output, filename
