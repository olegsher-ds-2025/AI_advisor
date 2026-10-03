import os

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import execute_values

load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "sher_stock_advisor"),
        user=os.environ.get("POSTGRES_USER", "sher"),
        password=os.environ.get("POSTGRES_PASSWORD", "sher"),
    )


def build_upsert(table: str, columns: list[str], conflict_keys: list[str], on_conflict_do_nothing: bool) -> sql.Composed:
    update_cols = [c for c in columns if c not in conflict_keys]
    if on_conflict_do_nothing or not update_cols:
        action = sql.SQL("DO NOTHING")
    else:
        assignments = sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
        )
        action = sql.SQL("DO UPDATE SET ") + assignments
    return sql.SQL("INSERT INTO {table} ({cols}) VALUES %s ON CONFLICT ({keys}) {action}").format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
        keys=sql.SQL(", ").join(map(sql.Identifier, conflict_keys)),
        action=action,
    )


def upsert(conn, table: str, rows: list[dict], conflict_keys: list[str], on_conflict_do_nothing: bool = False):
    if not rows:
        return
    columns = list(rows[0].keys())
    query = build_upsert(table, columns, conflict_keys, on_conflict_do_nothing)
    values = [tuple(row[c] for c in columns) for row in rows]
    try:
        with conn.cursor() as cur:
            execute_values(cur, query, values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
