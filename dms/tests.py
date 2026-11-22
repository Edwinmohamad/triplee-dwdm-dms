from pathlib import Path
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from .models import (
    Document,
    DocumentAttachment,
    DocumentVersion,
    InstallationBatch,
    Review,
    Site,
    User,
)
from .services.local_storage import (
    bundle_filename,
    document_filename,
    download_filename,
    open_document_file,
    store_document_file,
)


class LocalStorageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.document = Document.objects.select_related(
            "batch__site__project"
        ).exclude(batch__status=InstallationBatch.Status.PENDING_INSTALLATION).first()

    def test_document_is_stored_in_structured_relative_path(self):
        document = Document.objects.select_related("batch__site__project").get(
            document_type=Document.Type.FATP,
            batch__site__tower_id="SUM-BB-KBA-0057",
        )
        with TemporaryDirectory() as temporary_root, override_settings(
            DOCUMENT_STORAGE_ROOT=temporary_root
        ):
            uploaded = SimpleUploadedFile(
                "QC Final.PDF",
                b"test document",
                content_type="application/pdf",
            )
            result = store_document_file(document, uploaded, 0)
            stored_path = Path(temporary_root) / result["storage_key"]

            self.assertTrue(stored_path.is_file())
            self.assertIn("BATCH-", result["storage_key"])
            self.assertIn("REV-000", result["storage_key"])
            self.assertEqual(
                result["stored_filename"],
                document_filename(document, 0, uploaded.name, 1),
            )
            self.assertEqual(
                result["stored_filename"],
                "FATP_Koba_SUM-BB-KBA-0057.pdf",
            )
            self.assertEqual(stored_path.read_bytes(), b"test document")

    def test_additional_qc_file_uses_short_sequence_suffix(self):
        document = Document.objects.select_related("batch__site").get(
            document_type=Document.Type.QC,
            batch__site__tower_id="SUM-BB-KBA-0057",
        )

        filename = document_filename(document, 0, "Rack Photo.JPG", 2)

        self.assertEqual(filename, "QC_Koba_SUM-BB-KBA-0057_02.jpg")

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

    def test_nokia_reviewer_cannot_make_decision(self):
        self.client.force_login(self.reviewer)
        response = self.client.post(
            reverse("document_review", args=[self.document.pk]),
            {"decision": Review.Decision.APPROVED, "comment": "Dokumen sesuai."},
        )
        self.assertEqual(response.status_code, 403)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.UNDER_REVIEW)
        self.assertFalse(self.document.reviews.exists())

    def test_nokia_page_has_comment_but_no_decision_form(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kirim komentar")
        self.assertNotContains(response, "Simpan keputusan")

    def test_superadmin_can_record_internal_decision(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("document_review", args=[self.document.pk]),
            {"decision": Review.Decision.APPROVED, "comment": "Dokumen sesuai."},
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.APPROVED)
        self.assertTrue(self.document.reviews.filter(decision=Review.Decision.APPROVED).exists())

    def test_nokia_reviewer_can_add_comment(self):
        self.client.force_login(self.reviewer)
        response = self.client.post(
            reverse("document_comment", args=[self.document.pk]),
            {"body": "Mohon periksa kembali foto koneksi power."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.document.comments.filter(author=self.reviewer).exists()
        )

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
                "files": SimpleUploadedFile(
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
        self.assertEqual(version.attachments.count(), 1)
        upload_mock.assert_called_once()

    @patch("dms.views.store_document_file")
    def test_qc_accepts_multiple_files_and_appends_before_submit(self, upload_mock):
        qc_document = Document.objects.filter(
            document_type=Document.Type.QC,
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        upload_mock.side_effect = [
            {
                "storage_key": "NOKIA-DWDM/qc-r0-f1.pdf",
                "stored_filename": "qc-r0-f1.pdf",
                "mime_type": "application/pdf",
                "file_size": 11,
            },
            {
                "storage_key": "NOKIA-DWDM/qc-r0-f2.jpg",
                "stored_filename": "qc-r0-f2.jpg",
                "mime_type": "image/jpeg",
                "file_size": 12,
            },
        ]
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("document_upload", args=[qc_document.pk]),
            {
                "files": [
                    SimpleUploadedFile("power.pdf", b"power file", "application/pdf"),
                    SimpleUploadedFile("rack.jpg", b"rack image", "image/jpeg"),
                ],
                "change_summary": "QC perangkat dan power",
            },
        )
        self.assertEqual(response.status_code, 302)
        qc_document.refresh_from_db()
        version = qc_document.versions.get()
        self.assertEqual(version.revision_no, 0)
        self.assertEqual(version.attachments.count(), 2)
        self.assertEqual(qc_document.status, Document.Status.UPLOADED)

        upload_mock.side_effect = None
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/qc-r0-f3.png",
            "stored_filename": "qc-r0-f3.png",
            "mime_type": "image/png",
            "file_size": 13,
        }
        response = self.client.post(
            reverse("document_upload", args=[qc_document.pk]),
            {
                "files": SimpleUploadedFile(
                    "alarm.png",
                    b"alarm image",
                    "image/png",
                ),
                "change_summary": "Tambah capture alarm",
            },
        )
        self.assertEqual(response.status_code, 302)
        version.refresh_from_db()
        self.assertEqual(qc_document.versions.count(), 1)
        self.assertEqual(version.attachments.count(), 3)
        self.assertEqual(version.file_size, 36)

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
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{download_filename(self.version)}"',
        )

    @patch("dms.views.convert_office_to_pdf")
    @patch("dms.views.open_document_file")
    def test_docx_preview_is_converted_and_opened_inline(
        self, download_mock, convert_mock
    ):
        import io

        self.version.original_filename = "Report FATP.docx"
        self.version.stored_filename = "report-fatp.docx"
        self.version.mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        self.version.save(
            update_fields=["original_filename", "stored_filename", "mime_type"]
        )
        download_mock.return_value = io.BytesIO(b"docx")
        convert_mock.return_value = io.BytesIO(b"%PDF-1.7 preview")
        self.client.force_login(self.reviewer)

        response = self.client.get(
            reverse("document_preview", args=[self.version.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertNotIn("attachment;", response["Content-Disposition"])
        convert_mock.assert_called_once()

    @patch("dms.views.convert_office_to_pdf")
    @patch("dms.views.open_document_file")
    def test_docx_download_keeps_original_file(
        self, download_mock, convert_mock
    ):
        import io

        self.version.original_filename = "Report FATP.docx"
        self.version.stored_filename = "report-fatp.docx"
        self.version.mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        self.version.save(
            update_fields=["original_filename", "stored_filename", "mime_type"]
        )
        download_mock.return_value = io.BytesIO(b"docx")
        self.client.force_login(self.reviewer)

        response = self.client.get(
            reverse("document_download", args=[self.version.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertTrue(response["Content-Disposition"].endswith('.docx"'))
        convert_mock.assert_not_called()

    @patch("dms.views.open_document_file")
    def test_unsupported_preview_does_not_force_download(self, download_mock):
        import io

        self.version.original_filename = "archive.zip"
        self.version.stored_filename = "archive.zip"
        self.version.mime_type = "application/zip"
        self.version.save(
            update_fields=["original_filename", "stored_filename", "mime_type"]
        )
        download_mock.return_value = io.BytesIO(b"zip")
        self.client.force_login(self.reviewer)

        response = self.client.get(
            reverse("document_preview", args=[self.version.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview belum tersedia")
        self.assertNotIn("Content-Disposition", response)

    @patch("dms.views.open_document_file")
    def test_nokia_can_download_all_revision_attachments_as_zip(self, download_mock):
        import io
        import zipfile

        first_attachment = DocumentAttachment.objects.create(
            version=self.version,
            sequence_no=1,
            storage_key="DWDM/test.pdf",
            stored_filename="site-qc-f01.pdf",
            original_filename="power.pdf",
            mime_type="application/pdf",
            file_size=5,
            checksum_sha256="b" * 64,
        )
        second_attachment = DocumentAttachment.objects.create(
            version=self.version,
            sequence_no=2,
            storage_key="DWDM/test-2.jpg",
            stored_filename="site-qc-f02.jpg",
            original_filename="rack.jpg",
            mime_type="image/jpeg",
            file_size=4,
            checksum_sha256="c" * 64,
        )
        payloads = {
            "DWDM/test.pdf": b"power",
            "DWDM/test-2.jpg": b"rack",
        }
        download_mock.side_effect = lambda storage_key: io.BytesIO(payloads[storage_key])
        self.client.force_login(self.reviewer)

        response = self.client.get(
            reverse("version_download_all", args=[self.version.pk])
        )

        self.assertEqual(response.status_code, 200)
        archive_bytes = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    download_filename(first_attachment),
                    download_filename(second_attachment),
                ],
            )
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{bundle_filename(self.version)}"',
        )

    @patch("dms.views.delete_document_file")
    def test_triplee_can_delete_last_file_from_open_revision(self, delete_mock):
        document = Document.objects.filter(
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        document.status = Document.Status.UPLOADED
        document.save(update_fields=["status", "updated_at"])
        version = DocumentVersion.objects.create(
            document=document,
            revision_no=0,
            storage_key="DWDM/delete-last.pdf",
            stored_filename="delete-last.pdf",
            original_filename="delete-last.pdf",
            mime_type="application/pdf",
            file_size=12,
            checksum_sha256="d" * 64,
            uploaded_by=self.admin,
        )
        attachment = DocumentAttachment.objects.create(
            version=version,
            sequence_no=1,
            storage_key="DWDM/delete-last.pdf",
            stored_filename="delete-last.pdf",
            original_filename="delete-last.pdf",
            mime_type="application/pdf",
            file_size=12,
            checksum_sha256="d" * 64,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("attachment_delete", args=[attachment.pk])
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.NOT_STARTED)
        self.assertFalse(document.versions.exists())
        delete_mock.assert_called_once_with("DWDM/delete-last.pdf")

    @patch("dms.views.delete_document_file")
    def test_delete_primary_file_repoints_open_revision(self, delete_mock):
        document = Document.objects.filter(
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        document.status = Document.Status.UPLOADED
        document.save(update_fields=["status", "updated_at"])
        version = DocumentVersion.objects.create(
            document=document,
            revision_no=0,
            storage_key="DWDM/delete-primary-1.pdf",
            stored_filename="delete-primary-1.pdf",
            original_filename="primary.pdf",
            mime_type="application/pdf",
            file_size=20,
            checksum_sha256="e" * 64,
            uploaded_by=self.admin,
        )
        primary = DocumentAttachment.objects.create(
            version=version,
            sequence_no=1,
            storage_key="DWDM/delete-primary-1.pdf",
            stored_filename="delete-primary-1.pdf",
            original_filename="primary.pdf",
            mime_type="application/pdf",
            file_size=12,
            checksum_sha256="e" * 64,
        )
        remaining = DocumentAttachment.objects.create(
            version=version,
            sequence_no=2,
            storage_key="DWDM/delete-primary-2.jpg",
            stored_filename="delete-primary-2.jpg",
            original_filename="rack.jpg",
            mime_type="image/jpeg",
            file_size=8,
            checksum_sha256="f" * 64,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("attachment_delete", args=[primary.pk]))

        self.assertEqual(response.status_code, 302)
        version.refresh_from_db()
        self.assertEqual(version.storage_key, remaining.storage_key)
        self.assertEqual(version.file_size, remaining.file_size)
        self.assertEqual(version.attachments.count(), 1)
        delete_mock.assert_called_once_with(primary.storage_key)

    @patch("dms.views.delete_document_file")
    def test_nokia_cannot_delete_uploaded_file(self, delete_mock):
        self.client.force_login(self.reviewer)
        attachment = DocumentAttachment.objects.create(
            version=self.version,
            sequence_no=1,
            storage_key="DWDM/nokia-cannot-delete.pdf",
            stored_filename="nokia-cannot-delete.pdf",
            original_filename="test.pdf",
            mime_type="application/pdf",
            file_size=5,
            checksum_sha256="1" * 64,
        )

        response = self.client.post(
            reverse("attachment_delete", args=[attachment.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(DocumentAttachment.objects.filter(pk=attachment.pk).exists())
        delete_mock.assert_not_called()

    @patch("dms.views.delete_document_file")
    def test_superadmin_can_delete_last_file_from_approved_revision_and_keep_audit(
        self, delete_mock
    ):
        attachment = DocumentAttachment.objects.create(
            version=self.version,
            sequence_no=1,
            storage_key="DWDM/approved-file.pdf",
            stored_filename="very-long-approved-file-name.pdf",
            original_filename="approval.pdf",
            mime_type="application/pdf",
            file_size=9,
            checksum_sha256="2" * 64,
        )
        Review.objects.create(
            document=self.document,
            version=self.version,
            reviewer=self.admin,
            decision=Review.Decision.APPROVED,
            comment="Approved sebelum file dihapus.",
        )
        self.document.status = Document.Status.APPROVED
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("attachment_delete", args=[attachment.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.version.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.NOT_STARTED)
        self.assertFalse(self.version.has_file)
        self.assertTrue(self.version.storage_key.startswith("__deleted__/"))
        self.assertTrue(self.version.reviews.exists())
        self.assertFalse(self.version.attachments.exists())
        delete_mock.assert_called_once_with("DWDM/approved-file.pdf")

        page = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assertContains(page, "File revisi sudah dihapus")

    @patch("dms.views.delete_document_file")
    def test_triplee_admin_cannot_force_delete_locked_file(self, delete_mock):
        attachment = DocumentAttachment.objects.create(
            version=self.version,
            sequence_no=1,
            storage_key="DWDM/admin-cannot-delete.pdf",
            stored_filename="admin-cannot-delete.pdf",
            original_filename="test.pdf",
            mime_type="application/pdf",
            file_size=5,
            checksum_sha256="3" * 64,
        )
        self.admin.role = User.Role.TRIPLEE_ADMIN
        self.admin.is_superuser = False
        self.admin.save(update_fields=["role", "is_superuser"])
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("attachment_delete", args=[attachment.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(DocumentAttachment.objects.filter(pk=attachment.pk).exists())
        delete_mock.assert_not_called()


class ProgressReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.reviewer = User.objects.create_user(
            username="report-reviewer",
            full_name="Nokia Report Reviewer",
            password="VerySecure123!",
            role=User.Role.NOKIA_REVIEWER,
            must_change_password=False,
        )

    def test_progress_report_requires_login(self):
        response = self.client.get(reverse("progress_report_export"))
        self.assertEqual(response.status_code, 302)

    def test_progress_pdf_requires_login(self):
        response = self.client.get(reverse("progress_report_pdf"))
        self.assertEqual(response.status_code, 302)

    @override_settings(BRAND_LOGO_PATH="/path/that/does/not/exist/logo.png")
    def test_nokia_can_export_professional_total_progress_pdf(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("progress_report_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            "TripleE_DWDM_Total_Progress_",
            response["Content-Disposition"],
        )
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 5000)

    def test_nokia_can_export_auditable_progress_workbook(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("progress_report_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("TripleE_DWDM_Progress_", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content), data_only=False)
        self.assertEqual(
            workbook.sheetnames,
            ["Ringkasan", "Progress Site", "Detail Batch", "Riwayat Dokumen"],
        )
        self.assertEqual(workbook["Progress Site"].max_row, Site.objects.count() + 5)
        self.assertEqual(
            workbook["Detail Batch"].max_row,
            InstallationBatch.objects.count() + 5,
        )
        self.assertTrue(workbook["Progress Site"]["H6"].value.startswith("=IF("))


