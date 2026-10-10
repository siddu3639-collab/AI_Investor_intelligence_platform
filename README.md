# AI-Powered Investor Intelligence Platform

Upload a company's annual report (PDF), then ask questions in plain English.
Answers come from the actual pages of the report and cite them, e.g. `[Page 42]`.

```
PDF -> text -> chunks -> embeddings -> Azure AI Search
Question -> embedding -> hybrid search -> top chunks -> Azure OpenAI -> cited answer
```

**Stack:** Python 3.10+, FastAPI, Azure OpenAI (embeddings + chat), Azure AI Search
(vector + keyword), PostgreSQL + SQLAlchemy, PyPDF, Pydantic, Docker.

## Why the pieces are split this way

| Piece | Job | Why |
|---|---|---|
| Azure AI Search | stores chunk text + vectors, does retrieval | built for similarity search; hybrid keyword + vector in one call |
| PostgreSQL | companies, reports, KPIs, question history | structured data you query and join; the system of record |
| Azure OpenAI | embeddings and answer writing | the model *reads* evidence; it is never the source of truth |

## Project layout

```
app/
  main.py                 REST endpoints
  config.py               settings from .env
  database.py, models.py  PostgreSQL via SQLAlchemy
  schemas.py              request/response validation (Pydantic)
  clients/                azure_openai.py, azure_search.py
  ingestion/              extractor.py -> chunker.py -> pipeline.py (+ storage.py for uploads)
  rag/                    retriever.py, prompts.py, generator.py
  services/               kpi_service.py, analysis_service.py
scripts/                  create_search_index, check_setup, make_sample_report, ingest_report, ask
tests/                    23 tests, no Azure account needed
```

## 1. Create the Azure resources (once)

1. **Azure OpenAI** resource -> Foundry/Studio -> deploy two models:
   a chat model (e.g. `gpt-4.1-mini`) and `text-embedding-3-small`.
   Note the **deployment names** you give them, plus the endpoint and key.
2. **Azure AI Search** service (Basic tier is fine; Free works for a demo).
   Note the endpoint and the **admin key** (Keys page).
3. PostgreSQL runs locally in Docker, nothing to create in Azure.

## 2. Set up the project

macOS / Linux:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```
Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```
Open `.env` and fill in the Azure values. **Never commit `.env`.**

## 3. Start PostgreSQL

```bash
docker compose up -d postgres
```

## 4. Check everything is wired correctly

