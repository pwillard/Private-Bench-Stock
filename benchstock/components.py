import csv
import io

from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template,
                   request, url_for)

from .db import execute, get_db, query
from .files import list_reference_files
from .validation import parse_component

bp = Blueprint("components", __name__)

BASE_SELECT = """
SELECT c.*, s.name AS subcategory_name, cat.id AS category_id, cat.name AS category_name
FROM component c
JOIN subcategory s ON s.id = c.subcategory_id
JOIN category cat ON cat.id = s.category_id
"""

SORTS = {
    "name": ["c.name COLLATE NOCASE"],
    "category": ["cat.name COLLATE NOCASE", "s.name COLLATE NOCASE"],
    "manufacturer": ["c.manufacturer COLLATE NOCASE"],
    "package": ["c.package COLLATE NOCASE"],
    "location": ["c.location COLLATE NOCASE"],
    "pins": ["c.pins"],
    "smd": ["c.smd"],
    "price": ["c.price"],
    "quantity": ["c.quantity"],
    "order_quantity": ["c.order_quantity"],
}


def order_clause(default="name"):
    by = request.args.get("by", default)
    cols = SORTS.get(by, SORTS[default])
    direction = "DESC" if request.args.get("order") == "desc" else "ASC"
    parts = [f"{c} {direction}" for c in cols]
    if by != "name":
        parts.append("c.name COLLATE NOCASE ASC")
    return " ORDER BY " + ", ".join(parts)


def category_nav():
    return query(
        "SELECT cat.id, cat.name, COUNT(c.id) AS n FROM category cat"
        " LEFT JOIN subcategory s ON s.category_id = cat.id"
        " LEFT JOIN component c ON c.subcategory_id = s.id"
        " GROUP BY cat.id ORDER BY cat.name COLLATE NOCASE")


def subcategory_nav(cat_id):
    return query(
        "SELECT s.id, s.name, COUNT(c.id) AS n FROM subcategory s"
        " LEFT JOIN component c ON c.subcategory_id = s.id"
        " WHERE s.category_id = ? GROUP BY s.id ORDER BY s.name COLLATE NOCASE", (cat_id,))


def get_component(cid):
    row = query(BASE_SELECT + " WHERE c.id = ?", (cid,), one=True)
    if row is None:
        abort(404)
    return row


# --- listings ---------------------------------------------------------------

@bp.route("/")
def index():
    rows = query(BASE_SELECT + order_clause())
    return render_template("components/list.html", rows=rows, cats=category_nav(),
                           title="My components")


@bp.route("/category/<int:cat_id>")
def category(cat_id):
    cat = query("SELECT * FROM category WHERE id = ?", (cat_id,), one=True) or abort(404)
    rows = query(BASE_SELECT + " WHERE cat.id = ?" + order_clause(), (cat_id,))
    return render_template("components/list.html", rows=rows, cats=category_nav(),
                           subs=subcategory_nav(cat_id), active_cat=cat_id, title=cat["name"])


@bp.route("/subcategory/<int:sid>")
def subcategory(sid):
    sub = query("SELECT * FROM subcategory WHERE id = ?", (sid,), one=True) or abort(404)
    rows = query(BASE_SELECT + " WHERE s.id = ?" + order_clause(), (sid,))
    return render_template("components/list.html", rows=rows, cats=category_nav(),
                           subs=subcategory_nav(sub["category_id"]), active_cat=sub["category_id"],
                           active_sub=sid, title=sub["name"])


SEARCH_FIELDS = ["c.name", "c.manufacturer", "c.package", "CAST(c.pins AS TEXT)", "c.location",
                 "c.comment", "c.datasheet", "s.name", "cat.name"]


@bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    rows = []
    if q:
        where, args = [], []
        for term in q.split()[:10]:          # every word must match some field
            like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(" + " OR ".join(f"{f} LIKE ? ESCAPE '\\'" for f in SEARCH_FIELDS) + ")")
            args.extend([like] * len(SEARCH_FIELDS))
        rows = query(BASE_SELECT + " WHERE " + " AND ".join(where) + order_clause(), args)
    return render_template("components/list.html", rows=rows, cats=category_nav(), q=q,
                           title=f"Search: {q}" if q else "Search", is_search=True)


@bp.route("/shoplist")
def shoplist():
    rows = query(BASE_SELECT + " WHERE c.order_quantity > 0" + order_clause())
    total = sum((r["price"] or 0) * r["order_quantity"] for r in rows)
    missing_price = sum(1 for r in rows if r["price"] is None)
    return render_template("components/shoplist.html", rows=rows, total=total,
                           missing_price=missing_price)


@bp.route("/export.csv")
def export_csv():
    rows = query(BASE_SELECT + " ORDER BY c.name COLLATE NOCASE")
    cols = ["id", "name", "category_name", "subcategory_name", "manufacturer", "package", "pins",
            "smd", "scrap", "quantity", "order_quantity", "price", "location", "datasheet",
            "appnote", "image", "comment"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] if r[c] is not None else "" for c in cols])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=benchstock_components.csv"})


# --- single component ------------------------------------------------------

def component_projects(cid):
    return query("SELECT p.id, p.name, pc.quantity FROM project_component pc"
                 " JOIN project p ON p.id = pc.project_id WHERE pc.component_id = ?"
                 " ORDER BY p.name COLLATE NOCASE", (cid,))


