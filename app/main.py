import logging
from contextlib import asynccontextmanager
from typing import Optional

from azure.core.exceptions import AzureError
from fastapi import Depends, FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from openai import OpenAIError
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import Base, engine, get_db
from app.errors import ConflictError, IngestionError, NotFoundError
from app.ingestion.pipeline import delete_report, ingest_pdf
from app.ingestion.storage import UploadRejected, save_upload
from app.schemas import (
    AnalyzeRequest,
    CompanyCreate,
    CompanyOut,
    HistoryOut,
    KPIRecord,
    QueryRequest,
    QueryResponse,
    ReportOut,
    UploadResponse,
)
from app.services.analysis_service import analyze
from app.services.kpi_service import extract_and_store_kpis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("investor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Ask questions about company annual reports and get answers "
                "grounded in the actual pages, with citations.",
    version="1.0.0",
    lifespan=lifespan,
)


#errors

@app.exception_handler(NotFoundError)
async def _not_found(_, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def _conflict(_, exc: ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(IngestionError)
async def _ingestion(_, exc: IngestionError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(UploadRejected)
async def _upload_rejected(_, exc: UploadRejected):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(OpenAIError)
@app.exception_handler(AzureError)
async def _azure_down(_, exc: Exception):
    # Log the full thing, but only send a short message to the caller.
    log.exception("Azure call failed")
    return JSONResponse(
        status_code=502,
        content={"detail": f"Upstream Azure service error: {str(exc)[:300]}"},
    )


#health

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))  # proves the database connection works
    return {"status": "ok", "environment": settings.environment}


#companies

@app.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
    exists = (
        db.query(models.Company)
        .filter(func.lower(models.Company.name) == body.name.strip().lower())
        .first()
    )
    if exists:
        raise ConflictError(f"Company '{exists.name}' already exists (id {exists.id}).")

    company = models.Company(**body.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@app.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(models.Company).order_by(models.Company.name).all()


def _company_or_404(db: Session, company_id: int) -> models.Company:
    company = db.get(models.Company, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found")
    return company


@app.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    return _company_or_404(db, company_id)


#reports

@app.post("/reports/upload", response_model=UploadResponse, status_code=201)
def upload_report(
    file: UploadFile = File(..., description="The annual/quarterly report PDF"),
    company_name: str = Form(..., min_length=1, max_length=255),
    report_year: int = Form(..., ge=1990, le=2100),
    ticker: Optional[str] = Form(None),
    sector: Optional[str] = Form(None),
    extract_kpis: bool = Form(True),
    db: Session = Depends(get_db),
):
    """Upload a PDF, index it for search and (optionally) extract headline KPIs."""
    path, original_name = save_upload(file)

    report, kpi = ingest_pdf(
        db,
        path,
        company_name,
        report_year,
        display_name=original_name,
        ticker=ticker,
        sector=sector,
        extract_kpis=extract_kpis,
    )

    note = f"Indexed {report.chunk_count} chunks."
    if extract_kpis and kpi is None:
        note += " KPI extraction did not succeed; you can retry it from /reports/{id}/kpis."

    return UploadResponse(report=report, kpis=kpi, message=note)


@app.get("/reports", response_model=list[ReportOut])
def list_reports(
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Report)
    if company_id is not None:
        query = query.filter(models.Report.company_id == company_id)
    return query.order_by(models.Report.created_at.desc()).all()


def _report_or_404(db: Session, report_id: int) -> models.Report:
    report = db.get(models.Report, report_id)
    if report is None:
        raise NotFoundError(f"Report {report_id} not found")
    return report


@app.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    return _report_or_404(db, report_id)


@app.delete("/reports/{report_id}", status_code=204)
def remove_report(report_id: int, db: Session = Depends(get_db)):
    delete_report(db, _report_or_404(db, report_id))
    return Response(status_code=204)


# ------------------------------------------------------------------ KPIs

@app.post("/reports/{report_id}/kpis", response_model=KPIRecord)
def run_kpi_extraction(report_id: int, db: Session = Depends(get_db)):
    """(Re)run KPI extraction for a report that is already indexed."""
    report = _report_or_404(db, report_id)
    if report.status != "indexed":
        raise ConflictError(f"Report {report_id} is '{report.status}', not indexed.")
    try:
        return extract_and_store_kpis(db, report)
    except ValueError as exc:
        raise IngestionError(str(exc)) from exc


@app.get("/companies/{company_id}/kpis", response_model=list[KPIRecord])
def company_kpis(company_id: int, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    return (
        db.query(models.FinancialKPI)
        .join(models.Report, models.Report.id == models.FinancialKPI.report_id)
        .filter(models.FinancialKPI.company_id == company_id)
        .order_by(models.Report.report_year.desc())
        .all()
    )


#Q&A (RAG)

@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, db: Session = Depends(get_db)):
    """Ask across every indexed report, or narrow with company_id / report_year."""
    return analyze(db, request.question, request.company_id, request.report_year)


@app.post("/companies/{company_id}/analyze", response_model=QueryResponse)
def analyze_company(
    company_id: int, request: AnalyzeRequest, db: Session = Depends(get_db)
):
    return analyze(db, request.question, company_id, request.report_year)


@app.get("/companies/{company_id}/history", response_model=list[HistoryOut])
def company_history(
    company_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _company_or_404(db, company_id)
    return (
        db.query(models.AnalysisHistory)
        .filter(models.AnalysisHistory.company_id == company_id)
        .order_by(models.AnalysisHistory.created_at.desc())
        .limit(limit)
        .all()
    )
