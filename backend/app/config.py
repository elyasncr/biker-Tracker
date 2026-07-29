from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "../data"
    database_url: str = "sqlite:///./igpsport.db"

    ftp_watts: int = 220
    hr_max: int = 190
    hr_rest: int = 55

    # Necessario para estimar potencia por fisica quando nao ha potenciometro.
    rider_weight_kg: float = 75.0
    default_bike_weight_kg: float = 12.0

    igpsport_enabled: bool = False
    igpsport_client_id: str = ""
    igpsport_client_secret: str = ""
    igpsport_redirect_uri: str = "http://localhost:8000/api/igpsport/callback"
    igpsport_auth_url: str = ""
    igpsport_token_url: str = ""
    igpsport_api_base: str = ""

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
