"""
Minimal camera app for red laser spot detection.

Run:
    python camera_laser_detect.py

Keys:
    q or ESC: save settings and quit
    s: save settings and quit
"""

import argparse
import json
import sys
import time
import cv2
import numpy as np

WINDOW_NAME = "Laser Detect"
SETTINGS_FILE = "camera_laser_detect_settings.json"


def load_settings():
    defaults = {
        "sat_min": 150,
        "val_min": 200,
        "target_n": 1,
        "max_area": 150,
        "contrast": 30,
    }
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        defaults.update(saved)
        print(f"[INFO] Loaded settings from {SETTINGS_FILE}")
    except FileNotFoundError:
        pass
    return defaults


def save_settings(sat_min, val_min, target_n, max_area, contrast):
    data = {
        "sat_min": sat_min,
        "val_min": val_min,
        "target_n": target_n,
        "max_area": max_area,
        "contrast": contrast,
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[INFO] Settings saved to {SETTINGS_FILE}")


def create_main_window(
    sat_min: int, val_min: int, targets: int, max_area: int, contrast: int
):
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.createTrackbar("S min", WINDOW_NAME, int(sat_min), 255, lambda _v: None)
    cv2.createTrackbar("V min", WINDOW_NAME, int(val_min), 255, lambda _v: None)
    cv2.createTrackbar("Targets", WINDOW_NAME, int(targets), 10, lambda _v: None)
    cv2.createTrackbar("MaxArea", WINDOW_NAME, int(max_area), 1000, lambda _v: None)
    cv2.createTrackbar("Contrast", WINDOW_NAME, int(contrast), 200, lambda _v: None)


def open_camera(index: int, width: int, height: int, fps: int):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {index}")

    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps > 0:
        cap.set(cv2.CAP_PROP_FPS, fps)

    return cap


def detect_red_lasers(
    frame: np.ndarray,
    sat_min: int,
    val_min: int,
    min_area: float = 4.0,
    max_area_abs: float = 80.0,
    max_targets: int = 3,
    contrast_min: int = 30,
):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    b, g, r = cv2.split(frame)
    value_channel = hsv[:, :, 2]

    # Step 1: Find red regions (HSV mask).
    lower1 = np.array([0, sat_min, val_min], dtype=np.uint8)
    upper1 = np.array([12, 255, 255], dtype=np.uint8)
    lower2 = np.array([168, sat_min, val_min], dtype=np.uint8)
    upper2 = np.array([179, 255, 255], dtype=np.uint8)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2)
    )

    # White-hot core (R≈G≈B≈255, S≈0): not captured by HSV red range.
    # Include pixels where R dominates G,B by at least 10 and V >= val_min.
    r16 = r.astype(np.int16)
    dom_map = r16 - np.maximum(g, b).astype(np.int16)
    white_hot = cv2.bitwise_and(
        cv2.threshold(value_channel, int(val_min), 255, cv2.THRESH_BINARY)[1],
        cv2.inRange(dom_map, 10, 255),
    )
    mask = cv2.bitwise_or(mask, white_hot)

    # Step 2: Find contours in red mask.
    kernel = np.ones((3, 3), np.uint8)
    clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    dom_req = int(sat_min) // 8
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area_abs:
            continue

        (x, y), radius = cv2.minEnclosingCircle(cnt)
        cx, cy = int(x), int(y)

        # Step 3: Get brightness at contour center.
        y0 = max(0, cy - 3)
        y1 = min(frame.shape[0], cy + 4)
        x0 = max(0, cx - 3)
        x1 = min(frame.shape[1], cx + 4)
        local_peak = (
            int(value_channel[y0:y1, x0:x1].max()) if y1 > y0 and x1 > x0 else 0
        )
        if local_peak < int(val_min):
            continue

        # Step 4: Local peak check — center must be brighter than its surround.
        # This rejects contours inside uniformly bright TV areas.
        r_surround = 15
        sy0 = max(0, cy - r_surround)
        sy1 = min(value_channel.shape[0], cy + r_surround + 1)
        sx0 = max(0, cx - r_surround)
        sx1 = min(value_channel.shape[1], cx + r_surround + 1)
        surround_patch = value_channel[sy0:sy1, sx0:sx1].astype(np.float32)
        icy = cy - sy0
        icx = cx - sx0
        hs, ws = surround_patch.shape
        yy, xx = np.ogrid[:hs, :ws]
        d2 = (yy - icy) ** 2 + (xx - icx) ** 2
        outer_vals = surround_patch[d2 >= 25]  # exclude inner r=5
        if outer_vals.size == 0:
            continue
        mean_surround = float(outer_vals.mean())
        # Laser: bright spot on wall → local_peak >> mean_surround
        # TV content: flat bright region → local_peak ≈ mean_surround
        contrast = local_peak - mean_surround
        if contrast < contrast_min:
            continue

        # Step 5: Red dominance check.
        patch_r = r[y0:y1, x0:x1]
        patch_g = g[y0:y1, x0:x1]
        patch_b = b[y0:y1, x0:x1]
        if patch_r.size == 0:
            continue
        dom = float(np.mean(patch_r.astype(np.float32) - np.maximum(patch_g, patch_b)))
        if local_peak < 255 and dom < dom_req:
            continue

        score = local_peak + (dom * 2.0) - (area * 0.2)
        candidates.append((score, cx, cy, float(radius), float(area), local_peak))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[: max(1, int(max_targets))]
    return top, mask


