import dms.models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("full_name", models.CharField(max_length=160)),
                ("role", models.CharField(choices=[("SUPER_ADMIN", "Super Admin"), ("TRIPLEE_ADMIN", "Triple E Admin"), ("TRIPLEE_ENGINEER", "Triple E Engineer"), ("NOKIA_REVIEWER", "Nokia Reviewer"), ("NOKIA_VIEWER", "Nokia Viewer")], default="NOKIA_VIEWER", max_length=32)),
                ("must_change_password", models.BooleanField(default=True)),
                ("username", models.CharField(blank=True, max_length=160)),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={"abstract": False},
            managers=[("objects", dms.models.UserManager())],
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=180)),
                ("client", models.CharField(default="Nokia", max_length=120)),
                ("subcontractor", models.CharField(default="PT Triple E", max_length=160)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("locked_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Site",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("region", models.CharField(max_length=120)),
                ("tower_id", models.CharField(max_length=80)),
                ("name", models.CharField(max_length=160)),
                ("sequence_no", models.PositiveSmallIntegerField(default=1)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sites", to="dms.project")),
            ],
            options={"ordering": ["sequence_no", "name"]},
        ),
        migrations.CreateModel(
            name="InstallationBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("batch_no", models.PositiveSmallIntegerField(default=1)),
                ("label", models.CharField(default="Batch 1", max_length=80)),
                ("pic_name", models.CharField(blank=True, max_length=160)),
                ("scheduled_date", models.DateField(blank=True, null=True)),
                ("installed_at", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("PENDING_INSTALLATION", "Pending Installation"), ("INSTALLED", "Installed"), ("DOCUMENT_PREPARATION", "Document Preparation"), ("COMPLETED", "Completed")], default="PENDING_INSTALLATION", max_length=32)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="dms.site")),
            ],
            options={"ordering": ["site__sequence_no", "batch_no"]},
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(choices=[("QC", "QC"), ("ATP", "ATP"), ("FATP", "FATP")], max_length=8)),
                ("status", models.CharField(choices=[("NOT_STARTED", "Not Started"), ("DRAFT", "Draft"), ("UPLOADED", "Uploaded"), ("UNDER_REVIEW", "Under Review"), ("REVISION_REQUIRED", "Revision Required"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("NOT_APPLICABLE", "N/A")], default="NOT_STARTED", max_length=32)),
                ("legacy_note", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="dms.installationbatch")),
            ],
            options={"ordering": ["batch", "document_type"]},
        ),
        migrations.CreateModel(
            name="DocumentVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision_no", models.PositiveSmallIntegerField()),
                ("drive_file_id", models.CharField(max_length=255, unique=True)),
                ("stored_filename", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=160)),
                ("file_size", models.PositiveBigIntegerField()),
                ("checksum_sha256", models.CharField(max_length=64)),
                ("change_summary", models.TextField(blank=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("is_locked", models.BooleanField(default=False)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="dms.document")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="uploaded_versions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-revision_no"]},
        ),
        migrations.CreateModel(
            name="Review",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("APPROVED", "Approved"), ("REVISION_REQUIRED", "Request Revision"), ("REJECTED", "Rejected")], max_length=32)),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="dms.document")),
                ("reviewer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reviews", to=settings.AUTH_USER_MODEL)),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reviews", to="dms.documentversion")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DocumentComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_comments", to=settings.AUTH_USER_MODEL)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="dms.document")),
                ("version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="comments", to="dms.documentversion")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=80)),
                ("entity_type", models.CharField(max_length=80)),
                ("entity_id", models.CharField(blank=True, max_length=80)),
                ("description", models.CharField(max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activity_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("message", models.TextField()),
                ("url", models.CharField(blank=True, max_length=255)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GoogleDriveCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("encrypted_token", models.TextField()),
                ("google_email", models.EmailField(blank=True, max_length=254)),
                ("root_folder_id", models.CharField(blank=True, max_length=255)),
                ("backup_folder_id", models.CharField(blank=True, max_length=255)),
                ("connected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("connected_by", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="google_drive_credential", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="BackupRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("RUNNING", "Running"), ("SUCCESS", "Success"), ("FAILED", "Failed")], default="RUNNING", max_length=16)),
                ("drive_file_id", models.CharField(blank=True, max_length=255)),
                ("file_size", models.PositiveBigIntegerField(default=0)),
                ("message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddConstraint(
            model_name="site",
            constraint=models.UniqueConstraint(fields=("project", "tower_id"), name="unique_tower_per_project"),
        ),
        migrations.AddConstraint(
            model_name="installationbatch",
            constraint=models.UniqueConstraint(fields=("site", "batch_no"), name="unique_batch_per_site"),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(fields=("batch", "document_type"), name="unique_document_type_per_batch"),
        ),
        migrations.AddConstraint(
            model_name="documentversion",
            constraint=models.UniqueConstraint(fields=("document", "revision_no"), name="unique_revision_per_document"),
        ),
    ]
