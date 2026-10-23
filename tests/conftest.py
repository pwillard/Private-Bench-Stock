import hashlib
import io
import os
import re
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ecdb import create_app  # noqa: E402
from ecdb.security import hash_password  # noqa: E402


@pytest.fixture
def app(tmp_path):
    from ecdb import security
    security._failures.clear()
    media = tmp_path / "media"
    for sub in ("sheets", "appnotes", "img/parts"):
        (media / sub).mkdir(parents=True)
    (media / "sheets" / "LM317.pdf").write_bytes(b"%PDF-1.4 test")
    (media / "sheets" / "Unused.pdf").write_bytes(b"%PDF-1.4 test")
    (media / "img" / "parts" / "to220.jpg").write_bytes(b"\xff\xd8\xff")
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": str(tmp_path / "t.sqlite3"),
                      "MEDIA_ROOT": str(media)})
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("INSERT INTO category (id, name) VALUES (5, 'IC'), (12, 'Transistor')")
    db.execute("INSERT INTO subcategory (id, category_id, name) VALUES (501, 5, 'Regulator'),"
               " (1204, 12, 'NPN'), (1299, 12, 'Misc')")
    db.execute("INSERT INTO user (id, login, firstname, lastname, password_hash) VALUES"
               " (1, 'pete', 'Pete', 'Willard', ?)", ("md5$" + hashlib.md5(b"oldsecret").hexdigest(),))
    db.execute("INSERT INTO user (id, login, firstname, lastname, password_hash) VALUES"
               " (2, 'other', 'Other', 'User', ?)", (hash_password("otherpass1"),))
    db.execute("INSERT INTO component (id, owner_id, name, subcategory_id, package, quantity, price, datasheet, image, comment)"
               " VALUES (10, 1, 'LM317', 501, 'TO-220', 5, 0.5, 'LM317.pdf', 'to220.jpg', 'adjustable regulator')")
    db.execute("INSERT INTO component (id, owner_id, name, subcategory_id, package, quantity, datasheet)"
               " VALUES (11, 1, '2N2222A', 1204, 'TO-18', 16, 'lm317.PDF')")
    db.execute("INSERT INTO component (id, owner_id, name, subcategory_id, quantity)"
               " VALUES (20, 2, 'SECRET-PART', 1204, 1)")
    db.commit()
    db.close()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def login(client, user="pete", pw="oldsecret"):
    t = token(client)
    return client.post("/login", data={"login": user, "password": pw, "_csrf": t})


@pytest.fixture
def auth(client):
    r = login(client)
    assert r.status_code == 302
    return client


def post(client, url, data=None, **kw):
    data = dict(data or {})
    data["_csrf"] = token(client, "/")
    return client.post(url, data=data, **kw)
