"""Send a fake accident event to the Django backend (no video, YOLO or OpenCV needed).

Use it to test the AI -> Django -> notification path before running the real detector.
Run the Django server and `python manage.py seed_demo` first, then:
    python send_test_event.py --camera-id CAM-001
    python send_test_event.py --camera-id CAM-002 --severity high --confidence 0.93
    python send_test_event.py --camera-id CAM-004 --confidence 0.50      # below threshold -> admin verification

Note: the backend ignores a second event from the same camera within 2 minutes (duplicate suppression).
"""
import argparse
import os
import struct
import tempfile
import zlib
from datetime import datetime, timezone

from client import DjangoClient

COLORS = {"high": (217, 45, 32), "medium": (247, 144, 9), "low": (18, 183, 106)}
TYPES = {"car_collision": "Car and Car", "motorcycle_accident": "Motorcycle and Car", "multi_vehicle": "Truck, Car and Car",
         "vehicle_overturn": "Truck", "pedestrian_collision": "Car and Pedestrian"}


def make_png(path: str, color, width: int = 640, height: int = 360) -> None:
    """Write a simple placeholder snapshot (dark background with a coloured box) using only the standard library."""
    bg = bytes((27, 42, 65))
    fg = bytes(color)
    x1, y1, x2, y2, t = 190, 150, 450, 270, 5
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter type 0 (none)
        for x in range(width):
            on_box = (x1 <= x <= x2 and y1 <= y <= y2) and not (x1 + t <= x <= x2 - t and y1 + t <= y <= y2 - t)
            rows += fg if on_box else bg

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--camera-id", required=True)
    p.add_argument("--api-url", default=os.environ.get("RESQVISION_API_URL", "http://127.0.0.1:8000"))
    p.add_argument("--api-key", default=os.environ.get("AI_SERVICE_API_KEY", "dev-ai-key-change-me"))
    p.add_argument("--severity", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--type", default="car_collision", choices=list(TYPES))
    p.add_argument("--confidence", type=float, default=0.9)
    a = p.parse_args()

    path = os.path.join(tempfile.gettempdir(), "resqvision_test_event.png")
    make_png(path, COLORS[a.severity])

    event = {
        "camera_id": a.camera_id, "confidence": a.confidence, "severity": a.severity, "accident_type": a.type,
        "vehicles_involved": TYPES[a.type], "vehicles_count": 2, "people_count": 2,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    res = DjangoClient(a.api_url, a.api_key).send_event(event, snapshot_path=path)
    print(res)


if __name__ == "__main__":
    main()
