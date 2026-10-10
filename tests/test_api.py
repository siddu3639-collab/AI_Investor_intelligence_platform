from scripts.make_sample_report import build_pdf, sample_pages


def _pdf_bytes():
    return build_pdf(sample_pages())


def _upload(client, **overrides):
    data = {"company_name": "Acme Robotics", "report_year": "2025"} | overrides.pop("data", {})
    files = overrides.pop("files", {"file": ("acme.pdf", _pdf_bytes(), "application/pdf")})
    return client.post("/reports/upload", data=data, files=files)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_upload_indexes_chunks_and_extracts_kpis(client, index):
    response = _upload(client)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["report"]["status"] == "indexed"
    assert body["report"]["chunk_count"] == len(index.docs) > 0
    assert {d["page"] for d in index.docs} == {1, 2, 3, 4, 5}

    kpis = body["kpis"]
    assert kpis["revenue"] == 4820
    assert kpis["net_margin"] == 11.99
    assert kpis["reporting_unit"] == "USD millions"


def test_same_file_twice_is_rejected(client):
    assert _upload(client).status_code == 201
    assert _upload(client).status_code == 409


def test_non_pdf_and_fake_pdf_are_rejected(client):
    r1 = _upload(client, files={"file": ("notes.txt", b"hello", "text/plain")})
    r2 = _upload(client, files={"file": ("fake.pdf", b"not really a pdf", "application/pdf")})
    assert r1.status_code == 400 and r2.status_code == 400


def test_ask_question_returns_answer_sources_and_saves_history(client):
    company_id = _upload(client).json()["report"]["company_id"]

    response = client.post(
        f"/companies/{company_id}/analyze", json={"question": "Why did revenue grow?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "18.4%" in body["answer"]
    assert body["sources"] and body["sources"][0]["page"] in {1, 2, 3, 4, 5}
    assert "not personalised" in body["disclaimer"]

    history = client.get(f"/companies/{company_id}/history").json()
    assert len(history) == 1 and history[0]["question"] == "Why did revenue grow?"


def test_query_without_evidence_does_not_call_the_llm(client):
    body = client.post("/query", json={"question": "What is the debt position?"}).json()
    assert body["sources"] == []
    assert "could not find" in body["answer"].lower()


def test_unknown_company_is_404(client):
    assert client.post("/query", json={"company_id": 999, "question": "anything"}).status_code == 404


def test_delete_report_clears_index_and_database(client, index):
    report_id = _upload(client).json()["report"]["id"]
    assert index.docs

    assert client.delete(f"/reports/{report_id}").status_code == 204
    assert index.docs == []
    assert client.get(f"/reports/{report_id}").status_code == 404


def test_company_kpis_endpoint(client):
    company_id = _upload(client).json()["report"]["company_id"]
    rows = client.get(f"/companies/{company_id}/kpis").json()
    assert len(rows) == 1 and rows[0]["eps"] == 3.42
