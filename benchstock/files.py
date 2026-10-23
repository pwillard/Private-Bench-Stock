"""Reference files (datasheets, application notes, part images): serving,
uploading and the reference audit."""
import csv
import io
import os

from flask import (Blueprint, Response, current_app, flash, redirect, render_template,
                   request, send_from_directory, url_for)

from .db import query

bp = Blueprint("files", __name__)

PDF_EXT = {"pdf"}
IMAGE_EXT = {"jpg", "jpeg", "gif", "png", "webp"}
FOLDERS = {
    # field: (config key, url prefix, allowed extensions, label)
    "datasheet": ("SHEETS_DIR", "sheets", PDF_EXT, "Datasheets"),
    "appnote": ("APPNOTES_DIR", "appnotes", PDF_EXT, "Application notes"),
    "image": ("IMAGES_DIR", "img/parts", IMAGE_EXT, "Part images"),
}


def ext_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def list_reference_files(config_key, extensions=None):
    folder = current_app.config[config_key]
    if extensions is None:
        extensions = IMAGE_EXT if config_key == "IMAGES_DIR" else PDF_EXT
    try:
        names = [e.name for e in os.scandir(folder) if e.is_file() and ext_of(e.name) in extensions]
    except FileNotFoundError:
        return []
    return sorted(names, key=str.lower)


# --- serving (same URLs as the old site: /sheets/x.pdf, /appnotes/x.pdf, /img/parts/x.jpg)

def _serve(config_key, filename):
    return send_from_directory(current_app.config[config_key], filename, max_age=3600)


@bp.route("/sheets/<path:filename>")
def sheet(filename):
    return _serve("SHEETS_DIR", filename)


@bp.route("/appnotes/<path:filename>")
def appnote(filename):
    return _serve("APPNOTES_DIR", filename)


@bp.route("/img/parts/<path:filename>")
def image(filename):
    return _serve("IMAGES_DIR", filename)


# --- upload ----------------------------------------------------------------

def valid_upload_name(name):
    """Keep the exact file name (case matters on Linux) but refuse anything
    that could escape the folder or hide."""
    if not name or name != os.path.basename(name) or "/" in name or "\\" in name:
        return False
    if name.startswith(".") or ".." in name or any(ord(ch) < 32 for ch in name):
        return False
    return len(name) <= 200


def save_upload(storage, as_appnote):
    """Returns (ok, message)."""
    name = (storage.filename or "").strip()
    name = name.replace("\\", "/").rsplit("/", 1)[-1]   # some browsers send full paths
    if not name:
        return False, "No file was selected."
    if not valid_upload_name(name):
        return False, f"{name}: invalid file name."
    ext = ext_of(name)
    if ext in PDF_EXT:
        field = "appnote" if as_appnote else "datasheet"
    elif ext in IMAGE_EXT:
        field = "image"
    else:
        return False, f"{name}: only PDF, JPG, GIF, PNG and WEBP files are supported."
    config_key, prefix, _exts, label = FOLDERS[field]
    folder = current_app.config[config_key]
    if not os.path.isdir(folder):
        return False, f"Upload folder for {label.lower()} does not exist ({folder})."
    existing = {n.lower(): n for n in os.listdir(folder)}
    if name.lower() in existing:
        other = existing[name.lower()]
        if other == name:
            return False, f"{name} already exists in {prefix}/."
        return False, f"{name} was not uploaded: {other} already exists (same name, different case)."
    path = os.path.join(folder, name)
    try:
        with open(path, "xb") as out:          # "x" = never overwrite
            storage.save(out)
    except OSError as e:
        return False, f"{name} was not uploaded: {e.strerror}."
    return True, f"{name} uploaded to {prefix}/."


@bp.route("/reference", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = [f for f in request.files.getlist("file") if f and f.filename]
        if not files:
            flash("No file was selected.", "error")
        for f in files:
            ok, msg = save_upload(f, request.form.get("appnote") == "1")
            flash(msg, "success" if ok else "error")
        return redirect(url_for(".upload"))
    counts = {field: len(list_reference_files(v[0], v[2])) for field, v in FOLDERS.items()}
    return render_template("files/upload.html", folders=FOLDERS, counts=counts)


# --- audit -------------------------------------------------------------------

def audit_field(rows, field):
    config_key, prefix, exts, _label = FOLDERS[field]
    folder = current_app.config[config_key]
    exists = os.path.isdir(folder)
    files = list_reference_files(config_key, exts) if exists else []
    exact = set(files)
    lower_map = {}
    for n in files:
        lower_map.setdefault(n.lower(), []).append(n)

    issues = []
    s = dict(references=0, exact=0, case=0, missing=0, ambiguous=0, unreferenced=0,
             duplicates=sum(1 for v in lower_map.values() if len(v) > 1))

    def issue(kind, row, db_value, actual, message):
        issues.append(dict(type=kind, id=row["id"] if row else None, name=row["name"] if row else "",
                           field=field, folder=prefix, db_value=db_value, actual=actual, message=message))

    used = set()
    for r in rows:
        val = (r[field] or "").strip()
        if not val:
            continue
        s["references"] += 1
        used.add(val.lower())
        if val in exact:
            s["exact"] += 1
        elif val.lower() in lower_map:
            matches = lower_map[val.lower()]
            if len(matches) == 1:
                s["case"] += 1
                issue("CASE_MISMATCH", r, val, matches[0], "Database name differs from the file only by case.")
            else:
                s["ambiguous"] += 1
                issue("AMBIGUOUS_CASE_MATCH", r, val, " | ".join(matches),
                      "More than one file matches ignoring case.")
        else:
            s["missing"] += 1
            issue("MISSING_FILE", r, val, "", "Database references a file that was not found.")
    for n in files:
        if n.lower() not in used:
            s["unreferenced"] += 1
            issue("UNREFERENCED_FILE", None, "", n, "File is not used by any component.")
    for matches in lower_map.values():
        if len(matches) > 1:
            issue("DUPLICATE_CASE_FILE", None, "", " | ".join(matches), "Multiple files differ only by case.")
    s.update(field=field, folder=prefix, exists=exists)
    return s, issues


@bp.route("/reference/audit")
def audit():
    rows = query("SELECT id, name, datasheet, appnote, image FROM component ORDER BY name COLLATE NOCASE")
    summaries, issues = [], []
    for field in FOLDERS:
        s, i = audit_field(rows, field)
        summaries.append(s)
        issues.extend(i)
    show = request.args.get("show", "problems")
    if request.args.get("format") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["type", "id", "part_name", "field", "folder", "database_value", "actual_file", "message"])
        for i in issues:
            w.writerow([i["type"], i["id"] or "", i["name"], i["field"], i["folder"], i["db_value"],
                        i["actual"], i["message"]])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=reference_audit.csv"})
    if show == "problems":
        visible = [i for i in issues if i["type"] != "UNREFERENCED_FILE"]
    else:
        visible = issues
    return render_template("files/audit.html", summaries=summaries, issues=visible,
                           total=len(issues), show=show)


@bp.app_errorhandler(413)
def too_large(_e):
    flash("The uploaded file is too large (limit %d MB)."
          % (current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)), "error")
    return redirect(url_for("files.upload"))
