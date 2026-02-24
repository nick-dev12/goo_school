# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Aria (Goo-School) is a Django 5.2 school management platform. Single Django app `school_admin` with PostgreSQL backend.

### Services

| Service | Command | Port |
|---------|---------|------|
| PostgreSQL | `sudo pg_ctlcluster 16 main start` | 5432 |
| Django dev server | `source venv/bin/activate && python manage.py runserver 0.0.0.0:8000` | 8000 |

### Key caveats

- **Virtual environment**: Use `/workspace/venv/` (not `env/` which is a stale Windows venv committed to the repo).
- **Database**: PostgreSQL with DB `goo_school`, user `postgres`, password `Ludvanne`. Defaults are hardcoded in `school/settings.py`.
- **Migration conflicts**: Migrations 0023, 0024, 0034, 0049 have duplicate schema operations. On a fresh database, run migrations with auto-faking for failures (see setup notes below) or fake those four individually.
- **Django tests**: `tests.py` is empty. Running `python manage.py test` triggers model double-registration errors because the test runner discovers subpackages via both `school_admin.*` and `workspace.school_admin.*` paths. This is a pre-existing codebase issue.
- **Lint**: `flake8 school/ school_admin/ --max-line-length=120 --exclude=migrations` runs successfully (many pre-existing warnings).
- **Logs directory**: `mkdir -p logs media` must be run before starting the server (logging config writes to `logs/django.log` in production mode).
- **Login form fields**: The login form uses `email` (not `username`) and `conditions_acceptees` (not `accept_policy`).
- **Admin user setup**: A `CompteUser` must have `fonction='administrateur'` set (not just `type_compte`) to access the admin dashboard without redirect loops.
- **Start PostgreSQL before Django**: PostgreSQL must be running before the Django dev server starts.

### Standard commands

See `requirements.txt` for dependencies. Key commands:
- **Install deps**: `source venv/bin/activate && pip install -r requirements.txt`
- **Run dev server**: `source venv/bin/activate && python manage.py runserver 0.0.0.0:8000`
- **Run migrations**: `source venv/bin/activate && python manage.py migrate`
- **System check**: `source venv/bin/activate && python manage.py check`
- **Lint**: `source venv/bin/activate && flake8 school/ school_admin/ --max-line-length=120 --exclude=migrations`
