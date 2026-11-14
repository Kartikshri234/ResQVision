# Runtime Validation Report

**Generated**: 2026-11-14
**Target**: `D:\OneDrive\Desktop\programs\smartcrash_ai`

## Summary

| Step | Status | Exit code | Details |
|---|---:|---:|---|
| Django system check | PASS | 0 | No application configuration errors |
| Migration drift check | PASS | 0 | No pending model changes |
| Python compilation | PASS | 0 | `accounts`, `emergency`, `web`, `resqvision`, and `ai_service` compiled |
| Integration tests | PASS | 0 | 11 tests passed |
| Static collection | PASS | 0 | Static assets collect successfully |
| Live HTTP smoke | PASS | 0 | `/` and `/static/web/css/app.css` returned 200 |
| Browser smoke | PASS | 0 | Chromium loaded `/` and captured a screenshot |
| Deployment check | PASS | 0 | Production security checks are clean |
| Frontend JavaScript syntax | PASS | 0 | `core.js` and `screens_admin.js` parsed successfully |

## Test Coverage Added

- Authentication: login, session identity, logout, invalid credentials.
- AI ingestion: API-key rejection, persistence, alert creation, duplicate suppression.
- Response workflow: responder acceptance and admin dashboard read-back.
- Admin console API: overview sections, organization data, and non-admin rejection.
- OTP password reset: code consumption and new-password login credential.
- Web shell: HTML response, CSRF cookie, missing-route behavior.
- Offline map behavior: visible degraded state when Leaflet or map tiles are unavailable.

## Follow-up status (2026-11-14, after code review)

Nothing below was executed by the reviewer; run the commands in the last column to confirm.

| Item | Status | What changed | Confirm with |
|---|---|---|---|
| 3. Narrow coverage | Mostly closed | `emergency/tests_workflow.py` already covers dispatch, escalation, admin CRUD, role scoping, notifications, analytics, settings. Still untested: file-upload edge cases beyond ingest checks, management commands | `python manage.py test` |
| 6. Dev secrets / OTP | Closed | `settings.py` only falls back to dev keys when `DJANGO_DEBUG=1`; otherwise it refuses to start. `dev_otp` is returned only in debug | `python manage.py check --deploy` with prod env |
| 1. Browser journeys | Written, not yet run | `browser_tests/run_journeys.py`: bad login, police accept + timeline + sign out, reject needs reason, admin confirm, hospital dashboard, map with CDN blocked. Uses a temp DB | `python browser_tests/run_journeys.py` |
| 2. PostgreSQL | Open | `alert_respond` now runs in one transaction with a row lock (`select_for_update(of=("self",))`) and locks the ambulance it assigns. No-op on SQLite, so only a Postgres run proves it | CI `postgres` job |
| 4. AI detector runtime | Open | Unchanged | `ai_service/run_detector.py --dry-run` on a sample video |
| 5. CDN map | Open | Unchanged (degraded state exists) | Vendoring Leaflet is the remaining fix |

Also fixed: README listed wrong auth paths, claimed migrations were missing, and said debug defaults on.

## Where the Project Lags Behind

### High priority

1. **No real browser journey suite exists.** The browser check only proves the
   shell renders; login, dashboard navigation, accident confirmation, responder
   actions, and logout are not verified in Chromium.
2. **No local PostgreSQL test was run.** Docker is unavailable, so
   validation used Django's in-memory SQLite test database. PostgreSQL behavior,
   concurrency, and production database behavior are covered by the new CI
   PostgreSQL job but still require a successful hosted CI run.

### Medium priority

3. **Coverage is still narrow.** Hospital/ambulance dispatch, escalation,
   admin CRUD, permissions across every role, file uploads,
   analytics, notifications, and management commands have no automated tests.
4. **AI detector runtime is not fully validated.** Python modules compile, but
   YOLO/ByteTrack/video/RTSP execution and delivery against a live detector input
   were not exercised.

### Lower priority

5. **Frontend still depends on a CDN map library and external tiles.** The UI now
   preserves incident coordinates and displays a clear degraded-state notice when
   Leaflet or OpenStreetMap tiles cannot load.
6. **Development secrets and OTP behavior need release controls.** The fallback
   API key and development secret are present in settings, and debug mode exposes
   OTPs in API responses.

## Remediation completed

- Production defaults now use `DEBUG=False`; hosts must be configured explicitly.
- Production enables SSL redirect, one-year HSTS, secure session/CSRF cookies,
  and `SameSite=Lax`.
- Added `.github/workflows/test.yml` with SQLite and PostgreSQL test jobs.
- Added admin overview and OTP reset regression tests.
- Admin overview API was reproduced successfully with seeded data; the previous
  console failure is now covered by an authenticated API test.
- Map failures now degrade gracefully instead of leaving an unexplained blank map.

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
Production security and CI configuration are now addressed. Hosted PostgreSQL
execution, broader endpoint coverage, AI runtime validation, and full browser
journeys remain outstanding.

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
| Administrator console | PASS (API regression) | `/api/admin/overview/` returns 200 for admins and 403 for non-admins; browser replay still pending |
| Police login and dashboard | PASS | Dashboard showed assigned incidents and notification count |
| Police accident detail | PASS | RV-1004 detail, response status, timeline tabs, and route link rendered |
| Hospital login and dashboard | PASS | Bed capacity, ambulance count, alerts, and active responses rendered |
| Hospital emergency alerts | PASS | Pending alerts and Accept/Reject controls rendered |

### Frontend issues observed

1. **Browser replay of the admin console is still pending.** The underlying
   overview endpoint now has authenticated regression coverage and returns the
   expected console sections.
2. **Map tiles may still fail/abort from OpenStreetMap tile URLs.** The map
   shell and markers remain usable, and the UI now reports the degraded state
   with coordinates when tiles or Leaflet are unavailable.
3. **Mutation actions were not clicked against the shared demo database** to
   avoid changing seeded accident/user data. Accept, reject, dispatch, confirm,
   CRUD, and settings-save controls were verified as visible, but their complete
   browser workflows still need isolated test data.
