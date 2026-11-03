import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class NotificationRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=254)
    channel: Literal["email", "internal"]
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _email_needs_address(self) -> Self:
        if self.channel == "email" and "@" not in self.recipient:
            raise ValueError("el destinatario de un correo debe ser una dirección con '@'")
        return self

    def content_hash(self) -> str:
        """Huella del contenido: distingue un reintento legítimo de una clave reutilizada."""
        payload = json.dumps(
            [self.recipient, self.subject, self.body], ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class AuthenticatedClient(BaseModel):
    id: str
    name: str
    role: Literal["client", "admin"]
