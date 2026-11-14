"""Chromium user-journey tests for ResQVision.

Runs against a throw-away SQLite database and media folder (the shared demo database is never
touched), so mutating actions such as Accept / Confirm / Sign out can be clicked for real.

    pip install playwright && python -m playwright install chromium
    python browser_tests/run_journeys.py            # headless
    python browser_tests/run_journeys.py --headed   # watch it run

Exit code is 0 only if every journey passes. Screenshots of failures go to browser_tests/artifacts/.
"""
import argparse
import base64
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
PW = "Passw0rd!x9"

# 1x1 transparent PNG, served in place of real OpenStreetMap tiles so the tile journey needs no tile server.
TILE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


class SkipJourney(Exception):
    """Raised when a journey cannot run in this environment (for example Leaflet cannot be downloaded)."""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def setup_django(tmp):
    """Point Django at a temp DB, migrate it and create a small fixed data set."""
    os.environ.update({
        "DJANGO_DEBUG": "1",
        "SQLITE_PATH": str(Path(tmp) / "journeys.sqlite3"),
        "MEDIA_ROOT": str(Path(tmp) / "media"),
        "ALLOWED_HOSTS": "localhost,127.0.0.1",
        "DJANGO_SETTINGS_MODULE": "resqvision.settings",
        # Playwright's sync API runs an event loop in this thread; Django would otherwise refuse the
        # direct ORM reads/writes the journeys use to check results. Safe here: single-threaded test script.
        "DJANGO_ALLOW_ASYNC_UNSAFE": "true",
    })
    os.environ.pop("DB_NAME", None)  # never run these against PostgreSQL
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)

    from accounts.models import User
    from emergency.models import Accident, Alert, Ambulance, Hospital, PoliceStation, SystemSetting

    SystemSetting.get()
    station = PoliceStation.objects.create(name="Journey Police", latitude=12.9716, longitude=77.5946)
    hospital = Hospital.objects.create(name="Journey Hospital", latitude=12.972, longitude=77.595,
                                       total_beds=10, available_beds=5)
    User.objects.create_superuser("j-admin", "j-admin@example.com", PW)
    User.objects.create_user("j-police", password=PW, role="police", is_approved=True,
                             email="j-police@example.com", police_station=station)
    User.objects.create_user("j-hosp", password=PW, role="hospital", is_approved=True,
                             email="j-hosp@example.com", hospital=hospital)
    alerted = Accident.objects.create(latitude=12.9716, longitude=77.5946, location="Journey Road",
                                      confidence=0.95, status="alert_sent", severity="high")
    police_alert = Alert.objects.create(accident=alerted, kind="police", police_station=station, distance_km=0.1)
    pending = Accident.objects.create(latitude=12.97, longitude=77.59, location="Needs Review",
                                      confidence=0.4, status="verification_pending")
    # Already-accepted police alert: the dispatch -> arrive -> resolve journey starts here.
    dispatch_acc = Accident.objects.create(latitude=12.9718, longitude=77.5950, location="Dispatch Road",
                                           confidence=0.93, status="accepted", severity="high")
    dispatch_alert = Alert.objects.create(accident=dispatch_acc, kind="police", police_station=station,
                                          distance_km=0.2, status="accepted")
    # Pending hospital alert plus one free ambulance: the accept -> assign ambulance journey starts here.
    hosp_acc = Accident.objects.create(latitude=12.9722, longitude=77.5955, location="Hospital Road",
                                       confidence=0.91, status="alert_sent", severity="high")
    hosp_alert = Alert.objects.create(accident=hosp_acc, kind="hospital", hospital=hospital, distance_km=0.1)
    ambulance = Ambulance.objects.create(hospital=hospital, vehicle_number="JRN-AMB-1", driver_name="Journey Driver")
    return {"alerted": alerted.pk, "police_alert": police_alert.pk, "pending": pending.pk,
            "dispatch_acc": dispatch_acc.pk, "dispatch_alert": dispatch_alert.pk,
            "hosp_acc": hosp_acc.pk, "hosp_alert": hosp_alert.pk, "ambulance": ambulance.pk}


