import mimetypes
import shutil
import zipfile
from pathlib import Path
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    BatchUpdateForm,
    CommentForm,
    DocumentUploadForm,
    InitialSetupForm,
    ReviewForm,
    SecureAuthenticationForm,
    UserCreateForm,
    UserUpdateForm,
)
from .models import (
    ActivityLog,
    BackupRecord,
    Document,
    DocumentAttachment,
    DocumentComment,
    DocumentVersion,
    InstallationBatch,
    Notification,
    Review,
    Site,
    User,
)
from .services.audit import client_ip, log_activity
from .services.local_storage import (
    checksum_file,
    delete_document_file,
    open_document_file,
    store_document_file,
)
from .services.notifications import notify_roles


ADMIN_ROLES = {User.Role.SUPER_ADMIN, User.Role.TRIPLEE_ADMIN}
UPLOAD_ROLES = {User.Role.SUPER_ADMIN, User.Role.TRIPLEE_ADMIN, User.Role.TRIPLEE_ENGINEER}
REVIEW_ROLES = {User.Role.SUPER_ADMIN}
UPLOADABLE_STATUSES = {
    Document.Status.NOT_STARTED,
    Document.Status.DRAFT,
    Document.Status.UPLOADED,
    Document.Status.REVISION_REQUIRED,
    Document.Status.REJECTED,
}
HISTORICAL_STATUSES_WITHOUT_FILE = {
    Document.Status.UNDER_REVIEW,
    Document.Status.APPROVED,
}


def _summarize_documents(documents):
    statuses = {document.status for document in documents}
    if not documents or statuses <= {Document.Status.NOT_STARTED, Document.Status.NOT_APPLICABLE}:
        return {"code": Document.Status.NOT_STARTED, "label": "Not Started"}
    if Document.Status.REVISION_REQUIRED in statuses or Document.Status.REJECTED in statuses:
        return {"code": Document.Status.REVISION_REQUIRED, "label": "Perlu Revisi"}
    if statuses <= {Document.Status.APPROVED, Document.Status.NOT_APPLICABLE}:
        return {"code": Document.Status.APPROVED, "label": "Approved"}
    if Document.Status.UNDER_REVIEW in statuses:
        return {"code": Document.Status.UNDER_REVIEW, "label": "Under Review"}
    return {"code": "IN_PROGRESS", "label": "In Progress"}


def health(request):
    return JsonResponse({"status": "ok", "service": "triplee-dwdm-dms"})


def setup_view(request):
    if User.objects.exists():
        return redirect("login")
    form = InitialSetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        ActivityLog.objects.create(
            actor=user,
            action="INITIAL_SETUP",
            entity_type="User",
            entity_id=str(user.pk),
            description="Initial setup dan Super Admin dibuat",
            ip_address=client_ip(request),
        )
        messages.success(request, "Super Admin berhasil dibuat. Silakan login.")
        return redirect("login")
    return render(request, "setup.html", {"form": form})


class DMSLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = SecureAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect("setup")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(self.request, "LOGIN", self.request.user, "Pengguna login")
        if self.request.user.must_change_password:
            return redirect("change_password")
        return response


@login_required
@require_POST
def logout_view(request):
    log_activity(request, "LOGOUT", request.user, "Pengguna logout")
    logout(request)
    return redirect("login")


@login_required
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        log_activity(request, "PASSWORD_CHANGED", user, "Password pengguna diubah")
        messages.success(request, "Password berhasil diubah.")
        return redirect("dashboard")
    return render(request, "change_password.html", {"form": form})


