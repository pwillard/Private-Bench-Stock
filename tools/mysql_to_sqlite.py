#!/usr/bin/env python3
"""One-time converter: ecDB MySQL/phpMyAdmin dump (ecdb.sql) -> SQLite database.

Usage:
    python tools/mysql_to_sqlite.py <ecdb.sql> <output.sqlite3> [--force]

Reads only the INSERT statements of the dump (no MySQL server needed), maps the
old tables onto the new schema (ecdb/schema.sql) and prints a report of every
value it had to clean up. The source dump is never modified.

Old table        -> new table
category_head    -> category
category_sub     -> subcategory   (category_id = id // 100)
members          -> user          (MD5 password kept as "md5$<hash>", upgraded on next login)
members_stats    -> login_log
data             -> component
projects         -> project
projects_data    -> project_component
"""
import argparse
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "..", "ecdb", "schema.sql")

INSERT_RE = re.compile(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES\s*", re.I)
ESCAPES = {"0": "\0", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a", "b": "\b"}


def parse_values(text, pos):
    """Parse `(v, v, ...), (...);` starting at pos. Returns (rows, new_pos)."""
    rows, row, n = [], None, len(text)
    while pos < n:
        c = text[pos]
        if c == "(" and row is None:
            row = []
            pos += 1
        elif row is not None and c == "'":
            pos += 1
            buf = []
            while True:
                c = text[pos]
                if c == "\\":
                    nxt = text[pos + 1]
                    buf.append(ESCAPES.get(nxt, nxt))
                    pos += 2
                elif c == "'":
                    if pos + 1 < n and text[pos + 1] == "'":
                        buf.append("'")
                        pos += 2
                    else:
                        pos += 1
                        break
                else:
                    buf.append(c)
                    pos += 1
            row.append("".join(buf))
        elif row is not None and c in ",)":
            if c == ")":
                rows.append(row)
                row = None
            pos += 1
        elif row is not None and not c.isspace():
            m = re.compile(r"[^,)\s]+").match(text, pos)
            tok = m.group(0)
            pos = m.end()
            if tok.upper() == "NULL":
                row.append(None)
            else:
                try:
                    row.append(int(tok))
                except ValueError:
                    row.append(float(tok))
        elif row is None and c == ";":
            return rows, pos + 1
        else:
            pos += 1
    return rows, pos


def read_dump(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    tables = {}
    for m in INSERT_RE.finditer(text):
        name = m.group(1)
        cols = [c.strip().strip("`") for c in m.group(2).split(",")]
        rows, _ = parse_values(text, m.end())
        tables.setdefault(name, []).extend(dict(zip(cols, r)) for r in rows)
    return tables


class Report:
    def __init__(self):
        self.lines = []

    def __call__(self, msg):
        self.lines.append(msg)


def num(value, field, row_id, report, integer=False, empty=None):
    """'' -> empty; numeric strings (comma decimals allowed) -> number."""
    if value is None:
        return empty
    s = str(value).strip().replace(",", ".")
    if s == "":
        return empty
    try:
        f = float(s)
    except ValueError:
        report(f"component {row_id}: {field}={value!r} is not a number -> {empty!r}")
        return empty
    if integer or f.is_integer():
        if not f.is_integer():
            report(f"component {row_id}: {field}={value!r} rounded to {round(f)}")
        return int(round(f))
    return f


def yes(value):
    return 1 if str(value).strip().lower() in ("yes", "1", "on", "true") else 0


def convert(dump_path, out_path, force=False):
    if os.path.exists(out_path):
        if not force:
            sys.exit(f"{out_path} already exists (use --force to overwrite)")
        os.remove(out_path)

    t = read_dump(dump_path)
    report = Report()
    db = sqlite3.connect(out_path)
    db.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        db.executescript(f.read())

    # Categories
    for r in t.get("category_head", []):
        db.execute("INSERT INTO category (id, name) VALUES (?, ?)", (r["id"], r["name"]))
    cat_ids = {r["id"] for r in t.get("category_head", [])}
    for r in t.get("category_sub", []):
        head = int(r["id"]) // 100
        if head not in cat_ids:
            report(f"subcategory {r['id']} {r['name']!r}: parent category {head} missing (skipped)")
            continue
        db.execute("INSERT INTO subcategory (id, category_id, name) VALUES (?, ?, ?)",
                   (r["id"], head, r["name"]))
    sub_ids = {row[0] for row in db.execute("SELECT id FROM subcategory")}

    # Users
    for r in t.get("members", []):
        db.execute(
            "INSERT INTO user (id, login, firstname, lastname, email, password_hash, is_admin,"
            " measurement, currency, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["member_id"], r["login"], r["firstname"], r["lastname"], r["mail"],
             "md5$" + r["passwd"].lower(), int(r.get("admin") or 0), int(r.get("measurement") or 0),
             r.get("currency") or "USD", r.get("reg_date")))
    user_ids = {row[0] for row in db.execute("SELECT id FROM user")}

    for r in t.get("members_stats", []):
        if r["members_stats_member"] in user_ids:
            db.execute("INSERT INTO login_log (id, user_id, logged_at) VALUES (?,?,?)",
                       (r["members_stats_id"], r["members_stats_member"], r["members_stats_time"]))

    # Components
    skipped = 0
    for r in t.get("data", []):
        cid = r["id"]
        if r["owner"] not in user_ids:
            report(f"component {cid} {r['name']!r}: owner {r['owner']} does not exist (skipped)")
            skipped += 1
            continue
        sub = num(r["category"], "category", cid, report, integer=True)
        if sub not in sub_ids:
            report(f"component {cid} {r['name']!r}: category {r['category']!r} unknown -> 1799 (Misc)")
            sub = 1799 if 1799 in sub_ids else min(sub_ids)
        db.execute(
            "INSERT INTO component (id, owner_id, name, subcategory_id, manufacturer, package, pins,"
            " smd, scrap, quantity, order_quantity, price, location, datasheet, appnote, image, comment,"
            " created_at, updated_at)"   # the old site kept no dates: leave them blank
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'','')",
            (cid, r["owner"], r["name"].strip(), sub, r["manufacturer"].strip(), r["package"].strip(),
             num(r["pins"], "pins", cid, report, integer=True),
             yes(r["smd"]), yes(r["scrap"]),
             num(r["quantity"], "quantity", cid, report, empty=0),
             num(r["order_quantity"], "order_quantity", cid, report, empty=0),
             num(r["price"], "price", cid, report),
             r["location"].strip(), r["datasheet"].strip(), r["appnote"].strip(),
             r["cimage"].strip(), r["comment"]))
    comp_ids = {row[0] for row in db.execute("SELECT id FROM component")}

    # Projects
    for r in t.get("projects", []):
        if r["project_owner"] not in user_ids:
            report(f"project {r['project_id']} {r['project_name']!r}: owner missing (skipped)")
            continue
        db.execute("INSERT INTO project (id, owner_id, name) VALUES (?,?,?)",
                   (r["project_id"], r["project_owner"], r["project_name"]))
    proj_ids = {row[0] for row in db.execute("SELECT id FROM project")}
    for r in t.get("projects_data", []):
        pid, cid = r["projects_data_project_id"], r["projects_data_component_id"]
        if pid not in proj_ids or cid not in comp_ids:
            report(f"project link {r['projects_data_id']}: project {pid} / component {cid} missing (skipped)")
            continue
        db.execute("INSERT OR REPLACE INTO project_component (project_id, component_id, quantity)"
                   " VALUES (?,?,?)", (pid, cid, r["projects_data_quantity"]))

    db.commit()
    counts = {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in ("category", "subcategory", "user", "login_log", "component",
                           "project", "project_component")}
    db.close()

    print("Source rows:", {k: len(v) for k, v in t.items()})
    print("Imported   :", counts)
    if report.lines:
        print(f"\n{len(report.lines)} cleanup notes:")
        for line in report.lines:
            print("  " + line)
    else:
        print("No cleanup needed.")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("output")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output database")
    a = ap.parse_args()
    convert(a.dump, a.output, a.force)
