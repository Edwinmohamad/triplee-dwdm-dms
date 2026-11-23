import hashlib
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
from PIL import Image as PillowImage

from .models import (
    ActivityLog,
    Document,
    DocumentAttachment,
    DocumentVersion,
    FatpBuilder,
    FatpEquipment,
    FatpPhoto,
    FatpSection,
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
        self.assertEqual(InstallationBatch.objects.count(), 16)
        self.assertEqual(Document.objects.count(), 48)

    def test_mentigi_and_sungai_liat_only_have_one_batch(self):
        mentigi = Site.objects.get(tower_id="SUM-BB-TDN-0361")
        sungai_liat = Site.objects.get(tower_id="SUM-BB-SGL-0238")
        self.assertEqual(mentigi.batches.count(), 1)
        self.assertEqual(sungai_liat.batches.count(), 1)
        self.assertEqual(mentigi.batches.get().batch_no, 1)
        self.assertEqual(sungai_liat.batches.get().batch_no, 1)

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


class DriveFolderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.admin = User.objects.create_superuser(
            username="drive-admin",
            full_name="Drive Admin",
            password="VerySecure123!",
            must_change_password=False,
        )
        cls.viewer = User.objects.create_user(
            username="drive-viewer",
            full_name="Drive Viewer",
            password="VerySecure123!",
            role=User.Role.NOKIA_VIEWER,
            must_change_password=False,
        )
        cls.site = Site.objects.get(tower_id="SUM-BB-KBA-0057")
        cls.batch = cls.site.batches.get(batch_no=1)

    def test_admin_can_save_drive_folder_link(self):
        self.client.force_login(self.admin)
        url = "https://drive.google.com/drive/folders/example-folder-id"
        response = self.client.post(
            reverse("drive_folder_update", args=[self.batch.pk]),
            {"drive_folder_url": url},
        )
        self.assertRedirects(
            response,
            reverse("installation_photos") + f"?site={self.site.pk}#site-photo-detail",
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.drive_folder_url, url)

    def test_photo_library_is_available_to_viewer(self):
        self.batch.drive_folder_url = "https://drive.google.com/drive/folders/example-folder-id"
        self.batch.save(update_fields=["drive_folder_url"])
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("installation_photos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-photo-library')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertNotContains(response, 'data-drive-popup')
        self.assertContains(response, self.site.name)

    def test_non_drive_url_is_rejected(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("drive_folder_update", args=[self.batch.pk]),
            {"drive_folder_url": "https://example.com/folders/not-drive"},
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.drive_folder_url, "")

    def test_viewer_cannot_change_drive_folder(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("drive_folder_update", args=[self.batch.pk]),
            {"drive_folder_url": "https://drive.google.com/drive/folders/example-folder-id"},
        )
        self.assertEqual(response.status_code, 403)

    def test_dashboard_shows_customer_vendor_branding_and_svg_navigation(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="project-partnership"')
        self.assertContains(response, reverse("nokia_logo"))
        self.assertContains(response, 'class="nav-icon"')

    def test_two_batches_keep_separate_photo_folders(self):
        site = Site.objects.get(tower_id="SUM-BB-KBA-0057")
        first = site.batches.get(batch_no=1)
        second = InstallationBatch.objects.create(
            site=site,
            batch_no=2,
            label="Batch 2",
            pic_name="EDWIN",
            status=InstallationBatch.Status.INSTALLED,
        )
        first.drive_folder_url = "https://drive.google.com/drive/folders/batch-one"
        second.drive_folder_url = "https://drive.google.com/drive/folders/batch-two"
        first.save(update_fields=["drive_folder_url"])
        second.save(update_fields=["drive_folder_url"])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("installation_photos") + f"?site={site.pk}")
        self.assertContains(response, first.drive_folder_url)
        self.assertContains(response, second.drive_folder_url)
        self.assertContains(response, "2 installation batch")


class FatpBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.admin = User.objects.create_superuser(
            username="fatp-master",
            full_name="FATP Master",
            password="VerySecure123!",
            must_change_password=False,
        )
        cls.viewer = User.objects.create_user(
            username="fatp-viewer",
            full_name="FATP Viewer",
            password="VerySecure123!",
            role=User.Role.NOKIA_VIEWER,
            must_change_password=False,
        )
        cls.document = Document.objects.get(
            document_type=Document.Type.FATP,
            batch__site__tower_id="SUM-BB-KBA-0057",
        )

    @staticmethod
    def image_upload(name="power-main.jpg", color=(12, 110, 130)):
        payload = BytesIO()
        PillowImage.new("RGB", (900, 1200), color).save(payload, format="JPEG")
        return SimpleUploadedFile(name, payload.getvalue(), content_type="image/jpeg")

    def test_only_super_admin_can_open_builder(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("fatp_builder_editor", args=[self.document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_new_builder_uses_pdf_example_sections_by_default(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("fatp_builder_editor", args=[self.document.pk])
        )
        self.assertEqual(response.status_code, 200)
        builder = FatpBuilder.objects.get(document=self.document)
        self.assertEqual(builder.sections.count(), 7)
        self.assertEqual(
            list(builder.sections.values_list("title", flat=True)),
            [
                "Wiring Diagram Power Source",
                "Photo Power Connection - Main",
                "Photo Power Connection - Backup",
                "Failover Test - MCB Main Off (A1)",
                "Failover Test - MCB Backup Off (B1)",
                "Load Voltage and Ampere",
                "Photo LVD Setting",
            ],
        )
        self.assertContains(response, "Upload foto FATP")
        self.assertContains(response, "Atur bagian")

    def test_builder_saves_installation_info_and_equipment(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("fatp_builder_editor", args=[self.document.pk]))
        response = self.client.post(
            reverse("fatp_builder_settings", args=[self.document.pk]),
            {
                "installation_title": "Install 1 PSS16 & 1 Switch",
                "installation_date": "2026-05-28",
                "work_description": "Power integration",
                "equipment_name": ["Nokia PSS16II", "Network Switch"],
                "equipment_model": ["PSS16II", ""],
                "equipment_quantity": ["1", "1"],
                "equipment_notes": ["DWDM", "Management"],
            },
        )
        self.assertRedirects(response, reverse("fatp_builder_editor", args=[self.document.pk]))
        builder = FatpBuilder.objects.get(document=self.document)
        self.assertEqual(builder.installation_title, "Install 1 PSS16 & 1 Switch")
        self.assertEqual(builder.equipment.count(), 2)

    def test_multiple_identical_photos_are_allowed_and_pdf_is_generated(self):
        self.client.force_login(self.admin)
        with TemporaryDirectory() as temporary_root, override_settings(DOCUMENT_STORAGE_ROOT=temporary_root):
            self.client.get(reverse("fatp_builder_editor", args=[self.document.pk]))
            builder = FatpBuilder.objects.get(document=self.document)
            FatpEquipment.objects.create(builder=builder, name="Nokia PSS16II", quantity=1)
            section = FatpSection.objects.create(builder=builder, title="Power Connection", columns=2)
            original = self.image_upload()
            duplicate = SimpleUploadedFile("same-photo.jpg", original.read(), content_type="image/jpeg")
            original.seek(0)
            response = self.client.post(
                reverse("fatp_photo_upload", args=[section.pk]),
                {"photos": [original, duplicate]},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(FatpPhoto.objects.filter(section=section).count(), 2)
            response = self.client.get(reverse("fatp_builder_preview", args=[self.document.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b"%PDF"))
            response = self.client.post(
                reverse("fatp_builder_generate", args=[self.document.pk]),
                {"output_status": Document.Status.UNDER_REVIEW},
            )
            self.assertRedirects(response, reverse("document_detail", args=[self.document.pk]))
            self.document.refresh_from_db()
            self.assertEqual(self.document.status, Document.Status.UNDER_REVIEW)
            version = self.document.latest_version
            self.assertEqual(version.mime_type, "application/pdf")
            self.assertTrue(version.is_locked)


class BrandingTests(TestCase):
    def test_nokia_logo_endpoint_serves_configured_file(self):
        with TemporaryDirectory() as temporary_root:
            logo_path = Path(temporary_root) / "nokialogo.png"
            logo_path.write_bytes(b"test-nokia-logo")
            with override_settings(NOKIA_LOGO_PATH=str(logo_path)):
                response = self.client.get(reverse("nokia_logo"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"test-nokia-logo")


class ManualDocumentStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.admin = User.objects.create_superuser(
            username="status-master",
            full_name="Status Master",
            password="VerySecure123!",
            must_change_password=False,
        )
        cls.viewer = User.objects.create_user(
            username="status-viewer",
            full_name="Status Viewer",
            password="VerySecure123!",
            role=User.Role.NOKIA_VIEWER,
            must_change_password=False,
        )
        cls.document = Document.objects.filter(status=Document.Status.NOT_STARTED).first()

    def test_super_admin_can_set_any_supported_document_status(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("document_status_override", args=[self.document.pk]),
            {"status": Document.Status.APPROVED, "note": "Dokumen signed diterima."},
        )
        self.assertRedirects(response, reverse("document_detail", args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.APPROVED)
        self.assertIsNotNone(self.document.approved_at)
        self.assertTrue(
            ActivityLog.objects.filter(
                action="DOCUMENT_STATUS_OVERRIDDEN",
                entity_id=str(self.document.pk),
            ).exists()
        )

    def test_super_admin_can_change_status_without_optional_note(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("document_status_override", args=[self.document.pk]),
            {"status": Document.Status.UNDER_REVIEW},
        )
        self.assertRedirects(response, reverse("document_detail", args=[self.document.pk]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.UNDER_REVIEW)
        self.assertIsNotNone(self.document.submitted_at)

        activity = ActivityLog.objects.get(
            action="DOCUMENT_STATUS_OVERRIDDEN",
            entity_id=str(self.document.pk),
        )
        self.assertEqual(activity.metadata["note"], "")

    def test_manual_status_panel_is_only_rendered_for_super_admin(self):
        self.client.force_login(self.admin)
        admin_response = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assertContains(admin_response, "MASTER CONTROL")
        self.client.force_login(self.viewer)
        viewer_response = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assertNotContains(viewer_response, "MASTER CONTROL")

    def test_viewer_cannot_override_document_status(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("document_status_override", args=[self.document.pk]),
            {"status": Document.Status.APPROVED},
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_manual_status_is_rejected(self):
        self.client.force_login(self.admin)
        previous_status = self.document.status
        response = self.client.post(
            reverse("document_status_override", args=[self.document.pk]),
            {"status": "CUSTOM_UNKNOWN"},
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, previous_status)


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
        self.assertContains(response, "Project Control Center")
        self.assertContains(response, "data-control-search")
        self.assertContains(response, "data-control-row", count=16)

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
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        self.assertIsNotNone(qc_document)
        qc_document.status = Document.Status.NOT_STARTED
        qc_document.save(update_fields=["status", "updated_at"])
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

    @patch("dms.views.store_document_file")
    def test_upload_and_submit_review_is_one_step(self, upload_mock):
        document = Document.objects.filter(
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/direct-review.pdf",
            "stored_filename": "direct-review.pdf",
            "mime_type": "application/pdf",
            "file_size": 17,
        }
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("document_upload", args=[document.pk]),
            {
                "files": SimpleUploadedFile(
                    "review.pdf", b"direct review content", "application/pdf"
                ),
                "change_summary": "Submit langsung untuk review",
                "upload_action": "submit_review",
            },
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        version = document.versions.get()
        self.assertEqual(document.status, Document.Status.UNDER_REVIEW)
        self.assertIsNotNone(document.submitted_at)
        self.assertTrue(version.is_locked)

    @patch("dms.views.store_document_file")
    def test_superadmin_can_upload_signed_document_as_approved(self, upload_mock):
        document = Document.objects.filter(
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/signed-approved.pdf",
            "stored_filename": "signed-approved.pdf",
            "mime_type": "application/pdf",
            "file_size": 21,
        }
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("document_upload", args=[document.pk]),
            {
                "files": SimpleUploadedFile(
                    "signed.pdf", b"signed approved content", "application/pdf"
                ),
                "change_summary": "Dokumen sudah TTD",
                "upload_action": "signed_approved",
            },
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        version = document.versions.get()
        self.assertEqual(document.status, Document.Status.APPROVED)
        self.assertIsNotNone(document.approved_at)
        self.assertTrue(version.is_locked)
        self.assertTrue(
            document.reviews.filter(
                version=version,
                reviewer=self.admin,
                decision=Review.Decision.APPROVED,
            ).exists()
        )

    @patch("dms.views.store_document_file")
    def test_signed_document_can_replace_under_review_with_new_revision(
        self, upload_mock
    ):
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/signed-after-review.pdf",
            "stored_filename": "signed-after-review.pdf",
            "mime_type": "application/pdf",
            "file_size": 25,
        }
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("document_upload", args=[self.document.pk]),
            {
                "files": SimpleUploadedFile(
                    "signed-final.pdf",
                    b"signed after Nokia review",
                    "application/pdf",
                ),
                "change_summary": "Final signed document",
                "upload_action": "signed_approved",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        latest = self.document.latest_version
        self.assertEqual(self.document.status, Document.Status.APPROVED)
        self.assertEqual(latest.revision_no, 1)
        self.assertTrue(latest.is_locked)
        self.assertTrue(
            self.document.reviews.filter(
                version=latest,
                decision=Review.Decision.APPROVED,
            ).exists()
        )

    @patch("dms.views.store_document_file")
    def test_triplee_admin_cannot_mark_signed_document_approved(self, upload_mock):
        document = Document.objects.filter(
            status=Document.Status.NOT_STARTED,
            batch__status=InstallationBatch.Status.INSTALLED,
        ).first()
        self.admin.role = User.Role.TRIPLEE_ADMIN
        self.admin.is_superuser = False
        self.admin.save(update_fields=["role", "is_superuser"])
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("document_upload", args=[document.pk]),
            {
                "files": SimpleUploadedFile(
                    "signed.pdf", b"unauthorized signed content", "application/pdf"
                ),
                "upload_action": "signed_approved",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(document.versions.exists())
        upload_mock.assert_not_called()

    def test_revision_required_must_upload_a_new_version_before_submit(self):
        self.document.status = Document.Status.REVISION_REQUIRED
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document_submit", args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.REVISION_REQUIRED)

    @patch("dms.views.store_document_file")
    def test_same_file_is_allowed_when_uploading_a_new_revision(self, upload_mock):
        content = b"same content may be corrected without renaming"
        self.version.checksum_sha256 = hashlib.sha256(content).hexdigest()
        self.version.save(update_fields=["checksum_sha256"])
        self.document.status = Document.Status.REVISION_REQUIRED
        self.document.save(update_fields=["status", "updated_at"])
        upload_mock.return_value = {
            "storage_key": "NOKIA-DWDM/same-file-rev-001.pdf",
            "stored_filename": "same-file-rev-001.pdf",
            "mime_type": "application/pdf",
            "file_size": 18,
        }
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("document_upload", args=[self.document.pk]),
            {
                "files": SimpleUploadedFile(
                    "test.pdf",
                    content,
                    "application/pdf",
                ),
                "change_summary": "Revisi isi file dengan nama yang sama",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.document.versions.count(), 2)
        self.assertEqual(self.document.latest_version.revision_no, 1)

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

    @patch("dms.views.open_document_file")
    def test_preview_uses_original_file_inline(self, download_mock):
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
            reverse("document_preview", args=[self.version.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], self.version.mime_type)
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertTrue(response["Content-Disposition"].endswith('.docx"'))

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

    def test_nokia_can_export_progress_pdf(self):
        self.client.force_login(self.reviewer)

        response = self.client.get(reverse("progress_report_pdf_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("TripleE_DWDM_Progress_", response["Content-Disposition"])
        payload = b"".join(response.streaming_content)
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertGreater(len(payload), 5000)
