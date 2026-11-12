"""python manage.py simulate_accident [--count 3] [--low-confidence] [--camera CAM-001]"""
from django.core.management.base import BaseCommand, CommandError

from emergency import services
from emergency.models import Camera


class Command(BaseCommand):
    help = "Simulate AI-detected accidents (runs the full alert pipeline)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1)
        parser.add_argument("--low-confidence", action="store_true", help="Force admin verification.")
        parser.add_argument("--camera", help="Camera ID, e.g. CAM-001")

    def handle(self, *args, **o):
        cam = None
        if o["camera"]:
            cam = Camera.objects.filter(camera_id=o["camera"]).first()
            if not cam:
                raise CommandError(f"No camera with ID {o['camera']}")
        for _ in range(o["count"]):
            try:
                a = services.simulate_accident(camera=cam, low_confidence=o["low_confidence"])
            except ValueError as e:
                raise CommandError(str(e))
            self.stdout.write(f"{a.accident_id}  {a.accident_type}  {round(a.confidence * 100)}%  -> {a.status}")
