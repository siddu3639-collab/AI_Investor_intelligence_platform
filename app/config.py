import re
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_PLACEHOLDER = re.compile(r"(^|[^a-z])your[-_ ]|<[^>]*>", re.IGNORECASE)

_AZURE_FIELDS = (
    "azure_openai_endpoint",
    "azure_openai_api_key",
    "azure_openai_chat_deployment",
    "azure_openai_embedding_deployment",
    "azure_search_endpoint",
    "azure_search_api_key",
)


class Settings(BaseSettings):
    app_name: str = "Investor Intelligence Platform"
    environment: str = "development"

    database_url: str

    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str

    azure_search_endpoint: str
    azure_search_api_key: str
    azure_search_index: str = "investor-documents"

    embedding_dimensions: int = 1536
    embedding_batch_size: int = 16
    top_k: int = 6

    upload_dir: str = "data/reports"
    max_upload_mb: int = 50

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _clean_and_check(self):
        for name in _AZURE_FIELDS:
            setattr(self, name, getattr(self, name).strip())
        self.azure_openai_endpoint = self.azure_openai_endpoint.rstrip("/")
        self.azure_search_endpoint = self.azure_search_endpoint.rstrip("/")

        leftovers = [
            name.upper() for name in _AZURE_FIELDS if _PLACEHOLDER.search(getattr(self, name))
        ]
        if leftovers:
            raise ValueError(
                "These settings still contain placeholder text from .env.example: "
                + ", ".join(leftovers)
                + f". Edit {ENV_FILE}, SAVE the file, and restart the server."
            )

        for name in ("azure_openai_endpoint", "azure_search_endpoint"):
            if not getattr(self, name).startswith("https://"):
                raise ValueError(f"{name.upper()} must start with https://")
        return self


settings = Settings()
