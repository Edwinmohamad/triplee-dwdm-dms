from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dms.models import User


class Command(BaseCommand):
    help = "Membuat atau memperbarui akun awal DMS tanpa membutuhkan email."

    def add_arguments(self, parser):
        parser.add_argument("--superadmin-username", default="superadmin")
        parser.add_argument("--superadmin-password")
        parser.add_argument("--user-username", default="user")
        parser.add_argument("--user-password")
        parser.add_argument(
            "--allow-weak-password",
            action="store_true",
            help="Lewati validator password. Hanya untuk bootstrap sementara.",
        )

    def _validate_password(self, password, username):
        candidate = User(username=username, full_name=username)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

    @transaction.atomic
    def handle(self, *args, **options):
        superadmin_username = options["superadmin_username"].strip().lower()
        user_username = options["user_username"].strip().lower()
        superadmin_password = options["superadmin_password"] or getpass(
            f"Password untuk {superadmin_username}: "
        )
        user_password = options["user_password"] or getpass(
            f"Password untuk {user_username}: "
        )

        if superadmin_username == user_username:
            raise CommandError("Username Super Admin dan user harus berbeda.")

        if not options["allow_weak_password"]:
            self._validate_password(superadmin_password, superadmin_username)
            self._validate_password(user_password, user_username)

        superadmin, _ = User.objects.update_or_create(
            username=superadmin_username,
            defaults={
                "full_name": "Super Admin Triple E",
                "role": User.Role.SUPER_ADMIN,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
                "must_change_password": False,
            },
        )
        superadmin.set_password(superadmin_password)
        superadmin.save()

        reviewer, _ = User.objects.update_or_create(
            username=user_username,
            defaults={
                "full_name": "Nokia Reviewer",
                "role": User.Role.NOKIA_REVIEWER,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "must_change_password": False,
            },
        )
        reviewer.set_password(user_password)
        reviewer.save()

        self.stdout.write(self.style.SUCCESS(
            f"Akun '{superadmin.username}' (Super Admin) dan "
            f"'{reviewer.username}' (Nokia Reviewer) siap digunakan."
        ))
