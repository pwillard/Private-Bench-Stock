import io
import os
import sqlite3

import pytest

from conftest import post


def db(app):
    return sqlite3.connect(app.config["DATABASE"])


# --- access / security ------------------------------------------------------

def test_no_login_needed(client):
    r = client.get("/")
    assert r.status_code == 200 and b"LM317" in r.data
    assert client.get("/sheets/LM317.pdf").data.startswith(b"%PDF")
    assert client.get("/login").status_code == 404


def test_csrf_required(client):
    assert client.post("/component/10/delete").status_code == 400
    assert client.post("/component/10/delete", data={"_csrf": "forged"}).status_code == 400
    assert client.get("/component/10").status_code == 200


def test_every_page_renders(client):
    for url in ["/", "/add", "/add?based=10", "/component/10", "/component/10/edit", "/category/5",
                "/subcategory/501", "/search?q=lm", "/shoplist", "/projects/", "/reference",
                "/reference/audit", "/settings", "/about"]:
        assert client.get(url).status_code == 200, url


def test_output_is_escaped(client, app):
    c = db(app)
    c.execute("UPDATE component SET name = '<script>x</script>' WHERE id = 11")
    c.commit()
    html = client.get("/").get_data(as_text=True)
    assert "&lt;script&gt;" in html and "<script>x" not in html


# --- listing / search / sort --------------------------------------------------

@pytest.mark.parametrize("by", ["name", "category", "pins", "price", "quantity", "smd",
                                "name; DROP TABLE component", "x)--"])
def test_sorting_is_whitelisted(client, by):
    for order in ("asc", "desc", "bogus"):
        assert client.get("/", query_string={"by": by, "order": order}).status_code == 200
    assert b"LM317" in client.get("/").data


def test_category_and_subcategory(client):
    r = client.get("/category/12")
    assert b"2N2222A" in r.data and b"LM317</a>" not in r.data
    assert b"2N2222A" in client.get("/subcategory/1204").data
    assert client.get("/category/999").status_code == 404


def test_search_multiword_and_wildcards(client):
    assert b"LM317" in client.get("/search?q=adjustable+regulator").data
    assert b"LM317" in client.get("/search?q=to-220").data
    assert b"LM317</a>" not in client.get("/search?q=%25").data      # literal %, not a wildcard
    assert b"forgot to enter" in client.get("/search?q=").data


# --- add / edit / delete -------------------------------------------------------

def test_add_edit_delete_cycle(client, app):
    r = post(client, "/add", {"name": "NE555", "subcategory_id": "501", "quantity": "3,5", "price": "0.25",
                              "pins": "8", "smd": "0", "scrap": "1", "comment": "timer"})
    assert r.status_code == 302
    cid = int(r.headers["Location"].rsplit("/", 1)[1])
    page = client.get(f"/component/{cid}").get_data(as_text=True)
    assert "NE555" in page and "3.5" in page and "0.25" in page

    r = post(client, f"/component/{cid}/edit", {"name": "NE555P", "subcategory_id": "501", "quantity": "4",
                                                "pins": "8", "smd": "1", "scrap": "0"})
    assert r.status_code == 302
    row = db(app).execute("SELECT name, quantity, smd, scrap FROM component WHERE id=?", (cid,)).fetchone()
    assert row == ("NE555P", 4, 1, 0)

    assert post(client, f"/component/{cid}/delete").status_code == 302
    assert client.get(f"/component/{cid}").status_code == 404


@pytest.mark.parametrize("data,msg", [
    ({"name": "", "subcategory_id": "501"}, b"specify a name"),
    ({"name": "X", "subcategory_id": ""}, b"choose a category"),
    ({"name": "X", "subcategory_id": "501", "quantity": "lots"}, b"Quantity must be a number"),
    ({"name": "X", "subcategory_id": "501", "pins": "8.5"}, b"whole number"),
    ({"name": "X", "subcategory_id": "501", "comment": "a" * 2600}, b"2500"),
    ({"name": "X", "subcategory_id": "501", "project_quantity": "2"}, b"choose a project"),
])
def test_add_validation(client, data, msg):
    r = post(client, "/add", data)
    assert r.status_code == 200 and msg in r.data


def test_add_based_on_prefills(client):
    html = client.get("/add?based=10").get_data(as_text=True)
    assert 'value="LM317"' in html and "New component based on" in html
    assert client.get("/add?based=999").status_code == 404


def test_quantity_adjust_never_negative(client, app):
    for _ in range(7):
        post(client, "/component/10/adjust", {"field": "quantity", "delta": "-1"})
    assert db(app).execute("SELECT quantity FROM component WHERE id=10").fetchone()[0] == 0
    assert post(client, "/component/10/adjust", {"field": "name", "delta": "1"}).status_code == 400