@login_required
def dashboard(request):
    documents = Document.objects.select_related("batch__site")
    applicable = documents.exclude(status=Document.Status.NOT_APPLICABLE)
    total_documents = applicable.count()
    approved = applicable.filter(status=Document.Status.APPROVED).count()
    site_rows = list(Site.objects.prefetch_related("batches__documents"))
    completed_sites = 0
    revision_sites = 0
    for site in site_rows:
        site_documents = [
            document
            for batch in site.batches.all()
            for document in batch.documents.all()
            if document.status != Document.Status.NOT_APPLICABLE
        ]
        has_revision = any(
            document.status in {Document.Status.REVISION_REQUIRED, Document.Status.REJECTED}
            for document in site_documents
        )
        if site_documents and all(document.status == Document.Status.APPROVED for document in site_documents):
            completed_sites += 1
        elif has_revision:
            revision_sites += 1
    metrics = {
        "sites": len(site_rows),
        "batches": InstallationBatch.objects.count(),
        "documents": total_documents,
        "approved": approved,
        "sites_completed": completed_sites,
        "sites_revision": revision_sites,
        "sites_pending": len(site_rows) - completed_sites - revision_sites,
        "under_review": applicable.filter(status=Document.Status.UNDER_REVIEW).count(),
        "revision_required": applicable.filter(status=Document.Status.REVISION_REQUIRED).count(),
        "not_started": applicable.filter(status=Document.Status.NOT_STARTED).count(),
        "progress": round((approved / total_documents) * 100) if total_documents else 0,
    }
    type_summary = []
    for doc_type, label in Document.Type.choices:
        subset = applicable.filter(document_type=doc_type)
        count = subset.count()
        approved_count = subset.filter(status=Document.Status.APPROVED).count()
        type_summary.append(
            {
                "type": label,
                "total": count,
                "approved": approved_count,
                "under_review": subset.filter(status=Document.Status.UNDER_REVIEW).count(),
                "revision": subset.filter(status=Document.Status.REVISION_REQUIRED).count(),
                "progress": round((approved_count / count) * 100) if count else 0,
            }
        )
    attention = applicable.filter(
        Q(status=Document.Status.REVISION_REQUIRED)
        | Q(status=Document.Status.REJECTED)
        | Q(batch__status=InstallationBatch.Status.PENDING_INSTALLATION)
    ).select_related("batch__site")[:8]
    recent_activity = ActivityLog.objects.select_related("actor")[:8]
    return render(
        request,
        "dashboard.html",
        {
            "metrics": metrics,
            "type_summary": type_summary,
            "attention": attention,
            "recent_activity": recent_activity,
        },
    )


@login_required
def site_list(request):
    sites = list(Site.objects.select_related("project").prefetch_related("batches__documents"))
    for site in sites:
        site_documents = [
            document
            for batch in site.batches.all()
            for document in batch.documents.all()
            if document.status != Document.Status.NOT_APPLICABLE
        ]
        site.document_total = len(site_documents)
        site.document_approved = sum(
            document.status == Document.Status.APPROVED for document in site_documents
        )
        site.document_progress = (
            round(site.document_approved / site.document_total * 100) if site.document_total else 0
        )
        site.document_summaries = []
        for document_type, label in Document.Type.choices:
            type_documents = [
                document for document in site_documents if document.document_type == document_type
            ]
            site.document_summaries.append(
                {"type": label, **_summarize_documents(type_documents)}
            )
        site.overall = _summarize_documents(site_documents)
        if any(
            batch.status == InstallationBatch.Status.PENDING_INSTALLATION
            for batch in site.batches.all()
        ) and site.document_progress == 0:
            site.overall = {"code": "PENDING_INSTALLATION", "label": "Pending Instalasi"}
        site.filter_status = {
            Document.Status.APPROVED: "complete",
            Document.Status.REVISION_REQUIRED: "revision",
            Document.Status.UNDER_REVIEW: "review",
            "PENDING_INSTALLATION": "pending",
        }.get(site.overall["code"], "progress")
    regions = sorted({site.region for site in sites})
    return render(request, "sites.html", {"sites": sites, "regions": regions})


