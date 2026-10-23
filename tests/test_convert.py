"""Converter tests: synthetic dump with awkward values, plus the real dump if present."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from mysql_to_sqlite import convert, read_dump  # noqa: E402

REAL_DUMP = os.path.join(os.path.dirname(__file__), "..", "..", "html", "ecdb.sql")

SAMPLE = r"""
CREATE TABLE `category_head` (`id` int(11) NOT NULL, `name` varchar(64) NOT NULL);
INSERT INTO `category_head` (`id`, `name`) VALUES
(5, 'IC'),
(12, 'Transistor');
INSERT INTO `category_sub` (`id`, `name`) VALUES
(501, 'Regulator'),
(1204, 'NPN'),
(901, 'Orphan');
INSERT INTO `members` (`member_id`, `firstname`, `lastname`, `login`, `mail`, `passwd`, `admin`, `measurement`, `currency`, `reg_date`) VALUES
(7, 'Pete', 'O\'Brien', 'pete', 'p@x.com', '5179B96AEE89546EF7098194BA6D33C4', 0, 1, 'USD', '2013-07-25 03:03:56');
INSERT INTO `data` (`id`, `owner`, `name`, `manufacturer`, `package`, `pins`, `smd`, `quantity`, `order_quantity`, `location`, `scrap`, `datasheet`, `comment`, `category`, `cimage`, `appnote`, `price`) VALUES
(1, 7, 'LM317', 'TI', 'TO-220', '3', 'No', '5', '', 'Bin; A', 'No', 'lm317.pdf', 'line1\r\nline2 with ''quotes'' and (parens), commas', '501', 'to220.jpg', '', '0,45'),
(2, 7, '2N2222', '', '', '', 'Yes', '1.5', '2', '', 'Yes', '', '', '1204', '', '', ''),
(3, 99, 'Ghost', '', '', '', 'No', '', '', '', 'No', '', '', '501', '', '', '');
"""


def test_synthetic_dump(tmp_path):
    dump = tmp_path / "d.sql"
    dump.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "o.sqlite3"
    counts = convert(str(dump), str(out))
    assert counts["component"] == 2 and counts["subcategory"] == 2 and counts["user"] == 1
    db = sqlite3.connect(out)
    c1 = db.execute("SELECT comment, price, pins, quantity, order_quantity, smd, location FROM component WHERE id=1").fetchone()
    assert c1 == ("line1\r\nline2 with 'quotes' and (parens), commas", 0.45, 3, 5, 0, 0, "Bin; A")
    c2 = db.execute("SELECT price, pins, quantity, smd, scrap FROM component WHERE id=2").fetchone()
    assert c2 == (None, None, 1.5, 1, 1)
    assert db.execute("SELECT lastname, password_hash FROM user").fetchone() == \
        ("O'Brien", "md5$5179b96aee89546ef7098194ba6d33c4")
    with pytest.raises(SystemExit):
        convert(str(dump), str(out))                   # refuses to overwrite without --force


@pytest.mark.skipif(not os.path.exists(REAL_DUMP), reason="real ecdb.sql not available")
def test_real_dump_row_counts_match(tmp_path):
    src = read_dump(REAL_DUMP)
    out = tmp_path / "real.sqlite3"
    counts = convert(REAL_DUMP, str(out))
    assert counts["component"] == len(src["data"])
    assert counts["user"] == len(src["members"])
    db = sqlite3.connect(out)
    # spot-check every component's name and quantity round-trips
    rows = {r[0]: r[1:] for r in db.execute("SELECT id, name, quantity FROM component")}
    for r in src["data"]:
        name, qty = rows[r["id"]]
        assert name == r["name"].strip()
        assert float(qty) == float(r["quantity"] or 0)
