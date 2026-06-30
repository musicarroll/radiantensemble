# Radiant Ensemble Website

Django-based website for radiantensemble.com with a React-enabled home view, sqlite3 by default, Django-native authentication, member profiles, posts, private/group message threads, and shared musical artifacts.

## Local Setup

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

Open http://127.0.0.1:8000/.

For Turnstile-backed contact form testing, create `.env/config.py` using `.env.example/config.py` as the template.

## Core Concepts

- Django `User` and `Group` handle account management and member hierarchy.
- `MemberProfile` gives each user an optional personal page at `/members/<slug>/`.
- `Post` and `Artifact` default to members-only visibility, with public, group-scoped, and private options.
- `MessageThread` and `Message` provide members-only direct and group messaging foundations.
- Uploaded files are stored under `media/` in development and tracked by the database.
- React is built by Vite into `frontend/dist/assets/home.js`, which Django serves through static files.

## Artifact Metadata Harvesting

Artifact uploads record integrity metadata when the file is received:

- Original filename from the browser upload.
- Stored filename assigned by Django storage.
- MIME type detected with `python-magic` when available, falling back to Python's `mimetypes`.
- File size in bytes.
- SHA-256 checksum of the file contents.
- HMAC-SHA-256 metadata signature.

SHA-256 is used because it is widely supported and suitable for detecting accidental or unauthorized file changes. It verifies file integrity only; it does not prove authorship. The HMAC signature protects the metadata fields from unnoticed changes. Django generates the HMAC with `ARTIFACT_METADATA_HMAC_KEY`, which should be set in production:

```bash
ARTIFACT_METADATA_HMAC_KEY="replace-with-a-long-random-secret"
```

Development falls back to Django's `SECRET_KEY` when this variable is not set.

Uploaded filenames are preserved only as metadata and must not be trusted for filesystem paths. Django storage should use safe generated storage names, and uploaded files must never be executed.

Future storage workflow:

```text
Upload
  ↓
Harvest metadata
  ↓
Save metadata
  ↓
Transfer to Nextcloud (future)
  ↓
Periodically recompute SHA-256
  ↓
Compare against original checksum
  ↓
Raise warning if mismatch
```

Future enhancements may include page counts, media duration, image dimensions, MusicXML parsing, EXIF extraction, and public/private key digital signatures.

## Transfer Notes

Keep `SESSION_NOTES.md` current during development. Keep durable maintainer instructions in `doc/DEVELOPER_INSTRUCTIONS.md`.
