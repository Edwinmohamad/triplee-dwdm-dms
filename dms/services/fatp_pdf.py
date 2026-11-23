from io import BytesIO
from xml.sax.saxutils import escape

from PIL import Image as PillowImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .local_storage import open_document_file


INK = colors.HexColor("#162334")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
SOFT = colors.HexColor("#F4F7FA")
ACCENT = colors.HexColor("#087C8C")


def _safe(value):
    return escape(str(value or ""))


def _safe_lines(value):
    return _safe(value).replace("\n", "<br/>")


def _page_chrome(canvas, doc):
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(colors.HexColor("#D8E1E8"))
    canvas.line(doc.leftMargin, 18 * mm, width - doc.rightMargin, 18 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 12 * mm, "TRIPLE E - NOKIA DWDM DOCUMENT CONTROL")
    canvas.drawRightString(width - doc.rightMargin, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _fit_photo(photo, max_width, max_height):
    with open_document_file(photo.storage_key) as source:
        raw = source.read()
    image = PillowImage.open(BytesIO(raw))
    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "L"}:
        background = PillowImage.new("RGB", image.size, "white")
        if "A" in image.getbands():
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image.convert("RGB"))
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((1800, 1800), PillowImage.Resampling.LANCZOS)
    width, height = image.size
    scale = min(max_width / width, max_height / height)
    target_width = width * scale
    target_height = height * scale
    prepared = BytesIO()
    image.save(prepared, format="JPEG", quality=90, optimize=True)
    prepared.seek(0)
    return Image(prepared, width=target_width, height=target_height)


def build_fatp_pdf(builder):
    output = BytesIO()
    document = builder.document
    batch = document.batch
    site = batch.site
    pdf = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=24 * mm,
        title=f"FATP {site.name} {site.tower_id}",
        author="PT Triple E Global Transformasi",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FatpTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=INK,
        alignment=0,
        spaceAfter=4 * mm,
    )
    eyebrow = ParagraphStyle(
        "FatpEyebrow",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=ACCENT,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "FatpBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=INK,
    )
    small = ParagraphStyle(
        "FatpSmall",
        parent=body,
        fontSize=7.5,
        leading=10,
        textColor=MUTED,
    )
    section_style = ParagraphStyle(
        "FatpSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=INK,
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
    )
    caption_style = ParagraphStyle(
        "FatpCaption",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        spaceBefore=2 * mm,
    )

    story = [
        Paragraph("FINAL ACCEPTANCE TEST PROCEDURE", eyebrow),
        Paragraph(_safe(builder.installation_title), title_style),
    ]
    info_rows = [
        [Paragraph("SITE", small), Paragraph(_safe(site.name), body), Paragraph("SITE ID", small), Paragraph(_safe(site.tower_id), body)],
        [Paragraph("INSTALLATION BATCH", small), Paragraph(_safe(batch.label), body), Paragraph("INSTALLATION DATE", small), Paragraph(builder.installation_date.strftime("%d %B %Y") if builder.installation_date else "-", body)],
        [Paragraph("PIC", small), Paragraph(_safe(batch.pic_name or "-"), body), Paragraph("PROJECT", small), Paragraph(_safe(site.project.name), body)],
    ]
    info_table = Table(info_rows, colWidths=[31 * mm, 57 * mm, 35 * mm, 52 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([info_table, Spacer(1, 5 * mm)])

    equipment = list(builder.equipment.all())
    story.append(Paragraph("INSTALLED EQUIPMENT", eyebrow))
    equipment_rows = [["No.", "Equipment", "Model / Type", "Qty", "Notes"]]
    if equipment:
        for index, item in enumerate(equipment, 1):
            equipment_rows.append([
                str(index),
                Paragraph(_safe(item.name), body),
                Paragraph(_safe(item.model or "-"), body),
                str(item.quantity),
                Paragraph(_safe(item.notes or "-"), small),
            ])
    else:
        equipment_rows.append(["-", Paragraph("No equipment has been added", small), "-", "-", "-"])
    equipment_table = Table(equipment_rows, colWidths=[10 * mm, 50 * mm, 42 * mm, 13 * mm, 60 * mm], repeatRows=1)
    equipment_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([equipment_table])
    if builder.work_description:
        story.extend([
            Spacer(1, 4 * mm),
            Paragraph("WORK DESCRIPTION", eyebrow),
            Paragraph(_safe_lines(builder.work_description), body),
        ])

    sections = list(builder.sections.prefetch_related("photos").all())
    for section_index, section in enumerate(sections, 1):
        if section.page_break_before:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 5 * mm))
        heading = [Paragraph(f"{section_index}. {_safe(section.title)}", section_style)]
        if section.description:
            heading.append(Paragraph(_safe_lines(section.description), body))
        photos = list(section.photos.all())
        if not photos:
            empty_table = Table([[Paragraph("No photos have been uploaded for this section.", small)]], colWidths=[pdf.width])
            empty_table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]))
            story.append(KeepTogether(heading + [empty_table]))
            continue
        columns = max(1, min(3, section.columns))
        gutter = 4 * mm
        cell_width = (pdf.width - gutter * (columns - 1)) / columns
        image_height = {1: 105 * mm, 2: 63 * mm, 3: 46 * mm}[columns]
        rows = []
        for start in range(0, len(photos), columns):
            cells = []
            for photo in photos[start:start + columns]:
                try:
                    photo_image = _fit_photo(photo, cell_width - 8 * mm, image_height)
                    cell = [photo_image, Paragraph(_safe(photo.caption or f"Photo {photo.sequence_no}"), caption_style)]
                except Exception:
                    cell = [Paragraph("Image cannot be rendered", small), Paragraph(_safe(photo.caption or f"Photo {photo.sequence_no}"), caption_style)]
                cells.append(cell)
            while len(cells) < columns:
                cells.append("")
            rows.append(cells)
        def photo_table(table_rows):
            table = Table(table_rows, colWidths=[cell_width] * columns, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.65, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.65, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]))
            return table

        story.append(KeepTogether(heading + [photo_table(rows[:1])]))
        if len(rows) > 1:
            story.append(photo_table(rows[1:]))

    pdf.build(story, onFirstPage=_page_chrome, onLaterPages=_page_chrome)
    output.seek(0)
    return output.getvalue()
