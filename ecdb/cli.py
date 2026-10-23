"""Admin commands:  flask --app ecdb <command>   (or: python manage.py <command>)"""
import getpass
import os
import sqlite3
import sys

import click
from flask import current_app

from .db import init_db
from .security import hash_password


def _conn():
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ask_password():
    while True:
        p1 = getpass.getpass("New password: ")
        if len(p1) < 8:
            click.echo("Use at least 8 characters.")
            continue
        if p1 != getpass.getpass("Repeat password: "):
            click.echo("Passwords do not match.")
            continue
        return p1


def register_cli(app):
    @app.cli.command("init-db")
    def init_db_cmd():
        """Create an empty database (existing tables are left alone)."""
        init_db(current_app.config["DATABASE"])
        click.echo(f"Database ready: {current_app.config['DATABASE']}")

    @app.cli.command("import-mysql")
    @click.argument("dump", type=click.Path(exists=True, dir_okay=False))
    @click.option("--force", is_flag=True, help="Replace an existing database.")
    def import_mysql(dump, force):
        """Convert the old ecdb.sql MySQL dump into the SQLite database."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        from mysql_to_sqlite import convert
        convert(dump, current_app.config["DATABASE"], force)

    @app.cli.command("backup")
    @click.argument("dest_dir", type=click.Path(file_okay=False), default=None, required=False)
    @click.option("--keep", default=30, show_default=True, help="Number of backups to keep.")
    def backup(dest_dir, keep):
        """Safe online copy of the database to DEST_DIR (default instance/backups)."""
        import datetime
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

    @app.cli.command("user-list")
    def user_list():
        """List user accounts."""
        with _conn() as c:
            for u in c.execute("SELECT u.id, u.login, u.firstname, u.lastname, u.password_hash,"
                               " (SELECT COUNT(*) FROM component WHERE owner_id = u.id) AS n,"
                               " (SELECT MAX(logged_at) FROM login_log WHERE user_id = u.id) AS last"
                               " FROM user u ORDER BY u.id"):
                legacy = "  [old MD5 password - log in once or reset]" if u["password_hash"].startswith("md5$") else ""
                click.echo(f"{u['id']:>5}  {u['login']:<16} {u['firstname']} {u['lastname']}"
                           f"  components={u['n']}  last login={u['last'] or '-'}{legacy}")

    @app.cli.command("user-add")
    @click.argument("login")
    @click.option("--first", default="", help="First name")
    @click.option("--last", default="", help="Last name")
    @click.option("--email", default="")
    def user_add(login, first, last, email):
        """Create a user account (prompts for the password)."""
        pw = _ask_password()
        with _conn() as c:
            try:
                c.execute("INSERT INTO user (login, firstname, lastname, email, password_hash) VALUES (?,?,?,?,?)",
                          (login, first, last, email, hash_password(pw)))
            except sqlite3.IntegrityError:
                raise click.ClickException(f"User {login} already exists.")
        click.echo(f"User {login} created.")

    @app.cli.command("user-passwd")
    @click.argument("login")
    def user_passwd(login):
        """Set a new password for a user."""
        with _conn() as c:
            if not c.execute("SELECT 1 FROM user WHERE login = ?", (login,)).fetchone():
                raise click.ClickException(f"No user {login}.")
            pw = _ask_password()
            c.execute("UPDATE user SET password_hash = ? WHERE login = ?", (hash_password(pw), login))
        click.echo("Password updated.")

    @app.cli.command("user-delete")
    @click.argument("login")
    @click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
    def user_delete(login, yes):
        """Delete a user AND all of their components and projects."""
        with _conn() as c:
            u = c.execute("SELECT id, (SELECT COUNT(*) FROM component WHERE owner_id = user.id) AS n"
                          " FROM user WHERE login = ?", (login,)).fetchone()
            if not u:
                raise click.ClickException(f"No user {login}.")
            if not yes:
                click.confirm(f"Delete {login} and their {u['n']} components?", abort=True)
            c.execute("DELETE FROM user WHERE id = ?", (u["id"],))
        click.echo(f"User {login} deleted.")
