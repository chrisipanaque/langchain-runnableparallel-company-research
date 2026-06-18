from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="COMPANY_RESEARCH_",
    )

    github_token: str = ""
    request_timeout: int = 30
    verbose: bool = False


settings = Settings()