def start_server(port, tmp):
    log = open(Path(tmp) / "server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=ROOT, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
    proc.log_file = log
    url = f"http://127.0.0.1:{port}/static/web/css/app.css"
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError("Server exited early:\n" + (Path(tmp) / "server.log").read_text())
        try:
            urllib.request.urlopen(url, timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("Server did not start in 30 s")


def login(page, base, username, password=PW):
    page.goto(base + "/#/login")
    page.wait_for_selector('form[data-form="login"]')
    page.fill('form[data-form="login"] input[name=username]', username)
    page.fill('form[data-form="login"] input[name=password]', password)
    page.click('form[data-form="login"] button[type=submit]')


def wait_signed_in(page):
    page.wait_for_function("() => !location.hash.startsWith('#/login') && !!window.SC && !!SC.state.user",
                           timeout=10000)


def clear_toasts(page):
    """Remove old toasts so a later wait cannot be satisfied by a message from an earlier step."""
    page.evaluate("() => { const t = document.getElementById('toasts'); if (t) t.innerHTML = ''; }")


def sign_out(page, base):
    page.goto(base + "/#/profile")
    page.wait_for_selector('[data-act="logout"]')
    page.click('[data-act="logout"]')
    # The app may ask for confirmation before signing out.
    try:
        page.wait_for_selector('form[data-form="login"]', timeout=3000)
        return
    except Exception:
        confirm = page.locator("#modal-root button", has_text=re.compile(r"sign out|log ?out|yes|confirm", re.I))
        if confirm.count():
            confirm.first.click()
    page.wait_for_selector('form[data-form="login"]', timeout=8000)


# ---------------------------------------------------------------- journeys
def j_invalid_login(page, base, ids):
    login(page, base, "j-police", "wrong-password")
    page.wait_for_selector("#toasts *", timeout=8000)
    assert page.locator('form[data-form="login"]').count() == 1, "login form should stay on screen"
    assert page.evaluate("() => !SC.state.user"), "no session may be created for bad credentials"


def j_police_accept_and_logout(page, base, ids):
    from emergency.models import Alert
    login(page, base, "j-police")
    wait_signed_in(page)
    page.goto(f"{base}/#/accident/{ids['alerted']}")
    page.wait_for_selector('[data-act="accept-alert"]', timeout=10000)
    page.click('[data-act="accept-alert"]')
    page.wait_for_selector('[data-act="accept-alert"]', state="detached", timeout=10000)
    assert Alert.objects.get(pk=ids["police_alert"]).status == "accepted"
    page.goto(f"{base}/#/accident/{ids['alerted']}/timeline")
    page.wait_for_selector("text=accepted the incident", timeout=10000)
    sign_out(page, base)
    assert page.evaluate("() => !SC.state.user"), "session should be cleared after sign out"


def j_police_reject_needs_reason(page, base, ids):
    from emergency.models import Alert
    Alert.objects.filter(pk=ids["police_alert"]).update(status="pending", reject_reason="")
    login(page, base, "j-police")
    wait_signed_in(page)
    page.goto(f"{base}/#/accident/{ids['alerted']}")
    page.wait_for_selector('[data-act="reject-alert"]', timeout=10000)
    page.click('[data-act="reject-alert"]')
    page.wait_for_selector("#modal-root textarea[name=reason]")
    page.locator("#modal-root button[type=submit]").click()  # empty reason: browser validation blocks it
    assert Alert.objects.get(pk=ids["police_alert"]).status == "pending"
    page.fill("#modal-root textarea[name=reason]", "No units available")
    page.locator("#modal-root button[type=submit]").click()
    page.wait_for_function(
        "() => !document.querySelector('#modal-root textarea[name=reason]')", timeout=10000)
    status = Alert.objects.get(pk=ids["police_alert"]).status
    assert status == "rejected", f"expected rejected, got {status}"


def j_admin_confirms_pending_accident(page, base, ids):
    from emergency.models import Accident
    login(page, base, "j-admin")
    wait_signed_in(page)
    page.goto(f"{base}/#/accident/{ids['pending']}")
    page.wait_for_selector('[data-act="acc-op"][data-op="confirm"]', timeout=10000)
    page.click('[data-act="acc-op"][data-op="confirm"]')
    page.locator("#modal-root button", has_text=re.compile(r"confirm", re.I)).first.click()
    page.wait_for_function(
        "() => !document.querySelector('[data-act=\"acc-op\"][data-op=\"confirm\"]')", timeout=10000)
    status = Accident.objects.get(pk=ids["pending"]).status
    assert status != "verification_pending", f"accident still {status}"


def j_hospital_login_dashboard(page, base, ids):
    login(page, base, "j-hosp")
    wait_signed_in(page)
    page.wait_for_selector("text=Journey Hospital", timeout=10000)


def j_map_degrades_without_cdn(page, base, ids):
    """Leaflet and tiles are blocked: the page must not crash and must still render content."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(re.compile(r"https://(unpkg\.com|([a-c]\.)?tile\.openstreetmap\.org)/.*"), lambda r: r.abort())
    login(page, base, "j-police")
    page.wait_for_function("() => !!window.SC && !!SC.state.user", timeout=10000)
    page.goto(f"{base}/#/map")
    page.wait_for_selector("#screen *", timeout=10000)
    assert not errors, f"uncaught page errors: {errors}"


def j_map_tiles_request_shape(page, base, ids):
    """Tile requests must go to tile.openstreetmap.org and carry a Referer (OSM refuses tiles without one).

    Needs Leaflet from unpkg.com, so it is skipped when that cannot be downloaded. Tiles are faked locally.
    """
    seen = []

    def handle(route):
        seen.append(route.request.all_headers())
        route.fulfill(status=200, content_type="image/png", body=TILE_PNG)

    page.route(re.compile(r"https://([a-c]\.)?tile\.openstreetmap\.org/.*"), handle)
    login(page, base, "j-admin")
    wait_signed_in(page)
    page.goto(f"{base}/#/admin/home")
    try:
        page.wait_for_function("() => !!window.L", timeout=8000)
    except Exception:
        raise SkipJourney("Leaflet could not be loaded from unpkg.com (no internet?)")
    page.wait_for_selector("#map .leaflet-tile", state="attached", timeout=10000)
    page.wait_for_function("() => document.querySelectorAll('#map .leaflet-tile-loaded').length > 0", timeout=10000)
    assert seen, "no tile request reached tile.openstreetmap.org"
    assert all(h.get("referer") for h in seen), f"tile requests without a Referer: {seen[:1]}"
    assert page.locator("#map .map-offline").count() == 0, "degraded-map notice shown although tiles loaded"


def j_admin_console_overview(page, base, ids):
    """Browser replay of the administrator console (previously only its API was tested)."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    login(page, base, "j-admin")
    wait_signed_in(page)
    page.goto(f"{base}/#/admin/console")
    page.wait_for_selector("text=Administrator tasks", timeout=10000)
    page.wait_for_selector("text=Police stations - what they are doing")
    page.wait_for_selector("text=Hospitals - what they are doing")
    page.wait_for_selector("table.tbl td:has-text('Journey Police')")
    page.wait_for_selector("table.tbl td:has-text('j-police')")   # the linked login account
    page.wait_for_selector("table.tbl td:has-text('Journey Hospital')")
    assert page.locator("text=Something went wrong").count() == 0
    assert not errors, f"uncaught page errors: {errors}"


def j_police_dispatch_to_resolved(page, base, ids):
    from emergency.models import Alert
    login(page, base, "j-police")
    wait_signed_in(page)
    page.goto(f"{base}/#/police/dispatch/{ids['dispatch_acc']}")
    form = 'form[data-form="dispatch-team"]'
    page.wait_for_selector(form)
    page.click('[data-act="team-preset"][data-team="Patrol Team Bravo"]')
    page.wait_for_timeout(9000)   # longer than one 8 s auto-refresh: the chosen team must survive it
    assert page.input_value(f"{form} input[name=team_name]") == "Patrol Team Bravo", "auto-refresh wiped the team"
    page.click(f"{form} button[type=submit]")
    page.wait_for_selector('[data-act="set-state"][data-action="arrive"]')
    al = Alert.objects.get(pk=ids["dispatch_alert"])
    assert (al.status, al.team_name) == ("dispatched", "Patrol Team Bravo"), (al.status, al.team_name)
    page.click('[data-act="set-state"][data-action="arrive"]')
    page.wait_for_selector('[data-act="set-state"][data-action="resolve"]')
    assert Alert.objects.get(pk=ids["dispatch_alert"]).status == "arrived"
    page.click('[data-act="set-state"][data-action="resolve"]')
    page.wait_for_selector("text=Response completed")
    assert Alert.objects.get(pk=ids["dispatch_alert"]).status == "resolved"


def j_hospital_accept_and_assign_ambulance(page, base, ids):
    from emergency.models import Alert, Ambulance
    login(page, base, "j-hosp")
    wait_signed_in(page)
    page.goto(f"{base}/#/hospital/respond/{ids['hosp_acc']}")
    page.wait_for_selector('[data-act="accept-alert"]')
    page.click('[data-act="accept-alert"]')
    page.wait_for_selector("#picks .pick")
    # Dispatching without choosing an ambulance must be refused.
    clear_toasts(page)
    page.click('[data-act="dispatch-amb"]')
    page.wait_for_selector("#toasts .toast.error")
    assert Alert.objects.get(pk=ids["hosp_alert"]).status == "accepted"
    page.click("#picks .pick")
    page.wait_for_timeout(9000)   # longer than one 8 s auto-refresh: the selection must survive it
    assert page.locator("#picks .pick.sel").count() == 1, "auto-refresh wiped the ambulance selection"
    page.click('[data-act="dispatch-amb"]')
    page.wait_for_selector('[data-act="set-state"][data-action="arrive"]')
    al = Alert.objects.get(pk=ids["hosp_alert"])
    assert al.status == "dispatched" and al.ambulance_id == ids["ambulance"], (al.status, al.ambulance_id)
    assert Ambulance.objects.get(pk=ids["ambulance"]).status == "dispatched"


def j_admin_hospital_crud(page, base, ids):
    from emergency.models import Hospital
    login(page, base, "j-admin")
    wait_signed_in(page)
    page.goto(f"{base}/#/admin/hospitals")
    page.wait_for_selector('[data-act="crud-add"]')
    modal = "#modal-root"

    def fill_form(**values):
        for name, value in values.items():
            page.fill(f"{modal} input[name={name}]", str(value))

    # Impossible coordinates are refused by the server and nothing is created.
    page.click('[data-act="crud-add"]')
    fill_form(name="Bad Coords", latitude=999, longitude=77.6, total_beds=5, available_beds=2)
    clear_toasts(page)
    page.click(f"{modal} button[type=submit]")
    page.wait_for_selector("#toasts .toast.error")
    assert not Hospital.objects.filter(name="Bad Coords").exists()
    page.click(f'{modal} [data-act="close-modal"]')

    # Create.
    page.click('[data-act="crud-add"]')
    fill_form(name="Journey Clinic", latitude=12.98, longitude=77.6, total_beds=8, available_beds=4)
    page.click(f"{modal} button[type=submit]")
    page.wait_for_selector(".list .card:has-text('Journey Clinic')")
    assert Hospital.objects.filter(name="Journey Clinic", total_beds=8).exists()

    # Edit: more available beds than total is refused, then a valid edit is saved.
    card = ".list .card:has-text('Journey Clinic')"
    page.click(f'{card} [data-act="crud-edit"]')
    fill_form(available_beds=99)
    clear_toasts(page)
    page.click(f"{modal} button[type=submit]")
    page.wait_for_selector("#toasts .toast.error")
    assert Hospital.objects.get(name="Journey Clinic").available_beds == 4
    fill_form(total_beds=12, available_beds=6)
    page.click(f"{modal} button[type=submit]")
    page.wait_for_function("() => !document.querySelector('#modal-root input[name=name]')")
    clinic = Hospital.objects.get(name="Journey Clinic")
    assert (clinic.total_beds, clinic.available_beds) == (12, 6), (clinic.total_beds, clinic.available_beds)

    # A hospital that has alert history cannot be deleted.
    page.click(".list .card:has-text('Journey Hospital') [data-act=\"crud-del\"]")
    clear_toasts(page)
    page.click("#confirm-ok")
    page.wait_for_selector("#toasts .toast.error")
    assert Hospital.objects.filter(name="Journey Hospital").exists(), "hospital with history was deleted"
    page.locator(f'{modal} [data-act="close-modal"]').first.click()

    # One without history can.
    page.click(f'{card} [data-act="crud-del"]')
    page.click("#confirm-ok")
    page.wait_for_function("() => !document.querySelector('#modal-root .modal')")
    page.wait_for_function("() => ![...document.querySelectorAll('.list .card')].some(c => c.textContent.includes('Journey Clinic'))")
    assert not Hospital.objects.filter(name="Journey Clinic").exists()


def j_admin_settings_save(page, base, ids):
    from emergency.models import SystemSetting
    login(page, base, "j-admin")
    wait_signed_in(page)
    page.goto(f"{base}/#/admin/settings")
    form = 'form[data-form="sys-settings"]'
    page.wait_for_selector(form)
    page.fill(f"{form} input[name=min_confidence]", "75")
    page.fill(f"{form} input[name=notify_radius_km]", "30")
    page.fill(f"{form} input[name=max_police]", "3")
    page.fill(f"{form} input[name=max_hospitals]", "4")
    clear_toasts(page)
    page.click(f"{form} button[type=submit]")
    page.wait_for_selector("#toasts .toast.success")
    s = SystemSetting.get()
    assert (round(s.min_confidence, 2), s.notify_radius_km, s.max_police, s.max_hospitals) == (0.75, 30, 3, 4), \
        (s.min_confidence, s.notify_radius_km, s.max_police, s.max_hospitals)


JOURNEYS = [
    j_invalid_login,
    j_police_accept_and_logout,
    j_police_reject_needs_reason,
    j_admin_confirms_pending_accident,
    j_hospital_login_dashboard,
    j_map_degrades_without_cdn,
    j_map_tiles_request_shape,
    j_admin_console_overview,
    j_police_dispatch_to_resolved,
    j_hospital_accept_and_assign_ambulance,
    j_admin_hospital_crud,
    j_admin_settings_save,
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(exist_ok=True)
    results = []
    # Windows cannot delete an open SQLite file, so close our connection first and tolerate a late release.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        ids = setup_django(tmp)
        port = free_port()
        server = start_server(port, tmp)
        base = f"http://127.0.0.1:{port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not args.headed)
                for journey in JOURNEYS:
                    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                    ctx.set_default_timeout(10000)
                    page = ctx.new_page()
                    try:
                        journey(page, base, ids)
                        results.append((journey.__name__, True, ""))
                    except SkipJourney as exc:
                        results.append((journey.__name__, None, str(exc)))
                    except Exception as exc:  # noqa: BLE001 - report every failure, keep going
                        shot = ARTIFACTS / f"{journey.__name__}.png"
                        try:
                            page.screenshot(path=str(shot))
                        except Exception:
                            pass
                        results.append((journey.__name__, False, f"{exc!r}\n{traceback.format_exc(limit=3)}"))
                    finally:
                        ctx.close()
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
            server.log_file.close()
            from django.db import connections
            connections.close_all()

    print("\nBrowser journey results")
    print("-" * 60)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'SKIP' if ok is None else 'FAIL'}  {name}")
        if detail:
            print("      " + detail.replace("\n", "\n      "))
    failed = [r for r in results if r[1] is False]
    skipped = [r for r in results if r[1] is None]
    print("-" * 60)
    print(f"{len(results) - len(failed) - len(skipped)}/{len(results)} journeys passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
