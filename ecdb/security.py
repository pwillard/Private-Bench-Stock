"""Passwords, login requirement and CSRF protection."""
import hashlib
import hmac
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

LEGACY_PREFIX = "md5$"


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored, password):
    """Returns (ok, needs_rehash). Accepts legacy unsalted MD5 hashes imported
    from the PHP site; those are replaced by a strong hash on first login."""
    if stored.startswith(LEGACY_PREFIX):
        legacy = hashlib.md5(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored[len(LEGACY_PREFIX):]), True
    return check_password_hash(stored, password), False


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


# --- CSRF -------------------------------------------------------------------

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = session["_csrf"] = secrets.token_urlsafe(32)
    return token


def check_csrf():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Form expired or invalid security token. Go back, reload the page and try again.")


# --- simple login throttling (per client IP, in memory) ----------------------

_failures = {}
MAX_FAILURES = 5
LOCK_SECONDS = 300


def login_locked(ip):
    count, since = _failures.get(ip, (0, 0))
    if count >= MAX_FAILURES and time.time() - since < LOCK_SECONDS:
        return True
    if time.time() - since >= LOCK_SECONDS:
        _failures.pop(ip, None)
    return False


def note_login_failure(ip):
    count, since = _failures.get(ip, (0, time.time()))
    _failures[ip] = (count + 1, since)


def clear_login_failures(ip):
    _failures.pop(ip, None)
