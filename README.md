# ecDB 2 (Python/Flask + SQLite)

A rewrite of the ecDB PHP/MySQL site, which lives in `..\html`. It keeps all of your data
(parts, categories, projects, users), the datasheet, appnote and image folders, and the general
look of the old site. There is no PHP and no MySQL server any more.

## What's in the box

    ecdb/               the application (Flask)
      schema.sql        database layout (SQLite)
      templates/        HTML pages
      static/           CSS, JS, fonts, logo
    tools/mysql_to_sqlite.py   one-time converter for the old ecdb.sql dump
    manage.py           start the server + admin commands
    deploy/             Raspberry Pi installer and systemd units
    tests/              automated tests (pytest)
    config.example.py   optional settings (copy to instance/config.py)

Everything that belongs to *your* installation lives in `instance/`. Code updates never touch it.

    instance/ecdb.sqlite3          the database
    instance/media/sheets/         datasheets       (served at /sheets/...)
    instance/media/appnotes/       application notes (/appnotes/...)
    instance/media/img/parts/      part images       (/img/parts/...)
    instance/secret_key            session signing key (auto-generated)
    instance/backups/              daily backups

## Install on the Raspberry Pi

1. Copy this `app` folder to the Pi (e.g. `scp -r app pi@raspberrypi:~/ecdb-app`).
   Also copy `ecdb.sql` if the old site is on a different machine.
2. `..\html\ecdb.sql` is the current dump. Only if you edit data on the old site before
   switching over, make a new one:

       mysqldump -u ecdb -p ecdb > ecdb.sql

3. Install, import the dump and copy the reference files from the old web root:

       cd ~/ecdb-app
       sudo bash deploy/install_pi.sh --dump ~/ecdb.sql --files /var/www/html --port 8080

   This sets up `/opt/ecdb`, a Python virtual environment, a locked-down `ecdb` service user,
   the `ecdb` systemd service (starts at boot) and a daily database backup timer.
4. Open `http://<pi-address>:8080/`. Log in with your existing username and password.
   Your old MD5 password hash is upgraded to a modern salted hash the first time you log in.

To use port 80 instead, stop and disable Apache (`sudo systemctl disable --now apache2`), then
re-run the installer with `--port 80`.

**Updating** later: copy the new `app` folder over and run `sudo bash deploy/install_pi.sh`
again, with no options. The database and files are kept.

## Admin commands

Run these on the Pi from `/opt/ecdb`, as the service user:

    cd /opt/ecdb
    sudo -u ecdb .venv/bin/python manage.py user-list
    sudo -u ecdb .venv/bin/python manage.py user-passwd pwillard     # reset a password
    sudo -u ecdb .venv/bin/python manage.py user-add bob --first Bob --last Smith
    sudo -u ecdb .venv/bin/python manage.py user-delete demo          # remove the old demo account
    sudo -u ecdb .venv/bin/python manage.py backup                    # manual backup
    sudo journalctl -u ecdb -f                                        # server log

Restoring a backup: `sudo systemctl stop ecdb`, copy the backup file over
`instance/ecdb.sqlite3`, delete any `ecdb.sqlite3-wal` / `-shm` files, then `sudo systemctl start ecdb`.

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
`terms.php` / `contact.php`. Public registration is off: create users with `user-add`, or set
`ALLOW_REGISTRATION = True` in `instance/config.py`.

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

- Passwords: salted hashes (PBKDF2/scrypt via Werkzeug) replace unsalted MD5. Old hashes are
  upgraded when you log in.
- All SQL uses bound parameters. The old code built queries from strings and had injectable
  sort parameters.
- All page output is HTML-escaped automatically, which stops stored XSS through names or comments.
- Every form carries a CSRF token. Delete and +/- are POST-only.
- Every component and project is checked against the logged-in owner. The old delete and
  quantity actions didn't check.
- Datasheets, appnotes and images are only served to logged-in users. Path traversal is blocked.
- Login lockout: 5 failures locks that address for 5 minutes. Session cookies are HttpOnly and
  SameSite. Security headers are set. No database password is stored anywhere.

## Development

    .venv\Scripts\python.exe -m pytest -q

The tests cover every page, permissions, CSRF, upload rules, sorting and search injection,
the converter (including your real `..\html\ecdb.sql` when present) and the old URL redirects.
