from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from .db import execute
from .security import hash_password, login_required, verify_password
from .validation import validate_profile

bp = Blueprint("settings", __name__)


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    u = g.user
    form = request.form if request.method == "POST" else {
        "firstname": u["firstname"], "lastname": u["lastname"], "email": u["email"],
        "measurement": str(u["measurement"]), "currency": u["currency"]}
    if request.method == "POST":
        errors = validate_profile(form)
        currency = form.get("currency", "USD")
        if currency not in current_app.config["CURRENCIES"]:
            errors.append("Unknown currency.")
        newpass = form.get("newpass", "")
        if newpass and not verify_password(u["password_hash"], form.get("oldpass", ""))[0]:
            errors.append("Current password is wrong.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            execute("UPDATE user SET firstname = ?, lastname = ?, email = ?, measurement = ?, currency = ?"
                    " WHERE id = ?",
                    (form["firstname"].strip(), form["lastname"].strip(), form.get("email", "").strip(),
                     1 if form.get("measurement") == "1" else 0, currency, u["id"]))
            if newpass:
                execute("UPDATE user SET password_hash = ? WHERE id = ?", (hash_password(newpass), u["id"]))
            flash("Settings updated." + (" Password changed." if newpass else ""), "success")
            return redirect(url_for(".settings"))
    return render_template("settings.html", form=form)
