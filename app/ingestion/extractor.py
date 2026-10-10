import logging

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.errors import IngestionError

log = logging.getLogger(__name__)


def extract_pdf_text(file_path: str) -> list[dict]:
    try:
        reader = PdfReader(file_path)

        if reader.is_encrypted:
            # Many "protected" PDFs just have an empty user password.
            if not reader.decrypt(""):
                raise IngestionError("The PDF is password protected.")

        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:  # one bad page shouldn't sink a 200-page report
                log.warning("Could not read page %s of %s", page_number, file_path)
                continue

            if text:
                pages.append({"page": page_number, "text": text})

    except PyPdfError as exc:
        raise IngestionError(f"Could not read the PDF: {exc}") from exc

    if not pages:
        raise IngestionError(
            "No text could be extracted. The PDF is probably a scan; "
            "it needs OCR (e.g. Azure Document Intelligence) first."
        )

    return pages
