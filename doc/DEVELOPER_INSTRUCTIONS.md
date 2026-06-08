# Developer Instructions

## Project Shape

This repository is a Django site with a small React dashboard bundle.

- Django project: `radiantensemble/`
- Main app: `community/`
- React source: `frontend/src/home.jsx`
- React build output: `frontend/dist/`
- Shared docs: `doc/`
- Session history: `SESSION_NOTES.md`

## Development Workflow

Use these commands for a clean local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run build
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run backend tests with:

```bash
python manage.py test
```

Rebuild the React bundle after editing `frontend/src/home.jsx`:

```bash
npm run build
```

## Local Secret Configuration

Cloudflare Turnstile settings are loaded from `.env/config.py`, which is ignored by Git. Use `.env.example/config.py` as the shape of the file:

```python
CF_TURNSTILE_SITE_KEY = "..."
CF_TURNSTILE_SECRET_KEY = "..."
CF_TURNSTILE_ENABLED = True
```

Set `CF_TURNSTILE_ENABLED = False` only for local development when you need to test the contact form without external verification.

## Repository Safety

Never use `git clean` in this repository, including `git clean -fd`, `git clean -fdx`, or preview variants. Untracked local assets and symlinked files may be important.

## Data and Permissions

Django `User` and `Group` are the source of truth for accounts and group hierarchy. Use Django admin to manage staff/admin users and ordinary member users.

Posts and artifacts have these visibility modes:

- `public`: visible to everyone.
- `members`: visible to authenticated users. This is the default.
- `groups`: visible to selected Django groups.
- `private`: visible to the owner, staff, and explicitly selected users.

Message threads are only exposed through authenticated endpoints and only to participants.

## Transfer and Continuity

Keep `SESSION_NOTES.md` updated after meaningful design or implementation changes. Notes should capture why the change was made, not just that files changed.

When adding new features, prefer Django-native mechanisms first:

- Django auth and groups for identity and authorization.
- Django admin for early administrative workflows.
- Django migrations for database changes.
- Plain Django JSON views unless a larger API layer becomes necessary.

## Deployment Considerations

Before production deployment:

- Move `SECRET_KEY` and other secrets into environment variables.
- Set `DEBUG = False`.
- Configure durable file storage for `MEDIA_ROOT`.
- Configure HTTPS and secure cookie settings.
- Run `python manage.py collectstatic`.
- Add backups for sqlite3 or migrate to PostgreSQL if membership and artifact traffic outgrow sqlite.
