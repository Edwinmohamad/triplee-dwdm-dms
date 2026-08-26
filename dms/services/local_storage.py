import hashlib
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.utils import timezone


def _clean_component(value, fallback="item", max_length=100):
    compact = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return compact.strip("-_.")[:max_length] or fallback


def _storage_root():
    root = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_storage_key(storage_key):
    key = Path(storage_key)
    if key.is_absolute():
        raise SuspiciousFileOperation("Lokasi file tidak valid.")
    root = _storage_root()
    target = (root / key).resolve()
    if not target.is_relative_to(root):
        raise SuspiciousFileOperation("Lokasi file berada di luar document storage.")
    return target


def checksum_file(uploaded_file):
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def document_filename(document, revision_no, original_filename, attachment_no=1):
    extension = Path(original_filename).suffix.lower()
    original_stem = _clean_component(Path(original_filename).stem, "file")[:45]
    site_name = _clean_component(
        document.batch.site.name.replace(".", " "),
        "site",
        max_length=70,
    )
    date = timezone.localdate().strftime("%Y%m%d")
    base = _clean_component(
        f"{site_name}_{document.batch.site.tower_id}_"
        f"B{document.batch.batch_no:02d}_{document.document_type}_"
        f"R{revision_no:03d}_F{attachment_no:02d}_"
        f"{original_stem}_{date}",
        "document",
        max_length=220,
    )
    return f"{base}{extension}"


def store_document_file(document, uploaded_file, revision_no, attachment_no=1):
    project = document.batch.site.project
    site = document.batch.site
    batch = document.batch
    stored_filename = document_filename(
        document,
        revision_no,
        uploaded_file.name,
        attachment_no,
    )
    storage_key = Path(
        _clean_component(project.code, "project"),
        _clean_component(f"{site.tower_id}_{site.name}", "site"),
        _clean_component(f"BATCH-{batch.batch_no:02d}_{batch.label}", "batch"),
        _clean_component(document.document_type, "document"),
        f"REV-{revision_no:03d}",
        stored_filename,
    )
    destination = _resolve_storage_key(storage_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)
    uploaded_file.seek(0)
    mime_type = (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )
    return {
        "storage_key": storage_key.as_posix(),
        "stored_filename": stored_filename,
        "mime_type": mime_type,
        "file_size": destination.stat().st_size,
    }


def open_document_file(storage_key):
    return _resolve_storage_key(storage_key).open("rb")


def delete_document_file(storage_key):
    target = _resolve_storage_key(storage_key)
    target.unlink(missing_ok=True)
