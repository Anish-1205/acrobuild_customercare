"""Scan uploads before parsing or persistence; production requires an AV engine."""
import os
from pathlib import Path
import subprocess
import zipfile
import io


def scan_upload(content):
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Upload exceeds 10 MB")
    executable = os.getenv("CLAMSCAN_PATH", "").strip()
    if not executable:
        if os.getenv("ACROBUILD_ENV", "development") == "production":
            raise ValueError("Upload scanning is unavailable. Contact the administrator.")
        return "disabled_development"
    if not Path(executable).is_absolute():
        raise ValueError("CLAMSCAN_PATH must be an absolute executable path")
    try:
        result = subprocess.run([executable, "--no-summary", "-"], input=content, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Upload scanning failed") from error
    if result.returncode != 0:
        raise ValueError("Upload rejected by the malware scanner")
    return "clean"


def validate_knowledge_upload(content, filename):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("PDF content does not match its extension")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Not a Word document")
                if sum(info.file_size for info in archive.infolist()) > 30 * 1024 * 1024:
                    raise ValueError("Expanded document exceeds 30 MB")
        except zipfile.BadZipFile as error:
            raise ValueError("Invalid Word document") from error
    scan_upload(content)


def check_storage_quota(directory, incoming_bytes):
    quota = int(os.getenv("UPLOAD_STORAGE_QUOTA_BYTES", str(512 * 1024 * 1024)))
    used = sum(path.stat().st_size for path in Path(directory).rglob("*") if path.is_file())
    if used + incoming_bytes > quota:
        raise ValueError("Attachment storage quota exceeded")
