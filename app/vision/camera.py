"""Camera capture — only ever runs when explicitly triggered.

Privacy behaviour:
- Prints a visible "[CAMERA ACTIVE]" banner while the shutter is open.
- Saves snapshots under data/snapshots/ with timestamps.
- prune_old_snapshots() enforces SNAPSHOT_RETENTION_DAYS.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from app.config import Config
from app.logger import get_logger

log = get_logger("camera")

try:
    import cv2
except ImportError:
    cv2 = None


class CameraError(Exception):
    pass


class Camera:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @property
    def available(self) -> bool:
        return cv2 is not None

    def snapshot(self) -> Path:
        """Take one photo and return the saved file path."""
        if cv2 is None:
            raise CameraError(
                "OpenCV is not installed. Run: pip install opencv-python "
                "(on Raspberry Pi: sudo apt install python3-opencv)"
            )

        print("  [CAMERA ACTIVE] taking one snapshot...")
        cap = cv2.VideoCapture(self.cfg.camera_index)
        try:
            if not cap.isOpened():
                raise CameraError(
                    f"No camera found at index {self.cfg.camera_index}. "
                    "Check the USB cable, close other apps using the camera, "
                    "or try CAMERA_INDEX=1 in .env."
                )
            # A few warm-up frames — many webcams return dark frames at first.
            for _ in range(5):
                cap.read()
                time.sleep(0.05)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise CameraError(
                    "Camera opened but returned no image. Unplug/replug the webcam "
                    "or try a different USB port."
                )
        finally:
            cap.release()
            print("  [CAMERA OFF]")

        self.cfg.snapshots_dir.mkdir(parents=True, exist_ok=True)
        path = self.cfg.snapshots_dir / f"desk_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        if not cv2.imwrite(str(path), frame):
            raise CameraError(f"Could not write snapshot to {path} (disk full or permissions?).")
        log.info("Snapshot saved: %s", path)
        return path

    def prune_old_snapshots(self) -> int:
        """Delete snapshots older than the retention window. Returns count removed."""
        days = self.cfg.snapshot_retention_days
        if not self.cfg.snapshots_dir.exists():
            return 0
        cutoff = datetime.now() - timedelta(days=days)
        removed = 0
        for f in self.cfg.snapshots_dir.glob("desk_*.jpg"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff or days == 0:
                f.unlink(missing_ok=True)
                removed += 1
        if removed:
            log.info("Pruned %d old snapshot(s) (retention: %d days)", removed, days)
        return removed
