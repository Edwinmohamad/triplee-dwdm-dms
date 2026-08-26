import os
import shutil
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from dms.models import BackupRecord, Notification, User
from dms.services.google_drive import prune_drive_backups, upload_backup_file


class Command(BaseCommand):
    help = "Create an encrypted database backup and upload it to Google Drive."

    def handle(self, *args, **options):
        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        monthly = timezone.localdate().day == 1
        prefix = "monthly" if monthly else "daily"
        filename = f"{prefix}-triplee-dms-{timestamp}.dump.fernet"
        backup_dir = Path(settings.BACKUP_LOCAL_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        raw_path = backup_dir / f"triplee-dms-{timestamp}.raw"
        encrypted_path = backup_dir / filename
        record = BackupRecord.objects.create(filename=filename)
        try:
            self._dump_database(raw_path)
            self._encrypt(raw_path, encrypted_path)
            raw_path.unlink(missing_ok=True)
            result = upload_backup_file(encrypted_path, filename, monthly=monthly)
            record.status = BackupRecord.Status.SUCCESS
            record.drive_file_id = result["id"]
            record.file_size = encrypted_path.stat().st_size
            record.message = "Uploaded to Google Drive"
            record.finished_at = timezone.now()
            record.save()
            self._prune_local(backup_dir)
            prune_drive_backups(
                settings.BACKUP_DRIVE_RETENTION_DAYS,
                settings.BACKUP_DRIVE_MONTHLY_RETENTION_DAYS,
            )
            self.stdout.write(self.style.SUCCESS(filename))
        except Exception as exc:
            raw_path.unlink(missing_ok=True)
            record.status = BackupRecord.Status.FAILED
            record.message = str(exc)[:1000]
            record.finished_at = timezone.now()
            record.save()
            for user in User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True):
                Notification.objects.create(
                    user=user,
                    title="Backup database gagal",
                    message=str(exc)[:500],
                    url="/backups/",
                )
            raise CommandError(str(exc)) from exc

    def _dump_database(self, raw_path):
        if connection.vendor == "sqlite":
            shutil.copy2(connection.settings_dict["NAME"], raw_path)
            return
        if connection.vendor != "postgresql":
            raise CommandError("Backup hanya mendukung PostgreSQL dan SQLite development.")
        cfg = connection.settings_dict
        env = os.environ.copy()
        env["PGPASSWORD"] = cfg.get("PASSWORD") or ""
        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--host", cfg.get("HOST") or "db",
            "--port", str(cfg.get("PORT") or "5432"),
            "--username", cfg.get("USER") or "triplee_dms",
            "--file", str(raw_path),
            cfg.get("NAME") or "triplee_dms",
        ]
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)

    def _encrypt(self, raw_path, encrypted_path):
        key = settings.BACKUP_ENCRYPTION_KEY
        if not key:
            raise CommandError("BACKUP_ENCRYPTION_KEY belum dikonfigurasi.")
        try:
            cipher = Fernet(key.encode())
        except ValueError as exc:
            raise CommandError("BACKUP_ENCRYPTION_KEY tidak valid.") from exc
        encrypted_path.write_bytes(cipher.encrypt(raw_path.read_bytes()))

    def _prune_local(self, backup_dir):
        cutoff = timezone.now().timestamp() - settings.BACKUP_LOCAL_RETENTION_DAYS * 86400
        for path in backup_dir.glob("*.dump.fernet"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
