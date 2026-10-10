#Saving uploaded PDFs to disk safely
import hashlib
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings


class UploadRejected(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def safe_filename(name: str | None) -> str:
    base = Path(name or "report.pdf").name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "report.pdf"
    return base if base.lower().endswith(".pdf") else base + ".pdf"


def save_upload(file: UploadFile) -> tuple[Path, str]:
    original_name = safe_filename(file.filename)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise UploadRejected("Only .pdf files are accepted.")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    limit = settings.max_upload_mb * 1024 * 1024
    temp_path = upload_dir / f"{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    size = 0

    try:
        with open(temp_path, "wb") as out:
            while block := file.file.read(1024 * 1024):
                if size == 0 and not block.startswith(b"%PDF-"):
                    raise UploadRejected("That file is not a valid PDF.")
                size += len(block)
                if size > limit:
                    raise UploadRejected(
                        f"File is larger than {settings.max_upload_mb} MB.", 413
                    )
                digest.update(block)
                out.write(block)

        if size == 0:
            raise UploadRejected("The uploaded file is empty.")

        final_path = upload_dir / f"{digest.hexdigest()[:12]}_{original_name}"
        temp_path.replace(final_path)
        return final_path, original_name

    finally:
        temp_path.unlink(missing_ok=True)
