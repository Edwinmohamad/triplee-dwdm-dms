from django.core.management.base import BaseCommand
from django.db import transaction

from dms.models import Document, InstallationBatch, Project, Site


SITES = [
    {
        "sequence": 1,
        "region": "BANGKA BELITUNG",
        "tower_id": "SUM-BB-KBA-0057",
        "name": "KOBA",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "APPROVED", "FATP": "APPROVED"})],
    },
    {
        "sequence": 2,
        "region": "BANGKA BELITUNG",
        "tower_id": "SUM-BB-SGL-0238",
        "name": "HUT. SUNGAI LIAT",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 3,
        "region": "BANGKA BELITUNG",
        "tower_id": "SUM-BB-SGL-0537",
        "name": "PESAREN B2JS",
        "batches": [(1, "Batch 1", "ROBI", "INSTALLED", {"QC": "APPROVED", "ATP": "NOT_STARTED", "FATP": "NOT_STARTED"})],
    },
    {
        "sequence": 4,
        "region": "BANGKA BELITUNG",
        "tower_id": "SUM-BB-TDN-0361",
        "name": "MENTIGI",
        "batches": [(1, "Batch 1", "ROBI", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 5,
        "region": "DENPASAR",
        "tower_id": "BAL-BA-MGW-0066",
        "name": "PEMOGAN",
        "batches": [(1, "Batch 1", "ILHAM", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 6,
        "region": "JAMBI",
        "tower_id": "SUM-JA-KLT-0115",
        "name": "BSC PEMATANG LUMUT",
        "batches": [(1, "Batch 1", "FAHRI", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 7,
        "region": "JAMBI",
        "tower_id": "SUM-JA-KLT-0118",
        "name": "KUALA TUNGKAL",
        "batches": [(1, "Batch 1", "FAHRI", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 8,
        "region": "JAMBI",
        "tower_id": "SUM-JA-SNT-0257",
        "name": "PANDE ARANG",
        "batches": [(1, "Batch 1", "FAHRI", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 9,
        "region": "JAWA TIMUR",
        "tower_id": "JAW-JI-JMR-0677",
        "name": "PUGER",
        "batches": [(1, "Batch 1", "ILHAM", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 10,
        "region": "LAMPUNG",
        "tower_id": "SUM-LA-BDL-0105",
        "name": "KEDATON",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 11,
        "region": "RIAU",
        "tower_id": "SUM-RI-PBR-0172",
        "name": "PNB PEKANBARU",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 12,
        "region": "RIAU",
        "tower_id": "SUM-RI-DUM-0143",
        "name": "DUMAI",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 13,
        "region": "SUMATERA SELATAN",
        "tower_id": "SUM-SS-PLG-0477",
        "name": "PALEMBANG OFFICE",
        "batches": [(1, "Batch 1", "EDWIN", "INSTALLED", {"QC": "APPROVED", "ATP": "APPROVED", "FATP": "APPROVED"})],
    },
    {
        "sequence": 14,
        "region": "KEPULAUAN RIAU",
        "tower_id": "SUM-KR-BTM-0599",
        "name": "TANJUNG BEMBAN MTI",
        "batches": [(1, "Batch 1", "ILHAM", "INSTALLED", {"QC": "APPROVED", "ATP": "UNDER_REVIEW", "FATP": "UNDER_REVIEW"})],
    },
    {
        "sequence": 15,
        "region": "KEPULAUAN RIAU",
        "tower_id": "SUM-KR-BTM-0659",
        "name": "TANJUNG PINGGIR MTI",
        "batches": [(1, "Batch 1", "ILHAM", "INSTALLED", {"QC": "APPROVED", "ATP": "NOT_STARTED", "FATP": "NOT_STARTED"})],
    },
    {
        "sequence": 16,
        "region": "BANGKA BELITUNG",
        "tower_id": "SUM-BB-TDN-0530",
        "name": "TANJUNG PANDAN MTI",
        "batches": [(1, "Batch 1", "", "PENDING_INSTALLATION", {"QC": "NOT_STARTED", "ATP": "NOT_STARTED", "FATP": "NOT_STARTED"})],
    },
]


class Command(BaseCommand):
    help = "Create the Nokia DWDM project, 16 physical sites, 16 installation batches and document register."

    @transaction.atomic
    def handle(self, *args, **options):
        project, _ = Project.objects.update_or_create(
            code="NOKIA-DWDM",
            defaults={
                "name": "Nokia DWDM Document Project",
                "client": "Nokia",
                "subcontractor": "PT Triple E",
                "is_active": True,
            },
        )
        batch_count = 0
        for site_data in SITES:
            site, _ = Site.objects.update_or_create(
                project=project,
                tower_id=site_data["tower_id"],
                defaults={
                    "name": site_data["name"],
                    "region": site_data["region"],
                    "sequence_no": site_data["sequence"],
                },
            )
            for batch_no, label, pic, status, doc_statuses in site_data["batches"]:
                # Runtime workflow fields are intentionally create-only. This
                # command runs on every container start and must never roll back
                # status/PIC changes made in the application.
                batch, _ = InstallationBatch.objects.get_or_create(
                    site=site,
                    batch_no=batch_no,
                    defaults={"label": label, "pic_name": pic, "status": status},
                )
                batch_count += 1
                for doc_type in [Document.Type.QC, Document.Type.ATP, Document.Type.FATP]:
                    legacy_note = "Status awal diimpor dari tracker Excel; file historis belum dihubungkan."
                    Document.objects.get_or_create(
                        batch=batch,
                        document_type=doc_type,
                        defaults={"status": doc_statuses[doc_type], "legacy_note": legacy_note},
                    )
        self.stdout.write(self.style.SUCCESS(f"Seed complete: {len(SITES)} sites, {batch_count} batches, {batch_count * 3} documents."))
