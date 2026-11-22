import mimetypes
import shutil
import zipfile
from pathlib import Path
from tempfile import SpooledTemporaryFile

from PIL import Image as PillowImage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction
from django.db.models import Max, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    BatchUpdateForm,
    CommentForm,
    DocumentUploadForm,
    DriveFolderForm,
    FatpBuilderForm,
    FatpSectionForm,
    InitialSetupForm,
    ManualDocumentStatusForm,
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
    FatpBuilder,
    FatpEquipment,
    FatpPhoto,
    FatpSection,
    InstallationBatch,
    Notification,
    Review,
    Site,
    User,
)
from .services.audit import client_ip, log_activity
from .services.local_storage import (
    bundle_filename,
    checksum_file,
    delete_document_file,
    document_filename,
    download_filename,
    open_document_file,
    store_document_file,
    store_fatp_photo,
)
from .services.fatp_pdf import build_fatp_pdf
from .services.fatp_defaults import DEFAULT_FATP_SECTIONS, seed_default_fatp_sections
from .services.notifications import notify_roles
from .services.progress_pdf import build_progress_pdf
from .services.progress_report import build_progress_report
from .services.project_control import collect_project_control


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
    control = collect_project_control()
    control["recent_activity"] = ActivityLog.objects.select_related("actor")[:10]
    return render(
        request,
        "dashboard.html",
        control,
    )


@login_required
def installation_photos(request):
    sites = list(
        Site.objects.prefetch_related("batches__documents").order_by("sequence_no", "name")
    )
    total_batches = 0
    connected_count = 0
    for site in sites:
        batches = list(site.batches.all())
        site.photo_batch_count = len(batches)
        site.connected_batches = sum(bool(batch.drive_folder_url) for batch in batches)
        site.photo_status = "connected" if site.connected_batches else "missing"
        total_batches += len(batches)
        connected_count += site.connected_batches
        for batch in batches:
            documents = [
                document
                for document in batch.documents.all()
                if document.status != Document.Status.NOT_APPLICABLE
            ]
            batch.photo_documents = documents
            batch.photo_progress = (
                round(
                    sum(document.status == Document.Status.APPROVED for document in documents)
                    / len(documents)
                    * 100
                )
                if documents
                else 0
            )
    selected_id = request.GET.get("site")
    if not selected_id or not any(str(site.pk) == selected_id for site in sites):
        selected_id = str(sites[0].pk) if sites else ""
    return render(
        request,
        "installation_photos.html",
        {
            "sites": sites,
            "selected_id": selected_id,
            "connected_count": connected_count,
            "total_batches": total_batches,
            "regions": sorted({site.region for site in sites}),
        },
    )


@role_required(*ADMIN_ROLES)
@require_POST
def drive_folder_update(request, pk):
    batch = get_object_or_404(InstallationBatch.objects.select_related("site"), pk=pk)
    form = DriveFolderForm(request.POST, instance=batch)
    if form.is_valid():
        form.save()
        action = "DRIVE_FOLDER_UPDATED" if batch.drive_folder_url else "DRIVE_FOLDER_REMOVED"
        description = (
            f"Folder foto Google Drive untuk {batch.site.name} - {batch.label} diperbarui"
            if batch.drive_folder_url
            else f"Folder foto Google Drive untuk {batch.site.name} - {batch.label} dihapus"
        )
        log_activity(request, action, batch, description)
        messages.success(request, f"Link folder foto {batch.site.name} - {batch.label} berhasil disimpan.")
    else:
        messages.error(request, form.errors.get("drive_folder_url", ["Link Google Drive tidak valid."])[0])
    return redirect(f"{reverse('installation_photos')}?site={batch.site_id}#site-photo-detail")


