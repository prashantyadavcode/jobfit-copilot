from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_name: str = 'JobFit Copilot'
    app_env: str = 'development'
    log_level: str = 'INFO'
    spacy_model: str = 'en_core_web_sm'
    match_threshold: float = 55.0
    llm_provider: str = 'ollama'
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'llama3.2:3b'
    latex_compiler: str = 'pdflatex'
    openai_api_key: str | None = None
    openai_model: str = 'gpt-4.1-mini'


@lru_cache
def get_settings() -> Settings:
    return Settings()
