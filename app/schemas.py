from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

DISCLAIMER = (
    "Generated from the indexed company reports for information only. "
    "This is not personalised investment advice."
)


#companies

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ticker: Optional[str] = Field(default=None, max_length=50)
    sector: Optional[str] = Field(default=None, max_length=100)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    created_at: Optional[datetime] = None


#reports

class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    file_name: str
    report_year: Optional[int] = None
    status: str
    chunk_count: Optional[int] = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


#KPIs

class KPIResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_income: Optional[float] = None
    net_margin: Optional[float] = None
    eps: Optional[float] = None
    debt: Optional[float] = None
    cash: Optional[float] = None
    reporting_unit: Optional[str] = None


class KPIRecord(KPIResponse):
    id: int
    company_id: int
    report_id: int
    created_at: Optional[datetime] = None


class UploadResponse(BaseModel):
    report: ReportOut
    kpis: Optional[KPIRecord] = None
    message: str


#questions & answers

class QueryRequest(BaseModel):
    company_id: Optional[int] = None
    report_year: Optional[int] = None
    question: str = Field(min_length=3, max_length=2000)


class AnalyzeRequest(BaseModel):
    """Same as QueryRequest, but the company comes from the URL."""
    report_year: Optional[int] = None
    question: str = Field(min_length=3, max_length=2000)


class Source(BaseModel):
    document_id: str
    company: str
    report_year: Optional[int] = None
    page: Optional[int] = None
    content: str
    score: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    disclaimer: str = DISCLAIMER


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    question: str
    answer: str
    sources: Optional[list] = None
    created_at: Optional[datetime] = None
