"""Private Bench Stock - electronic components database (Flask + SQLite, single user)."""
import datetime
import os
import secrets
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from . import db
from .security import check_csrf, csrf_token

__version__ = "1.0.1"
TAGLINE = "Your parts. Your datasheets. Your workbench."


def _load_secret_key(instance_path):
    key_file = Path(instance_path) / "secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text(encoding="utf-8").strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "benchstock.sqlite3"),
        # Folder holding sheets/, appnotes/ and img/parts/ (same layout as the old site)
        MEDIA_ROOT=os.path.join(app.instance_path, "media"),
        MAX_CONTENT_LENGTH=150 * 1024 * 1024,
        SESSION_COOKIE_NAME="benchstock",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 365,
        CURRENCIES=["USD", "EUR", "GBP", "SEK", "CAD", "AUD"],
    )
    if test_config is None:
        # Optional overrides: instance/config.py, then BENCHSTOCK_* environment variables
        app.config.from_pyfile("config.py", silent=True)
        app.config.from_prefixed_env("BENCHSTOCK")
    else:
        app.config.from_mapping(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_secret_key(app.instance_path)

    media = Path(app.config["MEDIA_ROOT"])
    app.config.setdefault("SHEETS_DIR", str(media / "sheets"))
    app.config.setdefault("APPNOTES_DIR", str(media / "appnotes"))
    app.config.setdefault("IMAGES_DIR", str(media / "img" / "parts"))

    db.init_app(app)
    if not os.path.exists(app.config["DATABASE"]):
        db.init_db(app.config["DATABASE"])

    from . import components, files, projects, settings
    for bp in (components.bp, projects.bp, settings.bp, files.bp):
        app.register_blueprint(bp)

    app.before_request(check_csrf)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.context_processor
    def inject_globals():
        stats = db.query("SELECT (SELECT COUNT(*) FROM component) AS components,"
                         " (SELECT COUNT(*) FROM project) AS projects", one=True)
        return {"stats": stats, "version": __version__, "year": datetime.date.today().year, "tagline": TAGLINE,
                "currency": settings.get_setting("currency")}

    from .formatting import register_filters
    register_filters(app)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.errorhandler(400)
    @app.errorhandler(404)
    def http_error(err):
        return render_template("error.html", error=err), err.code

    _register_legacy_redirects(app)

    from .cli import register_cli
    register_cli(app)
    return app


def _register_legacy_redirects(app):
    """Old PHP URLs (bookmarks, links in notes) redirect to the new pages."""
    simple = {
        "index.php": "components.index", "add.php": "components.add",
        "shoplist.php": "components.shoplist", "proj_list.php": "projects.list_projects",
        "my.php": "settings.settings", "maintenance.php": "files.upload",
        "reference_audit.php": "files.audit", "about.php": "components.about",
    }

    @app.route("/<page>.php")
    def legacy(page):
        a = request.args
        name = page + ".php"
        if name in simple:
            return redirect(url_for(simple[name]), 301)
        if name == "component.php" and a.get("view", "").isdigit():
            return redirect(url_for("components.view", cid=int(a["view"])), 301)
        if name == "component_edit.php" and a.get("edit", "").isdigit():
            return redirect(url_for("components.edit", cid=int(a["edit"])), 301)
        if name == "add_based.php" and a.get("based", "").isdigit():
            return redirect(url_for("components.add", based=int(a["based"])), 301)
        if name == "category.php":
            if a.get("subcat", "").isdigit():
                return redirect(url_for("components.subcategory", sid=int(a["subcat"])), 301)
            if a.get("cat", "").isdigit():
                return redirect(url_for("components.category", cat_id=int(a["cat"])), 301)
        if name == "search.php":
            return redirect(url_for("components.search", q=a.get("q", "")), 301)
        if name in ("proj_show.php", "proj_edit.php") and a.get("proj_id", "").isdigit():
            return redirect(url_for("projects.show", pid=int(a["proj_id"])), 301)
        return redirect(url_for("components.index"))