def update_tracks(
    tracks: list,
    detections: list,
    next_track_id: int,
    max_miss: int = 3,
    max_dist: float = 40.0,
    ema_alpha: float = 0.45,
    min_hits: int = 4,
    max_new_tracks: int = 5,
):
    """Update point tracks with nearest-neighbor matching and confirmation gate.

    Only tracks with hits >= min_hits are considered 'confirmed' (safe to display).
    New tracks are created tentatively and promoted only after min_hits consecutive matches.
    """
    updated = []
    used_track_idx = set()
    used_det_idx = set()

    # confirmed tracks first (prefer matching to stable tracks over tentative ones)
    confirmed = [t for t in tracks if t["hits"] >= min_hits]
    tentative = [t for t in tracks if t["hits"] < min_hits]
    ordered = confirmed + tentative

    pairs = []
    for ti, tr in enumerate(ordered):
        for di, det in enumerate(detections):
            dx = tr["x"] - det["x"]
            dy = tr["y"] - det["y"]
            dist = float(np.hypot(dx, dy))
            pairs.append((dist, ti, di))

    pairs.sort(key=lambda x: x[0])
    for dist, ti, di in pairs:
        if dist > max_dist:
            continue
        if ti in used_track_idx or di in used_det_idx:
            continue
        tr = ordered[ti]
        det = detections[di]
        tr["x"] = (ema_alpha * det["x"]) + ((1.0 - ema_alpha) * tr["x"])
        tr["y"] = (ema_alpha * det["y"]) + ((1.0 - ema_alpha) * tr["y"])
        tr["radius"] = (ema_alpha * det["radius"]) + ((1.0 - ema_alpha) * tr["radius"])
        tr["area"] = det["area"]
        tr["peak"] = det["peak"]
        tr["score"] = det["score"]
        tr["miss"] = 0
        tr["hits"] = tr["hits"] + 1
        tr["fresh"] = True
        updated.append(tr)
        used_track_idx.add(ti)
        used_det_idx.add(di)

    for ti, tr in enumerate(ordered):
        if ti in used_track_idx:
            continue
        tr["miss"] += 1
        tr["fresh"] = False
        if tr["miss"] <= max_miss:
            updated.append(tr)
        # else: track dies (not appended)

    # Only spawn new tentative tracks up to max_new_tracks to suppress noise bursts
    tentative_count = sum(1 for t in updated if t["hits"] < min_hits)
    for di, det in enumerate(detections):
        if di in used_det_idx:
            continue
        if tentative_count >= max_new_tracks:
            break
        updated.append(
            {
                "id": next_track_id,
                "x": float(det["x"]),
                "y": float(det["y"]),
                "radius": float(det["radius"]),
                "area": float(det["area"]),
                "peak": int(det["peak"]),
                "score": float(det["score"]),
                "miss": 0,
                "hits": 1,
                "fresh": True,
            }
        )
        next_track_id += 1
        tentative_count += 1

    # Sort: confirmed first, then by score
    updated.sort(
        key=lambda t: (t["hits"] >= min_hits, t["score"]),
        reverse=True,
    )
    return updated, next_track_id


