"""Form parsing/validation shared by the add/edit/clone pages and settings."""
COMMENT_MAX = 2500


def parse_number(raw, label, errors, integer=False, allow_empty=True):
    s = (raw or "").strip().replace(",", ".")
    if s == "":
        if not allow_empty:
            errors.append(f"{label} is required.")
        return None
    try:
        f = float(s)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if f < 0:
        errors.append(f"{label} cannot be negative.")
        return None
    if integer:
        if not f.is_integer():
            errors.append(f"{label} must be a whole number.")
            return None
        return int(f)
    return int(f) if f.is_integer() else f


def clean_filename(raw):
    """Reference fields store bare file names only (no folders)."""
    name = (raw or "").strip().replace("\\", "/")
    return name.rsplit("/", 1)[-1]


def parse_component(form, subcategory_ids, project_ids):
    """Returns (values, project_add, project_edits, errors)."""
    errors = []
    v = {
        "name": form.get("name", "").strip(),
        "manufacturer": form.get("manufacturer", "").strip(),
        "package": form.get("package", "").strip(),
        "location": form.get("location", "").strip(),
        "datasheet": clean_filename(form.get("datasheet")),
        "appnote": clean_filename(form.get("appnote")),
        "image": clean_filename(form.get("image")),
        "comment": form.get("comment", "").replace("\r\n", "\n").strip(),
        "smd": 1 if form.get("smd") == "1" else 0,
        "scrap": 1 if form.get("scrap") == "1" else 0,
    }
    if not v["name"]:
        errors.append("You have to specify a name.")
    sub = form.get("subcategory_id", "")
    if not sub.isdigit() or int(sub) not in subcategory_ids:
        errors.append("You have to choose a category.")
        v["subcategory_id"] = None
    else:
        v["subcategory_id"] = int(sub)
    v["quantity"] = parse_number(form.get("quantity"), "Quantity", errors) or 0
    v["order_quantity"] = parse_number(form.get("order_quantity"), "Order quantity", errors) or 0
    v["pins"] = parse_number(form.get("pins"), "Pin count", errors, integer=True)
    v["price"] = parse_number(form.get("price"), "Price", errors)
    if len(v["comment"]) > COMMENT_MAX:
        errors.append(f"Max {COMMENT_MAX} characters in the comment.")

    project_add = None
    pid = form.get("project_id", "")
    pq = parse_number(form.get("project_quantity"), "Project quantity", errors)
    if pid:
        if not pid.isdigit() or int(pid) not in project_ids:
            errors.append("Unknown project.")
        elif not pq:
            errors.append("Specify a quantity for the project.")
        else:
            project_add = (int(pid), pq)
    elif pq:
        errors.append("You have to choose a project for that project quantity.")

    project_edits = {}
    for key in form:
        if key.startswith("projqty_"):
            p = key[len("projqty_"):]
            if p.isdigit() and int(p) in project_ids:
                project_edits[int(p)] = parse_number(form[key], "Project quantity", errors) or 0
    return v, project_add, project_edits, errors

