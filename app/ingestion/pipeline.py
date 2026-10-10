import hashlib
import logging
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.clients.azure_openai import create_embeddings
from app.clients.azure_search import delete_report_chunks, upload_chunks
from app.errors import ConflictError, IngestionError
from app.ingestion.chunker import semantic_chunk
from app.ingestion.extractor import extract_pdf_text
from app.models import Company, FinancialKPI, Report

log = logging.getLogger(__name__)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_or_create_company(
    db: Session,
    name: str,
    ticker: str | None = None,
    sector: str | None = None,
) -> Company:
    name = name.strip()
    company = (
        db.query(Company).filter(func.lower(Company.name) == name.lower()).first()
    )

    if company is None:
        company = Company(name=name, ticker=ticker, sector=sector)
        db.add(company)
    else:
        # Fill in blanks if this upload knows something the first one didn't.
        company.ticker = company.ticker or ticker
        company.sector = company.sector or sector

    db.commit()
    db.refresh(company)
    return company


def ingest_pdf(
    db: Session,
    file_path: str | Path,
    company_name: str,
    report_year: int,
    *,
    display_name: str | None = None,
    ticker: str | None = None,
    sector: str | None = None,
    extract_kpis: bool = True,
) -> tuple[Report, FinancialKPI | None]:
    file_path = Path(file_path)
    file_hash = file_sha256(file_path)
    company = get_or_create_company(db, company_name, ticker, sector)

    # ---- have we seen this exact file for this company before? ----
    report = (
        db.query(Report)
        .filter(Report.company_id == company.id, Report.file_hash == file_hash)
        .first()
    )
    if report and report.status == "indexed":
        raise ConflictError(
            f"This file was already ingested for {company.name} (report id {report.id})."
        )

    if report is None:
        report = Report(
            company_id=company.id,
            file_name=display_name or file_path.name,
            file_path=str(file_path),
            file_hash=file_hash,
            report_year=report_year,
            status="processing",
        )
        db.add(report)
    else:  # an earlier attempt failed or was interrupted: start it over
        report.status = "processing"
        report.error_message = None
        report.report_year = report_year
    db.commit()
    db.refresh(report)
    report_id = report.id

    # ---- the actual work ----
    try:
        pages = extract_pdf_text(str(file_path))
        chunks = semantic_chunk(pages)
        if not chunks:
            raise IngestionError("The PDF contained no usable text after cleaning.")

        # Clear leftovers from a previous failed attempt, if any.
        delete_report_chunks(report_id)

        vectors = create_embeddings([c["content"] for c in chunks])

        documents = [
            {
                # Deterministic id: re-running the same report overwrites, never duplicates.
                "id": f"r{report_id}-c{index:05d}",
                "company_id": company.id,
                "company": company.name,
                "report_id": report_id,
                "report_year": report_year,
                "page": chunk["page"],
                "content": chunk["content"],
                "content_vector": vector,
                "source": report.file_name,
            }
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        upload_chunks(documents)

        report.chunk_count = len(documents)
        report.status = "indexed"
        report.error_message = None
        db.commit()

    except Exception as exc:
        db.rollback()
        report = db.get(Report, report_id)
        report.status = "failed"
        report.error_message = str(exc)[:1000]
        db.commit()
        try:  # don't leave half a report searchable
            delete_report_chunks(report_id)
        except Exception:
            log.warning("Cleanup of partial chunks for report %s failed", report_id)
        raise

    db.refresh(report)

    #KPI extraction is a bonus: its failure must not undo a good ingest
    kpi = None
    if extract_kpis:
        # imported here to avoid a circular import (kpi_service uses the retriever)
        from app.services.kpi_service import extract_and_store_kpis

        try:
            kpi = extract_and_store_kpis(db, report)
        except Exception as exc:
            db.rollback()
            log.warning("KPI extraction failed for report %s: %s", report_id, exc)

    return report, kpi


def delete_report(db: Session, report: Report) -> None:
    delete_report_chunks(report.id)

    file_path = Path(report.file_path) if report.file_path else None
    db.delete(report)  # cascades to its KPI rows
    db.commit()

    if file_path and not db.query(Report).filter(Report.file_path == str(file_path)).count():
        file_path.unlink(missing_ok=True)