def main():
    parser = argparse.ArgumentParser(description="Detect a red laser spot from webcam")
    parser.add_argument("--camera", type=int, default=0, help="camera index")
    parser.add_argument("--width", type=int, default=1280, help="capture width")
    parser.add_argument("--height", type=int, default=720, help="capture height")
    parser.add_argument("--fps", type=int, default=30, help="capture fps")
    parser.add_argument(
        "--show-mask", action="store_true", help="show binary mask window"
    )
    parser.add_argument(
        "--retry-seconds", type=float, default=1.0, help="reconnect wait time"
    )
    parser.add_argument(
        "--log-interval",
        type=int,
        default=30,
        help="frames between periodic status logs",
    )
    args = parser.parse_args()
    print(
        f"[INFO] start camera={args.camera} width={args.width} "
        f"height={args.height} fps={args.fps}"
    )

    try:
        cap = open_camera(args.camera, args.width, args.height, args.fps)
    except RuntimeError as exc:
        print(f"[ERROR] {str(exc)}")
        sys.exit(1)

    s = load_settings()
    sat_min = s["sat_min"]
    val_min = s["val_min"]
    target_n = s["target_n"]
    max_area_ui = s["max_area"]
    contrast_ui = s["contrast"]
    create_main_window(sat_min, val_min, target_n, max_area_ui, contrast_ui)

    fail_count = 0
    tracks = []
    next_track_id = 1
    frame_idx = 0

    while True:
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            print("[INFO] Window closed by user")
            save_settings(sat_min, val_min, target_n, max_area_ui, contrast_ui)
            break

        ret, frame = cap.read()
        if not ret or frame is None:
            fail_count += 1
            if fail_count < 5:
                print(f"[WARN] Camera frame read failed ({fail_count})")
                time.sleep(0.05)
                continue

            print("[WARN] Camera read failed repeatedly. Reconnecting...")
            cap.release()
            time.sleep(max(0.1, args.retry_seconds))
            try:
                cap = open_camera(args.camera, args.width, args.height, args.fps)
                print("[INFO] Reconnected camera successfully")
                fail_count = 0
                continue
            except RuntimeError:
                print("[WARN] Reconnection failed. Retrying...")
                time.sleep(max(0.2, args.retry_seconds))
                continue

        fail_count = 0
        frame_idx += 1

        try:
            sat_min = cv2.getTrackbarPos("S min", WINDOW_NAME)
            val_min = cv2.getTrackbarPos("V min", WINDOW_NAME)
            target_n = max(1, cv2.getTrackbarPos("Targets", WINDOW_NAME))
            max_area_ui = cv2.getTrackbarPos("MaxArea", WINDOW_NAME)
            contrast_ui = cv2.getTrackbarPos("Contrast", WINDOW_NAME)
        except cv2.error:
            print("[INFO] Trackbar unavailable (window closed)")
            break

        detect_limit = max(target_n * 3, target_n)
        targets, mask = detect_red_lasers(
            frame,
            sat_min=sat_min,
            val_min=val_min,
            max_area_abs=float(max_area_ui),
            max_targets=detect_limit,
            contrast_min=contrast_ui,
        )

        detections = [
            {
                "score": float(t[0]),
                "x": int(t[1]),
                "y": int(t[2]),
                "radius": float(t[3]),
                "area": float(t[4]),
                "peak": int(t[5]),
            }
            for t in targets
        ]

        # Filter detections — no additional filter currently
        tracks, next_track_id = update_tracks(tracks, detections, next_track_id)
        confirmed_tracks = [t for t in tracks if t["hits"] >= 4]
        draw_tracks = confirmed_tracks[:target_n]

        if frame_idx % max(1, args.log_interval) == 0:
            confirmed_count = len([t for t in tracks if t["hits"] >= 4])
            if draw_tracks:
                t0 = draw_tracks[0]
                print(
                    f"[LOG] frame={frame_idx} det={len(detections)} confirmed={confirmed_count} tracks={len(draw_tracks)} "
                    f"top1=({int(round(t0['x']))},{int(round(t0['y']))}) "
                    f"peak={int(t0['peak'])} area={float(t0['area']):.1f} hits={t0['hits']} "
                    f"S>={sat_min} V>={val_min} MaxArea={max_area_ui} Contrast={contrast_ui}"
                )
            else:
                print(
                    f"[LOG] frame={frame_idx} det={len(detections)} confirmed={confirmed_count} tracks=0 S>={sat_min} V>={val_min} MaxArea={max_area_ui} Contrast={contrast_ui}"
                )

        if draw_tracks:
            for idx, tr in enumerate(draw_tracks, start=1):
                cx = int(round(tr["x"]))
                cy = int(round(tr["y"]))
                radius = tr["radius"]
                area = tr["area"]
                color = (0, 255, 255) if tr["fresh"] else (130, 130, 130)
                cv2.circle(frame, (cx, cy), max(5, int(radius) + 6), color, 2)
                cv2.drawMarker(
                    frame,
                    (cx, cy),
                    color,
                    markerType=cv2.MARKER_CROSS,
                    markerSize=20,
                    thickness=2,
                )
                cv2.putText(
                    frame,
                    f"T{idx}",
                    (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            t0 = draw_tracks[0]
            cx0 = int(round(t0["x"]))
            cy0 = int(round(t0["y"]))
            area0 = t0["area"]
            peak0 = t0["peak"]
            cv2.putText(
                frame,
                f"Tracks={len(draw_tracks)} Top1 x={cx0} y={cy0} area={area0:.1f} peak={peak0} S>={sat_min} V>={val_min}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                frame,
                f"No red laser detected  Tracks=0 S>={sat_min} V>={val_min}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (180, 180, 180),
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            frame,
            "Press q or ESC to quit",
            (10, frame.shape[0] - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )

        cv2.imshow(WINDOW_NAME, frame)
        if args.show_mask:
            cv2.imshow("Laser Mask", mask)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27 or key == ord("s"):
            save_settings(sat_min, val_min, target_n, max_area_ui, contrast_ui)
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] stopped")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user")
