DEFAULT_FATP_SECTIONS = (
    {
        "title": "Wiring Diagram Power Source",
        "description": "Wiring Power Diagram",
        "columns": 1,
        "page_break_before": False,
        "upload_hint": "Upload diagram wiring power source",
    },
    {
        "title": "Photo Power Connection - Main",
        "description": "DCPDU Main dan Eaton Rectifier Main",
        "columns": 2,
        "page_break_before": True,
        "upload_hint": "DCPDU Main dan Eaton Rectifier Main",
    },
    {
        "title": "Photo Power Connection - Backup",
        "description": "DCPDU Backup dan Eaton Rectifier Backup",
        "columns": 2,
        "page_break_before": True,
        "upload_hint": "DCPDU Backup dan Eaton Rectifier Backup",
    },
    {
        "title": "Failover Test - MCB Main Off (A1)",
        "description": "MCB Main Off (A1) dan Alarm Board Power Main",
        "columns": 2,
        "page_break_before": True,
        "upload_hint": "MCB Main Off dan Alarm Board Power Main",
    },
    {
        "title": "Failover Test - MCB Backup Off (B1)",
        "description": "Backup MCB Off (B1) dan Alarm Board Power Backup",
        "columns": 2,
        "page_break_before": False,
        "upload_hint": "MCB Backup Off dan Alarm Board Power Backup",
    },
    {
        "title": "Load Voltage and Ampere",
        "description": "Main Rectifier dan Backup Rectifier Voltage & Ampere",
        "columns": 2,
        "page_break_before": True,
        "upload_hint": "Main dan Backup Rectifier Voltage & Ampere",
    },
    {
        "title": "Photo LVD Setting",
        "description": "Main Rectifier dan Backup Rectifier LVD Setting",
        "columns": 2,
        "page_break_before": False,
        "upload_hint": "Main dan Backup Rectifier LVD Setting",
    },
)


def seed_default_fatp_sections(builder):
    from ..models import FatpSection

    if builder.sections.exists():
        return []
    sections = [
        FatpSection(
            builder=builder,
            sequence_no=index,
            title=item["title"],
            description=item["description"],
            columns=item["columns"],
            page_break_before=item["page_break_before"],
        )
        for index, item in enumerate(DEFAULT_FATP_SECTIONS, 1)
    ]
    return FatpSection.objects.bulk_create(sections)
