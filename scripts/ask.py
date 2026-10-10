"""
Ask a question from the terminal, no API server needed.

    python -m scripts.ask "What are the main risks?" --company-id 1
"""
import argparse

from app.database import Base, SessionLocal, engine
from app.services.analysis_service import analyze


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--year", type=int)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        result = analyze(db, args.question, args.company_id, args.year)

    print(result["answer"])
    print("\nSources:")
    for s in result["sources"]:
        print(f"  - {s['company']} {s.get('report_year')} page {s.get('page')} (score {s.get('score')})")


if __name__ == "__main__":
    main()
