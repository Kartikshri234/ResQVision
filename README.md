# ResQVision

ResQVision is a Django-based emergency response coordination system for
AI-detected road accidents. It receives verified accident events from an
external detection service, determines whether an event requires manual
verification, alerts nearby police stations and hospitals, and tracks the
response through resolution.

## What it provides

- Session-authenticated REST APIs for administrators, police, and hospital users.
- Accident ingestion from an AI detection service using an `X-API-Key` header.
- Confidence-based automatic confirmation or administrator verification.
- Distance-based selection of nearby police stations and accepting hospitals.
- Separate alert and response tracking for each notified organisation.
- Police team and hospital ambulance dispatch workflows.
- Status timeline and in-app notifications.
- Hospital bed and ambulance availability management.
- Camera, organisation, user, system-setting, and analytics administration.
- Demo data seeding and simulated CCTV accident events.

## Technology

- Python and Django 4.2-5.x
- Django REST Framework
- HTML, CSS, and vanilla JavaScript frontend with Leaflet maps
- Pillow for generated and uploaded accident evidence
- SQLite by default, with optional PostgreSQL configuration
- Django session authentication and the Django admin

## Project structure

```text
ResQVision/
├── manage.py
├── requirements.txt
├── .env.example              # Environment variables (API key, database)
├── accounts/                 # Custom user model and authentication APIs
├── emergency/                # Accident domain, APIs, services, and commands
├── web/                      # HTML / CSS / JavaScript frontend served by Django
│   ├── templates/web/index.html
│   └── static/web/{css,js}/  # app.css, core.js, screens_*.js, app.js
├── resqvision/               # Django project settings, URLs, and WSGI entry point
├── ai_service/               # Standalone AI detector (YOLO + ByteTrack) and test sender
│   ├── detector.py           # Accident logic (pure Python)
│   ├── run_detector.py       # Reads video/RTSP/webcam and reports accidents
│   ├── client.py             # Sends events to POST /api/ingest/
│   ├── send_test_event.py    # Fake event for testing without video or YOLO
│   └── requirements.txt      # Separate dependencies (ultralytics, opencv)
```

All frontend files (HTML template, CSS, JavaScript) live in one place, the
`web/` app. There are no separate project-level `static/` or `templates/`
folders.

The frontend is a single-page app (plain HTML, CSS, and JavaScript) served at
`/`. It talks to the REST API with the Django session cookie, shows different
screens for administrators, police, and hospital users, and uses Leaflet
(loaded from a CDN, so an internet connection is needed for the maps).

## Quick start

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure local settings

The application uses SQLite automatically when `DB_NAME` is not set. For a
local development server, the defaults are sufficient. Set a strong
`DJANGO_SECRET_KEY` and `AI_SERVICE_API_KEY` before exposing the application.

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django signing and session key |
| `DJANGO_DEBUG` | Debug mode; defaults to `1` |
| `ALLOWED_HOSTS` | Comma-separated hosts when debug is disabled |
| `AI_SERVICE_API_KEY` | Shared secret for `/api/ingest/` |
| `DB_NAME` | PostgreSQL database name; enables PostgreSQL mode |
| `DB_USER` | PostgreSQL user |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host, default `localhost` |
| `DB_PORT` | PostgreSQL port, default `5432` |

When using PostgreSQL, install the optional `psycopg2-binary` dependency
listed in `requirements.txt` and provide the database variables.

### 4. Initialize the database

The repository does not include migration files yet, so create them first
(this is needed once), then apply them:

```bash
python manage.py makemigrations accounts emergency
python manage.py migrate
```

Create the super admin (the only way to get the first account; there is no
public sign-up). It reads `SUPERADMIN_USERNAME`, `SUPERADMIN_EMAIL` and
`SUPERADMIN_PASSWORD` from `.env`, or prompts for them:

```bash
python manage.py create_superadmin
```

Sign in with it, then create every other account (admin, police, hospital,
ambulance) from **Admin > Services > Users**. Only the super admin can create
or change other admin accounts, and the super admin account cannot be deleted.

### 5. Load demo data (optional)

```bash
python manage.py seed_demo
```

This creates cameras, hospitals, police stations, ambulances, system
settings, sample accidents, and demo accounts. The command prints the demo
credentials when it completes:

```text
admin / Admin@123
police_cp / Police@123
hosp_aiims / Hospital@123
```

These credentials are for local demonstrations only and must be changed or
removed in any shared environment. To seed only reference data:

```bash
python manage.py seed_demo --no-accidents
```

### 6. Run the server

```bash
python manage.py runserver
```

Useful URLs:

- Web app (login and all dashboards): `http://127.0.0.1:8000/`
- Django admin: `http://127.0.0.1:8000/admin/`

## Accident workflow

1. The AI service submits an accident to `POST /api/ingest/`.
2. The service validates the API key, normalizes coordinates and confidence,
   and suppresses duplicate reports from the same camera within two minutes.
3. If confidence meets the configured threshold and automatic alerts are
   enabled, the accident is confirmed and nearby services are notified.
4. Otherwise, the accident enters `verification_pending` and an administrator
   must confirm it.
5. Police and hospital users accept or reject their alerts. Rejections can
   trigger escalation to the next available organisation.
