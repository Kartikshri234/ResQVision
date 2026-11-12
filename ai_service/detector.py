"""Accident detection logic on top of tracked objects.

This module is framework independent (pure Python): it receives tracked detections
(id, class name, bounding box) for every processed frame and decides whether a
road accident happened. Detection and tracking themselves (YOLO + ByteTrack) live
in run_detector.py.

Pipeline per processed frame
  1. Update the trajectory of every tracked vehicle / pedestrian.
  2. Suppress analysis during traffic jams (many slow vehicles).
  3. Open a candidate when two road users that were MOVING make contact
     (parked or stationary vehicles touching are ignored).
  4. Verify the candidate over several following frames using several signals:
     contact strength, sudden speed drop, persistence, direction change /
     person-down, and the speed before contact.
  5. Also watch single vehicles for overturning (sudden aspect-ratio flip + stop).
  6. Emit an AccidentEvent with a confidence score and an AI severity estimate.

Normal braking, turning, parking and slow traffic never produce a contact between
moving objects followed by a sudden stop, so they do not raise events.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

VEHICLE_NAMES = {"bicycle", "car", "motorcycle", "bus", "truck"}
PERSON_NAME = "person"


@dataclass
class DetectorConfig:
    fps: float = 15.0              # effective processing rate (video fps / stride)
    min_confidence: float = 0.60   # minimum score to raise an event
    lookback_s: float = 1.0        # window used to measure speed before contact
    verify_s: float = 0.7          # how long a candidate must be observed
    window_s: float = 2.5          # candidate expires after this
    stale_s: float = 2.0           # forget tracks not seen for this long
    moving_speed: float = 0.05     # body-lengths per step that counts as "moving"
    iou_contact: float = 0.08      # vehicle-vehicle overlap that counts as contact
    person_contact: float = 0.25   # share of the person box covered by a vehicle
    min_drop: float = 0.40         # required speed drop of the mover
    jam_vehicles: int = 8          # this many slow vehicles = traffic jam
    jam_speed: float = 0.03

    def steps(self, seconds: float) -> int:
        return max(1, int(round(seconds * self.fps)))


@dataclass
class AccidentEvent:
    accident_type: str
    confidence: float
    severity: str
    vehicles_involved: str
    vehicles_count: int
    people_count: int
    box: tuple
    step: int
    signals: dict = field(default_factory=dict)


class Track:
    def __init__(self, tid: int, name: str, maxlen: int):
        self.id = tid
        self.name = name
        self.hist: deque = deque(maxlen=maxlen)  # (step, cx, cy, w, h)
        self.last_step = -1
        self.flip_steps = 0
        self.reported = False

    def add(self, step: int, box) -> None:
        x1, y1, x2, y2 = box
        self.hist.append((step, (x1 + x2) / 2.0, (y1 + y2) / 2.0, max(1.0, x2 - x1), max(1.0, y2 - y1)))
        self.last_step = step

    @property
    def box(self):
        _, cx, cy, w, h = self.hist[-1]
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    @property
    def aspect(self) -> float:
        return self.hist[-1][3] / self.hist[-1][4]

    def speed_at(self, offset: int = 0, n: int = 3) -> float:
        """Average displacement per step (in body lengths) ending `offset` steps ago."""
        h = self.hist
        end = len(h) - 1 - offset
        if end < 1:
            return 0.0
        start = max(0, end - n)
        steps = h[end][0] - h[start][0]
        if steps <= 0:
            return 0.0
        dist = math.hypot(h[end][1] - h[start][1], h[end][2] - h[start][2])
        return dist / steps / max(h[end][3], h[end][4])

    def peak_speed(self, offset: int, span: int) -> float:
        return max((self.speed_at(o) for o in range(offset, offset + span + 1)), default=0.0)

    def heading_at(self, offset: int = 0, n: int = 4):
        h = self.hist
        end = len(h) - 1 - offset
        if end < 1:
            return None
        start = max(0, end - n)
        dx, dy = h[end][1] - h[start][1], h[end][2] - h[start][2]
        if math.hypot(dx, dy) < 1e-6:
            return None
        return math.atan2(dy, dx)


@dataclass
class Candidate:
    a: int
    b: int
    start: int
    last_contact: int
    mover: int
    pre_speed: float
    pre_heading: float | None
    person: bool
    max_overlap: float = 0.0
    contact_steps: int = 1
    reported: bool = False


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def iou(a, b):
    i = _inter(a, b)
    u = _area(a) + _area(b) - i
    return i / u if u > 0 else 0.0


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _angle_diff(a, b):
    d = abs(a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


class AccidentDetector:
    def __init__(self, cfg: DetectorConfig | None = None):
        self.cfg = cfg or DetectorConfig()
        self.tracks: dict[int, Track] = {}
        self.cands: dict[tuple, Candidate] = {}
        self.step = -1
        self.jam = False

    # ------------------------------------------------------------------ public
    def update(self, detections) -> list[AccidentEvent]:
        """detections: iterable of dicts {id, name, box=(x1,y1,x2,y2)} for ONE processed frame."""
        cfg = self.cfg
        self.step += 1
        step = self.step
        seen = []
        for d in detections:
            name = d["name"]
            if name not in VEHICLE_NAMES and name != PERSON_NAME:
                continue
            t = self.tracks.get(d["id"])
            if t is None:
                t = self.tracks[d["id"]] = Track(d["id"], name, cfg.steps(cfg.lookback_s) * 4 + 8)
            t.add(step, d["box"])
            seen.append(t)

        stale = cfg.steps(cfg.stale_s)
        for tid in [k for k, t in self.tracks.items() if step - t.last_step > stale]:
            del self.tracks[tid]

        vehicles = [t for t in seen if t.name in VEHICLE_NAMES]
        persons = [t for t in seen if t.name == PERSON_NAME]

        speeds = sorted(t.speed_at() for t in vehicles)
        self.jam = len(vehicles) >= cfg.jam_vehicles and speeds[len(speeds) // 2] < cfg.jam_speed

        events: list[AccidentEvent] = []
        if not self.jam:
            self._open_candidates(vehicles, persons)
            events += self._verify_candidates(vehicles, persons)
            events += self._check_overturn(vehicles, persons)
        else:
            self.cands.clear()
        return events

    # ----------------------------------------------------------------- helpers
    def _open_candidates(self, vehicles, persons):
        cfg, step = self.cfg, self.step
        lb = cfg.steps(cfg.lookback_s)
        pairs = []
        for i, a in enumerate(vehicles):
            for b in vehicles[i + 1:]:
                if iou(a.box, b.box) >= cfg.iou_contact:
                    pairs.append((a, b, iou(a.box, b.box), False))
            for p in persons:
                share = _inter(a.box, p.box) / max(1.0, _area(p.box))
                if share >= cfg.person_contact:
                    pairs.append((a, p, share, True))
        for a, b, overlap, person in pairs:
            key = (min(a.id, b.id), max(a.id, b.id))
            c = self.cands.get(key)
            if c is not None:
                c.last_contact = step
                c.contact_steps += 1
                c.max_overlap = max(c.max_overlap, overlap)
                continue
            pre_a, pre_b = a.peak_speed(0, lb), (0.0 if person else b.peak_speed(0, lb))
            pre = max(pre_a, pre_b)
            if person:
                # the vehicle must have been moving when it hit the pedestrian
                if pre_a < cfg.moving_speed:
                    continue
                mover = a
            else:
                if pre < cfg.moving_speed:  # two stationary vehicles touching = parked / jam
                    continue
                mover = a if pre_a >= pre_b else b
            self.cands[key] = Candidate(
                a=key[0], b=key[1], start=step, last_contact=step, mover=mover.id,
                pre_speed=pre, pre_heading=mover.heading_at(offset=2), person=person, max_overlap=overlap,
            )

    def _verify_candidates(self, vehicles, persons):
        cfg, step = self.cfg, self.step
        verify, window = cfg.steps(cfg.verify_s), cfg.steps(cfg.window_s)
        out = []
        for key in list(self.cands):
            c = self.cands[key]
            ta, tb = self.tracks.get(c.a), self.tracks.get(c.b)
            mover = self.tracks.get(c.mover)
            if ta is None or tb is None or mover is None or step - c.last_contact > window or step - c.start > window * 2:
                del self.cands[key]
                continue
            age = step - c.start
            if c.reported or age < verify:
                continue

            drop = max(0.0, min(1.0, 1.0 - mover.speed_at() / max(c.pre_speed, 1e-6)))
            contact = min(1.0, c.max_overlap / (0.3 if not c.person else 0.6))
            persist = min(1.0, c.contact_steps / (age + 1))
            pre = min(1.0, c.pre_speed / (3 * cfg.moving_speed))
            change = 0.0
            if c.person:
                p = ta if ta.name == PERSON_NAME else tb
                change = 1.0 if p.aspect > 1.1 else 0.0  # person lying down
            else:
                now = mover.heading_at()
                if c.pre_heading is not None and now is not None:
                    change = min(1.0, _angle_diff(c.pre_heading, now) / (math.pi / 2))
            score = 0.20 * contact + 0.35 * drop + 0.20 * persist + 0.10 * change + 0.15 * pre
            if drop < cfg.min_drop or score < cfg.min_confidence:
                continue

            c.reported = True
            out.append(self._build(c, ta, tb, vehicles, persons, min(0.99, score),
                                   {"contact": contact, "drop": drop, "persist": persist, "change": change, "pre": pre}))
        return out

    def _build(self, c, ta, tb, vehicles, persons, confidence, signals):
        union = _union(ta.box, tb.box)
        group = {ta.id: ta, tb.id: tb}
        for v in vehicles:
            if v.id not in group and (iou(v.box, ta.box) >= self.cfg.iou_contact / 2 or iou(v.box, tb.box) >= self.cfg.iou_contact / 2):
                group[v.id] = v
                union = _union(union, v.box)
        members = list(group.values())
        veh = [t for t in members if t.name in VEHICLE_NAMES]
        ped = [t for t in members if t.name == PERSON_NAME]
        margin_w, margin_h = (union[2] - union[0]), (union[3] - union[1])
        area = (union[0] - margin_w * 0.5, union[1] - margin_h * 0.5, union[2] + margin_w * 0.5, union[3] + margin_h * 0.5)
        nearby = {p.id for p in persons if _inter(area, p.box) > 0} | {p.id for p in ped}

        if ped:
            atype = "pedestrian_collision"
        elif len(veh) >= 3:
            atype = "multi_vehicle"
        elif any(t.name in ("motorcycle", "bicycle") for t in veh):
            atype = "motorcycle_accident"
        else:
            atype = "car_collision"

        points = 0
        points += 1 if c.pre_speed >= 0.12 else 0
        points += 1 if signals["drop"] >= 0.8 else 0
        points += 1 if len(veh) >= 3 else 0
        points += 1 if (ped or any(t.name in ("motorcycle", "bicycle") for t in veh)) else 0
        points += 1 if len(nearby) >= 3 else 0
        severity = "high" if points >= 3 else "medium" if points == 2 else "low"
        if points == 1 and signals["drop"] >= 0.8:
            severity = "medium"

        return AccidentEvent(
            accident_type=atype, confidence=round(confidence, 2), severity=severity,
            vehicles_involved=_label(members), vehicles_count=len(veh), people_count=len(nearby),
            box=tuple(int(x) for x in union), step=self.step, signals={k: round(v, 2) for k, v in signals.items()},
        )

    def _check_overturn(self, vehicles, persons):
        """A moving vehicle whose box shape flips abruptly and which then stops."""
        cfg = self.cfg
        lb, verify = cfg.steps(cfg.lookback_s), cfg.steps(cfg.verify_s)
        out = []
        for t in vehicles:
            if t.reported or len(t.hist) < lb + 4:
                continue
            before = t.hist[-1 - lb]
            ratio = (t.hist[-1][3] / t.hist[-1][4]) / (before[3] / before[4])
            pre = t.peak_speed(lb // 2, lb)
            drop = max(0.0, min(1.0, 1.0 - t.speed_at() / max(pre, 1e-6))) if pre >= cfg.moving_speed else 0.0
            flipped = (ratio > 1.7 or ratio < 0.55) and drop >= 0.6
            t.flip_steps = t.flip_steps + 1 if flipped else 0
            if t.flip_steps < verify:
                continue
            score = 0.5 * min(1.0, abs(math.log(ratio)) / math.log(2.5)) + 0.35 * drop + 0.15 * min(1.0, pre / (3 * cfg.moving_speed))
            if score < cfg.min_confidence:
                continue
            t.reported = True
            area = t.box
            nearby = sum(1 for p in persons if _inter(area, p.box) > 0 or iou(area, p.box) > 0)
            out.append(AccidentEvent(
                accident_type="vehicle_overturn", confidence=round(min(0.99, score), 2),
                severity="high" if pre >= 0.12 else "medium", vehicles_involved=_label([t]), vehicles_count=1,
                people_count=nearby, box=tuple(int(x) for x in area), step=self.step,
                signals={"shape_change": round(ratio, 2), "drop": round(drop, 2)},
            ))
        return out


def _label(tracks) -> str:
    names = []
    for t in tracks:
        n = "Pedestrian" if t.name == PERSON_NAME else t.name.capitalize()
        names.append(n)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
