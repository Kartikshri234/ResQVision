# Runtime Validation Report

**Generated**: 2026-11-13
**Target**: `D:\OneDrive\Desktop\programs\smartcrash_ai`

## Summary

| Step | Status | Exit code | Details |
|---|---:|---:|---|
| Django system check | PASS | 0 | No application configuration errors |
| Migration drift check | PASS | 0 | No pending model changes |
| Python compilation | PASS | 0 | `accounts`, `emergency`, `web`, `resqvision`, and `ai_service` compiled |
| Integration tests | PASS | 0 | 8 tests passed |
| Static collection | PASS | 0 | Static assets collect successfully |
| Live HTTP smoke | PASS | 0 | `/` and `/static/web/css/app.css` returned 200 |
| Browser smoke | PASS | 0 | Chromium loaded `/` and captured a screenshot |
| Deployment check | PASS with warnings | 0 | 5 Django security warnings |

## Test Coverage Added

- Authentication: login, session identity, logout, invalid credentials.
- AI ingestion: API-key rejection, persistence, alert creation, duplicate suppression.
- Response workflow: responder acceptance and admin dashboard read-back.
- Web shell: HTML response, CSRF cookie, missing-route behavior.

## Where the Project Lags Behind

### High priority

1. **Production security defaults are unsafe.** `DEBUG` defaults to enabled and
   `ALLOWED_HOSTS` defaults to `*` in
   [settings.py](D:/OneDrive/Desktop/programs/smartcrash_ai/resqvision/settings.py).
   `check --deploy` also reports missing HSTS, SSL redirect, secure session
   cookies, and secure CSRF cookies.
2. **No real browser journey suite exists.** The browser check only proves the
   shell renders; login, dashboard navigation, accident confirmation, responder
   actions, and logout are not verified in Chromium.
3. **No PostgreSQL/infrastructure test was run.** Docker is unavailable, so
   validation used Django's in-memory SQLite test database. PostgreSQL behavior,
   concurrency, and production database configuration remain unverified.

### Medium priority

4. **Coverage is still narrow.** Hospital/ambulance dispatch, escalation,
   password reset/OTP, admin CRUD, permissions across every role, file uploads,
   analytics, notifications, and management commands have no automated tests.
5. **No CI test command is present.** The project has no package/CI configuration
   that automatically runs the Django suite on every change.
6. **AI detector runtime is not fully validated.** Python modules compile, but
   YOLO/ByteTrack/video/RTSP execution and delivery against a live detector input
   were not exercised.

### Lower priority

7. **Frontend depends on a CDN map library.** Offline or restricted-network
   behavior is only a fallback message, not a tested degraded mode.
8. **Development secrets and OTP behavior need release controls.** The fallback
   API key and development secret are present in settings, and debug mode exposes
   OTPs in API responses.

## Environment

```text
Python: 3.14.10
Django: 5.2.19
Node.js: v24.19.0
Playwright: 1.65.0
Docker: unavailable (command missing)
Infra tier: fallback SQLite
Browser tier: Playwright smoke available
```

## Verdict

**Overall: PASS for the tested local scope; NEEDS SIGN-OFF before production.**
The core tested flows are green, but production security hardening, broader
endpoint coverage, PostgreSQL validation, and full browser journeys remain.

## Frontend User Walkthrough

| Role / flow | Result | Evidence |
|---|---:|---|
| Administrator login and logout | PASS | Demo admin session opened and returned to login after sign-out |
| Administrator dashboard | PASS | Metrics, recent accidents, map, and verification banner rendered |
| Administrator users, hospitals, police, cameras | PASS | Seeded records rendered in each management screen |
| Administrator system settings | PASS | Alert settings and AI-ingest endpoint rendered |
| Administrator live monitoring | PASS | Verification queue, active incidents, and cameras rendered |
| Administrator accidents and analytics | PASS | Filters, accident list, charts/statistics rendered |
| Administrator profile and notifications | PASS | Profile details and notification empty state rendered |
| Administrator console | **FAIL** | Route `#/admin/console` displayed `Request failed (500)` |
| Police login and dashboard | PASS | Dashboard showed assigned incidents and notification count |
| Police accident detail | PASS | RV-1004 detail, response status, timeline tabs, and route link rendered |
| Hospital login and dashboard | PASS | Bed capacity, ambulance count, alerts, and active responses rendered |
| Hospital emergency alerts | PASS | Pending alerts and Accept/Reject controls rendered |

### Frontend issues observed

1. **Admin console returns HTTP 500.** The UI replaces the page with
   “Something went wrong — Request failed (500)”. This is a release-blocking
   defect for the administrator landing page.
2. **Map tiles repeatedly fail/abort from OpenStreetMap tile URLs.** The map
   shell and markers render, but tile availability depends on external network
   access. Offline/degraded behavior needs a tested fallback.
3. **Mutation actions were not clicked against the shared demo database** to
   avoid changing seeded accident/user data. Accept, reject, dispatch, confirm,
   CRUD, and settings-save controls were verified as visible, but their complete
   browser workflows still need isolated test data.
