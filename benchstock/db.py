"""SQLite access. Every query in the app goes through these helpers with
parameter binding (`?`), never string formatting of user input."""
import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def init_db(path):
    """Create an empty database from schema.sql (no-op for existing tables)."""
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    conn.commit()
    conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