def test_shoplist_total(client):
    post(client, "/component/10/adjust", {"field": "order_quantity", "delta": "1"})
    post(client, "/component/10/adjust", {"field": "order_quantity", "delta": "1"})
    html = client.get("/shoplist").get_data(as_text=True)
    assert "LM317" in html and "1.00 USD" in html          # 2 x 0.50


def test_export_csv(client):
    r = client.get("/export.csv")
    assert r.mimetype == "text/csv" and b"LM317" in r.data and b"2N2222A" in r.data


def test_settings_currency(client):
    r = post(client, "/settings", {"currency": "EUR"}, follow_redirects=True)
    assert b"Settings updated" in r.data
    assert "0.50 EUR" in client.get("/component/10").get_data(as_text=True)
    assert b"Unknown currency" in post(client, "/settings", {"currency": "XXX"}, follow_redirects=True).data


# --- projects -----------------------------------------------------------------

def test_project_bom_flow(client, app):
    r = post(client, "/projects/", {"name": "Bench PSU"})
    pid = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    base = {"name": "LM317", "subcategory_id": "501", "quantity": "5", "price": "0.5"}
    r = post(client, "/component/10/edit", dict(base, project_id=str(pid), project_quantity="8"))
    assert r.status_code == 302
    html = client.get(f"/projects/{pid}").get_data(as_text=True)
    assert "LM317" in html and "short" in html and "4.00" in html     # 8 x 0.50
    post(client, f"/projects/{pid}/order-shortfall")
    assert db(app).execute("SELECT order_quantity FROM component WHERE id=10").fetchone()[0] == 3
    post(client, "/component/10/edit", dict(base, **{f"projqty_{pid}": "0"}))   # 0 removes link
    assert "LM317" not in client.get(f"/projects/{pid}").get_data(as_text=True).split("<tbody>")[-1]
    assert post(client, f"/projects/{pid}/delete").status_code == 302
    assert client.get(f"/projects/{pid}").status_code == 404


# --- files ----------------------------------------------------------------------

def test_media_traversal_blocked(client):
    assert client.get("/sheets/../t.sqlite3").status_code == 404
    assert client.get("/sheets/..%2Ft.sqlite3").status_code == 404


def test_upload_rules(client, app):
    def up(name, data=b"%PDF", appnote=False):
        d = {"file": (io.BytesIO(data), name)}
        if appnote:
            d["appnote"] = "1"
        return post(client, "/reference", d, content_type="multipart/form-data", follow_redirects=True).data

    assert b"NE555.pdf uploaded to sheets/" in up("NE555.pdf")
    assert b"uploaded to appnotes/" in up("AN-1.pdf", appnote=True)
    assert b"uploaded to img/parts/" in up("Part.PNG")
    assert b"already exists" in up("NE555.pdf")
    assert b"different case" in up("ne555.pdf")
    assert b"only PDF" in up("evil.php")
    up("../escape.pdf")                                 # folder part stripped
    assert not os.path.exists(os.path.join(app.config["MEDIA_ROOT"], "escape.pdf"))
    assert b"invalid file name" in up(".hidden.pdf")


def test_suggest(client):
    assert client.get("/api/suggest/datasheet?term=lm3").get_json() == ["LM317.pdf"]
    assert client.get("/api/suggest/package?term=to-2").get_json() == ["TO-220"]
    assert client.get("/api/suggest/comment?term=a").status_code == 404


def test_audit(client):
    html = client.get("/reference/audit").get_data(as_text=True)
    assert "CASE_MISMATCH" in html and "lm317.PDF" in html
    assert "Unused.pdf" not in html
    assert "Unused.pdf" in client.get("/reference/audit?show=all").get_data(as_text=True)
    assert b"CASE_MISMATCH" in client.get("/reference/audit?format=csv").data


# --- legacy URLs --------------------------------------------------------------------

@pytest.mark.parametrize("old,new", [
    ("/index.php", "/"), ("/component.php?view=10", "/component/10"),
    ("/component_edit.php?edit=10", "/component/10/edit"), ("/category.php?cat=12", "/category/12"),
    ("/category.php?subcat=1204", "/subcategory/1204"), ("/proj_show.php?proj_id=3", "/projects/3"),
    ("/maintenance.php", "/reference"), ("/search.php?q=lm", "/search?q=lm"), ("/login.php", "/"),
])
def test_legacy_redirects(client, old, new):
    r = client.get(old)
    assert r.status_code in (301, 302) and r.headers["Location"] == new
