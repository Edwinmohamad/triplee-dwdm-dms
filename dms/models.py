from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, password, **extra_fields):
        if not username:
            raise ValueError("Username wajib diisi")
        username = self.model.normalize_username(username).strip().lower()
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser harus memiliki is_staff dan is_superuser")
        return self._create_user(username, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        TRIPLEE_ADMIN = "TRIPLEE_ADMIN", "Triple E Admin"
        TRIPLEE_ENGINEER = "TRIPLEE_ENGINEER", "Triple E Engineer"
        NOKIA_REVIEWER = "NOKIA_REVIEWER", "Nokia Reviewer"
        NOKIA_VIEWER = "NOKIA_VIEWER", "Nokia Viewer"

    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator()],
    )
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=160)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.NOKIA_VIEWER)
    must_change_password = models.BooleanField(default=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    def save(self, *args, **kwargs):
        self.username = self.normalize_username(self.username).strip().lower()
        self.email = self.__class__.objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or self.username

    @property
    def is_triplee(self):
        return self.role in {self.Role.SUPER_ADMIN, self.Role.TRIPLEE_ADMIN, self.Role.TRIPLEE_ENGINEER}

    @property
    def can_review(self):
        return self.role == self.Role.SUPER_ADMIN


class Project(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=180)
    client = models.CharField(max_length=120, default="Nokia")
    subcontractor = models.CharField(max_length=160, default="PT Triple E")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Site(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sites")
    region = models.CharField(max_length=120)
    tower_id = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    sequence_no = models.PositiveSmallIntegerField(default=1)
    drive_folder_url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ["sequence_no", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "tower_id"], name="unique_tower_per_project")
        ]

    def __str__(self):
        return f"{self.name} ({self.tower_id})"


class InstallationBatch(models.Model):
    class Status(models.TextChoices):
        PENDING_INSTALLATION = "PENDING_INSTALLATION", "Pending Installation"
        INSTALLED = "INSTALLED", "Installed"
        DOCUMENT_PREPARATION = "DOCUMENT_PREPARATION", "Document Preparation"
        COMPLETED = "COMPLETED", "Completed"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="batches")
    batch_no = models.PositiveSmallIntegerField(default=1)
    label = models.CharField(max_length=80, default="Batch 1")
    pic_name = models.CharField(max_length=160, blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    installed_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_INSTALLATION)
    notes = models.TextField(blank=True)
    drive_folder_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["site__sequence_no", "batch_no"]
        constraints = [
            models.UniqueConstraint(fields=["site", "batch_no"], name="unique_batch_per_site")
        ]

    def __str__(self):
        return f"{self.site.name} - {self.label}"


class Document(models.Model):
    class Type(models.TextChoices):
        QC = "QC", "QC"
        ATP = "ATP", "ATP"
        FATP = "FATP", "FATP"

    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        DRAFT = "DRAFT", "Draft"
        UPLOADED = "UPLOADED", "Uploaded"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        REVISION_REQUIRED = "REVISION_REQUIRED", "Revision Required"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        NOT_APPLICABLE = "NOT_APPLICABLE", "N/A"

    batch = models.ForeignKey(InstallationBatch, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=8, choices=Type.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NOT_STARTED)
    legacy_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["batch", "document_type"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "document_type"], name="unique_document_type_per_batch")
        ]

    def __str__(self):
        return f"{self.batch} - {self.document_type}"

    @property
    def latest_version(self):
        return self.versions.order_by("-revision_no").first()

    @property
    def progress_value(self):
        return {
            self.Status.NOT_STARTED: 0,
            self.Status.DRAFT: 10,
            self.Status.UPLOADED: 30,
            self.Status.UNDER_REVIEW: 60,
            self.Status.REVISION_REQUIRED: 50,
            self.Status.APPROVED: 100,
            self.Status.REJECTED: 0,
            self.Status.NOT_APPLICABLE: 0,
        }.get(self.status, 0)


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    revision_no = models.PositiveSmallIntegerField()
    storage_key = models.CharField(max_length=500, unique=True)
    stored_filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=160)
    file_size = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(max_length=64)
    change_summary = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_versions")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-revision_no"]
        constraints = [
            models.UniqueConstraint(fields=["document", "revision_no"], name="unique_revision_per_document")
        ]

    def __str__(self):
        return f"{self.document} Rev {self.revision_no}"

    @property
    def has_file(self):
        return self.file_size > 0 and not self.storage_key.startswith("__deleted__/")


class DocumentAttachment(models.Model):
    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    sequence_no = models.PositiveSmallIntegerField()
    storage_key = models.CharField(max_length=500, unique=True)
    stored_filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=160)
    file_size = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(max_length=64)
    description = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_no", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "sequence_no"],
                name="unique_attachment_sequence_per_version",
            ),
        ]

    def __str__(self):
        return f"{self.version} - {self.original_filename}"


class FatpBuilder(models.Model):
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="fatp_builder",
        limit_choices_to={"document_type": Document.Type.FATP},
    )
    installation_title = models.CharField(
        max_length=220,
        default="Installation Acceptance Test",
    )
    installation_date = models.DateField(null=True, blank=True)
    work_description = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_fatp_builders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FATP Builder - {self.document.batch}"


class FatpEquipment(models.Model):
    builder = models.ForeignKey(
        FatpBuilder,
        on_delete=models.CASCADE,
        related_name="equipment",
    )
    sequence_no = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=180)
    model = models.CharField(max_length=160, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    notes = models.CharField(max_length=220, blank=True)

    class Meta:
        ordering = ["sequence_no", "pk"]

    def __str__(self):
        return f"{self.name} ({self.quantity})"


class FatpSection(models.Model):
    builder = models.ForeignKey(
        FatpBuilder,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    sequence_no = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    columns = models.PositiveSmallIntegerField(default=2)
    page_break_before = models.BooleanField(default=False)

    class Meta:
        ordering = ["sequence_no", "pk"]

    def __str__(self):
        return f"{self.sequence_no}. {self.title}"


class FatpPhoto(models.Model):
    section = models.ForeignKey(
        FatpSection,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    sequence_no = models.PositiveSmallIntegerField(default=1)
    storage_key = models.CharField(max_length=500, unique=True)
    stored_filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=160)
    file_size = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(max_length=64)
    caption = models.CharField(max_length=220, blank=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="uploaded_fatp_photos",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_no", "pk"]

    def __str__(self):
        return f"{self.section} - Foto {self.sequence_no}"


class Review(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REVISION_REQUIRED = "REVISION_REQUIRED", "Request Revision"
        REJECTED = "REJECTED", "Rejected"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="reviews")
    version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reviews")
    decision = models.CharField(max_length=32, choices=Decision.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class DocumentComment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="comments")
    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
    )
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="document_comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ActivityLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80, blank=True)
    description = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BackupRecord(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    storage_key = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    message = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class LoginAttempt(models.Model):
    identifier = models.CharField(max_length=150, unique=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_locked(self):
        return self.locked_until and self.locked_until > timezone.now()
