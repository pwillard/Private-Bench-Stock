import io
import os
import sqlite3

import pytest

from conftest import login, post, token


# --- auth / security ------------------------------------------------------

def test_requires_login(client):
    r = client.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert client.get("/sheets/LM317.pdf").status_code == 302


def test_legacy_md5_login_upgrades_hash(app, client):
    assert login(client).status_code == 302
    h = sqlite3.connect(app.config["DATABASE"]).execute("SELECT password_hash FROM user WHERE id=1").fetchone()[0]
    assert not h.startswith("md5$")
    client.post("/logout", data={"_csrf": token(client, "/")})
    assert login(client).status_code == 302          # still works with the new hash


def test_bad_password_and_lockout(client):
    for _ in range(5):
        r = login(client, pw="wrong")
        assert r.status_code == 200 and b"Login failed" in r.data
    r = login(client)                                  # correct password but locked
    assert b"Too many failed logins" in r.data


def test_csrf_required(auth):
    r = auth.post("/component/10/delete")
    assert r.status_code == 400
    assert auth.get("/component/10").status_code == 200


def test_cannot_touch_other_users_parts(auth):
    assert auth.get("/component/20").status_code == 404
    assert auth.get("/component/20/edit").status_code == 404
    assert post(auth, "/component/20/delete").status_code == 404
    assert post(auth, "/component/20/adjust", {"field": "quantity", "delta": "1"}).status_code == 404
    assert b"SECRET-PART" not in auth.get("/search?q=SECRET").data


def test_registration_disabled_by_default(client):
    assert client.get("/register").status_code == 404


def test_open_redirect_blocked(client):
    t = token(client)
    r = client.post("/login?next=//evil.example", data={"login": "pete", "password": "oldsecret", "_csrf": t})
    assert r.headers["Location"] == "/"


# --- listing / search / sort --------------------------------------------------

def test_index_lists_parts_and_escapes(auth, app):
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("UPDATE component SET name = '<script>x</script>' WHERE id = 11")
    db.commit()
    html = auth.get("/").get_data(as_text=True)
    assert "LM317" in html and "&lt;script&gt;" in html and "<script>x" not in html


@pytest.mark.parametrize("by", ["name", "category", "pins", "price", "quantity", "smd",
                                "name; DROP TABLE component", "x)--"])
def test_sorting_is_whitelisted(auth, by):
    for order in ("asc", "desc", "bogus"):
        assert auth.get("/", query_string={"by": by, "order": order}).status_code == 200
    assert b"LM317" in auth.get("/").data


def test_category_and_subcategory(auth):
    r = auth.get("/category/12")
    assert b"2N2222A" in r.data and b"LM317</a>" not in r.data
    assert b"2N2222A" in auth.get("/subcategory/1204").data
    assert auth.get("/category/999").status_code == 404


def test_search_multiword_and_wildcards(auth):
    assert b"LM317" in auth.get("/search?q=adjustable+regulator").data
    assert b"LM317" in auth.get("/search?q=to-220").data
    r = auth.get("/search?q=%25")                      # literal %, must not match everything
    assert b"LM317</a>" not in r.data
    assert b"forgot to enter" in auth.get("/search?q=").data


# --- add / edit / delete -------------------------------------------------------

def test_add_edit_delete_cycle(auth, app):
    r = post(auth, "/add", {"name": "NE555", "subcategory_id": "501", "quantity": "3,5", "price": "0.25",
                            "pins": "8", "smd": "0", "scrap": "1", "comment": "timer"})
    assert r.status_code == 302
    cid = int(r.headers["Location"].rsplit("/", 1)[1])
    page = auth.get(f"/component/{cid}").get_data(as_text=True)
    assert "NE555" in page and "3.5" in page and "0.25" in page

    r = post(auth, f"/component/{cid}/edit", {"name": "NE555P", "subcategory_id": "501", "quantity": "4",
                                              "pins": "8", "smd": "1", "scrap": "0"})
    assert r.status_code == 302
    row = sqlite3.connect(app.config["DATABASE"]).execute(
        "SELECT name, quantity, smd, scrap FROM component WHERE id=?", (cid,)).fetchone()
    assert row == ("NE555P", 4, 1, 0)

    assert post(auth, f"/component/{cid}/delete").status_code == 302
    assert auth.get(f"/component/{cid}").status_code == 404


@pytest.mark.parametrize("data,msg", [
    ({"name": "", "subcategory_id": "501"}, b"specify a name"),
    ({"name": "X", "subcategory_id": ""}, b"choose a category"),
    ({"name": "X", "subcategory_id": "501", "quantity": "lots"}, b"Quantity must be a number"),
    ({"name": "X", "subcategory_id": "501", "pins": "8.5"}, b"whole number"),
    ({"name": "X", "subcategory_id": "501", "comment": "a" * 2600}, b"2500"),
    ({"name": "X", "subcategory_id": "501", "project_quantity": "2"}, b"choose a project"),
])
def test_add_validation(auth, data, msg):
    r = post(auth, "/add", data)
    assert r.status_code == 200 and msg in r.data


def test_every_page_renders(auth):
    for url in ["/", "/add", "/add?based=10", "/component/10", "/component/10/edit", "/category/5",
                "/subcategory/501", "/search?q=lm", "/shoplist", "/projects/", "/reference",
                "/reference/audit", "/settings", "/about"]:
        assert auth.get(url).status_code == 200, url


def test_add_based_on_prefills(auth):
    html = auth.get("/add?based=10").get_data(as_text=True)
    assert 'value="LM317"' in html and "New component based on" in html
    assert auth.get("/add?based=20").status_code == 404


