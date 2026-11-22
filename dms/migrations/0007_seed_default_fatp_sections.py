from django.db import migrations


DEFAULT_SECTIONS = (
    ("Wiring Diagram Power Source", "Wiring Power Diagram", 1, False),
    ("Photo Power Connection - Main", "DCPDU Main dan Eaton Rectifier Main", 2, True),
    ("Photo Power Connection - Backup", "DCPDU Backup dan Eaton Rectifier Backup", 2, True),
    ("Failover Test - MCB Main Off (A1)", "MCB Main Off (A1) dan Alarm Board Power Main", 2, True),
    ("Failover Test - MCB Backup Off (B1)", "Backup MCB Off (B1) dan Alarm Board Power Backup", 2, False),
    ("Load Voltage and Ampere", "Main Rectifier dan Backup Rectifier Voltage & Ampere", 2, True),
    ("Photo LVD Setting", "Main Rectifier dan Backup Rectifier LVD Setting", 2, False),
)


def seed_empty_builders(apps, schema_editor):
    FatpBuilder = apps.get_model("dms", "FatpBuilder")
    FatpSection = apps.get_model("dms", "FatpSection")
    for builder in FatpBuilder.objects.all():
        if FatpSection.objects.filter(builder=builder).exists():
            continue
        FatpSection.objects.bulk_create(
            [
                FatpSection(
                    builder=builder,
                    sequence_no=index,
                    title=title,
                    description=description,
                    columns=columns,
                    page_break_before=page_break,
                )
                for index, (title, description, columns, page_break) in enumerate(
                    DEFAULT_SECTIONS, 1
                )
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("dms", "0006_fatp_custom_builder")]

    operations = [
        migrations.RunPython(seed_empty_builders, migrations.RunPython.noop),
    ]
