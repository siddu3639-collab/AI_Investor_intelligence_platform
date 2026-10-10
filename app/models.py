from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    ticker = Column(String(50))
    sector = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=_now)

    reports = relationship("Report", back_populates="company")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("company_id", "file_hash", name="uq_report_company_hash"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000))
    file_hash = Column(String(64), nullable=False)  # sha256 of the PDF bytes
    report_year = Column(Integer)

    # processing -> indexed, or processing -> failed (with error_message)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text)
    chunk_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=_now)

    company = relationship("Company", back_populates="reports")
    kpis = relationship(
        "FinancialKPI", back_populates="report", cascade="all, delete-orphan"
    )


class FinancialKPI(Base):
    __tablename__ = "financial_kpis"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)

    revenue = Column(Float)
    revenue_growth = Column(Float)  # percent
    net_income = Column(Float)
    net_margin = Column(Float)  # percent
    eps = Column(Float)
    debt = Column(Float)
    cash = Column(Float)
    reporting_unit = Column(String(100))

    created_at = Column(DateTime(timezone=True), default=_now)

    report = relationship("Report", back_populates="kpis")


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=_now)
