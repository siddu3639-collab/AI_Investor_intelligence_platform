from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import AnalysisHistory, Company
from app.rag.generator import generate_investor_insight
from app.rag.retriever import retrieve


def analyze(
    db: Session,
    question: str,
    company_id: int | None = None,
    report_year: int | None = None,
) -> dict:
    """Retrieve evidence -> generate a grounded answer -> remember the exchange."""
    if company_id is not None and db.get(Company, company_id) is None:
        raise NotFoundError(f"Company {company_id} not found")

    documents = retrieve(question, company_id=company_id, report_year=report_year)
    answer = generate_investor_insight(question, documents)

    db.add(
        AnalysisHistory(
            company_id=company_id,
            question=question,
            answer=answer,
            sources=[
                {
                    "document_id": d["id"],
                    "company": d["company"],
                    "report_year": d.get("report_year"),
                    "page": d.get("page"),
                }
                for d in documents
            ],
        )
    )
    db.commit()

    sources = [
        {
            "document_id": d["id"],
            "company": d["company"],
            "report_year": d.get("report_year"),
            "page": d.get("page"),
            "content": d["content"],
            "score": d.get("score"),
        }
        for d in documents
    ]
    return {"answer": answer, "sources": sources}
