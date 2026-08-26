import shutil
import subprocess
from pathlib import Path
from tempfile import SpooledTemporaryFile, TemporaryDirectory


OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".docm",
    ".odt",
    ".rtf",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".ods",
    ".ppt",
    ".pptx",
    ".pptm",
    ".odp",
}

INLINE_MIME_TYPES = {
    "application/pdf",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/csv",
    "text/plain",
}


class PreviewConversionError(RuntimeError):
    pass


def file_extension(filename):
    return Path(filename or "").suffix.lower()


def can_preview_inline(mime_type):
    return mime_type in INLINE_MIME_TYPES


def can_convert_to_pdf(filename):
    return file_extension(filename) in OFFICE_EXTENSIONS


def convert_office_to_pdf(source, filename, timeout=90):
    """Convert an Office document to an in-memory PDF using LibreOffice."""
    binary = shutil.which("libreoffice")
    if not binary:
        raise PreviewConversionError("LibreOffice tidak tersedia di container web.")

    extension = file_extension(filename)
    if extension not in OFFICE_EXTENSIONS:
        raise PreviewConversionError("Format file tidak mendukung preview PDF.")

    try:
        with TemporaryDirectory(prefix="dms-preview-") as temporary_dir:
            workdir = Path(temporary_dir)
            input_path = workdir / f"source{extension}"
            output_path = workdir / "source.pdf"
            profile_uri = (workdir / "profile").resolve().as_uri()

            with input_path.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

            completed = subprocess.run(
                [
                    binary,
                    "--headless",
                    "--invisible",
                    "--nologo",
                    "--nodefault",
                    "--nolockcheck",
                    "--norestore",
                    f"-env:UserInstallation={profile_uri}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(workdir),
                    str(input_path),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            if completed.returncode != 0 or not output_path.is_file():
                detail = completed.stdout.decode("utf-8", errors="replace").strip()
                raise PreviewConversionError(
                    f"Konversi file gagal{': ' + detail[-300:] if detail else '.'}"
                )

            preview = SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
            with output_path.open("rb") as converted:
                shutil.copyfileobj(converted, preview, length=1024 * 1024)
            preview.seek(0)
            return preview
    except subprocess.TimeoutExpired as exc:
        raise PreviewConversionError("Konversi preview melebihi batas waktu 90 detik.") from exc
    except OSError as exc:
        raise PreviewConversionError(f"File tidak dapat dikonversi: {exc}") from exc