@login_required
def site_detail(request, pk):
    site = get_object_or_404(Site.objects.select_related("project"), pk=pk)
    batches = site.batches.prefetch_related("documents").all()
    return render(request, "site_detail.html", {"site": site, "batches": batches})


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(
        InstallationBatch.objects.select_related("site__project").prefetch_related("documents__versions"),
        pk=pk,
    )
    documents = batch.documents.all()
    return render(request, "batch_detail.html", {"batch": batch, "documents": documents})


@role_required(*ADMIN_ROLES)
def batch_update(request, pk):
    batch = get_object_or_404(InstallationBatch, pk=pk)
    form = BatchUpdateForm(request.POST or None, instance=batch)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(request, "BATCH_UPDATED", batch, f"Batch {batch} diperbarui")
        messages.success(request, "Installation batch berhasil diperbarui.")
        return redirect("batch_detail", pk=batch.pk)
    return render(request, "batch_form.html", {"form": form, "batch": batch})


@login_required
def document_detail(request, pk):
    document = get_object_or_404(
        Document.objects.select_related("batch__site__project").prefetch_related(
            "versions__uploaded_by",
            "versions__attachments",
            "reviews__reviewer",
            "comments__author",
        ),
        pk=pk,
    )
    latest_version = document.latest_version
    historical_status_without_file = (
        document.status in HISTORICAL_STATUSES_WITHOUT_FILE and not latest_version
    )
    upload_allowed_by_state = document.status in UPLOADABLE_STATUSES or historical_status_without_file
    return render(
        request,
        "document_detail.html",
        {
            "document": document,
            "upload_form": DocumentUploadForm(
                allow_multiple=document.document_type == Document.Type.QC
            ),
            "review_form": ReviewForm(),
            "comment_form": CommentForm(),
            "can_upload": request.user.role in UPLOAD_ROLES,
            "can_review": request.user.role in REVIEW_ROLES,
            "can_upload_file": (
                request.user.role in UPLOAD_ROLES
                and document.batch.status != InstallationBatch.Status.PENDING_INSTALLATION
                and upload_allowed_by_state
            ),
            "can_submit": (
                request.user.role in UPLOAD_ROLES
                and bool(latest_version)
                and document.status
                in {
                    Document.Status.UPLOADED,
                    Document.Status.DRAFT,
                }
            ),
            "can_reopen": request.user.role in ADMIN_ROLES and document.status == Document.Status.APPROVED,
            "historical_status_without_file": historical_status_without_file,
        },
    )