def test_quantity_adjust_never_negative(auth, app):
    for _ in range(7):
        post(auth, "/component/10/adjust", {"field": "quantity", "delta": "-1"})
    q = sqlite3.connect(app.config["DATABASE"]).execute("SELECT quantity FROM component WHERE id=10").fetchone()[0]
    assert q == 0
    assert post(auth, "/component/10/adjust", {"field": "owner_id", "delta": "1"}).status_code == 400


def test_shoplist_total(auth):
    post(auth, "/component/10/adjust", {"field": "order_quantity", "delta": "1"})
    post(auth, "/component/10/adjust", {"field": "order_quantity", "delta": "1"})
    html = auth.get("/shoplist").get_data(as_text=True)
    assert "LM317" in html and "1.00" in html          # 2 x 0.50


def test_export_csv(auth):
    r = auth.get("/export.csv")
    assert r.mimetype == "text/csv" and b"LM317" in r.data and b"SECRET" not in r.data


# --- projects -----------------------------------------------------------------

def test_project_bom_flow(auth, app):
    r = post(auth, "/projects/", {"name": "Bench PSU"})
    pid = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    r = post(auth, "/component/10/edit", {"name": "LM317", "subcategory_id": "501", "quantity": "5", "price": "0.5",
                                          "project_id": str(pid), "project_quantity": "8"})
    assert r.status_code == 302
    html = auth.get(f"/projects/{pid}").get_data(as_text=True)
    assert "LM317" in html and "short" in html and "4.00" in html     # 8 x 0.50
    post(auth, f"/projects/{pid}/order-shortfall")
    oq = sqlite3.connect(app.config["DATABASE"]).execute("SELECT order_quantity FROM component WHERE id=10").fetchone()[0]
    assert oq == 3
    # edit project quantity to 0 removes the link
    post(auth, "/component/10/edit", {"name": "LM317", "subcategory_id": "501", "quantity": "5", "price": "0.5",
                                      f"projqty_{pid}": "0"})
    assert "LM317" not in auth.get(f"/projects/{pid}").get_data(as_text=True).split("<tbody>")[-1]
    assert post(auth, f"/projects/{pid}/delete").status_code == 302
    assert auth.get(f"/projects/{pid}").status_code == 404


# --- files ----------------------------------------------------------------------

def test_media_served_and_traversal_blocked(auth):
    assert auth.get("/sheets/LM317.pdf").data.startswith(b"%PDF")
    assert auth.get("/sheets/../t.sqlite3").status_code == 404
    assert auth.get("/sheets/..%2Ft.sqlite3").status_code == 404


def test_upload_rules(auth, app):
    def up(name, data=b"%PDF", appnote=False):
        d = {"file": (io.BytesIO(data), name)}
        if appnote:
            d["appnote"] = "1"
        return post(auth, "/reference", d, content_type="multipart/form-data", follow_redirects=True).data

    assert b"NE555.pdf uploaded to sheets/" in up("NE555.pdf")
    assert b"uploaded to appnotes/" in up("AN-1.pdf", appnote=True)
    assert b"uploaded to img/parts/" in up("Part.PNG")
    assert b"already exists" in up("NE555.pdf")
    assert b"different case" in up("ne555.pdf")
    assert b"only PDF" in up("evil.php")
    up("../escape.pdf")                                 # path stripped -> sheets/escape.pdf
    assert not os.path.exists(os.path.join(app.config["MEDIA_ROOT"], "escape.pdf"))
    assert b"invalid file name" in up(".hidden.pdf")


def test_suggest(auth):
    assert auth.get("/api/suggest/datasheet?term=lm3").get_json() == ["LM317.pdf"]
    assert auth.get("/api/suggest/package?term=to-2").get_json() == ["TO-220"]
    assert auth.get("/api/suggest/name?term=SECRET").get_json() == []
    assert auth.get("/api/suggest/password_hash?term=a").status_code == 404


def test_audit(auth):
    html = auth.get("/reference/audit").get_data(as_text=True)
    assert "CASE_MISMATCH" in html and "lm317.PDF" in html
    assert "Unused.pdf" not in html
    assert "Unused.pdf" in auth.get("/reference/audit?show=all").get_data(as_text=True)
    assert b"CASE_MISMATCH" in auth.get("/reference/audit?format=csv").data


# --- settings ---------------------------------------------------------------------

def test_settings_password_change(auth, client):
    r = post(auth, "/settings", {"firstname": "Pete", "lastname": "Willard", "email": "p@example.com",
                                 "measurement": "1", "currency": "EUR",
                                 "oldpass": "wrong", "newpass": "newpassword1", "confirmpass": "newpassword1"})
    assert b"Current password is wrong" in r.data
    r = post(auth, "/settings", {"firstname": "Pete", "lastname": "Willard", "email": "p@example.com",
                                 "measurement": "1", "currency": "EUR",
                                 "oldpass": "oldsecret", "newpass": "newpassword1", "confirmpass": "newpassword1"},
             follow_redirects=True)
    assert b"Password changed" in r.data and b"EUR" in r.data
    post(client, "/logout")
    assert login(client, pw="newpassword1").status_code == 302


# --- legacy URLs --------------------------------------------------------------------

@pytest.mark.parametrize("old,new", [
    ("/index.php", "/"), ("/component.php?view=10", "/component/10"),
    ("/component_edit.php?edit=10", "/component/10/edit"), ("/category.php?cat=12", "/category/12"),
    ("/category.php?subcat=1204", "/subcategory/1204"), ("/proj_show.php?proj_id=3", "/projects/3"),
    ("/maintenance.php", "/reference"), ("/search.php?q=lm", "/search?q=lm"),
])
def test_legacy_redirects(auth, old, new):
    r = auth.get(old)
    assert r.status_code == 301 and r.headers["Location"] == new
