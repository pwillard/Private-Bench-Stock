from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .components import BASE_SELECT
from .db import execute, query

bp = Blueprint("projects", __name__, url_prefix="/projects")

PROJECT_SORTS = {
    "name": "c.name COLLATE NOCASE", "category": "cat.name COLLATE NOCASE",
    "manufacturer": "c.manufacturer COLLATE NOCASE", "package": "c.package COLLATE NOCASE",
    "smd": "c.smd", "price": "c.price", "quantity": "c.quantity", "needed": "pc.quantity",
}


def get_project(pid):
    p = query("SELECT * FROM project WHERE id = ?", (pid,), one=True)
    if p is None:
        abort(404)
    return p


@bp.route("/", methods=["GET", "POST"])
def list_projects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("You have to specify a name.", "error")
        else:
            pid = execute("INSERT INTO project (name) VALUES (?)", (name,))
            flash(f"Project {name} added.", "success")
            return redirect(url_for(".show", pid=pid))
    direction = "DESC" if request.args.get("order") == "desc" else "ASC"
    projects = query(
        "SELECT p.id, p.name, COUNT(pc.component_id) AS parts,"
        " SUM(pc.quantity * c.price) AS total,"
        " SUM(CASE WHEN c.quantity < pc.quantity THEN 1 ELSE 0 END) AS short"
        " FROM project p LEFT JOIN project_component pc ON pc.project_id = p.id"
        " LEFT JOIN component c ON c.id = pc.component_id"
        f" GROUP BY p.id ORDER BY p.name COLLATE NOCASE {direction}")
    return render_template("projects/list.html", projects=projects)


@bp.route("/<int:pid>")
def show(pid):
    project = get_project(pid)
    by = request.args.get("by", "name")
    direction = "DESC" if request.args.get("order") == "desc" else "ASC"
    order = PROJECT_SORTS.get(by, PROJECT_SORTS["name"])
    rows = query(
        BASE_SELECT.replace("SELECT c.*", "SELECT c.*, pc.quantity AS needed")
        + " JOIN project_component pc ON pc.component_id = c.id"
        f" WHERE pc.project_id = ? ORDER BY {order} {direction}, c.name COLLATE NOCASE", (pid,))
    total = sum((r["price"] or 0) * r["needed"] for r in rows)
    return render_template("projects/show.html", project=project, rows=rows, total=total)


@bp.route("/<int:pid>/rename", methods=["POST"])
def rename(pid):
    get_project(pid)
    name = request.form.get("name", "").strip()
    if not name:
        flash("You have to specify a name.", "error")
    else:
        execute("UPDATE project SET name = ? WHERE id = ?", (name, pid))
        flash("Project renamed.", "success")
    return redirect(url_for(".show", pid=pid))


@bp.route("/<int:pid>/delete", methods=["POST"])
def delete(pid):
    p = get_project(pid)
    execute("DELETE FROM project WHERE id = ?", (pid,))
    flash(f"Project {p['name']} deleted (components were kept).", "success")
    return redirect(url_for(".list_projects"))


@bp.route("/<int:pid>/remove/<int:cid>", methods=["POST"])
def remove_component(pid, cid):
    get_project(pid)
    execute("DELETE FROM project_component WHERE project_id = ? AND component_id = ?", (pid, cid))
    return redirect(url_for(".show", pid=pid))


@bp.route("/<int:pid>/order-shortfall", methods=["POST"])
def order_shortfall(pid):
    """Put every missing part of the project on the shopping list."""
    get_project(pid)
    rows = query("SELECT c.id, c.quantity, c.order_quantity, pc.quantity AS needed FROM component c"
                 " JOIN project_component pc ON pc.component_id = c.id"
                 " WHERE pc.project_id = ?", (pid,))
    n = 0
    for r in rows:
        short = r["needed"] - r["quantity"]
        if short > 0 and r["order_quantity"] < short:
            execute("UPDATE component SET order_quantity = ? WHERE id = ?", (short, r["id"]))
            n += 1
    flash(f"{n} component(s) added to the shopping list." if n else "Nothing is short.", "success")
    return redirect(url_for(".show", pid=pid))
