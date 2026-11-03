from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOTIFIER_", env_file=".env", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql://notifier:notifier@localhost:5432/notifier"

    # Reintentos: max_attempts cuenta el intento inicial (3 = inicial + 2 reintentos).
    max_attempts: int = 3
    retry_backoff_seconds: float = 5.0  # espera = base * 2^(intento-1)
    lock_seconds: int = 60  # un trabajo "en proceso" sin terminar se recupera pasado este plazo
    poll_interval_seconds: float = 1.0
    worker_metrics_port: int = 9100

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_timeout_seconds: float = 5.0
    mail_from: str = "notificaciones@plataforma.test"

    # Inyección de fallas del proveedor de correo (prueba P1-2 e incidente controlado).
    email_fault_rate: float = 0.0
    email_fault_kind: Literal["503", "timeout"] = "503"


settings = Settings()
