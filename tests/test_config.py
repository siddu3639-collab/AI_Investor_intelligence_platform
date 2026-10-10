import pytest
from pydantic import ValidationError

from app.config import Settings

GOOD = dict(
    database_url="sqlite:///x.db",
    azure_openai_endpoint="https://real.openai.azure.com/",
    azure_openai_api_key="abc123",
    azure_openai_chat_deployment="gpt-5-mini",
    azure_openai_embedding_deployment="text-embedding-3-small",
    azure_search_endpoint="https://real.search.windows.net",
    azure_search_api_key="def456",
)


def test_valid_settings_and_trailing_slash_removed():
    s = Settings(_env_file=None, **GOOD)
    assert s.azure_openai_endpoint == "https://real.openai.azure.com"


def test_placeholder_values_are_rejected_with_a_clear_message():
    bad = GOOD | {"azure_search_endpoint": "https://your-service.search.windows.net"}
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None, **bad)
    assert "AZURE_SEARCH_ENDPOINT" in str(err.value) and "SAVE" in str(err.value)


def test_endpoint_must_be_https():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(GOOD | {"azure_openai_endpoint": "real.openai.azure.com"}))
