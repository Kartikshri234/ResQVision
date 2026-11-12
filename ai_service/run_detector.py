"""ResQVision AI detection service.

Reads a video source (file, webcam index, RTSP/HTTP stream), detects and tracks vehicles and
pedestrians with YOLO + ByteTrack, runs the accident logic from detector.py and sends every
verified accident (snapshot + short clip + confidence) to the Django backend.

Examples (run from this folder, with the Django server already running):
    python run_detector.py --source sample.mp4 --camera-id CAM-001 --show
    python run_detector.py --source 0 --camera-id CAM-002
    python run_detector.py --source rtsp://user:pass@192.168.1.20/stream --camera-id CAM-003
    python run_detector.py --source sample.mp4 --camera-id CAM-001 --dry-run     # do not send anything
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import deque
from datetime import datetime, timezone

import cv2

from client import DjangoClient
from detector import AccidentDetector, DetectorConfig

COCO_ROAD_CLASSES = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck
COLORS = {"high": (32, 45, 217), "medium": (9, 144, 247), "low": (106, 183, 18)}


def parse_args():
    p = argparse.ArgumentParser(description="ResQVision accident detection service")
    p.add_argument("--source", required=True, help="video file, webcam index (0), or RTSP/HTTP URL")
    p.add_argument("--camera-id", default="", help="camera ID registered in the admin app (gives the location)")
    p.add_argument("--lat", type=float, help="GPS latitude for a mobile camera (when no --camera-id)")
    p.add_argument("--lng", type=float, help="GPS longitude for a mobile camera (when no --camera-id)")
    p.add_argument("--location", default="", help="location description for a mobile camera")
    p.add_argument("--api-url", default=os.environ.get("RESQVISION_API_URL", "http://127.0.0.1:8000"))
    p.add_argument("--api-key", default=os.environ.get("AI_SERVICE_API_KEY", "dev-ai-key-change-me"))
    p.add_argument("--model", default="yolov8n.pt", help="YOLO weights (downloaded automatically on first run)")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.35, help="YOLO detection confidence")
    p.add_argument("--stride", type=int, default=2, help="analyse every Nth frame")
    p.add_argument("--threshold", type=float, default=0.60, help="minimum accident confidence to report")
    p.add_argument("--cooldown", type=int, default=60, help="seconds before another event from this source")
    p.add_argument("--pre-seconds", type=float, default=3.0, help="clip seconds before the accident")
    p.add_argument("--post-seconds", type=float, default=3.0, help="clip seconds after the accident")
    p.add_argument("--loop", action="store_true", help="restart a video file when it ends")
    p.add_argument("--show", action="store_true", help="show a live preview window (press q to quit)")
    p.add_argument("--dry-run", action="store_true", help="detect and save evidence locally but do not send")
    p.add_argument("--evidence-dir", default="evidence", help="where snapshots and clips are kept")
    return p.parse_args()


def open_source(src):
    return cv2.VideoCapture(int(src) if str(src).isdigit() else src)


def draw(frame, dets, event=None):
    for d in dets:
        x1, y1, x2, y2 = (int(v) for v in d["box"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 160, 40), 2)
        cv2.putText(frame, f"{d['name']} #{d['id']}", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    if event is not None:
        x1, y1, x2, y2 = event.box
        color = COLORS[event.severity]
        cv2.rectangle(frame, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), color, 4)
        label = f"ACCIDENT {round(event.confidence * 100)}%  {event.severity.upper()}"
        cv2.rectangle(frame, (x1 - 8, max(0, y1 - 38)), (x1 + 330, max(0, y1 - 8)), color, -1)
        cv2.putText(frame, label, (x1, max(18, y1 - 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def write_clip(frames, fps, path):
    """Write frames to an MP4. Re-encodes to H.264 with ffmpeg when available so browsers can play it."""
    h, w = frames[0].shape[:2]
    raw = path + ".raw.mp4"
    writer = cv2.VideoWriter(raw, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()
    if shutil.which("ffmpeg"):
        res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vcodec", "libx264", "-pix_fmt", "yuv420p", path], capture_output=True)
        if res.returncode == 0:
            os.remove(raw)
            return path
    os.replace(raw, path)
    return path


def main():
    args = parse_args()
    if not args.camera_id and (args.lat is None or args.lng is None):
        sys.exit("Give --camera-id (a camera registered in the app) or both --lat and --lng for a mobile camera.")

    from ultralytics import YOLO  # imported late so --help works without it

    model = YOLO(args.model)
    cap = open_source(args.source)
    if not cap.isOpened():
        sys.exit(f"Cannot open video source: {args.source}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if fps != fps or fps > 120:
        fps = 25.0
    eff_fps = fps / max(1, args.stride)
    detector = AccidentDetector(DetectorConfig(fps=eff_fps, min_confidence=args.threshold))
    client = None if args.dry_run else DjangoClient(args.api_url, args.api_key)
    os.makedirs(args.evidence_dir, exist_ok=True)

    ring = deque(maxlen=max(1, int(args.pre_seconds * eff_fps)))
    post_target = max(1, int(args.post_seconds * eff_fps))
    pending = None  # {event, frames, snapshot, detected_at}
    last_event_time = 0.0
    last_beat = 0.0
    frame_idx = 0
    print(f"[resqvision] source={args.source} camera={args.camera_id or 'mobile GPS'} fps={fps:.1f} stride={args.stride} -> {'DRY RUN' if args.dry_run else args.api_url}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if args.loop and not str(args.source).isdigit() and not str(args.source).startswith(("rtsp", "http")):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                print("[resqvision] end of stream")
                break
            frame_idx += 1
            if frame_idx % args.stride:
                continue

            if client and args.camera_id and time.time() - last_beat > 30:
                client.heartbeat(args.camera_id)
                last_beat = time.time()

            result = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=COCO_ROAD_CLASSES, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
            dets = []
            if result.boxes is not None and result.boxes.id is not None:
                for box, tid, cls in zip(result.boxes.xyxy.tolist(), result.boxes.id.int().tolist(), result.boxes.cls.int().tolist()):
                    dets.append({"id": tid, "name": result.names[cls], "box": tuple(box)})

            events = detector.update(dets)
            annotated = draw(frame.copy(), dets)
            ring.append(annotated)

            if pending is not None:
                pending["frames"].append(annotated)
                pending["left"] -= 1
                if pending["left"] <= 0:
                    deliver(pending, args, client, eff_fps)
                    pending = None

            if events and pending is None and time.time() - last_event_time > args.cooldown:
                event = max(events, key=lambda e: e.confidence)
                last_event_time = time.time()
                marked = draw(frame.copy(), dets, event)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snap = os.path.join(args.evidence_dir, f"accident_{stamp}.jpg")
                cv2.imwrite(snap, marked, [cv2.IMWRITE_JPEG_QUALITY, 90])
                print(f"[resqvision] ACCIDENT {event.accident_type} confidence={event.confidence} severity={event.severity} signals={event.signals}")
                pending = {"event": event, "frames": list(ring), "left": post_target, "snapshot": snap, "stamp": stamp, "detected_at": datetime.now(timezone.utc).isoformat()}

            if args.show:
                cv2.imshow("ResQVision", draw(frame.copy(), dets, events[0] if events else None))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\n[resqvision] stopped")
    finally:
        if pending is not None:
            deliver(pending, args, client, eff_fps)
        cap.release()
        cv2.destroyAllWindows()


def deliver(pending, args, client, fps):
    event = pending["event"]
    clip = None
    try:
        clip = write_clip(pending["frames"], fps, os.path.join(args.evidence_dir, f"accident_{pending['stamp']}.mp4"))
    except Exception as exc:  # the alert is more important than the clip
        print(f"[resqvision] could not write the video clip: {exc}")
    payload = {
        "camera_id": args.camera_id,
        "latitude": args.lat if not args.camera_id else None,
        "longitude": args.lng if not args.camera_id else None,
        "location_description": args.location,
        "confidence": event.confidence,
        "severity": event.severity,
        "accident_type": event.accident_type,
        "vehicles_involved": event.vehicles_involved,
        "vehicles_count": event.vehicles_count,
        "people_count": event.people_count,
        "detected_at": pending["detected_at"],
    }
    if client is None:
        print(f"[resqvision] dry run - evidence saved: {pending['snapshot']} {clip or ''}")
        return
    try:
        res = client.send_event(payload, pending["snapshot"], clip)
        if res.get("duplicate"):
            print(f"[resqvision] backend already has a recent accident for this camera: {res.get('accident_id')}")
        else:
            print(f"[resqvision] sent -> {res.get('accident_id')} ({res.get('status')})")
    except Exception as exc:
        print(f"[resqvision] FAILED to send event: {exc}")


if __name__ == "__main__":
    main()
