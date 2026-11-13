"""Small HTTP client that sends verified accident events to the Django backend (POST /api/ingest/)."""
import os
import time

import requests

# Load the project's .env (one folder up) if python-dotenv is installed.
# Real environment variables already set in the terminal take priority.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, ".env"))
except ImportError:
    pass


def to_ingest_payload(event: dict) -> dict:
    """Translate the detector's event dict into the field names /api/ingest/ expects."""
    accident_type = str(event.get("accident_type") or "").replace("_", " ").strip().capitalize()
    payload = {
        "camera_id": event.get("camera_id"),
        "latitude": event.get("latitude"),
        "longitude": event.get("longitude"),
        "location": event.get("location_description") or event.get("location"),
        "confidence": event.get("confidence"),  # 0..1 (the backend also accepts 0..100)
        "severity": event.get("severity"),
        "accident_type": accident_type,
        "vehicles": event.get("vehicles_involved") or event.get("vehicles"),
        "people_count": event.get("people_count"),
        "detected_at": event.get("detected_at"),
    }
    # Empty values are left out so the backend can fall back to the camera's own location.
    return {k: str(v) for k, v in payload.items() if v not in (None, "")}


class DjangoClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 60):
        self.base = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}
        self.timeout = timeout

    def send_event(self, event: dict, snapshot_path: str | None = None, video_path: str | None = None, retries: int = 3) -> dict:
        """POST /api/ingest/ as multipart. Retries on network errors / 5xx."""
        data = to_ingest_payload(event)
        last = None
        for attempt in range(1, retries + 1):
            files, handles = {}, []
            try:
                if snapshot_path and os.path.exists(snapshot_path):
                    fh = open(snapshot_path, "rb")
                    handles.append(fh)
                    mime = "image/png" if snapshot_path.lower().endswith(".png") else "image/jpeg"
                    files["snapshot"] = (os.path.basename(snapshot_path), fh, mime)
                if video_path and os.path.exists(video_path):
                    fh = open(video_path, "rb")
                    handles.append(fh)
                    files["video"] = (os.path.basename(video_path), fh, "video/mp4")
                resp = requests.post(
                    f"{self.base}/api/ingest/",
                    data=data,
                    files=files or None,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if resp.status_code < 500:
                    if resp.status_code >= 400:
                        raise RuntimeError(f"Backend rejected the event ({resp.status_code}): {resp.text[:300]}")
                    return resp.json()
                last = RuntimeError(f"Backend error {resp.status_code}")
            except requests.RequestException as exc:
                last = exc
            finally:
                for fh in handles:
                    fh.close()
            time.sleep(2 * attempt)
        raise RuntimeError(f"Could not deliver the event after {retries} attempts: {last}")

    def heartbeat(self, camera_id: str) -> bool:
        """The backend has no heartbeat endpoint; kept so run_detector.py can call it safely."""
        return True
