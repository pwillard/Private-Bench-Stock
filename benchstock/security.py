"""CSRF protection.

There are no logins (single-user tool on a home network), but every form still
carries a token: otherwise any web page you visit could make your browser post
"delete component" etc. to the BenchStock server behind your back."""
import hmac
import secrets

from flask import abort, request, session


def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = session["_csrf"] = secrets.token_urlsafe(32)
        session.permanent = True
    return token


def check_csrf():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Form expired or invalid security token. Go back, reload the page and try again.")
