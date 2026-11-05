# Results Manager

Flask + Jinja + PostgreSQL results compilation tool (PWA). Operator at `/admin`, staff at `/staff`.

## First-time setup (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then edit .env: SECRET_KEY and your NEW database password
```
Generate a SECRET_KEY with: `python -c "import secrets; print(secrets.token_hex(32))"`

Create the database once (psql or pgAdmin): `CREATE DATABASE school_results;`

```powershell
flask --app run.py db upgrade            # builds all tables from the migration
flask --app run.py create-operator       # creates the first admin account
python run.py                            # http://127.0.0.1:5000
```

## Everyday workflow when you change a model
```powershell
flask --app run.py db migrate -m "describe change"
# open the new file in migrations/versions and read it
flask --app run.py db upgrade
pytest
```
Never use `db.create_all()` outside the tests. Commit `migrations/` to Git.

## Layout
- `app/models/` tables (no cross-imports; relationships use string names)
- `app/services/` business rules + permission checks (routes stay thin)
- `app/auth|operator|staff/` blueprints
- `tests/` run with `pytest`

## Where the build stands
Done: foundation, users/login, role guards, backend permission checks, per-student subjects,
audit log, PWA shell. Next: operator CRUD screens, score entry, calculation, workflow, reports.


## CSS: one stylesheet per page
```
app/static/css/base.css          shared: colours, top bar, sidebar, buttons, forms, tables, messages
app/static/css/pages/<page>.css  ONLY that page's own rules
```
- A template picks its stylesheet with one line at the top: `{% set page = "sessions" %}`.
  `base.html` then loads `base.css` + `pages/sessions.css` and gives `<main>` the class `page-sessions`.
- Every rule in a page file starts with `.page-<name>`, so it can never change another page (a test enforces this).
- Change ONE page: edit its file. Change EVERYTHING (e.g. button colour): edit `base.css`.
- No inline `style=""` in templates (a test enforces this too).
- 403, 404 and the offline page share `pages/error.css`.
- Adding a page? Create `templates/.../x.html` with `{% set page = "x" %}` and `static/css/pages/x.css`.
- If CSS ever looks "stuck": hard-refresh (Ctrl+Shift+R). The service worker is network-first for `/static/`.

## Enrollment rule
A student is in at most ONE class per academic session. This is enforced by the database
(`uq_student_enrollment_session`), not just by Python checks. Moving to a new session = Promote;
moving between arms in the same session = Transfer.
If `flask db upgrade` refuses because of old duplicates, list them with
`flask --app run.py check-enrollments`, remove the wrong enrollment on the class page, and upgrade again.


## Results engine and printing
- **Printed columns:** every assessment fills one of four columns on the result: 1'st CA, 2'nd CA, 3'rd CA, Exams
  (choose it under Classes > subject > Assessments, "Printed as"). Weights should add up to 100.
- **Entering scores:** class page > *Enter scores* (one student per card, swipe or Previous / Save & next), or
  student page > *Scores* for any past class/term (also for graduated or withdrawn students).
  Blank = not entered; 0 = a real zero. Totals round to a whole number (.5 up).
- **Automatic:** every save recomputes totals, grades, class highest/lowest, subject positions (1,2,2,4 ties),
  the student's average and overall position. Printing always recomputes first, so a sheet is never stale.
- **Lock / unlock:** class page > Lock term. Nobody (operator included) can change locked scores until unlocked.
- **Ratings:** the affective/psychomotor ratings are *suggested* from the student's average, stored once, and stay
  the same on every reprint. Edit any one in "Remarks & ratings" and it is never overwritten.
- **Print:** class page prints the whole class (one A4 page per student); student page prints one student.
  *Download PDF* is made on demand, sent to the browser and never stored.
- **Annual result:** average of the terms that have results (no annual template was supplied, so it reuses the
  terminal layout with 1st/2nd/3rd Term, Total and Average columns).
- **Wording:** every word on the sheet is in `app/report_labels.py`, copied from your template (typos included).
  Logo and signature: Settings page.

### PDF on Windows
`pip install -r requirements.txt` installs WeasyPrint, but it also needs the Pango/GTK libraries. On Windows follow
WeasyPrint's "Windows" install instructions. Until then the **Print** button (browser > Save as PDF) gives the
same A4 page. On a Linux server it works out of the box (`apt install libpango-1.0-0 libpangoft2-1.0-0`).

### Upgrading an existing database
`flask --app run.py db upgrade` then restart. Existing assessments are given printed columns in their order.
