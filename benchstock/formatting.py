"""Jinja filters and small display helpers."""
from urllib.parse import urlencode

from flask import request


def fmt_number(value):
    """3.0 -> '3', 2.5 -> '2.5', None/'' -> ''."""
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f.is_integer():
        return str(int(f))
    return ("%.4f" % f).rstrip("0").rstrip(".")


def fmt_price(value):
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    return "%.2f" % f if round(f, 2) == f else fmt_number(f)


def sort_url(column, default_order="asc"):
    """Link for a sortable column header: toggles asc/desc on the active column."""
    args = request.args.to_dict()
    if args.get("by") == column:
        order = "desc" if args.get("order", "asc") == "asc" else "asc"
    else:
        order = default_order
    args.update(by=column, order=order)
    return "?" + urlencode(args)


def sort_icon(column):
    if request.args.get("by") != column:
        return ""
    return "fa-sort-asc" if request.args.get("order", "asc") == "asc" else "fa-sort-desc"


def register_filters(app):
    app.jinja_env.filters["num"] = fmt_number
    app.jinja_env.filters["price"] = fmt_price
    app.jinja_env.globals["sort_url"] = sort_url
    app.jinja_env.globals["sort_icon"] = sort_icon