@role_required(*UPLOAD_ROLES)
@require_POST
def document_upload(request, pk):
    document = get_object_or_404(Document.objects.select_related("batch__site"), pk=pk)
    form = DocumentUploadForm(
        request.POST,
        request.FILES,
        allow_multiple=document.document_type == Document.Type.QC,
    )
    if document.batch.status == InstallationBatch.Status.PENDING_INSTALLATION:
        messages.error(request, "Dokumen belum dapat diunggah karena instalasi masih pending.")
        return redirect("document_detail", pk=pk)
    historical_status = (
        document.status
        if document.status in HISTORICAL_STATUSES_WITHOUT_FILE and not document.latest_version
        else None
    )
    if document.status not in UPLOADABLE_STATUSES and not historical_status:
        messages.error(request, "Dokumen tidak dapat diunggah pada status saat ini.")
        return redirect("document_detail", pk=pk)
    if document.status == Document.Status.APPROVED and not historical_status:
        messages.error(request, "Dokumen Approved terkunci. Admin harus membuka kembali terlebih dahulu.")
        return redirect("document_detail", pk=pk)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("document_detail", pk=pk)

    uploads = form.cleaned_data["files"]
    upload_items = []
    seen_checksums = set()
    for uploaded in uploads:
        checksum = checksum_file(uploaded)
        duplicate_exists = document.versions.filter(
            Q(checksum_sha256=checksum) | Q(attachments__checksum_sha256=checksum)
        ).exists()
        if checksum in seen_checksums or duplicate_exists:
            messages.error(
                request,
                f"File {uploaded.name} sama dengan file yang sudah dipilih atau pernah diunggah.",
            )
            return redirect("document_detail", pk=pk)
        seen_checksums.add(checksum)
        upload_items.append((uploaded, checksum))

    latest_version = document.latest_version
    append_to_latest = bool(
        latest_version
        and not latest_version.is_locked
        and document.status in {Document.Status.UPLOADED, Document.Status.DRAFT}
    )
    if append_to_latest:
        version = latest_version
        revision_no = version.revision_no
        first_sequence = version.attachments.count() + 1
    else:
        latest_revision = (
            document.versions.order_by("-revision_no")
            .values_list("revision_no", flat=True)
            .first()
        )
        revision_no = 0 if latest_revision is None else latest_revision + 1
        first_sequence = 1

    stored_items = []
    try:
        for offset, (uploaded, checksum) in enumerate(upload_items):
            sequence_no = first_sequence + offset
            storage_result = store_document_file(
                document,
                uploaded,
                revision_no,
                attachment_no=sequence_no,
            )
            stored_items.append(
                {
                    "uploaded": uploaded,
                    "checksum": checksum,
                    "sequence_no": sequence_no,
                    "storage": storage_result,
                }
            )
    except Exception as exc:
        for item in stored_items:
            delete_document_file(item["storage"]["storage_key"])
        messages.error(request, f"File gagal disimpan ke server: {exc}")
        return redirect("document_detail", pk=pk)

    try:
        with transaction.atomic():
            if not append_to_latest:
                primary = stored_items[0]
                version = DocumentVersion.objects.create(
                    document=document,
                    revision_no=revision_no,
                    storage_key=primary["storage"]["storage_key"],
                    stored_filename=primary["storage"]["stored_filename"],
                    original_filename=primary["uploaded"].name,
                    mime_type=primary["storage"]["mime_type"],
                    file_size=sum(item["storage"]["file_size"] for item in stored_items),
                    checksum_sha256=primary["checksum"],
                    change_summary=form.cleaned_data["change_summary"],
                    uploaded_by=request.user,
                )
            for item in stored_items:
                DocumentAttachment.objects.create(
                    version=version,
                    sequence_no=item["sequence_no"],
                    storage_key=item["storage"]["storage_key"],
                    stored_filename=item["storage"]["stored_filename"],
                    original_filename=item["uploaded"].name,
                    mime_type=item["storage"]["mime_type"],
                    file_size=item["storage"]["file_size"],
                    checksum_sha256=item["checksum"],
                )

            if append_to_latest:
                version.file_size = version.attachments.aggregate(total=Sum("file_size"))["total"] or 0
                new_summary = form.cleaned_data["change_summary"].strip()
                if new_summary:
                    version.change_summary = "\n".join(
                        value for value in [version.change_summary, new_summary] if value
                    )
                version.save(update_fields=["file_size", "change_summary"])
                document.status = Document.Status.UPLOADED
                document.approved_at = None
            elif historical_status:
                version.is_locked = True
                version.save(update_fields=["is_locked"])
                document.status = historical_status
                if historical_status == Document.Status.APPROVED:
                    document.approved_at = document.approved_at or timezone.now()
                else:
                    document.submitted_at = document.submitted_at or timezone.now()
                    document.approved_at = None
            else:
                document.status = Document.Status.UPLOADED
                document.approved_at = None
            document.save(
                update_fields=["status", "submitted_at", "approved_at", "updated_at"]
            )
    except Exception as exc:
        for item in stored_items:
            delete_document_file(item["storage"]["storage_key"])
        messages.error(request, f"Data versi dokumen gagal disimpan: {exc}")
        return redirect("document_detail", pk=pk)
    log_activity(
        request,
        "DOCUMENT_UPLOADED",
        version,
        f"{len(stored_items)} file ditambahkan ke {document.document_type} Rev {revision_no}",
        {
            "document_id": document.pk,
            "revision": revision_no,
            "file_count": len(stored_items),
            "appended": append_to_latest,
            "checksums": [item["checksum"] for item in stored_items],
        },
    )
    action_label = "ditambahkan ke" if append_to_latest else "diunggah sebagai"
    messages.success(
        request,
        f"{len(stored_items)} file berhasil {action_label} Rev {revision_no}.",
    )
    return redirect("document_detail", pk=pk)


