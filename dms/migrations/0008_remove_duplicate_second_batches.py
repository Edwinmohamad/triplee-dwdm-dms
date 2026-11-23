from django.db import migrations


TARGET_TOWERS = ("SUM-BB-SGL-0238", "SUM-BB-TDN-0361")


def remove_duplicate_batches(apps, schema_editor):
    InstallationBatch = apps.get_model("dms", "InstallationBatch")
    DocumentVersion = apps.get_model("dms", "DocumentVersion")
    DocumentComment = apps.get_model("dms", "DocumentComment")
    FatpBuilder = apps.get_model("dms", "FatpBuilder")

    batches = InstallationBatch.objects.filter(
        site__project__code="NOKIA-DWDM",
        site__tower_id__in=TARGET_TOWERS,
        batch_no=2,
    ).select_related("site")

    blocked = []
    for batch in batches:
        first_batch = InstallationBatch.objects.filter(
            site=batch.site,
            batch_no=1,
        ).first()
        conflicting_folder = bool(
            batch.drive_folder_url
            and first_batch
            and first_batch.drive_folder_url
            and first_batch.drive_folder_url != batch.drive_folder_url
        )
        if batch.drive_folder_url and first_batch and not first_batch.drive_folder_url:
            first_batch.drive_folder_url = batch.drive_folder_url
            first_batch.save(update_fields=["drive_folder_url"])

        has_user_data = (
            conflicting_folder
            or bool(batch.scheduled_date)
            or bool(batch.installed_at)
            or bool(batch.notes.strip())
            or DocumentVersion.objects.filter(document__batch=batch).exists()
            or DocumentComment.objects.filter(document__batch=batch).exists()
            or FatpBuilder.objects.filter(document__batch=batch).exists()
        )
        if has_user_data:
            blocked.append(f"{batch.site.name} ({batch.site.tower_id})")

    if blocked:
        names = ", ".join(blocked)
        raise RuntimeError(
            "Migration 0008 tidak menghapus Batch 2 karena sudah berisi data pengguna: "
            f"{names}. Backup dan periksa data tersebut sebelum melanjutkan."
        )

    batches.delete()


def restore_empty_batches(apps, schema_editor):
    Site = apps.get_model("dms", "Site")
    InstallationBatch = apps.get_model("dms", "InstallationBatch")
    Document = apps.get_model("dms", "Document")
    definitions = {
        "SUM-BB-SGL-0238": {
            "QC": "REVISION_REQUIRED",
            "ATP": "NOT_STARTED",
            "FATP": "NOT_STARTED",
        },
        "SUM-BB-TDN-0361": {
            "QC": "NOT_STARTED",
            "ATP": "NOT_STARTED",
            "FATP": "NOT_STARTED",
        },
    }
    for tower_id, statuses in definitions.items():
        site = Site.objects.filter(
            project__code="NOKIA-DWDM",
            tower_id=tower_id,
        ).first()
        if not site:
            continue
        batch, _ = InstallationBatch.objects.get_or_create(
            site=site,
            batch_no=2,
            defaults={
                "label": "Batch 2",
                "pic_name": "ROBI",
                "status": "INSTALLED",
            },
        )
        for document_type, status in statuses.items():
            Document.objects.get_or_create(
                batch=batch,
                document_type=document_type,
                defaults={"status": status},
            )


class Migration(migrations.Migration):
    dependencies = [("dms", "0007_seed_default_fatp_sections")]

    operations = [
        migrations.RunPython(remove_duplicate_batches, restore_empty_batches),
    ]
