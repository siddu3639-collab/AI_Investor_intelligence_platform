from app.rag.prompts import build_user_prompt
from app.rag.retriever import build_filter


def test_filter_combinations():
    assert build_filter() is None
    assert build_filter(company_id=3) == "company_id eq 3"
    assert build_filter(company_id=3, report_year=2025) == "company_id eq 3 and report_year eq 2025"


def test_prompt_contains_page_and_question():
    docs = [{"company": "Acme", "report_year": 2025, "page": 9, "content": "Revenue up."}]
    prompt = build_user_prompt("Why?", docs)
    assert "Page: 9" in prompt and "Why?" in prompt and "Revenue up." in prompt
