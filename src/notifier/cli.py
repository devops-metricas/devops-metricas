"""Administración mínima: registrar aplicaciones cliente.

python -m notifier.cli create-client app-pedidos
python -m notifier.cli create-client operaciones --admin
"""

import argparse
import sys

from notifier.db import close_pool, get_pool
from notifier.security import generate_key, hash_key


def create_client(name: str, admin: bool) -> str:
    api_key = generate_key()
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO clients (name, api_key_hash, role) VALUES (%s, %s, %s)",
            (name, hash_key(api_key), "admin" if admin else "client"),
        )
    return api_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notifier.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    cc = sub.add_parser("create-client", help="registra una aplicación y muestra su API key")
    cc.add_argument("name")
    cc.add_argument("--admin", action="store_true", help="rol admin (reproceso y estadísticas)")
    args = parser.parse_args(argv)

    key = create_client(args.name, args.admin)
    close_pool()
    print(f"cliente: {args.name}\nAPI key (se muestra una sola vez): {key}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
