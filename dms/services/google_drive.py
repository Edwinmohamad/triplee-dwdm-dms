import hashlib
import io
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from ..models import GoogleDriveCredential


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_MIME = "application/vnd.google-apps.folder"


def _cipher():
    key = settings.GOOGLE_TOKEN_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured("GOOGLE_TOKEN_ENCRYPTION_KEY belum dikonfigurasi.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("GOOGLE_TOKEN_ENCRYPTION_KEY tidak valid.") from exc


def encrypt_token(payload):
    return _cipher().encrypt(json.dumps(payload).encode()).decode()


def decrypt_token(value):
    try:
        return json.loads(_cipher().decrypt(value.encode()).decode())
    except InvalidToken as exc:
        raise ImproperlyConfigured("Token Google Drive tidak dapat dibuka.") from exc


def oauth_client_config():
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise ImproperlyConfigured("Google OAuth Client ID dan Client Secret belum dikonfigurasi.")
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def create_oauth_flow(state=None):
    return Flow.from_client_config(
        oauth_client_config(),
        scopes=[DRIVE_SCOPE],
        state=state,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
    )


def authorization_url(request):
    flow = create_oauth_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["google_oauth_state"] = state
    return url


def _credentials_payload(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or [DRIVE_SCOPE]),
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }


def _credentials_from_record(record):
    payload = decrypt_token(record.encrypted_token)
    expiry = None
    if payload.get("expiry"):
        expiry = datetime.fromisoformat(payload["expiry"])
    credentials = Credentials(
        token=payload.get("token"),
        refresh_token=payload.get("refresh_token"),
        token_uri=payload.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=payload.get("client_id") or settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=payload.get("client_secret") or settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=payload.get("scopes") or [DRIVE_SCOPE],
        expiry=expiry,
    )
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ImproperlyConfigured("Refresh token Google Drive tidak tersedia. Hubungkan ulang akun.")
        credentials.refresh(Request())
        record.encrypted_token = encrypt_token(_credentials_payload(credentials))
        record.save(update_fields=["encrypted_token", "updated_at"])
    return credentials


def get_active_record():
    record = GoogleDriveCredential.objects.order_by("-updated_at").first()
    if not record:
        raise ImproperlyConfigured("Google Drive belum dihubungkan.")
    return record


def get_service(record=None):
    record = record or get_active_record()
    return build("drive", "v3", credentials=_credentials_from_record(record), cache_discovery=False), record


def complete_oauth(request, authorization_response):
    expected_state = request.session.pop("google_oauth_state", None)
    if not expected_state:
        raise ImproperlyConfigured("Sesi OAuth kedaluwarsa. Mulai koneksi ulang.")
    flow = create_oauth_flow(state=expected_state)
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    user_info = service.about().get(fields="user(emailAddress)").execute().get("user", {})
    record, _ = GoogleDriveCredential.objects.update_or_create(
        connected_by=request.user,
        defaults={
            "encrypted_token": encrypt_token(_credentials_payload(credentials)),
            "google_email": user_info.get("emailAddress", ""),
        },
    )
    ensure_root_folders(record)
    return record


def _escape_query(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder(service, name, parent_id=None, app_kind="folder"):
    clauses = [
        f"name = '{_escape_query(name)}'",
        f"mimeType = '{FOLDER_MIME}'",
        "trashed = false",
    ]
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    response = service.files().list(
        q=" and ".join(clauses),
        spaces="drive",
        fields="files(id,name)",
        pageSize=10,
    ).execute()
    files = response.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "appProperties": {"triplee_dms": app_kind},
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    return service.files().create(body=metadata, fields="id").execute()["id"]


def ensure_root_folders(record=None):
    service, record = get_service(record)
    root_id = record.root_folder_id or ensure_folder(
        service,
        settings.GOOGLE_DRIVE_ROOT_FOLDER,
        app_kind="root",
    )
    backup_id = record.backup_folder_id or ensure_folder(
        service,
        "Database-Backup",
        parent_id=root_id,
        app_kind="backup-root",
    )
    if record.root_folder_id != root_id or record.backup_folder_id != backup_id:
        record.root_folder_id = root_id
        record.backup_folder_id = backup_id
        record.save(update_fields=["root_folder_id", "backup_folder_id", "updated_at"])
    return service, record


def _clean_component(value):
    compact = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return compact.strip("-_")[:90] or "item"


def ensure_document_folder(document, service=None, record=None):
    if service is None or record is None:
        service, record = ensure_root_folders(record)
    project = document.batch.site.project
    site = document.batch.site
    batch = document.batch
    project_id = ensure_folder(service, _clean_component(f"{project.code}_{project.name}"), record.root_folder_id, "project")
    site_id = ensure_folder(service, _clean_component(f"{site.tower_id}_{site.name}"), project_id, "site")
    batch_id = ensure_folder(service, _clean_component(f"BATCH-{batch.batch_no:02d}_{batch.label}"), site_id, "batch")
    return service, ensure_folder(service, document.document_type, batch_id, "document-type")


def document_filename(document, revision_no, original_filename):
    ext = Path(original_filename).suffix.lower()
    date = timezone.localdate().strftime("%Y%m%d")
    return _clean_component(
        f"{document.batch.site.tower_id}_BATCH-{document.batch.batch_no:02d}_{document.document_type}_REV-{revision_no}_{date}"
    ) + ext


def checksum_file(uploaded_file):
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def upload_document_file(document, uploaded_file, revision_no):
    service, folder_id = ensure_document_folder(document)
    stored_filename = document_filename(document, revision_no, uploaded_file.name)
    mime_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"
    metadata = {
        "name": stored_filename,
        "parents": [folder_id],
        "appProperties": {
            "triplee_dms": "document-version",
            "document_id": str(document.pk),
            "revision_no": str(revision_no),
        },
    }
    media = MediaIoBaseUpload(uploaded_file.file, mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id,name,mimeType,size,createdTime",
    ).execute()
    return {
        "drive_file_id": result["id"],
        "stored_filename": result.get("name", stored_filename),
        "mime_type": result.get("mimeType", mime_type),
        "file_size": int(result.get("size") or uploaded_file.size),
    }


def download_drive_file(file_id):
    service, _ = get_service()
    handle = io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(handle, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    handle.seek(0)
    return handle


def upload_backup_file(file_path, filename, monthly=False):
    service, record = ensure_root_folders()
    metadata = {
        "name": filename,
        "parents": [record.backup_folder_id],
        "appProperties": {
            "triplee_dms": "database-backup",
            "retention": "monthly" if monthly else "daily",
        },
    }
    with open(file_path, "rb") as source:
        result = service.files().create(
            body=metadata,
            media_body=MediaIoBaseUpload(source, mimetype="application/octet-stream", resumable=True),
            fields="id,size,createdTime",
        ).execute()
    return result


def prune_drive_backups(daily_retention_days=30, monthly_retention_days=365):
    service, record = ensure_root_folders()
    response = service.files().list(
        q=f"'{record.backup_folder_id}' in parents and trashed = false",
        spaces="drive",
        fields="files(id,name,createdTime,appProperties)",
        pageSize=1000,
    ).execute()
    now = datetime.now(dt_timezone.utc)
    removed = 0
    for item in response.get("files", []):
        created_raw = item.get("createdTime")
        if not created_raw:
            continue
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        retention = (item.get("appProperties") or {}).get("retention", "daily")
        max_age = monthly_retention_days if retention == "monthly" else daily_retention_days
        if now - created > timedelta(days=max_age):
            service.files().delete(fileId=item["id"]).execute()
            removed += 1
    return removed
