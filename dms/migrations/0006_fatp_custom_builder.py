from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_site_folders_to_batches(apps, schema_editor):
    InstallationBatch = apps.get_model("dms", "InstallationBatch")
    for batch in InstallationBatch.objects.select_related("site").all():
        if batch.site.drive_folder_url and not batch.drive_folder_url:
            batch.drive_folder_url = batch.site.drive_folder_url
            batch.save(update_fields=["drive_folder_url"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dms", "0005_site_drive_folder_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="installationbatch",
            name="drive_folder_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.RunPython(copy_site_folders_to_batches, migrations.RunPython.noop),
        migrations.CreateModel(
            name="FatpBuilder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installation_title", models.CharField(default="Installation Acceptance Test", max_length=220)),
                ("installation_date", models.DateField(blank=True, null=True)),
                ("work_description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("document", models.OneToOneField(limit_choices_to={"document_type": "FATP"}, on_delete=django.db.models.deletion.CASCADE, related_name="fatp_builder", to="dms.document")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_fatp_builders", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="FatpEquipment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence_no", models.PositiveSmallIntegerField(default=1)),
                ("name", models.CharField(max_length=180)),
                ("model", models.CharField(blank=True, max_length=160)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("notes", models.CharField(blank=True, max_length=220)),
                ("builder", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="equipment", to="dms.fatpbuilder")),
            ],
            options={"ordering": ["sequence_no", "pk"]},
        ),
        migrations.CreateModel(
            name="FatpSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence_no", models.PositiveSmallIntegerField(default=1)),
                ("title", models.CharField(max_length=220)),
                ("description", models.TextField(blank=True)),
                ("columns", models.PositiveSmallIntegerField(default=2)),
                ("page_break_before", models.BooleanField(default=False)),
                ("builder", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sections", to="dms.fatpbuilder")),
            ],
            options={"ordering": ["sequence_no", "pk"]},
        ),
        migrations.CreateModel(
            name="FatpPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence_no", models.PositiveSmallIntegerField(default=1)),
                ("storage_key", models.CharField(max_length=500, unique=True)),
                ("stored_filename", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=160)),
                ("file_size", models.PositiveBigIntegerField()),
                ("checksum_sha256", models.CharField(max_length=64)),
                ("caption", models.CharField(blank=True, max_length=220)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="dms.fatpsection")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="uploaded_fatp_photos", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["sequence_no", "pk"]},
        ),
    ]