@login_required
def progress_report_export(request):
    report, filename = build_progress_report()
    log_activity(
        request,
        "PROGRESS_REPORT_EXPORTED",
        None,
        "Laporan progress dokumen diekspor ke Excel",
        {"filename": filename},
    )
    response = HttpResponse(
        report.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@login_required
def progress_report_pdf_export(request):
    report, filename = build_progress_pdf()
    log_activity(
        request,
        "PROGRESS_PDF_EXPORTED",
        None,
        "Laporan progress dokumen diekspor ke PDF",
        {"filename": filename},
    )
    response = FileResponse(
        report,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )
    response["Cache-Control"] = "no-store"
    return response


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
    storage_ready = document.batch.status != InstallationBatch.Status.PENDING_INSTALLATION
    return render(
        request,
        "document_detail.html",
        {
            "document": document,
            "upload_form": DocumentUploadForm(
                allow_multiple=document.document_type == Document.Type.QC
            ),
            "review_form": ReviewForm(),
            "manual_status_form": ManualDocumentStatusForm(
                initial={"status": document.status}
            ),
            "comment_form": CommentForm(),
            "can_upload": request.user.role in UPLOAD_ROLES,
            "can_mark_signed": request.user.role == User.Role.SUPER_ADMIN,
            "can_delete_files": request.user.role == User.Role.SUPER_ADMIN,
            "can_review": request.user.role in REVIEW_ROLES,
            "can_upload_file": (
                request.user.role in UPLOAD_ROLES
                and storage_ready
                and upload_allowed_by_state
            ),
            "can_upload_signed": (
                request.user.role == User.Role.SUPER_ADMIN
                and storage_ready
                and document.status != Document.Status.APPROVED
                and (
                    upload_allowed_by_state
                    or document.status == Document.Status.UNDER_REVIEW
                )
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
            "has_fatp_builder": hasattr(document, "fatp_builder"),
        },
    )


def _fatp_document(pk):
    document = get_object_or_404(
        Document.objects.select_related("batch__site__project"),
        pk=pk,
        document_type=Document.Type.FATP,
    )
    return document


def _fatp_builder(document, user):
    builder, created = FatpBuilder.objects.get_or_create(
        document=document,
        defaults={
            "installation_date": document.batch.installed_at,
            "updated_by": user,
        },
    )
    if created:
        seed_default_fatp_sections(builder)
    return builder


def _renumber_sections(builder):
    for number, section in enumerate(builder.sections.order_by("sequence_no", "pk"), 1):
        if section.sequence_no != number:
            section.sequence_no = number
            section.save(update_fields=["sequence_no"])


def _renumber_photos(section):
    for number, photo in enumerate(section.photos.order_by("sequence_no", "pk"), 1):
        if photo.sequence_no != number:
            photo.sequence_no = number
            photo.save(update_fields=["sequence_no"])


@role_required(User.Role.SUPER_ADMIN)
def fatp_builder_editor(request, pk):
    document = _fatp_document(pk)
    builder = _fatp_builder(document, request.user)
    builder = FatpBuilder.objects.select_related(
        "document__batch__site__project", "updated_by"
    ).prefetch_related("equipment", "sections__photos").get(pk=builder.pk)
    default_hints = {
        item["title"]: item["upload_hint"] for item in DEFAULT_FATP_SECTIONS
    }
    sections = list(builder.sections.all())
    for section in sections:
        section.upload_hint = default_hints.get(
            section.title,
            section.description or "Upload foto untuk bagian ini",
        )
    completed_sections = sum(bool(list(section.photos.all())) for section in sections)
    return render(
        request,
        "fatp_builder.html",
        {
            "document": document,
            "builder": builder,
            "builder_form": FatpBuilderForm(instance=builder),
            "photo_count": sum(section.photos.count() for section in builder.sections.all()),
            "sections": sections,
            "completed_sections": completed_sections,
            "builder_progress": round(completed_sections / len(sections) * 100)
            if sections
            else 0,
            "status_choices": Document.Status.choices,
        },
    )


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_builder_settings(request, pk):
    document = _fatp_document(pk)
    builder = _fatp_builder(document, request.user)
    form = FatpBuilderForm(request.POST, instance=builder)
    if not form.is_valid():
        messages.error(request, "Informasi instalasi belum lengkap atau tidak valid.")
        return redirect("fatp_builder_editor", pk=pk)

    names = request.POST.getlist("equipment_name")
    models = request.POST.getlist("equipment_model")
    quantities = request.POST.getlist("equipment_quantity")
    notes = request.POST.getlist("equipment_notes")
    equipment = []
    for index, raw_name in enumerate(names):
        name = raw_name.strip()
        if not name:
            continue
        try:
            quantity = max(1, min(999, int(quantities[index] if index < len(quantities) else 1)))
        except (TypeError, ValueError):
            quantity = 1
        equipment.append(
            FatpEquipment(
                builder=builder,
                sequence_no=len(equipment) + 1,
                name=name[:180],
                model=(models[index] if index < len(models) else "").strip()[:160],
                quantity=quantity,
                notes=(notes[index] if index < len(notes) else "").strip()[:220],
            )
        )
    with transaction.atomic():
        builder = form.save(commit=False)
        builder.updated_by = request.user
        builder.save()
        builder.equipment.all().delete()
        FatpEquipment.objects.bulk_create(equipment)
    log_activity(
        request,
        "FATP_BUILDER_SETTINGS_UPDATED",
        builder,
        f"Informasi FATP {document.batch.site.name} diperbarui",
        {"equipment_count": len(equipment)},
    )
    messages.success(request, "Informasi site dan perangkat berhasil disimpan.")
    return redirect("fatp_builder_editor", pk=pk)


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_section_add(request, pk):
    document = _fatp_document(pk)
    builder = _fatp_builder(document, request.user)
    next_no = (builder.sections.aggregate(last=Max("sequence_no"))["last"] or 0) + 1
    title = (request.POST.get("title") or f"Bagian {next_no}").strip()[:220]
    section = FatpSection.objects.create(
        builder=builder,
        sequence_no=next_no,
        title=title or f"Bagian {next_no}",
        columns=2,
    )
    log_activity(request, "FATP_SECTION_ADDED", section, f"Bagian FATP '{section.title}' ditambahkan")
    messages.success(request, "Bagian baru ditambahkan. Sekarang unggah fotonya.")
    return redirect(f"{reverse('fatp_builder_editor', args=[pk])}#section-{section.pk}")


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_section_update(request, section_pk):
    section = get_object_or_404(
        FatpSection.objects.select_related("builder__document"), pk=section_pk
    )
    form = FatpSectionForm(request.POST, instance=section)
    if form.is_valid():
        section = form.save()
        for photo in section.photos.all():
            caption = request.POST.get(f"caption_{photo.pk}")
            if caption is not None:
                photo.caption = caption.strip()[:220]
                photo.save(update_fields=["caption"])
        log_activity(request, "FATP_SECTION_UPDATED", section, f"Bagian FATP '{section.title}' diperbarui")
        messages.success(request, f"Bagian {section.title} berhasil disimpan.")
    else:
        messages.error(request, "Pengaturan bagian tidak valid.")
    return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_section_delete(request, section_pk):
    section = get_object_or_404(
        FatpSection.objects.select_related("builder__document").prefetch_related("photos"),
        pk=section_pk,
    )
    builder = section.builder
    document_id = builder.document_id
    title = section.title
    for photo in section.photos.all():
        delete_document_file(photo.storage_key)
    section.delete()
    _renumber_sections(builder)
    log_activity(request, "FATP_SECTION_DELETED", builder, f"Bagian FATP '{title}' dihapus")
    messages.success(request, f"Bagian {title} dan seluruh fotonya dihapus.")
    return redirect("fatp_builder_editor", pk=document_id)


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_section_move(request, section_pk, direction):
    section = get_object_or_404(
        FatpSection.objects.select_related("builder__document"), pk=section_pk
    )
    sections = list(section.builder.sections.order_by("sequence_no", "pk"))
    index = sections.index(section)
    target_index = index - 1 if direction == "up" else index + 1
    if 0 <= target_index < len(sections):
        target = sections[target_index]
        section.sequence_no, target.sequence_no = target.sequence_no, section.sequence_no
        with transaction.atomic():
            section.save(update_fields=["sequence_no"])
            target.save(update_fields=["sequence_no"])
    return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_photo_upload(request, section_pk):
    section = get_object_or_404(
        FatpSection.objects.select_related("builder__document__batch__site"), pk=section_pk
    )
    uploads = request.FILES.getlist("photos")
    if not uploads:
        messages.error(request, "Pilih minimal satu foto.")
        return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")
    if len(uploads) > 30:
        messages.error(request, "Maksimal 30 foto dalam satu kali upload.")
        return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if sum(upload.size for upload in uploads) > max_bytes:
        messages.error(request, f"Total upload maksimal {settings.MAX_UPLOAD_SIZE_MB} MB.")
        return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")
    for upload in uploads:
        if Path(upload.name).suffix.lower() not in allowed_extensions:
            messages.error(request, f"{upload.name}: gunakan JPG, PNG, atau WEBP.")
            return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")
        try:
            PillowImage.open(upload).verify()
            upload.seek(0)
        except Exception:
            messages.error(request, f"{upload.name} bukan file gambar yang valid.")
            return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")

    first_no = (section.photos.aggregate(last=Max("sequence_no"))["last"] or 0) + 1
    stored = []
    try:
        for offset, upload in enumerate(uploads):
            sequence_no = first_no + offset
            checksum = checksum_file(upload)
            result = store_fatp_photo(section, upload, sequence_no)
            stored.append((upload, checksum, sequence_no, result))
        with transaction.atomic():
            for upload, checksum, sequence_no, result in stored:
                FatpPhoto.objects.create(
                    section=section,
                    sequence_no=sequence_no,
                    storage_key=result["storage_key"],
                    stored_filename=result["stored_filename"],
                    original_filename=upload.name,
                    mime_type=result["mime_type"],
                    file_size=result["file_size"],
                    checksum_sha256=checksum,
                    caption=Path(upload.name).stem.replace("_", " ").replace("-", " ")[:220],
                    uploaded_by=request.user,
                )
    except Exception as exc:
        for _, _, _, result in stored:
            delete_document_file(result["storage_key"])
        messages.error(request, f"Foto gagal disimpan: {exc}")
        return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")
    log_activity(
        request,
        "FATP_PHOTOS_UPLOADED",
        section,
        f"{len(stored)} foto ditambahkan ke bagian '{section.title}'",
    )
    messages.success(request, f"{len(stored)} foto berhasil ditambahkan.")
    return redirect(f"{reverse('fatp_builder_editor', args=[section.builder.document_id])}#section-{section.pk}")


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_photo_delete(request, photo_pk):
    photo = get_object_or_404(
        FatpPhoto.objects.select_related("section__builder__document"), pk=photo_pk
    )
    section = photo.section
    document_id = section.builder.document_id
    delete_document_file(photo.storage_key)
    photo.delete()
    _renumber_photos(section)
    log_activity(request, "FATP_PHOTO_DELETED", section, f"Foto dari bagian '{section.title}' dihapus")
    messages.success(request, "Foto berhasil dihapus.")
    return redirect(f"{reverse('fatp_builder_editor', args=[document_id])}#section-{section.pk}")


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_photo_move(request, photo_pk, direction):
    photo = get_object_or_404(
        FatpPhoto.objects.select_related("section__builder__document"), pk=photo_pk
    )
    photos = list(photo.section.photos.order_by("sequence_no", "pk"))
    index = photos.index(photo)
    target_index = index - 1 if direction == "up" else index + 1
    if 0 <= target_index < len(photos):
        target = photos[target_index]
        photo.sequence_no, target.sequence_no = target.sequence_no, photo.sequence_no
        with transaction.atomic():
            photo.save(update_fields=["sequence_no"])
            target.save(update_fields=["sequence_no"])
    return redirect(f"{reverse('fatp_builder_editor', args=[photo.section.builder.document_id])}#section-{photo.section_id}")


@role_required(User.Role.SUPER_ADMIN)
def fatp_photo_file(request, photo_pk):
    photo = get_object_or_404(FatpPhoto, pk=photo_pk)
    try:
        handle = open_document_file(photo.storage_key)
    except Exception:
        raise Http404("Foto tidak ditemukan")
    return FileResponse(handle, content_type=photo.mime_type)


@role_required(User.Role.SUPER_ADMIN)
def fatp_builder_preview(request, pk):
    document = _fatp_document(pk)
    try:
        builder = FatpBuilder.objects.select_related(
            "document__batch__site__project"
        ).prefetch_related("equipment", "sections__photos").get(document=document)
    except FatpBuilder.DoesNotExist:
        messages.error(request, "Simpan informasi FATP terlebih dahulu.")
        return redirect("fatp_builder_editor", pk=pk)
    pdf_bytes = build_fatp_pdf(builder)
    filename = document_filename(document, 0, "preview.pdf")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def fatp_builder_generate(request, pk):
    document = _fatp_document(pk)
    builder = get_object_or_404(
        FatpBuilder.objects.select_related("document__batch__site__project").prefetch_related(
            "equipment", "sections__photos"
        ),
        document=document,
    )
    total_photos = sum(section.photos.count() for section in builder.sections.all())
    if not builder.sections.exists() or total_photos == 0:
        messages.error(request, "Tambahkan minimal satu bagian dan satu foto sebelum membuat PDF.")
        return redirect("fatp_builder_editor", pk=pk)
    output_status = request.POST.get("output_status", Document.Status.DRAFT)
    allowed_statuses = {value for value, _ in Document.Status.choices}
    if output_status not in allowed_statuses:
        messages.error(request, "Status output tidak valid.")
        return redirect("fatp_builder_editor", pk=pk)

    pdf_bytes = build_fatp_pdf(builder)
    latest_revision = document.versions.aggregate(last=Max("revision_no"))["last"]
    revision_no = 0 if latest_revision is None else latest_revision + 1
    output_name = document_filename(document, revision_no, "generated.pdf")
    uploaded = ContentFile(pdf_bytes, name=output_name)
    checksum = checksum_file(uploaded)
    try:
        stored = store_document_file(document, uploaded, revision_no, attachment_no=1)
    except Exception as exc:
        messages.error(request, f"PDF gagal disimpan: {exc}")
        return redirect("fatp_builder_editor", pk=pk)

    try:
        with transaction.atomic():
            version = DocumentVersion.objects.create(
                document=document,
                revision_no=revision_no,
                storage_key=stored["storage_key"],
                stored_filename=stored["stored_filename"],
                original_filename=output_name,
                mime_type="application/pdf",
                file_size=stored["file_size"],
                checksum_sha256=checksum,
                change_summary="Generated melalui FATP Custom Builder",
                uploaded_by=request.user,
                is_locked=output_status in {Document.Status.UNDER_REVIEW, Document.Status.APPROVED},
            )
            DocumentAttachment.objects.create(
                version=version,
                sequence_no=1,
                storage_key=stored["storage_key"],
                stored_filename=stored["stored_filename"],
                original_filename=output_name,
                mime_type="application/pdf",
                file_size=stored["file_size"],
                checksum_sha256=checksum,
                description="FATP Custom Builder",
            )
            now = timezone.now()
            document.status = output_status
            document.submitted_at = now if output_status in {Document.Status.UNDER_REVIEW, Document.Status.APPROVED} else None
            document.approved_at = now if output_status == Document.Status.APPROVED else None
            document.save(update_fields=["status", "submitted_at", "approved_at", "updated_at"])
            if output_status == Document.Status.APPROVED:
                Review.objects.create(
                    document=document,
                    version=version,
                    reviewer=request.user,
                    decision=Review.Decision.APPROVED,
                    comment="FATP generated dan ditetapkan Approved oleh Super Admin.",
                )
    except Exception as exc:
        delete_document_file(stored["storage_key"])
        messages.error(request, f"Versi FATP gagal dibuat: {exc}")
        return redirect("fatp_builder_editor", pk=pk)

    log_activity(
        request,
        "FATP_PDF_GENERATED",
        version,
        f"FATP {document.batch.site.name} Rev {revision_no} dibuat dari {total_photos} foto",
        {"photo_count": total_photos, "status": output_status},
    )
    if output_status in {Document.Status.UNDER_REVIEW, Document.Status.APPROVED}:
        notify_roles(
            [User.Role.NOKIA_REVIEWER, User.Role.NOKIA_VIEWER],
            "FATP baru tersedia",
            f"{document.batch.site.name} - {document.batch.label} Rev {revision_no}",
            reverse("document_detail", args=[document.pk]),
            request.user,
        )
    messages.success(request, f"FATP Rev {revision_no} berhasil dibuat sebagai {document.get_status_display()}.")
    return redirect("document_detail", pk=document.pk)


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def document_status_override(request, pk):
    document = get_object_or_404(
        Document.objects.select_related("batch__site"),
        pk=pk,
    )
    form = ManualDocumentStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Status dokumen tidak valid.")
        return redirect("document_detail", pk=pk)

    previous_status = document.status
    target_status = form.cleaned_data["status"]
    # Keep manual status changes working even when an older/cached form submits
    # only the status field.
    note = (form.cleaned_data.get("note") or "").strip()
    if previous_status == target_status:
        messages.info(request, f"Status tetap {document.get_status_display()}.")
        return redirect("document_detail", pk=pk)

    action_time = timezone.now()
    document.status = target_status
    if target_status == Document.Status.APPROVED:
        document.submitted_at = document.submitted_at or action_time
        document.approved_at = action_time
    elif target_status == Document.Status.UNDER_REVIEW:
        document.submitted_at = action_time
        document.approved_at = None
    elif target_status in {
        Document.Status.NOT_STARTED,
        Document.Status.DRAFT,
        Document.Status.UPLOADED,
        Document.Status.NOT_APPLICABLE,
    }:
        document.submitted_at = None
        document.approved_at = None
    else:
        document.approved_at = None
    document.save(
        update_fields=["status", "submitted_at", "approved_at", "updated_at"]
    )

    latest = document.latest_version
    if latest and target_status in {
        Document.Status.UNDER_REVIEW,
        Document.Status.APPROVED,
    } and not latest.is_locked:
        latest.is_locked = True
        latest.save(update_fields=["is_locked"])

    previous_label = dict(Document.Status.choices).get(previous_status, previous_status)
    log_activity(
        request,
        "DOCUMENT_STATUS_OVERRIDDEN",
        document,
        f"Status {document.document_type} {document.batch.site.name} diubah manual: {previous_label} → {document.get_status_display()}",
        {
            "previous_status": previous_status,
            "new_status": target_status,
            "note": note,
            "override_by_super_admin": True,
        },
    )
    messages.success(
        request,
        f"Status berhasil diubah menjadi {document.get_status_display()}.",
    )
    return redirect("document_detail", pk=pk)


@role_required(*UPLOAD_ROLES)
@require_POST
def document_upload(request, pk):
    document = get_object_or_404(Document.objects.select_related("batch__site"), pk=pk)
    upload_action = request.POST.get("upload_action", "draft")
    if upload_action not in {"draft", "submit_review", "signed_approved"}:
        messages.error(request, "Aksi upload tidak valid.")
        return redirect("document_detail", pk=pk)
    if (
        upload_action == "signed_approved"
        and request.user.role != User.Role.SUPER_ADMIN
    ):
        raise PermissionDenied
    signed_override = (
        upload_action == "signed_approved"
        and document.status == Document.Status.UNDER_REVIEW
    )
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
    if (
        document.status not in UPLOADABLE_STATUSES
        and not historical_status
        and not signed_override
    ):
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
    latest_version = document.latest_version
    append_to_latest = bool(
        latest_version
        and not latest_version.is_locked
        and document.status in {Document.Status.UPLOADED, Document.Status.DRAFT}
    )
    upload_items = []
    seen_checksums = set()
    for uploaded in uploads:
        checksum = checksum_file(uploaded)
        duplicate_exists = bool(
            append_to_latest
            and latest_version.attachments.filter(checksum_sha256=checksum).exists()
        )
        if checksum in seen_checksums or duplicate_exists:
            messages.error(
                request,
                f"File {uploaded.name} sama dengan file yang sudah ada di draft revisi ini.",
            )
            return redirect("document_detail", pk=pk)
        seen_checksums.add(checksum)
        upload_items.append((uploaded, checksum))

    if append_to_latest:
        version = latest_version
        revision_no = version.revision_no
        first_sequence = (
            version.attachments.aggregate(last=Max("sequence_no"))["last"] or 0
        ) + 1
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

            if historical_status and upload_action == "draft":
                target_status = historical_status
            elif upload_action == "submit_review":
                target_status = Document.Status.UNDER_REVIEW
            elif upload_action == "signed_approved":
                target_status = Document.Status.APPROVED
            else:
                target_status = Document.Status.UPLOADED

            if target_status in {
                Document.Status.UNDER_REVIEW,
                Document.Status.APPROVED,
            }:
                version.is_locked = True
                version.save(update_fields=["is_locked"])

            action_time = timezone.now()
            document.status = target_status
            if target_status == Document.Status.APPROVED:
                document.submitted_at = document.submitted_at or action_time
                document.approved_at = action_time
                if upload_action == "signed_approved":
                    Review.objects.create(
                        document=document,
                        version=version,
                        reviewer=request.user,
                        decision=Review.Decision.APPROVED,
                        comment="Dokumen signed/TTD diunggah dan ditetapkan Approved.",
                    )
            elif target_status == Document.Status.UNDER_REVIEW:
                document.submitted_at = action_time
                document.approved_at = None
            else:
                document.submitted_at = None
                document.approved_at = None
            document.save(
                update_fields=["status", "submitted_at", "approved_at", "updated_at"]
            )
    except Exception as exc:
        for item in stored_items:
            delete_document_file(item["storage"]["storage_key"])
        messages.error(request, f"Data versi dokumen gagal disimpan: {exc}")
        return redirect("document_detail", pk=pk)
    action_name = {
        "draft": "DOCUMENT_UPLOADED",
        "submit_review": "DOCUMENT_UPLOADED_AND_SUBMITTED",
        "signed_approved": "SIGNED_DOCUMENT_UPLOADED",
    }[upload_action]
    log_activity(
        request,
        action_name,
        version,
        f"{len(stored_items)} file ditambahkan ke {document.document_type} Rev {revision_no} sebagai {document.get_status_display()}",
        {
            "document_id": document.pk,
            "revision": revision_no,
            "file_count": len(stored_items),
            "appended": append_to_latest,
            "upload_action": upload_action,
            "resulting_status": document.status,
            "checksums": [item["checksum"] for item in stored_items],
        },
    )
    url = reverse("document_detail", args=[document.pk])
    if upload_action == "submit_review":
        notify_roles(
            [User.Role.NOKIA_REVIEWER, User.Role.NOKIA_VIEWER],
            f"{document.document_type} menunggu review",
            f"{document.batch.site.name} - {document.batch.label} Rev {revision_no}",
            url,
            request.user,
        )
        messages.success(request, "File berhasil diunggah dan disubmit untuk review Nokia.")
    elif upload_action == "signed_approved":
        notify_roles(
            [User.Role.NOKIA_REVIEWER, User.Role.NOKIA_VIEWER],
            f"{document.document_type} signed sudah tersedia",
            f"{document.batch.site.name} - {document.batch.label} berstatus Approved",
            url,
            request.user,
        )
        messages.success(request, "Dokumen signed/TTD berhasil diunggah dan ditetapkan Approved.")
    else:
        action_label = "ditambahkan ke" if append_to_latest else "diunggah sebagai"
        messages.success(
            request,
            f"{len(stored_items)} file berhasil {action_label} Rev {revision_no} sebagai Draft Upload.",
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


@role_required(User.Role.SUPER_ADMIN)
@require_POST
def attachment_delete(request, attachment_pk):
    attachment = get_object_or_404(
        DocumentAttachment.objects.select_related(
            "version__document__batch__site"
        ),
        pk=attachment_pk,
    )
    version = attachment.version
    document = version.document
    latest = document.latest_version
    storage_key = attachment.storage_key
    version_id = version.pk
    revision_no = version.revision_no
    deleted_filename = download_filename(attachment)
    stored_filename = attachment.stored_filename
    deleted_checksum = attachment.checksum_sha256
    with transaction.atomic():
        attachment.delete()
        remaining = list(version.attachments.all())
        if remaining:
            primary = remaining[0]
            version.storage_key = primary.storage_key
            version.stored_filename = primary.stored_filename
            version.original_filename = primary.original_filename
            version.mime_type = primary.mime_type
            version.checksum_sha256 = primary.checksum_sha256
            version.file_size = sum(item.file_size for item in remaining)
            version.save(
                update_fields=[
                    "storage_key",
                    "stored_filename",
                    "original_filename",
                    "mime_type",
                    "checksum_sha256",
                    "file_size",
                ]
            )
            document.save(update_fields=["updated_at"])
        else:
            preserve_audit = version.is_locked or version.reviews.exists()
            if preserve_audit:
                deletion_note = (
                    f"[{timezone.localtime():%d-%m-%Y %H:%M}] "
                    f"File terakhir dihapus oleh Super Admin {request.user}."
                )
                version.storage_key = (
                    f"__deleted__/version-{version.pk}-"
                    f"{timezone.now():%Y%m%d%H%M%S%f}"
                )
                version.stored_filename = deleted_filename
                version.original_filename = attachment.original_filename
                version.mime_type = "application/octet-stream"
                version.file_size = 0
                version.checksum_sha256 = "0" * 64
                version.change_summary = "\n".join(
                    item for item in [version.change_summary, deletion_note] if item
                )
                version.save(
                    update_fields=[
                        "storage_key",
                        "stored_filename",
                        "original_filename",
                        "mime_type",
                        "file_size",
                        "checksum_sha256",
                        "change_summary",
                    ]
                )
            else:
                version.delete()

            if latest and latest.pk == version_id:
                has_previous_file = (
                    document.versions.exclude(pk=version_id)
                    .filter(file_size__gt=0)
                    .exclude(storage_key__startswith="__deleted__/")
                    .exists()
                )
                document.status = (
                    Document.Status.REVISION_REQUIRED
                    if has_previous_file
                    else Document.Status.NOT_STARTED
                )
                document.approved_at = None
                if document.status == Document.Status.NOT_STARTED:
                    document.submitted_at = None
            document.save(
                update_fields=["status", "submitted_at", "approved_at", "updated_at"]
            )

    try:
        delete_document_file(storage_key)
    except Exception as exc:
        messages.warning(
            request,
            f"File sudah dihapus dari DMS, tetapi pembersihan storage perlu diperiksa: {exc}",
        )
    log_activity(
        request,
        "DOCUMENT_ATTACHMENT_DELETED",
        document,
        f"File {deleted_filename} dihapus dari {document.document_type} Rev {revision_no}",
        {
            "version_id": version_id,
            "revision": revision_no,
            "stored_filename": deleted_filename,
            "physical_filename": stored_filename,
            "checksum": deleted_checksum,
        },
    )
    messages.success(request, f"File {deleted_filename} berhasil dihapus.")
    return redirect("document_detail", pk=document.pk)


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
    filename = download_filename(entity)
    inline = mode == "preview"
    response = FileResponse(
        handle,
        as_attachment=not inline,
        filename=filename,
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
        DocumentVersion.objects.select_related(
            "document__batch__site"
        ).prefetch_related("attachments"),
        pk=version_pk,
    )
    attachment = version.attachments.first()
    if attachment:
        return _stored_file_response(request, attachment, version.document_id, mode)
    if not version.has_file:
        messages.error(request, "File pada revisi ini sudah dihapus oleh Super Admin.")
        return redirect("document_detail", pk=version.document_id)
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
        if not version.has_file:
            messages.error(request, "File pada revisi ini sudah dihapus oleh Super Admin.")
            return redirect("document_detail", pk=version.document_id)
        return document_file(request, version_pk, mode="download")

    bundle = SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for attachment in attachments:
                archive_name = download_filename(attachment)
                with open_document_file(attachment.storage_key) as source:
                    with archive.open(archive_name, "w") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
        bundle.seek(0)
    except Exception as exc:
        bundle.close()
        messages.error(request, f"Paket ZIP tidak dapat dibuat: {exc}")
        return redirect("document_detail", pk=version.document_id)

    filename = bundle_filename(version)
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


def nokia_logo(request):
    logo_path = Path(settings.NOKIA_LOGO_PATH)
    if not logo_path.is_file():
        raise Http404("Logo Nokia belum tersedia")
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
