from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Document, DocumentVersion, InstallationBatch, Review, Site, User
from .services.local_storage import open_document_file, store_document_file


class LocalStorageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.document = Document.objects.select_related(
            "batch__site__project"
        ).exclude(batch__status=InstallationBatch.Status.PENDING_INSTALLATION).first()

    def test_document_is_stored_in_structured_relative_path(self):
        with TemporaryDirectory() as temporary_root, override_settings(
            DOCUMENT_STORAGE_ROOT=temporary_root
        ):
            uploaded = SimpleUploadedFile(
                "QC Final.PDF",
                b"test document",
                content_type="application/pdf",
            )
            result = store_document_file(self.document, uploaded, 0)
            stored_path = Path(temporary_root) / result["storage_key"]

            self.assertTrue(stored_path.is_file())
            self.assertIn("BATCH-", result["storage_key"])
            self.assertIn("REV-000", result["storage_key"])
            self.assertEqual(stored_path.read_bytes(), b"test document")

    def test_storage_key_cannot_escape_document_root(self):
        with TemporaryDirectory() as temporary_root, override_settings(
            DOCUMENT_STORAGE_ROOT=temporary_root
        ):
            with self.assertRaises(SuspiciousFileOperation):
                open_document_file("../outside.pdf")


class InitialDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")

    def test_seed_counts(self):
        self.assertEqual(Site.objects.count(), 16)
        self.assertEqual(InstallationBatch.objects.count(), 18)
        self.assertEqual(Document.objects.count(), 54)

    def test_duplicate_towers_are_batches_not_sites(self):
        mentigi = Site.objects.get(tower_id="SUM-BB-TDN-0361")
        sungai_liat = Site.objects.get(tower_id="SUM-BB-SGL-0238")
        self.assertEqual(mentigi.batches.count(), 2)
        self.assertEqual(sungai_liat.batches.count(), 2)

    def test_tanjung_pandan_is_pending(self):
        site = Site.objects.get(tower_id="SUM-BB-TDN-0530")
        self.assertEqual(site.batches.get().status, InstallationBatch.Status.PENDING_INSTALLATION)

    def test_seed_is_idempotent_and_preserves_workflow_changes(self):
        batch = InstallationBatch.objects.get(site__tower_id="SUM-BB-TDN-0530")
        document = batch.documents.get(document_type=Document.Type.QC)
        batch.status = InstallationBatch.Status.INSTALLED
        batch.pic_name = "PIC BARU"
        batch.save(update_fields=["status", "pic_name", "updated_at"])
        document.status = Document.Status.DRAFT
        document.save(update_fields=["status", "updated_at"])

        call_command("seed_initial_data")

        batch.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(batch.status, InstallationBatch.Status.INSTALLED)
        self.assertEqual(batch.pic_name, "PIC BARU")
        self.assertEqual(document.status, Document.Status.DRAFT)


class AccountProvisioningTests(TestCase):
    def test_provisions_username_only_accounts(self):
        call_command(
            "provision_accounts",
            superadmin_password="TemporaryAdminTestPass1!",
            user_password="temporary-test-user-pass",
            allow_weak_password=True,
        )
        superadmin = User.objects.get(username="superadmin")
        reviewer = User.objects.get(username="user")
        self.assertTrue(superadmin.is_superuser)
        self.assertEqual(superadmin.role, User.Role.SUPER_ADMIN)
        self.assertTrue(superadmin.check_password("TemporaryAdminTestPass1!"))
        self.assertEqual(reviewer.role, User.Role.NOKIA_REVIEWER)
        self.assertTrue(reviewer.check_password("temporary-test-user-pass"))


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.admin = User.objects.create_superuser(
            username="admin",
            full_name="Admin Triple E",
            password="VerySecure123!",
            must_change_password=False,
        )
        cls.reviewer = User.objects.create_user(
            username="reviewer",
            full_name="Nokia Reviewer",
            password="VerySecure123!",
            role=User.Role.NOKIA_REVIEWER,
            must_change_password=False,
        )
        cls.document = Document.objects.filter(status=Document.Status.UNDER_REVIEW).first()
        cls.version = DocumentVersion.objects.create(
            document=cls.document,
            revision_no=0,
            storage_key="DWDM/test.pdf",
            stored_filename="test.pdf",
            original_filename="test.pdf",
            mime_type="application/pdf",
            file_size=100,
            checksum_sha256="a" * 64,
            uploaded_by=cls.admin,
            is_locked=True,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_login_uses_username_without_email(self):
        response = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "VerySecure123!"},
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_dashboard_shows_seeded_counts(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "16")
        self.assertContains(response, "18")

    def test_nokia_reviewer_can_approve(self):
        self.client.force_login(self.reviewer)
        response = self.client.post(
            reverse("document_review", args=[self.document.pk]),
            {"decision": Review.Decision.APPROVED, "comment": "Dokumen sesuai."},
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.APPROVED)
        self.assertTrue(self.document.reviews.filter(decision=Review.Decision.APPROVED).exists())

    def test_reviewer_cannot_upload(self):
        self.client.force_login(self.reviewer)
        response = self.client.post(reverse("document_upload", args=[self.document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_triplee_admin_cannot_make_nokia_decision(self):
        self.client.force_login(self.admin)
        self.admin.role = User.Role.TRIPLEE_ADMIN
        self.admin.is_superuser = False
        self.admin.save(update_fields=["role", "is_superuser"])
        response = self.client.post(
            reverse("document_review", args=[self.document.pk]),
            {"decision": Review.Decision.APPROVED, "comment": "Dokumen sesuai."},
        )
        self.assertEqual(response.status_code, 403)

    @patch("dms.views.store_document_file")
    def test_upload_is_blocked_while_under_review(self, upload_mock):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document_upload", args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        upload_mock.assert_not_called()

    @patch("dms.views.store_document_file")
    def test_historical_under_review_without_file_accepts_first_upload(self, upload_mock):
        historical = Document.objects.filter(
            status=Document.Status.UNDER_REVIEW,
            versions__isnull=True,
        ).exclude(pk=self.document.pk).first()
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/historical-atp-rev-000.pdf",
            "stored_filename": "historical-atp-rev-000.pdf",
            "mime_type": "application/pdf",
            "file_size": 12,
        }
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("document_upload", args=[historical.pk]),
            {
                "file": SimpleUploadedFile(
                    "historical-atp.pdf",
                    b"test content",
                    content_type="application/pdf",
                ),
                "change_summary": "Melengkapi file historis",
            },
        )

        self.assertEqual(response.status_code, 302)
        historical.refresh_from_db()
        version = historical.versions.get()
        self.assertEqual(historical.status, Document.Status.UNDER_REVIEW)
        self.assertTrue(version.is_locked)
        upload_mock.assert_called_once()

    def test_revision_required_must_upload_a_new_version_before_submit(self):
        self.document.status = Document.Status.REVISION_REQUIRED
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document_submit", args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.REVISION_REQUIRED)

    @patch("dms.views.open_document_file")
    def test_download_is_available_to_nokia(self, download_mock):
        import io

        download_mock.return_value = io.BytesIO(b"test")
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("document_download", args=[self.version.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="test.pdf"')
