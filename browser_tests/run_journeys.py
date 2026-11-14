"""Chromium user-journey tests for ResQVision.

Runs against a throw-away SQLite database and media folder (the shared demo database is never
touched), so mutating actions such as Accept / Confirm / Sign out can be clicked for real.

    pip install playwright && python -m playwright install chromium
    python browser_tests/run_journeys.py            # headless
    python browser_tests/run_journeys.py --headed   # watch it run

Exit code is 0 only if every journey passes. Screenshots of failures go to browser_tests/artifacts/.
"""
import argparse
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
    from emergency.models import Accident, Alert, Hospital, PoliceStation, SystemSetting

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
    return {"alerted": alerted.pk, "police_alert": police_alert.pk, "pending": pending.pk}


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
    page.route(re.compile(r"https://(unpkg\.com|[a-c]\.tile\.openstreetmap\.org)/.*"), lambda r: r.abort())
    login(page, base, "j-police")
    page.wait_for_function("() => !!window.SC && !!SC.state.user", timeout=10000)
    page.goto(f"{base}/#/map")
    page.wait_for_selector("#screen *", timeout=10000)
    assert not errors, f"uncaught page errors: {errors}"


JOURNEYS = [
    j_invalid_login,
    j_police_accept_and_logout,
    j_police_reject_needs_reason,
    j_admin_confirms_pending_accident,
    j_hospital_login_dashboard,
    j_map_degrades_without_cdn,
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
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if detail:
            print("      " + detail.replace("\n", "\n      "))
    failed = [r for r in results if not r[1]]
    print("-" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} journeys passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
