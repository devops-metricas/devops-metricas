"""Aplica las migraciones SQL pendientes. Seguro si corren varias réplicas a la vez."""

from pathlib import Path

import psycopg

from notifier.config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
ADVISORY_LOCK_ID = 7_340_001


def run() -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.stem in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text())
                    conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,)
                    )
                applied_now.append(path.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
    return applied_now


if __name__ == "__main__":
    applied = run()
    print(f"migraciones aplicadas: {applied or 'ninguna (al día)'}")
