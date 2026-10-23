# Private Bench Stock

*Your parts. Your datasheets. Your workbench.*

A personal electronic-components inventory (Python/Flask + SQLite). It replaces the old ecDB PHP/MySQL site, which lives in `..\html`. It keeps all of your data
(parts, categories, projects), the datasheet, appnote and image folders, and the general look of
the old site. There is no PHP and no MySQL server any more.

It is a single-user tool with no accounts and no login: anyone who can reach it on your
network can use it. The user system in the old code was left over from the original author's
plans for a public web service.

## What's in the box

    benchstock/               the application (Flask)
      schema.sql        database layout (SQLite)
      templates/        HTML pages
      static/           CSS, JS, fonts, logo
    tools/mysql_to_sqlite.py   one-time converter for the old ecdb.sql dump
    manage.py           start the server + admin commands
    deploy/             Raspberry Pi installer and systemd units
    tests/              automated tests (pytest)
    config.example.py   optional settings (copy to instance/config.py)

Everything that belongs to *your* installation lives in `instance/`. Code updates never touch it.

    instance/benchstock.sqlite3          the database
    instance/media/sheets/         datasheets       (served at /sheets/...)
    instance/media/appnotes/       application notes (/appnotes/...)
    instance/media/img/parts/      part images       (/img/parts/...)
    instance/secret_key            signs the form security tokens (auto-generated)
    instance/backups/              daily backups

## Install on the Raspberry Pi

1. Copy this `app` folder to the Pi (e.g. `scp -r app pi@raspberrypi:~/benchstock-app`).
   Also copy `ecdb.sql` if the old site is on a different machine.
2. `..\html\ecdb.sql` is the current dump. Only if you edit data on the old site before
   switching over, make a new one:

       mysqldump -u ecdb -p ecdb > ecdb.sql

3. Install, import the dump and copy the reference files from the old web root:

       cd ~/benchstock-app
       sudo bash deploy/install_pi.sh --dump ~/ecdb.sql --files /var/www/html --port 8080

   This sets up `/opt/benchstock`, a Python virtual environment, a locked-down `benchstock` service user,
   the `benchstock` systemd service (starts at boot) and a daily database backup timer.
4. Open `http://<pi-address>:8080/`.

   The importer brings in the parts and projects of one old member (by default the one with
   the most parts, i.e. you), plus that member's currency. Accounts are not imported. The
   old `demo` account owned only an empty "Robot" project, so it is skipped and the import
   report says so.

To use port 80 instead, stop and disable Apache (`sudo systemctl disable --now apache2`), then
re-run the installer with `--port 80`.

**Updating** later: copy the new `app` folder to a separate folder on the Pi (e.g. `~/benchstock-new`,
not `/opt/benchstock` itself) and run `sudo bash deploy/install_pi.sh` from there, with no options.
The database and files are kept.

**Re-importing** the old dump by hand:

    sudo systemctl stop benchstock
    cd /opt/benchstock
    sudo .venv/bin/python manage.py import-mysql /path/to/ecdb.sql      # add --force if the database already has parts
    sudo chown -R benchstock:benchstock instance
    sudo systemctl start benchstock

Both phpMyAdmin exports and plain `mysqldump` files work. An empty database (the app creates one
at first start) is replaced automatically. A dump that contains no parts is rejected, and the
existing database is left unchanged.

## Admin commands

Run these on the Pi from `/opt/benchstock`, as the service user:

    cd /opt/benchstock
    sudo -u benchstock .venv/bin/python manage.py backup                    # manual backup
    sudo journalctl -u benchstock -f                                        # server log

Restoring a backup: `sudo systemctl stop benchstock`, copy the backup file over
`instance/benchstock.sqlite3`, delete any `benchstock.sqlite3-wal` / `-shm` files, then `sudo systemctl start benchstock`.

## Run on Windows (testing)

    .\run_local.ps1 -Media C:\dev\claude\ecdb\html

Then open http://127.0.0.1:8080. `-Media` serves the sheets, appnotes and images straight from
the old site folder.

## Page map (old → new)

The old `.php` addresses redirect automatically, so bookmarks keep working.

| Old                                  | New                          |
|--------------------------------------|------------------------------|
| index.php                            | /                            |
| category.php?cat= / ?subcat=         | /category/N, /subcategory/N  |
| component.php?view=N                 | /component/N                 |
| component_edit.php?edit=N            | /component/N/edit            |
| add.php, add_based.php?based=N       | /add, /add?based=N           |
| search.php?q=                        | /search?q=                   |
| shoplist.php                         | /shoplist                    |
| proj_list.php, proj_show/edit.php    | /projects/, /projects/N      |
| my.php                               | /settings                    |
| maintenance.php                      | /reference                   |
| reference_audit.php                  | /reference/audit (+ CSV)     |

Dropped: `test.php` (phpinfo), `oldcomponent.php`, `oldmaintenance.php`, `orig-maint.php`,
`reports.php` (empty stub; replaced by **Export CSV**), and the public-site leftovers
`terms.php` / `contact.php`, and everything to do with accounts (login, logout, register, the
user table and login history). The unused "measurement system" preference is gone too.
`login.php` and `logout.php` just redirect to the component list.

## New compared to the PHP site

- Search matches every word you type, across name, manufacturer, package, pins, location,
  comment, datasheet and category.
- A filter box above long tables narrows the list as you type.
- Category chips show how many parts each category has.
- Projects (BOM) show parts you are short of, and have a button that puts the missing
  quantities on the shopping list.
- The shopping list shows a total for each line.
- Export the whole inventory to CSV.
- Upload several files at once, by drag-and-drop. Existing files are never overwritten, and
  names that differ only by case are refused.
- "Save and add another" on the Add page.
- Quantities can't go below 0.
- Layout works on a phone, and there is a print layout.

## Security changes

- No accounts, so no passwords to leak. The old MD5 password hashes are not carried over.
- All SQL uses bound parameters. The old code built queries from strings and had injectable
  sort parameters.
- All page output is HTML-escaped automatically, which stops stored XSS through names or comments.
- Every form carries a CSRF token, and delete and +/- are POST-only. Without the token, any web
  page you visit could make your browser send "delete" requests to the Pi.
- File serving blocks path traversal. Uploads only accept PDF and image files, and never
  overwrite.
- Security headers are set. No database password is stored anywhere.
- Access control is your network. To limit who can reach it, firewall port 8080 on the Pi
  (e.g. `sudo ufw allow from 192.168.1.0/24 to any port 8080`), or change `--host 0.0.0.0`
  to `--host 127.0.0.1` in `/etc/systemd/system/benchstock.service` to allow only the Pi itself.

## Development

    .venv\Scripts\python.exe -m pytest -q

The tests cover every page, CSRF, upload rules, sorting and search injection,
the converter (including your real `..\html\ecdb.sql` when present) and the old URL redirects.