@bp.route("/component/<int:cid>")
def view(cid):
    return render_template("components/view.html", c=get_component(cid), projects=component_projects(cid))


@bp.route("/component/<int:cid>/adjust", methods=["POST"])
def adjust(cid):
    c = get_component(cid)
    field = request.form.get("field")
    if field not in ("quantity", "order_quantity"):
        abort(400)
    delta = 1 if request.form.get("delta") == "1" else -1
    new = max(0, (c[field] or 0) + delta)
    execute(f"UPDATE component SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new, cid))
    return redirect(request.form.get("back") if request.form.get("back", "").startswith("/")
                    else url_for(".view", cid=cid))


@bp.route("/component/<int:cid>/delete", methods=["POST"])
def delete(cid):
    c = get_component(cid)
    execute("DELETE FROM component WHERE id = ?", (cid,))
    flash(f"Deleted {c['name']}.", "success")
    return redirect(url_for(".index"))


BLANK_COMPONENT = {
    "name": "", "subcategory_id": None, "manufacturer": "", "package": "", "pins": None, "smd": 0,
    "scrap": 0, "quantity": None, "order_quantity": None, "price": None, "location": "",
    "datasheet": "", "appnote": "", "image": "", "comment": "",
}


def _form_choices():
    subs = query("SELECT s.id, s.name, cat.name AS category_name FROM subcategory s"
                 " JOIN category cat ON cat.id = s.category_id"
                 " ORDER BY cat.name COLLATE NOCASE, s.name COLLATE NOCASE")
    projects = query("SELECT id, name FROM project ORDER BY name COLLATE NOCASE")
    return subs, projects


def _save(cid=None):
    """Handle add/edit POST. Returns (new_or_existing_id, form_values, errors)."""
    subs, projects = _form_choices()
    values, proj_add, proj_edits, errors = parse_component(
        request.form, {s["id"] for s in subs}, {p["id"] for p in projects})
    if errors:
        return None, values, errors
    conn = get_db()
    cols = ["name", "subcategory_id", "manufacturer", "package", "pins", "smd", "scrap", "quantity",
            "order_quantity", "price", "location", "datasheet", "appnote", "image", "comment"]
    with conn:
        if cid is None:
            cur = conn.execute(
                f"INSERT INTO component ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [values[c] for c in cols])
            cid = cur.lastrowid
        else:
            conn.execute(
                f"UPDATE component SET {', '.join(c + ' = ?' for c in cols)},"
                " updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                [values[c] for c in cols] + [cid])
        for pid, qty in proj_edits.items():
            if qty:
                conn.execute("UPDATE project_component SET quantity = ? WHERE project_id = ? AND component_id = ?",
                             (qty, pid, cid))
            else:
                conn.execute("DELETE FROM project_component WHERE project_id = ? AND component_id = ?",
                             (pid, cid))
        if proj_add:
            conn.execute("INSERT INTO project_component (project_id, component_id, quantity) VALUES (?,?,?)"
                         " ON CONFLICT(project_id, component_id) DO UPDATE SET quantity = excluded.quantity",
                         (proj_add[0], cid, proj_add[1]))
    return cid, values, []


@bp.route("/add", methods=["GET", "POST"])
def add():
    subs, projects = _form_choices()
    based = None
    if request.args.get("based", "").isdigit():
        based = get_component(int(request.args["based"]))
    if request.method == "POST":
        cid, values, errors = _save()
        if not errors:
            flash("Component added.", "success")
            if request.form.get("again"):
                return redirect(url_for(".add"))
            return redirect(url_for(".view", cid=cid))
        for e in errors:
            flash(e, "error")
        c = values
    else:
        c = dict(based) if based else dict(BLANK_COMPONENT)
    return render_template("components/form.html", c=c, subs=subs, projects=projects,
                           based=based, mode="add")


@bp.route("/component/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    existing = get_component(cid)
    subs, projects = _form_choices()
    if request.method == "POST":
        _, values, errors = _save(cid)
        if not errors:
            flash("Component updated.", "success")
            return redirect(url_for(".view", cid=cid))
        for e in errors:
            flash(e, "error")
        c = dict(existing, **values)
    else:
        c = existing
    linked = component_projects(cid)
    linked_ids = {p["id"] for p in linked}
    return render_template("components/form.html", c=c, subs=subs, mode="edit", linked=linked,
                           projects=[p for p in projects if p["id"] not in linked_ids])


# --- autocomplete -------------------------------------------------------------

DB_SUGGEST = {"name", "manufacturer", "package", "location"}
FILE_SUGGEST = {"datasheet": "SHEETS_DIR", "appnote": "APPNOTES_DIR", "image": "IMAGES_DIR"}


@bp.route("/api/suggest/<field>")
def suggest(field):
    term = request.args.get("term", "").strip()
    if field in DB_SUGGEST:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = query(f"SELECT DISTINCT {field} AS v FROM component WHERE {field} != ''"
                     f" AND {field} LIKE ? ESCAPE '\\' ORDER BY {field} COLLATE NOCASE LIMIT 30",
                     (like,))
        return jsonify([r["v"] for r in rows])
    if field in FILE_SUGGEST:
        t = term.lower()
        names = [n for n in list_reference_files(FILE_SUGGEST[field]) if t in n.lower()]
        return jsonify(names[:30])
    abort(404)


@bp.route("/about")
def about():
    return render_template("about.html")
