from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(
        default="postgresql+psycopg://receipt:receipt@localhost:5432/receipt_intelligence",
        alias="DATABASE_URL",
    )
    blob_sas_token: str = Field(default="", alias="BLOB_SAS_TOKEN")
    document_intelligence_endpoint: str = Field(default="", alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    document_intelligence_key: str = Field(default="", alias="AZURE_DOCUMENT_INTELLIGENCE_KEY")
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(default="", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-10-21", alias="AZURE_OPENAI_API_VERSION")
    environment: str = Field(default="dev", alias="ENVIRONMENT")
    otel_service_name: str = Field(default="mimojo-receipt-intelligence", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
