from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from .db import execute, query
from .security import (clear_login_failures, hash_password, login_locked,
                       note_login_failure, verify_password)
from .validation import validate_profile

bp = Blueprint("auth", __name__)


def _safe_next(target):
    # Only allow local redirects after login
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("components.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None and request.method == "GET":
        return redirect(url_for("components.index"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        login_name = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        if login_locked(ip):
            flash("Too many failed logins. Wait a few minutes and try again.", "error")
        elif not login_name or not password:
            flash("Enter your username and password.", "error")
        else:
            user = query("SELECT * FROM user WHERE login = ?", (login_name,), one=True)
            ok, rehash = verify_password(user["password_hash"], password) if user else (False, False)
            if ok:
                clear_login_failures(ip)
                if rehash:
                    execute("UPDATE user SET password_hash = ? WHERE id = ?",
                            (hash_password(password), user["id"]))
                execute("INSERT INTO login_log (user_id) VALUES (?)", (user["id"],))
                session.clear()
                session.permanent = True
                session["user_id"] = user["id"]
                return redirect(_safe_next(request.args.get("next")))
            note_login_failure(ip)
            flash("Login failed, please try again.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    was_logged_in = g.user is not None
    session.clear()
    if was_logged_in:
        flash("You have signed out.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["ALLOW_REGISTRATION"]:
        abort(404)
    form = request.form
    if request.method == "POST":
        errors = validate_profile(form, require_password=True)
        login_name = form.get("login", "").strip()
        if len(login_name) < 2:
            errors.append("Username needs at least 2 characters.")
        elif query("SELECT 1 FROM user WHERE login = ?", (login_name,), one=True):
            errors.append("Username already in use.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            execute("INSERT INTO user (login, firstname, lastname, email, password_hash) VALUES (?,?,?,?,?)",
                    (login_name, form["firstname"].strip(), form["lastname"].strip(),
                     form["email"].strip(), hash_password(form["newpass"])))
            flash("Account created. Please log in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/about")
def about():
    return render_template("about.html")
