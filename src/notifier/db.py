from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from notifier.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Pool compartido. `with pool.connection()` abre una transacción y la confirma al salir."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
