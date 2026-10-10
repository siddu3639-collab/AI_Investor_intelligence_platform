from app.clients.azure_openai import create_embedding
from app.clients.azure_search import hybrid_search
from app.config import settings


def build_filter(
    company_id: int | None = None,
    report_year: int | None = None,
    report_id: int | None = None,
) -> str | None:
    parts = []
    if company_id is not None:
        parts.append(f"company_id eq {int(company_id)}")
    if report_year is not None:
        parts.append(f"report_year eq {int(report_year)}")
    if report_id is not None:
        parts.append(f"report_id eq {int(report_id)}")
    return " and ".join(parts) or None


def retrieve(
    question: str,
    company_id: int | None = None,
    report_year: int | None = None,
    report_id: int | None = None,
    top_k: int | None = None,
) -> list[dict]:
    top_k = top_k or settings.top_k
    query_vector = create_embedding(question)

    return hybrid_search(
        query_text=question,
        query_vector=query_vector,
        top_k=top_k,
        odata_filter=build_filter(company_id, report_year, report_id),
    )
