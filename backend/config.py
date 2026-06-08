from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    YC_FOLDER_ID: str = ""
    YC_API_KEY: str = ""
    EXOLVE_SIP_LOGIN: str = ""
    EXOLVE_SIP_PASSWORD: str = ""
    EXOLVE_MANAGER_NUMBER: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).with_name(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def yandex_is_configured(self) -> bool:
        return bool(self.YC_FOLDER_ID and self.YC_API_KEY)

    def exolve_is_configured(self) -> bool:
        return all(
            (
                self.EXOLVE_SIP_LOGIN,
                self.EXOLVE_SIP_PASSWORD,
                self.EXOLVE_MANAGER_NUMBER,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