@role_required(*UPLOAD_ROLES)
@require_POST
def document_submit(request, pk):
    document = get_object_or_404(Document, pk=pk)
    latest = document.latest_version
    if not latest:
        messages.error(request, "Unggah dokumen terlebih dahulu.")
        return redirect("document_detail", pk=pk)
    if document.status not in {Document.Status.UPLOADED, Document.Status.DRAFT}:
        messages.error(request, "Status dokumen tidak dapat disubmit.")
        return redirect("document_detail", pk=pk)
    document.status = Document.Status.UNDER_REVIEW
    document.submitted_at = timezone.now()
    document.save(update_fields=["status", "submitted_at", "updated_at"])
    latest.is_locked = True
    latest.save(update_fields=["is_locked"])
    url = reverse("document_detail", args=[document.pk])
    notify_roles(
        [User.Role.NOKIA_REVIEWER],
        f"{document.document_type} menunggu review",
        f"{document.batch.site.name} - {document.batch.label} Rev {latest.revision_no}",
        url,
    )
    log_activity(request, "DOCUMENT_SUBMITTED", document, f"{document} disubmit ke Nokia")
    messages.success(request, "Dokumen berhasil disubmit ke Nokia.")
    return redirect("document_detail", pk=pk)


@role_required(*REVIEW_ROLES)
@require_POST
def document_review(request, pk):
    document = get_object_or_404(Document, pk=pk)
    latest = document.latest_version
    form = ReviewForm(request.POST)
    if document.status != Document.Status.UNDER_REVIEW or not latest:
        messages.error(request, "Dokumen tidak sedang menunggu review.")
        return redirect("document_detail", pk=pk)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("document_detail", pk=pk)
    decision = form.cleaned_data["decision"]
    Review.objects.create(
        document=document,
        version=latest,
        reviewer=request.user,
        decision=decision,
        comment=form.cleaned_data["comment"],
    )
    if decision == Review.Decision.APPROVED:
        document.status = Document.Status.APPROVED
        document.approved_at = timezone.now()
    elif decision == Review.Decision.REVISION_REQUIRED:
        document.status = Document.Status.REVISION_REQUIRED
        document.approved_at = None
    else:
        document.status = Document.Status.REJECTED
        document.approved_at = None
    document.save(update_fields=["status", "approved_at", "updated_at"])
    url = reverse("document_detail", args=[document.pk])
    notify_roles(
        [User.Role.SUPER_ADMIN, User.Role.TRIPLEE_ADMIN, User.Role.TRIPLEE_ENGINEER],
        f"Review {document.document_type}: {document.get_status_display()}",
        f"{document.batch.site.name} - {document.batch.label} Rev {latest.revision_no}",
        url,
        exclude_user=request.user,
    )
    log_activity(
        request,
        "DOCUMENT_REVIEWED",
        document,
        f"{document} direview: {document.get_status_display()}",
        {"decision": decision, "revision": latest.revision_no},
    )
    messages.success(request, "Keputusan review berhasil disimpan.")
    return redirect("document_detail", pk=pk)


