"""Import paths that failed on the Pi: CLI into an auto-created empty database,
plain mysqldump format (no column lists), UTF-16 dumps, and dumps with no data."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from benchstock import create_app  # noqa: E402
from mysql_to_sqlite import convert  # noqa: E402

REAL_DUMP = os.path.join(os.path.dirname(__file__), "..", "..", "html", "ecdb.sql")

# Plain `mysqldump` output: column order only in CREATE TABLE, extended inserts on one line
MYSQLDUMP = """-- MySQL dump 10.13
/*!40101 SET NAMES utf8mb4 */;
DROP TABLE IF EXISTS `category_head`;
CREATE TABLE `category_head` (
  `id` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb3;
LOCK TABLES `category_head` WRITE;
INSERT INTO `category_head` VALUES (5,'IC'),(12,'Transistor');
UNLOCK TABLES;
CREATE TABLE `category_sub` (
  `id` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  UNIQUE KEY `id` (`id`)
) ENGINE=MyISAM;
INSERT INTO `category_sub` VALUES (501,'Regulator'),(1204,'NPN');
CREATE TABLE `members` (
  `member_id` int(11) NOT NULL AUTO_INCREMENT,
  `firstname` varchar(32) NOT NULL,
  `lastname` varchar(32) NOT NULL,
  `login` varchar(32) NOT NULL,
  `mail` varchar(32) NOT NULL,
  `passwd` varchar(32) NOT NULL,
  `admin` int(11) NOT NULL DEFAULT 0,
  `measurement` int(11) NOT NULL DEFAULT 1,
  `currency` varchar(3) NOT NULL DEFAULT 'USD',
  `reg_date` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`member_id`)
) ENGINE=MyISAM;
INSERT INTO `members` VALUES (1800,'Pete','Willard','pwillard','p@x.com','abc',0,1,'EUR','2013-07-25 03:03:56');
CREATE TABLE `data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `owner` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  `manufacturer` varchar(64) NOT NULL,
  `package` varchar(64) NOT NULL,
  `pins` varchar(11) NOT NULL,
  `smd` varchar(3) NOT NULL DEFAULT 'No',
  `quantity` varchar(11) NOT NULL,
  `order_quantity` varchar(11) NOT NULL,
  `location` varchar(32) NOT NULL,
  `scrap` varchar(3) NOT NULL DEFAULT 'No',
  `datasheet` varchar(256) NOT NULL,
  `comment` text NOT NULL,
  `category` varchar(11) NOT NULL,
  `cimage` varchar(256) NOT NULL,
  `appnote` varchar(256) NOT NULL,
  `price` varchar(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `Id` (`id`)
) ENGINE=MyISAM;
INSERT INTO `data` VALUES (1,1800,'LM317','TI','TO-220','3','No','5','','Bin A','No','lm317.pdf','it\\'s a regulator','501','to220.jpg','','0.45'),(2,1800,'2N2222','','','','Yes','7','','','No','','','1204','','','');
"""


def make_app(tmp_path):
    return create_app({"TESTING": True, "SECRET_KEY": "x", "DATABASE": str(tmp_path / "b.sqlite3"),
                       "MEDIA_ROOT": str(tmp_path / "media")})


def count(path, table="component"):
    return sqlite3.connect(path).execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_mysqldump_format(tmp_path):
    dump = tmp_path / "d.sql"
    dump.write_text(MYSQLDUMP, encoding="utf-8")
    out = tmp_path / "o.sqlite3"
    counts = convert(str(dump), str(out))
    assert counts["component"] == 2
    db = sqlite3.connect(out)
    assert db.execute("SELECT name, comment, price FROM component WHERE id=1").fetchone() == \
        ("LM317", "it's a regulator", 0.45)
    assert db.execute("SELECT value FROM setting").fetchone() == ("EUR",)


def test_utf16_dump(tmp_path):
    dump = tmp_path / "d.sql"
    dump.write_bytes(MYSQLDUMP.encode("utf-16"))      # what PowerShell's ">" produces
    assert convert(str(dump), str(tmp_path / "o.sqlite3"))["component"] == 2


def test_cli_import_replaces_auto_created_empty_db(tmp_path):
    """The Pi bug: the app creates an empty DB on start, then import refused it."""
    app = make_app(tmp_path)
    db_path = app.config["DATABASE"]
    assert os.path.exists(db_path) and count(db_path) == 0
    dump = tmp_path / "d.sql"
    dump.write_text(MYSQLDUMP, encoding="utf-8")
    r = app.test_cli_runner().invoke(args=["import-mysql", str(dump)])
    assert r.exit_code == 0, r.output
    assert count(db_path) == 2


def test_cli_import_refuses_db_with_parts_unless_force(tmp_path):
    app = make_app(tmp_path)
    dump = tmp_path / "d.sql"
    dump.write_text(MYSQLDUMP, encoding="utf-8")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["import-mysql", str(dump)]).exit_code == 0
    r = runner.invoke(args=["import-mysql", str(dump)])
    assert r.exit_code != 0 and "already holds 2 components" in r.output
    assert runner.invoke(args=["import-mysql", str(dump), "--force"]).exit_code == 0


def test_empty_dump_leaves_database_untouched(tmp_path):
    app = make_app(tmp_path)
    good = tmp_path / "good.sql"
    good.write_text(MYSQLDUMP, encoding="utf-8")
    runner = app.test_cli_runner()
    runner.invoke(args=["import-mysql", str(good)])
    bad = tmp_path / "bad.sql"
    bad.write_text("-- nothing here\n", encoding="utf-8")
    r = runner.invoke(args=["import-mysql", str(bad), "--force"])
    assert r.exit_code != 0
    assert count(app.config["DATABASE"]) == 2         # previous data still there
    assert not os.path.exists(app.config["DATABASE"] + ".importing")


@pytest.mark.skipif(not os.path.exists(REAL_DUMP), reason="real ecdb.sql not available")
def test_cli_import_real_dump_into_fresh_install(tmp_path):
    app = make_app(tmp_path)
    r = app.test_cli_runner().invoke(args=["import-mysql", REAL_DUMP])
    assert r.exit_code == 0, r.output
    assert count(app.config["DATABASE"]) == 1568
