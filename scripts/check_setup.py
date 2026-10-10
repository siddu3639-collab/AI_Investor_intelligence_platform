"""
Run this first (and again whenever something fails). It shows which settings the
app really sees and tests each external service on its own.

    python -m scripts.check_setup
"""
import os
from urllib.parse import urlparse

try:
    from app.config import ENV_FILE, settings
except Exception as exc:  # bad or placeholder settings: say so plainly
    print("[FAIL] Settings could not be loaded:\n")
    print(exc)
    raise SystemExit(1)

from dotenv import dotenv_values
from sqlalchemy import text

# Known error text -> what to do about it
HINTS = {
    "Failed to resolve": "The host name is wrong or still a placeholder. Fix the endpoint in .env, save, restart.",
    "DeploymentNotFound": "AZURE_OPENAI_*_DEPLOYMENT must be the deployment NAME from Azure, not the model name.",
    "Responses API is enabled only": "Set AZURE_OPENAI_API_VERSION=2025-04-01-preview (GPT-5/o-series need >= 2025-03-01-preview).",
    "401": "Wrong API key for that resource.",
    "403": "Wrong key, or the service blocks your IP / network.",
    "ResourceNotFound": "The search index doesn't exist yet: python -m scripts.create_search_index",
    "index": "If the index is missing: python -m scripts.create_search_index",
    "could not connect": "PostgreSQL isn't running: docker compose up -d postgres",
    "Connection refused": "PostgreSQL isn't running: docker compose up -d postgres",
}


def show_configuration() -> None:
    print("Configuration the app is using")
    print(f"  .env file        : {ENV_FILE} ({'found' if ENV_FILE.exists() else 'NOT FOUND'})")
    print(f"  OpenAI host      : {urlparse(settings.azure_openai_endpoint).hostname}")
    print(f"  Chat deployment  : {settings.azure_openai_chat_deployment}")
    print(f"  Embed deployment : {settings.azure_openai_embedding_deployment}")
    print(f"  API version      : {settings.azure_openai_api_version}")
    print(f"  Search host      : {urlparse(settings.azure_search_endpoint).hostname}")
    print(f"  Search index     : {settings.azure_search_index}")

    # Real shell variables beat the .env file, a classic cause of "I edited .env
    # but nothing changed".
    from_file = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    for key, value in from_file.items():
        shell_value = os.environ.get(key.upper())
        if value and shell_value is not None and shell_value != value:
            print(f"  WARNING: your terminal has {key.upper()} set, and it overrides the .env file. Run: unset {key.upper()}")
    print()


def step(name, fn) -> bool:
    try:
        print(f"[ OK ] {name}: {fn()}")
        return True
    except Exception as exc:
        message = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        print(f"[FAIL] {name}: {message}")
        hint = next((h for key, h in HINTS.items() if key.lower() in str(exc).lower() or key in exc.__class__.__name__), None)
        if hint:
            print(f"       -> {hint}")
        return False


def check_database():
    from app.database import engine
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return "connected"


def check_embeddings():
    from app.clients.azure_openai import create_embedding
    return f"{len(create_embedding('hello'))} dimensions"


def check_chat():
    from app.clients.azure_openai import generate_answer
    return generate_answer("Reply with one word.", "Say OK").strip()[:40] or "(empty reply)"


def check_index():
    from app.clients.azure_search import get_search_client
    return f"index '{settings.azure_search_index}' reachable, {get_search_client().get_document_count()} documents"


if __name__ == "__main__":
    show_configuration()
    results = [
        step("PostgreSQL", check_database),
        step("Azure OpenAI embeddings", check_embeddings),
        step("Azure OpenAI chat", check_chat),
        step("Azure AI Search index", check_index),
    ]
    raise SystemExit(0 if all(results) else 1)
