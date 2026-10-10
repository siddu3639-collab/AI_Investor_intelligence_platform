"""
Ingest a PDF from the command line (same pipeline the API uses).

    python -m scripts.ingest_report data/reports/tesla_2025.pdf --company Tesla --year 2025
"""
import argparse

from app.database import Base, SessionLocal, engine
from app.ingestion.pipeline import ingest_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="path to the PDF")
    parser.add_argument("--company", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--ticker")
    parser.add_argument("--sector")
    parser.add_argument("--no-kpis", action="store_true", help="skip KPI extraction")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        report, kpi = ingest_pdf(
            db,
            args.pdf,
            args.company,
            args.year,
            ticker=args.ticker,
            sector=args.sector,
            extract_kpis=not args.no_kpis,
        )

    print(f"Indexed {report.chunk_count} chunks (report id {report.id}, company id {report.company_id}).")
    if kpi:
        print(
            f"KPIs: revenue={kpi.revenue} growth={kpi.revenue_growth}% "
            f"net_income={kpi.net_income} margin={kpi.net_margin}% eps={kpi.eps} "
            f"debt={kpi.debt} cash={kpi.cash} unit={kpi.reporting_unit}"
        )


if __name__ == "__main__":
    main()
