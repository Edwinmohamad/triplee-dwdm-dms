from django.db import migrations, models
import django.db.models.deletion


def copy_existing_files(apps, schema_editor):
    DocumentVersion = apps.get_model("dms", "DocumentVersion")
    DocumentAttachment = apps.get_model("dms", "DocumentAttachment")
    attachments = []
    for version in DocumentVersion.objects.all().iterator():
        attachments.append(
            DocumentAttachment(
                version_id=version.pk,
                sequence_no=1,
                storage_key=version.storage_key,
                stored_filename=version.stored_filename,
                original_filename=version.original_filename,
                mime_type=version.mime_type,
                file_size=version.file_size,
                checksum_sha256=version.checksum_sha256,
            )
        )
    DocumentAttachment.objects.bulk_create(attachments, batch_size=500)


def remove_copied_files(apps, schema_editor):
    apps.get_model("dms", "DocumentAttachment").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("dms", "0003_local_server_storage")]

    operations = [
        migrations.CreateModel(
            name="DocumentAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence_no", models.PositiveSmallIntegerField()),
                ("storage_key", models.CharField(max_length=500, unique=True)),
                ("stored_filename", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=160)),
                ("file_size", models.PositiveBigIntegerField()),
                ("checksum_sha256", models.CharField(max_length=64)),
                ("description", models.CharField(blank=True, max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="dms.documentversion")),
            ],
            options={"ordering": ["sequence_no", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="documentattachment",
            constraint=models.UniqueConstraint(fields=("version", "sequence_no"), name="unique_attachment_sequence_per_version"),
        ),
        migrations.RunPython(copy_existing_files, remove_copied_files),
    ]