6. Responders move alerts through accepted, dispatched, arrived, and resolved.
7. The accident is synchronized from its alerts and can be closed by an
   administrator.

By default, the system notifies up to two police stations and three accepting
hospitals within 25 km. If no service is within the configured radius, the
nearest available service is used so an event is not left without a target.

## API overview

All API paths are under `/api/`. Protected endpoints use Django session
authentication and require an authenticated user.

### Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login/` | Log in by username or email |
| POST | `/api/auth/logout/` | End the current session |
| GET/PATCH | `/api/auth/me/` | Read or update the current profile |
| POST | `/api/auth/password/` | Change the current password |
| POST | `/api/auth/forgot/` | Send a password-reset OTP |
| POST | `/api/auth/verify-otp/` | Verify an OTP |
| POST | `/api/auth/reset/` | Reset a password using an OTP |

### Accidents and response

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/dashboard/` | Role-specific dashboard metrics |
| GET | `/api/map/` | Active accidents and responder locations |
| GET | `/api/accidents/` | Scoped accident list with filters |
| GET | `/api/accidents/<id>/` | Accident detail and timeline |
| POST | `/api/accidents/<id>/confirm/` | Admin confirmation |
| POST | `/api/accidents/<id>/close/` | Admin closure |
| POST | `/api/alerts/<id>/respond/` | Accept, reject, dispatch, arrive, or resolve |
| GET/POST | `/api/ingest/` | Receive an AI-detected accident |
| POST | `/api/simulate/` | Admin-only simulated accident |

The accident list supports `view=all|new|active|history`, plus `q` and
`severity=low|medium|high` filters.

### Administration and operations

The remaining endpoints manage hospitals, police stations, ambulances,
cameras, users, notifications, analytics, and system settings:

```text
/api/hospitals/
/api/police-stations/
/api/hospital/me/
/api/ambulances/
/api/cameras/
/api/users/
/api/notifications/
/api/analytics/
/api/settings/
```

Create, update, and delete operations are role-restricted. Administrators
have global visibility; police and hospital users only see accidents linked
to their organisation.

## AI ingestion example

The endpoint accepts JSON or multipart form data. Coordinates can be supplied
directly or resolved from a registered `camera_id`.

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/ \
  -H "X-API-Key: replace-with-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "CAM-001",
    "confidence": 92,
    "severity": "high",
    "accident_type": "Car collision",
    "vehicles": "Car, Car",
    "people_count": 2,
    "location": "Vikas Marg, ITO"
  }'
```

The response contains the generated accident ID and its initial status.
Optional multipart fields include `snapshot` and `video`.

## AI detection service

The `ai_service/` folder is a separate program with its own dependencies. It
uses the same `AI_SERVICE_API_KEY` as Django and sends accidents to
`POST /api/ingest/`.

```bash
cd ai_service
pip install -r requirements.txt

# Test the AI -> Django -> alert path without video or YOLO (needs seed_demo data)
python send_test_event.py --camera-id CAM-001

# Run the real detector on a video file, webcam (0), or RTSP stream
python run_detector.py --source sample.mp4 --camera-id CAM-001 --show
python run_detector.py --source sample.mp4 --camera-id CAM-001 --dry-run
```

Use a camera ID registered in the admin app (it supplies the location), or
pass `--lat`, `--lng`, and `--location` for a mobile camera. If you change
`AI_SERVICE_API_KEY` for Django, set the same value in the terminal that runs
the detector, or pass `--api-key`. Django ignores a second report from the
same camera within two minutes.

## Simulation

After demo data has been loaded, simulate one or more AI events:

```bash
python manage.py simulate_accident
python manage.py simulate_accident --count 3
python manage.py simulate_accident --low-confidence
python manage.py simulate_accident --camera CAM-001
```

Normal simulations exercise the automatic alert pipeline. Low-confidence
simulations exercise the administrator verification path.

## Data model

The emergency app stores:

- `Accident`: detection evidence, location, confidence, severity, and status.
- `Alert`: one organisation-specific request per accident.
- `TimelineEvent`: human-readable status history.
- `Notification`: user-specific in-app notifications.
- `Camera`: detection sources and coordinates.
- `PoliceStation` and `Hospital`: responder organisations and availability.
- `Ambulance`: hospital vehicles and dispatch state.
- `SystemSetting`: alert radius, organisation limits, confidence threshold,
  and automatic-alert behavior.

The accounts app provides a custom `User` model with `admin`, `police`,
`hospital`, and `ambulance` roles, plus time-limited password-reset OTPs.

## Production considerations

Before deployment:

- Set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, explicit
  `ALLOWED_HOSTS`, and a strong `AI_SERVICE_API_KEY`.
- Configure PostgreSQL and a real email backend instead of the console email
  backend used for development.
- Do not expose demo credentials or development OTP responses.
- Configure HTTPS, secure cookies, CSRF settings, media storage, backups, and
  appropriate file-upload limits.
- Run `python manage.py collectstatic` and serve `/static/` and `/media/` from a web server.
- Run `python manage.py check --deploy` and apply migrations during release.

## License

No license file is currently included in this repository. Add a license
before distributing the project.
