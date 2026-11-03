import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from notifier.db import get_pool
from notifier.models import AuthenticatedClient


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_key() -> str:
    return "ntf_" + secrets.token_urlsafe(32)


def authenticate(x_api_key: Annotated[str | None, Header()] = None) -> AuthenticatedClient:
    if not x_api_key:
        raise HTTPException(401, "falta el encabezado X-API-Key")
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id::text AS id, name, role FROM clients WHERE api_key_hash = %s",
            (hash_key(x_api_key),),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "credencial inválida")
    return AuthenticatedClient(**row)


def require_admin(
    client: Annotated[AuthenticatedClient, Depends(authenticate)],
) -> AuthenticatedClient:
    if client.role != "admin":
        raise HTTPException(403, "requiere rol admin")
    return client
