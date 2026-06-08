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

## Transfer Notes

Keep `SESSION_NOTES.md` current during development. Keep durable maintainer instructions in `doc/DEVELOPER_INSTRUCTIONS.md`.