@role_required(*ADMIN_ROLES)
@require_POST
def document_reopen(request, pk):
    document = get_object_or_404(Document, pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    if document.status != Document.Status.APPROVED:
        messages.error(request, "Hanya dokumen Approved yang dapat dibuka kembali.")
    elif not reason:
        messages.error(request, "Alasan membuka kembali wajib diisi.")
    else:
        document.status = Document.Status.REVISION_REQUIRED
        document.approved_at = None
        document.save(update_fields=["status", "approved_at", "updated_at"])
        log_activity(request, "DOCUMENT_REOPENED", document, f"Dokumen dibuka kembali: {reason}")
        messages.success(request, "Dokumen dibuka kembali untuk revisi.")
    return redirect("document_detail", pk=pk)


@login_required
@require_POST
def document_comment(request, pk):
    document = get_object_or_404(Document, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.document = document
        comment.version = document.latest_version
        comment.author = request.user
        comment.save()
        url = reverse("document_detail", args=[document.pk])
        if request.user.is_triplee:
            roles = [User.Role.NOKIA_REVIEWER, User.Role.NOKIA_VIEWER]
        else:
            roles = [User.Role.SUPER_ADMIN, User.Role.TRIPLEE_ADMIN, User.Role.TRIPLEE_ENGINEER]
        notify_roles(roles, f"Komentar baru pada {document.document_type}", comment.body[:160], url, request.user)
        log_activity(request, "COMMENT_ADDED", comment, f"Komentar ditambahkan pada {document}")
        messages.success(request, "Komentar ditambahkan.")
    else:
        messages.error(request, "Komentar tidak boleh kosong.")
    return redirect("document_detail", pk=pk)


def _stored_file_response(request, entity, document_id, mode="download"):
    try:
        handle = open_document_file(entity.storage_key)
    except Exception as exc:
        messages.error(request, f"File tidak dapat diambil dari server: {exc}")
        return redirect("document_detail", pk=document_id)
    inline = mode == "preview" and entity.mime_type in {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }
    response = FileResponse(
        handle,
        as_attachment=not inline,
        filename=entity.stored_filename,
        content_type=entity.mime_type,
    )
    log_activity(
        request,
        "DOCUMENT_PREVIEWED" if inline else "DOCUMENT_DOWNLOADED",
        entity,
        f"{entity} {'dipreview' if inline else 'diunduh'}",
    )
    return response


@login_required
def attachment_file(request, attachment_pk, mode="download"):
    attachment = get_object_or_404(
        DocumentAttachment.objects.select_related("version__document"),
        pk=attachment_pk,
    )
    return _stored_file_response(
        request,
        attachment,
        attachment.version.document_id,
        mode,
    )


@login_required
def document_file(request, version_pk, mode="download"):
    version = get_object_or_404(
        DocumentVersion.objects.select_related("document").prefetch_related("attachments"),
        pk=version_pk,
    )
    attachment = version.attachments.first()
    if attachment:
        return _stored_file_response(request, attachment, version.document_id, mode)
    return _stored_file_response(request, version, version.document_id, mode)


@login_required
def version_download_all(request, version_pk):
    version = get_object_or_404(
        DocumentVersion.objects.select_related("document__batch__site").prefetch_related(
            "attachments"
        ),
        pk=version_pk,
    )
    attachments = list(version.attachments.all())
    if not attachments:
        return document_file(request, version_pk, mode="download")

    bundle = SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for attachment in attachments:
                archive_name = Path(
                    attachment.stored_filename.replace("\\", "/")
                ).name
                with open_document_file(attachment.storage_key) as source:
                    with archive.open(archive_name, "w") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
        bundle.seek(0)
    except Exception as exc:
        bundle.close()
        messages.error(request, f"Paket ZIP tidak dapat dibuat: {exc}")
        return redirect("document_detail", pk=version.document_id)

    site = version.document.batch.site
    filename = (
        f"{site.tower_id}_BATCH-{version.document.batch.batch_no:02d}_"
        f"{version.document.document_type}_REV-{version.revision_no:03d}.zip"
    )
    log_activity(
        request,
        "DOCUMENT_BUNDLE_DOWNLOADED",
        version,
        f"{version} diunduh sebagai ZIP ({len(attachments)} file)",
    )
    return FileResponse(
        bundle,
        as_attachment=True,
        filename=filename,
        content_type="application/zip",
    )


@login_required
def notifications(request):
    items = request.user.notifications.all()[:100]
    return render(request, "notifications.html", {"notifications": items})


@login_required
@require_POST
def notification_read(request, pk):
    item = get_object_or_404(Notification, pk=pk, user=request.user)
    item.is_read = True
    item.save(update_fields=["is_read"])
    return redirect(item.url or "notifications")


@login_required
@require_POST
def notifications_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, "Semua notifikasi ditandai sudah dibaca.")
    return redirect("notifications")


@role_required(*ADMIN_ROLES)
def audit_log(request):
    logs = ActivityLog.objects.select_related("actor")[:300]
    return render(request, "audit.html", {"logs": logs})


@role_required(*ADMIN_ROLES)
def user_management(request):
    form = UserCreateForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        log_activity(request, "USER_CREATED", user, f"Pengguna {user.username} dibuat")
        messages.success(request, "Pengguna berhasil dibuat.")
        return redirect("user_management")
    role_choices = User.Role.choices
    if request.user.role != User.Role.SUPER_ADMIN:
        role_choices = [choice for choice in role_choices if choice[0] != User.Role.SUPER_ADMIN]
    return render(
        request,
        "users.html",
        {"users": User.objects.order_by("full_name"), "form": form, "role_choices": role_choices},
    )


@role_required(*ADMIN_ROLES)
@require_POST
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    requested_active = "is_active" in request.POST
    requested_role = request.POST.get("role")
    if user == request.user and (requested_role != user.role or not requested_active):
        messages.error(request, "Anda tidak dapat mengubah role atau menonaktifkan akun sendiri.")
        return redirect("user_management")
    if user.role == User.Role.SUPER_ADMIN and request.user.role != User.Role.SUPER_ADMIN:
        raise PermissionDenied
    removing_super_admin = user.role == User.Role.SUPER_ADMIN and (
        requested_role != User.Role.SUPER_ADMIN or not requested_active
    )
    if removing_super_admin and User.objects.filter(
        role=User.Role.SUPER_ADMIN, is_active=True
    ).count() <= 1:
        messages.error(request, "Super Admin aktif terakhir tidak dapat dinonaktifkan atau diturunkan rolenya.")
        return redirect("user_management")
    form = UserUpdateForm(request.POST, instance=user, actor=request.user)
    if form.is_valid():
        form.save()
        log_activity(request, "USER_UPDATED", user, f"Pengguna {user.username} diperbarui")
        messages.success(request, "Pengguna berhasil diperbarui.")
    else:
        messages.error(request, "Data pengguna tidak valid.")
    return redirect("user_management")


def brand_logo(request):
    logo_path = Path(settings.BRAND_LOGO_PATH)
    if not logo_path.is_file():
        raise Http404("Logo belum tersedia")
    content_type = mimetypes.guess_type(logo_path.name)[0] or "image/png"
    return FileResponse(logo_path.open("rb"), content_type=content_type)


@role_required(User.Role.SUPER_ADMIN)
def storage_status(request):
    storage_root = Path(settings.DOCUMENT_STORAGE_ROOT)
    storage_root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(storage_root)
    document_bytes = DocumentVersion.objects.aggregate(total=Sum("file_size"))["total"] or 0
    latest_backup = BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS).first()
    return render(
        request,
        "storage.html",
        {
            "storage_path": settings.DOCUMENT_STORAGE_DISPLAY_PATH,
            "document_count": DocumentVersion.objects.count(),
            "document_bytes": document_bytes,
            "disk_total": usage.total,
            "disk_used": usage.used,
            "disk_free": usage.free,
            "disk_percent": round(usage.used / usage.total * 100) if usage.total else 0,
            "latest_backup": latest_backup,
        },
    )


@role_required(User.Role.SUPER_ADMIN)
def backup_status(request):
    return render(request, "backups.html", {"backups": BackupRecord.objects.all()[:100]})


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def backup_run(request):
    try:
        call_command("backup_database")
        messages.success(request, "Backup database berhasil dijalankan.")
    except Exception as exc:
        messages.error(request, f"Backup gagal: {exc}")
    return redirect("backup_status")
