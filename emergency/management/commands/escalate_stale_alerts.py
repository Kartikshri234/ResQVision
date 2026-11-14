"""python manage.py escalate_stale_alerts [--loop SECONDS]

Re-routes emergency alerts that no police station / hospital answered within
ALERT_RESPONSE_TIMEOUT_SECONDS (default 180) to the next nearest service.

The web app already runs this check whenever a signed-in user's screen polls for notifications, so nothing
needs scheduling while anybody is logged in. Run this command from cron / Task Scheduler (every minute), or
as a small always-on process with --loop 30, so alerts are also re-routed when nobody has the portal open.
"""
import time

from django.core.management.base import BaseCommand

from emergency import services


class Command(BaseCommand):
    help = "Re-route emergency alerts that nobody answered in time."

    def add_arguments(self, parser):
        parser.add_argument("--loop", type=int, default=0, metavar="SECONDS",
                            help="keep running and repeat every SECONDS seconds (default: run once)")

    def handle(self, *args, **opts):
        while True:
            handled = services.escalate_stale_alerts()
            self.stdout.write(f"{handled} unanswered alert(s) re-routed.")
            if not opts["loop"]:
                return
            try:
                time.sleep(max(1, opts["loop"]))
            except KeyboardInterrupt:
                return
