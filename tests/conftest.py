import json
import os
import re
import tempfile

_tmp = tempfile.mkdtemp(prefix="investor-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    UPLOAD_DIR=f"{_tmp}/reports",
    AZURE_OPENAI_ENDPOINT="https://fake.openai.azure.com",
    AZURE_OPENAI_API_KEY="fake",
    AZURE_OPENAI_CHAT_DEPLOYMENT="fake-chat",
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT="fake-embed",
    AZURE_SEARCH_ENDPOINT="https://fake.search.windows.net",
    AZURE_SEARCH_API_KEY="fake",
)

import pytest 
from fastapi.testclient import TestClient  

from app.database import Base, engine  
from app.main import app 


class FakeSearchIndex:

    def __init__(self):
        self.docs: list[dict] = []

    def upload(self, documents):
        self.docs.extend(documents)

    def delete_report(self, report_id):
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["report_id"] != report_id]
        return before - len(self.docs)

    def search(self, query_text, query_vector, top_k, odata_filter=None):
        hits = self.docs
        for field in ("company_id", "report_year", "report_id"):
            match = re.search(rf"{field} eq (\d+)", odata_filter or "")
            if match:
                hits = [d for d in hits if d[field] == int(match.group(1))]
        return [
            {k: d.get(k) for k in ("id", "company", "report_year", "page", "content", "source")}
            | {"score": 0.5}
            for d in hits[:top_k]
        ]


FAKE_KPI_JSON = json.dumps(
    {
        "revenue": "4,820", "revenue_growth": 18.4, "net_income": 578,
        "net_margin": 99,  # deliberately wrong: the service must recompute it
        "eps": 3.42, "debt": 940, "cash": 1350, "reporting_unit": "USD millions",
    }
)


@pytest.fixture
def index(monkeypatch):
    fake = FakeSearchIndex()

    monkeypatch.setattr("app.ingestion.pipeline.create_embeddings", lambda texts: [[0.1, 0.2]] * len(texts))
    monkeypatch.setattr("app.ingestion.pipeline.upload_chunks", fake.upload)
    monkeypatch.setattr("app.ingestion.pipeline.delete_report_chunks", fake.delete_report)
    monkeypatch.setattr("app.rag.retriever.create_embedding", lambda text: [0.1, 0.2])
    monkeypatch.setattr("app.rag.retriever.hybrid_search", fake.search)
    monkeypatch.setattr("app.rag.generator.generate_answer", lambda system, user, **kw: "Revenue rose 18.4% [Page 1].")
    monkeypatch.setattr("app.services.kpi_service.generate_answer", lambda system, user, **kw: FAKE_KPI_JSON)
    return fake


@pytest.fixture
def client(index):
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client: 
        yield test_client
