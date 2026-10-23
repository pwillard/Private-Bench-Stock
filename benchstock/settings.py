from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .db import execute, query

bp = Blueprint("settings", __name__)

DEFAULTS = {"currency": "USD"}


def get_setting(key):
    row = query("SELECT value FROM setting WHERE key = ?", (key,), one=True)
    return row["value"] if row else DEFAULTS.get(key, "")


def set_setting(key, value):
    execute("INSERT INTO setting (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        currency = request.form.get("currency", "USD")
        if currency not in current_app.config["CURRENCIES"]:
            flash("Unknown currency.", "error")
        else:
            set_setting("currency", currency)
            flash("Settings updated.", "success")
        return redirect(url_for(".settings"))
    return render_template("settings.html")
