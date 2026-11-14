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

Items marked closed were confirmed by the project owner running the commands in the last column. Items still open need the checks named there.

| Item | Status | What changed | Confirm with |
|---|---|---|---|
| 3. Narrow coverage | Mostly closed | `emergency/tests_workflow.py` already covers dispatch, escalation, admin CRUD, role scoping, notifications, analytics, settings. Still untested: file-upload edge cases beyond ingest checks, management commands | `python manage.py test` |
| 6. Dev secrets / OTP | Closed | `settings.py` only falls back to dev keys when `DJANGO_DEBUG=1`; otherwise it refuses to start. `dev_otp` is returned only in debug | `python manage.py check --deploy` with prod env |
| 1. Browser journeys | Closed (run and confirmed by project owner, 2026-11-15) | `browser_tests/run_journeys.py`: bad login, police accept + timeline + sign out, reject needs reason, admin confirm, hospital dashboard, map with CDN blocked. Uses a temp DB | `python browser_tests/run_journeys.py` |
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
| Administrator console | PASS (API regression) | `/api/admin/overview/` returns 200 for admins and 403 for non-admins; browser replay added as `j_admin_console_overview` (run `browser_tests/run_journeys.py` to confirm) |
| Police login and dashboard | PASS | Dashboard showed assigned incidents and notification count |
| Police accident detail | PASS | RV-1004 detail, response status, timeline tabs, and route link rendered |
| Hospital login and dashboard | PASS | Bed capacity, ambulance count, alerts, and active responses rendered |
| Hospital emergency alerts | PASS | Pending alerts and Accept/Reject controls rendered |

### Frontend issues observed (status: journeys added, awaiting a run)

1. **Browser replay of the admin console.** Added `j_admin_console_overview`: it signs in
   as an admin, opens `/admin/console`, and checks the task cards, both organisation tables
   (including the linked login account) and that no page error occurs. The overview endpoint
   keeps its API regression test.
2. **Map tiles from OpenStreetMap.** The tile layer now uses the single
   `https://tile.openstreetmap.org/{z}/{x}/{y}.png` host (the `{s}` subdomains are deprecated),
   sends a Referer (`referrerPolicy` plus `SECURE_REFERRER_POLICY`), and carries the required
   attribution link. The CSP already allowed that host. `j_map_tiles_request_shape` fakes the
   tiles locally and asserts every tile request is made with a Referer; it is skipped when
   Leaflet cannot be downloaded. `j_map_degrades_without_cdn` still covers the blocked case.
   Whether the real OSM servers accept the requests can only be seen on a machine with internet.
3. **Mutation workflows on isolated data.** The journeys run on a temporary database (never the
   demo one), so they now click the real controls:
   - `j_police_dispatch_to_resolved`: team preset survives the 8 s auto-refresh, dispatch, arrive, resolve.
   - `j_hospital_accept_and_assign_ambulance`: accept, refusal without a selection, selection
     survives the auto-refresh, dispatch, ambulance marked busy.
   - `j_admin_hospital_crud`: create, rejected coordinates, rejected `available > total`, edit,
     delete blocked for a hospital with alert history, delete of one without.
   - `j_admin_settings_save`: settings saved and read back from the database.
   - Earlier journeys already cover accept, reject (reason required) and admin confirm.
   Still not covered: user and camera CRUD, police-station CRUD, ambulance management screens.