```bash
python -m scripts.check_setup
```
You want four `[ OK ]` lines. Any `[FAIL]` tells you which credential is wrong.
(The Search check fails until step 5 creates the index. That's expected.)

## 5. Create the search index

```bash
python -m scripts.create_search_index
python -m scripts.check_setup        # all four should pass now
```
If you ever change `EMBEDDING_DIMENSIONS`, run it with `--recreate`.

## 6. Start the API

```bash
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs, where you can try every endpoint in the browser.

## 7. Try it with the built-in sample report

```bash
python -m scripts.make_sample_report      # fictional "Acme Robotics" 2025 report
```
In `/docs`, call **POST /reports/upload** with the file `data/reports/acme_robotics_2025.pdf`,
`company_name = Acme Robotics`, `report_year = 2025`. Or with curl:

```bash
curl -X POST http://127.0.0.1:8000/reports/upload \
  -F "file=@data/reports/acme_robotics_2025.pdf" \
  -F "company_name=Acme Robotics" -F "report_year=2025" -F "ticker=ACME"
```
Then ask (use the `company_id` returned by the upload):

```bash
curl -X POST http://127.0.0.1:8000/companies/1/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "What drove revenue growth and what are the main risks?"}'
```
For a real report, download a 10-K or annual report PDF from a company's investor-relations
page and upload it the same way (or `python -m scripts.ingest_report file.pdf --company Tesla --year 2025`).

## API summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/reports/upload` | upload PDF -> index it -> extract KPIs |
| GET | `/reports`, `/reports/{id}` | list / inspect reports and their status |
| DELETE | `/reports/{id}` | remove from index, database and disk |
| POST | `/reports/{id}/kpis` | re-run KPI extraction |
| POST | `/companies` / GET `/companies` | manage companies |
| GET | `/companies/{id}/kpis` | extracted KPIs, newest year first |
| POST | `/companies/{id}/analyze` | ask about one company |
| POST | `/query` | ask across everything (optional `company_id`, `report_year`) |
| GET | `/companies/{id}/history` | past questions and answers |
| GET | `/health` | app + database check |

## Run everything in Docker instead

```bash
docker compose up --build
```
The `api` container reads Azure settings from `.env` and talks to Postgres over the compose network.
Run one-off scripts inside it: `docker compose exec api python -m scripts.create_search_index`.

## Run the tests

```bash
python -m pytest -q
```
They use SQLite and fake Azure calls, so they run offline and prove the logic (chunking, uploads,
duplicates, KPI validation, retrieval filters, history, delete).

## How a question gets answered

1. The question is embedded (turned into a vector of 1536 numbers capturing its meaning).
2. Azure AI Search runs **hybrid** retrieval: BM25 keyword match *and* vector similarity, merged.
   Keywords catch exact terms (EBITDA, FY2025); vectors catch meaning ("why did sales go up").
3. The top `TOP_K` chunks go into a prompt that says: use only this evidence, don't invent numbers,
   cite pages, say so if information is missing.
4. If retrieval returns nothing, the LLM is **not called**; you get a "not found" message.
5. The exchange is stored in PostgreSQL (`analysis_history`).

## Design decisions worth knowing

- **Chunking:** about 1800 characters with 300 overlap, split on paragraphs then sentences, never
  across pages, so each chunk has one citable page number.
- **KPIs are validated:** the LLM returns JSON; Pydantic coerces/validates it; net margin is recomputed
  from revenue and net income rather than trusted. Values keep the report's own unit (`reporting_unit`).
- **Idempotent ingestion:** chunk ids are `r{report_id}-c{n}`, and a file's SHA-256 stops duplicate uploads.
- **Safe uploads:** `.pdf` extension, `%PDF-` magic bytes, size cap, sanitised filename.
- **Not investment advice:** the prompt forbids buy/sell/hold recommendations and every response carries a disclaimer.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `DeploymentNotFound` | `.env` has the *model* name instead of your *deployment* name |
| `Unsupported value: 'temperature'` | you deployed a reasoning model (o-series/GPT-5); remove `temperature` in `generate_answer` |
| 502 "Upstream Azure service error" | wrong key/endpoint, or Azure quota exceeded, so check `scripts.check_setup` |
| "Embedding model returned N dimensions" | set `EMBEDDING_DIMENSIONS=N`, then `create_search_index --recreate` |
| 422 "No text could be extracted" | scanned PDF; needs OCR first (Azure Document Intelligence) |
| Answers miss table numbers | PyPDF flattens tables; use a layout-aware parser for table-heavy reports |
| `could not connect to server` | `docker compose up -d postgres`, and check `DATABASE_URL` |
| New upload not found immediately | Search indexing can lag a second or two, so retry |

## Known limits / next steps

Synchronous ingestion (move to a background queue for very large reports), table-aware parsing,
reranking, authentication and rate limiting, Alembic migrations, an evaluation set for retrieval
quality, and a front end.

## 8. Run the dashboard frontend

The API docs at `/docs` are only the FastAPI developer interface. The React dashboard is in `frontend/` and runs separately.

Terminal 1 — start the API on port 8001 (or change the Vite proxy target in `frontend/vite.config.js` if you use another port):

```bash
uvicorn app.main:app --reload --port 8001
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`. The dashboard uses a Vite proxy to send `/api/*` requests to FastAPI. Do not open `/docs` expecting the dashboard UI.

### If uploads or AI insights fail

1. Confirm `http://127.0.0.1:8001/health` returns `{"status":"ok", ...}`.
2. Run `python -m scripts.check_setup` from the project root and fix every failed Azure/PostgreSQL check. The `.env.example` values are placeholders; create `.env` with real Azure OpenAI and Azure AI Search deployment/service credentials.
3. Create the Azure AI Search index with `python -m scripts.create_search_index` after setting `.env`.
4. Upload a text-based PDF (not a scanned image-only PDF). Scanned PDFs need OCR before this pipeline can extract content.
5. In browser Developer Tools → Network, inspect `POST /api/reports/upload` or `POST /api/query`; the response's `detail` message should identify the failing service or input.

The current backend extracts revenue, revenue growth, net income, net margin, EPS, debt and cash. It does **not** extract operating income or total assets, so the dashboard marks those two values unavailable rather than inventing numbers. The sample values in any design mockup are not real uploaded-report results.
