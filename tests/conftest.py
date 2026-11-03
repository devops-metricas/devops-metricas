import os

import pytest

# Las pruebas de integración necesitan PostgreSQL: NOTIFIER_DATABASE_URL=postgresql://...
HAS_DB = "NOTIFIER_DATABASE_URL" in os.environ


def pytest_collection_modifyitems(config, items):
    if HAS_DB:
        return
    skip = pytest.mark.skip(reason="sin NOTIFIER_DATABASE_URL")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture()
def db():
    """Base limpia con el esquema aplicado, dos clientes y un admin."""
    from notifier import migrate
    from notifier.cli import create_client
    from notifier.db import get_pool

    migrate.run()
    with get_pool().connection() as conn:
        conn.execute(
            "TRUNCATE internal_messages, delivery_attempts, notification_events, "
            "notifications, clients CASCADE"
        )
    return {
        "app_a": create_client("app-a", admin=False),
        "app_b": create_client("app-b", admin=False),
        "admin": create_client("ops", admin=True),
    }


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from notifier.api.app import app

    with TestClient(app) as c:
        yield c


def auth(key: str) -> dict:
    return {"X-API-Key": key}
