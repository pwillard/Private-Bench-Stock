"""Admin commands:  python manage.py <command>"""
import datetime
import os
import sqlite3
import sys

import click
from flask import current_app

from .db import init_db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db_cmd():
        """Create an empty database (existing tables are left alone)."""
        init_db(current_app.config["DATABASE"])
        click.echo(f"Database ready: {current_app.config['DATABASE']}")

    @app.cli.command("import-mysql")
    @click.argument("dump", type=click.Path(exists=True, dir_okay=False))
    @click.option("--force", is_flag=True, help="Replace an existing database.")
    @click.option("--owner", type=int, default=None,
                  help="Member id whose parts to import (default: the one with the most parts).")
    def import_mysql(dump, force, owner):
        """Convert the old ecdb.sql MySQL dump into the SQLite database."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        from mysql_to_sqlite import convert
        convert(dump, current_app.config["DATABASE"], force, owner)

    @app.cli.command("backup")
    @click.argument("dest_dir", type=click.Path(file_okay=False), default=None, required=False)
    @click.option("--keep", default=30, show_default=True, help="Number of backups to keep.")
    def backup(dest_dir, keep):
        """Safe online copy of the database to DEST_DIR (default instance/backups)."""
        dest_dir = dest_dir or os.path.join(current_app.instance_path, "backups")
        os.makedirs(dest_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = os.path.join(dest_dir, f"ecdb-{stamp}.sqlite3")
        src = sqlite3.connect(current_app.config["DATABASE"])
        dst = sqlite3.connect(target)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        old = sorted(f for f in os.listdir(dest_dir) if f.startswith("ecdb-") and f.endswith(".sqlite3"))
        for f in old[:-keep] if keep > 0 else []:
            os.remove(os.path.join(dest_dir, f))
        click.echo(f"Backup written: {target}")
