"""
KPI extraction. The LLM reads a handful of retrieved passages and fills in a
fixed JSON shape; we then validate that JSON with Pydantic before anything is
written to PostgreSQL. The database never stores raw model output.
"""
import json
import re

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.clients.azure_openai import generate_answer
from app.models import FinancialKPI, Report
from app.rag.retriever import retrieve

KPI_PROMPT = """
Extract financial KPIs for the MOST RECENT fiscal year from the supplied
company-report excerpts.

Return ONLY a JSON object with exactly these keys:

{
  "revenue": number or null,
  "revenue_growth": number or null,
  "net_income": number or null,
  "net_margin": number or null,
  "eps": number or null,
  "debt": number or null,
  "cash": number or null,
  "reporting_unit": string or null
}

Rules:
- Never invent values. Use null when the excerpts don't state it.
- Copy monetary values exactly as the report states them (do not convert units).
- reporting_unit is the currency and scale of those values, e.g. "USD millions".
- revenue_growth and net_margin are percentages (12.5 means 12.5%).
- eps is the diluted earnings per share if available.
- debt is total debt (short-term plus long-term borrowings).
"""

# Different questions pull in different parts of the report (income statement,
# balance sheet, MD&A), which is how we gather all the numbers.
KPI_SEARCH_QUERIES = [
    "total revenue net sales for the year and growth compared with the prior year",
    "net income profit for the year and net profit margin",
    "diluted earnings per share EPS",
    "total debt borrowings long-term debt notes payable",
    "cash and cash equivalents balance sheet",
]

MAX_CONTEXT_CHARS = 14000


class KPIData(BaseModel):
    revenue: float | None = None
    revenue_growth: float | None = None
    net_income: float | None = None
    net_margin: float | None = None
    eps: float | None = None
    debt: float | None = None
    cash: float | None = None
    reporting_unit: str | None = None

    @field_validator(
        "revenue", "revenue_growth", "net_income", "net_margin", "eps", "debt", "cash",
        mode="before",
    )
    @classmethod
    def _coerce_number(cls, value):
        """Models sometimes answer "1,234.5" or "(310)" instead of a number."""
        if value is None or isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            text = value.strip()
            negative = text.startswith("(") and text.endswith(")")
            cleaned = re.sub(r"[^0-9.\-]", "", text)
            try:
                number = float(cleaned)
            except ValueError:
                return None
            return -abs(number) if negative else number
        return None


def parse_kpi_response(raw: str) -> KPIData:
    """Turn the model's text into a validated KPIData, or raise ValueError."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM did not return a JSON object for the KPIs")

    try:
        data = KPIData.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("LLM returned invalid KPI JSON") from exc

    # Don't trust the model's arithmetic: if we have both numbers, compute it.
    if data.revenue and data.net_income is not None:
        data.net_margin = round(data.net_income / data.revenue * 100, 2)

    return data


def _gather_context(report: Report) -> str:
    seen: set[str] = set()
    passages: list[dict] = []

    for query in KPI_SEARCH_QUERIES:
        for doc in retrieve(query, report_id=report.id, top_k=4):
            if doc["id"] not in seen:
                seen.add(doc["id"])
                passages.append(doc)

    # Reading order (by page) is easier for the model than relevance order.
    passages.sort(key=lambda d: d.get("page") or 0)

    text = "\n\n".join(f"[Page {d.get('page')}]\n{d['content']}" for d in passages)
    return text[:MAX_CONTEXT_CHARS]


def extract_and_store_kpis(db: Session, report: Report) -> FinancialKPI:
    context = _gather_context(report)
    if not context:
        raise ValueError("No indexed text found for this report")

    raw = generate_answer(KPI_PROMPT, context, temperature=0.0, json_mode=True)
    data = parse_kpi_response(raw)

    # One KPI row per report: re-extracting replaces the old one.
    db.query(FinancialKPI).filter(FinancialKPI.report_id == report.id).delete()

    kpi = FinancialKPI(
        company_id=report.company_id,
        report_id=report.id,
        **data.model_dump(),
    )
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    return kpi
