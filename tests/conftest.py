import os
import re
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ecdb import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
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
    db.execute("INSERT INTO component (id, name, subcategory_id, package, quantity, price, datasheet, image, comment)"
               " VALUES (10, 'LM317', 501, 'TO-220', 5, 0.5, 'LM317.pdf', 'to220.jpg', 'adjustable regulator')")
    db.execute("INSERT INTO component (id, name, subcategory_id, package, quantity, datasheet)"
               " VALUES (11, '2N2222A', 1204, 'TO-18', 16, 'lm317.PDF')")
    db.commit()
    db.close()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, url="/"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def post(client, url, data=None, **kw):
    data = dict(data or {})
    data["_csrf"] = token(client)
    return client.post(url, data=data, **kw)
