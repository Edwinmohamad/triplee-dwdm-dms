import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run the database backup daily at BACKUP_TIME."

    def handle(self, *args, **options):
        self.stdout.write(f"Backup scheduler active at {settings.BACKUP_TIME} {settings.TIME_ZONE}")
        while True:
            now = timezone.localtime()
            hour, minute = [int(value) for value in settings.BACKUP_TIME.split(":", 1)]
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            sleep_seconds = max(1, int((target - now).total_seconds()))
            time.sleep(sleep_seconds)
            try:
                call_command("backup_database")
            except Exception as exc:
                self.stderr.write(f"Backup failed: {exc}")

