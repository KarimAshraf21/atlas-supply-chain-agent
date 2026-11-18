from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ".env"), extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("atlas-dev-password")
    neo4j_database: str = "neo4j"

    groq_api_key: SecretStr | None = None
    llm_reasoning_model: str = "openai/gpt-oss-120b"
    llm_fast_model: str = "openai/gpt-oss-20b"
    stt_model: str = "whisper-large-v3-turbo"

    agent_max_steps: int = 6  # tool-calling rounds per specialist
    agent_tool_timeout_s: float = 30.0

    seed_dir: Path = ROOT / "data" / "seed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
