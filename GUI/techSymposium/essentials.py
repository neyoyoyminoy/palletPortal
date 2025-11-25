"""
essentials.py

Shared core for Pallet Portal:

- USB + manifest helpers:
    - BARCODE_FILENAME_CANDIDATES
    - guess_mount_roots()
    - DEFAULT_MOUNT_ROOTS
    - ShipmentList
    - USBWatcher

- LED control (dual WS2812 strips via SPI):
    - SPItoWS
    - LEDWorker

- Dual ultrasonic worker (MB1040):
    - DualPingWorker  (with distanceUpdated for radar)

- Manifest matching + CSI barcode scanning:
    - SimpleManifestMatcher
    - BarcodeReaderWorker

- Generic glitch title widget for themed screens:
    - GlitchTitle
"""

import os
import re
import sys
import time
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QColor
import spidev


# ----------------------------------------------------------------------
#  USB + manifest helpers
# ----------------------------------------------------------------------

BARCODE_FILENAME_CANDIDATES = ["barcode.txt", "barcodes.txt", "manifest.txt"]


def guess_mount_roots():
    roots = set()
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    for base in ["/media", "/mnt", "/run/media"]:
        roots.add(base)
        if user:
            roots.add(os.path.join(base, user))
    roots.add("/media/jetson")
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = line.split()
                if len(p) >= 3:
                    mnt = p[1]
                    fstype = p[2].lower()
                    if any(fs in fstype for fs in ("vfat", "exfat", "ntfs", "fuseblk")):
                        roots.add(mnt)
    except Exception:
        pass
    return [r for r in sorted(roots) if os.path.exists(r)]


DEFAULT_MOUNT_ROOTS = guess_mount_roots()


class ShipmentList:
    """Carries a list of unique barcodes from a manifest text file."""

    def __init__(self, barcodes):
        self.barcodes = barcodes

    @staticmethod
    def parse(text: str):
        # strip BOM if present
        if text and text[0] == "\ufeff":
            text = text[1:]
        parts = [t.strip() for t in re.split(r"[\s,]+", text) if t.strip()]
        seen = set()
        uniq = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return ShipmentList(uniq) if uniq else None


class USBWatcher(QObject):
    """
    Scans mount_roots for known manifest filenames, parses them with
    ShipmentList.parse(txt) and emits validListFound(parsed, mount_dir).

    - mount_roots: list of top-level mount roots to scan (default guessed)
    - filename_candidates: list of filenames to look for (lowercased)
    - poll_ms: polling interval in ms
    """

    validListFound = pyqtSignal(object, str)  # (ShipmentList, mount_dir)
    status = pyqtSignal(str)

    def __init__(self, mount_roots=None, filename_candidates=None, poll_ms=1000, parent=None):
        super().__init__(parent)
        self.mount_roots = mount_roots or DEFAULT_MOUNT_ROOTS
        self.filename_candidates = [
            c.lower()
            for c in (filename_candidates or BARCODE_FILENAME_CANDIDATES)
        ]
        self.timer = QTimer(self)
        self.timer.setInterval(poll_ms)
        self.timer.timeout.connect(self.scan_once)

    def start(self):
        self.scan_once()
        self.timer.start()

    def stop(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    def scan_once(self):
        any_found = False
        for root in self.mount_roots:
            if not os.path.exists(root):
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                depth = (
                    dirpath.strip(os.sep).count(os.sep)
                    - root.strip(os.sep).count(os.sep)
                )
                if depth > 3:
                    dirnames[:] = []
                    continue

                if any(p in dirpath for p in ("/proc", "/sys", "/dev", "/run/lock")):
                    continue

                lower_files = {fn.lower(): fn for fn in filenames}
                for cand_lower in self.filename_candidates:
                    if cand_lower in lower_files:
                        any_found = True
                        found = lower_files[cand_lower]
                        full = os.path.join(dirpath, found)
                        try:
                            txt = Path(full).read_text(
                                encoding="utf-8", errors="ignore"
                            )
                        except Exception as e:
                            self.status.emit(
                                f"found {found} at {dirpath}, but couldn't read: {e}"
                            )
                            continue

                        try:
                            parsed = ShipmentList.parse(txt)
                        except Exception as e:
                            parsed = None
                            self.status.emit(f"error parsing {full}: {e}")

                        if parsed:
                            self.status.emit(f"valid list found at: {full}")
                            self.validListFound.emit(
                                parsed, os.path.normpath(dirpath)
                            )
                            return
                        else:
                            self.status.emit(
                                f"{found} at {dirpath} did not contain any readable barcodes"
                            )
        if not any_found:
            self.status.emit("scanning for usb + barcodes file...")


# ----------------------------------------------------------------------
#  WS2812 LED control (two strips, SPI0 + SPI1)
# ----------------------------------------------------------------------

class SPItoWS:
    """
    Low-level WS2812 driver over SPI, based on:
    https://github.com/seitomatsubara/Jetson-nano-WS2812-LED-/blob/master/W2812.py
    """

    def __init__(self, ledc=5, bus=0, device=0):
        self.led_count = ledc
        self.bus = bus
        self.device = device
        self.X = "100" * (self.led_count * 8 * 3)
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 2400000
        self.LED_OFF_ALL()

    def __del__(self):
        try:
            self.spi.close()
        except Exception:
            pass

    def _Bytesto3Bytes(self, num, RGB):
        base = num * 24
        for i in range(8):
            pat = "100" if RGB[i] == "0" else "110"
            self.X = self.X[: base + i * 3] + pat + self.X[base + i * 3 + 3 :]

    def LED_show(self):
        Y = []
        for i in range(self.led_count * 9):
            Y.append(int(self.X[i * 8 : (i + 1) * 8], 2))
        self.spi.xfer3(Y, 2400000, 0, 8)

    def RGBto3Bytes(self, led_num, R, G, B):
        if any(v > 255 or v < 0 for v in (R, G, B)):
            raise ValueError("invalid rgb value")
        if led_num > self.led_count - 1 or led_num < 0:
            raise ValueError("invalid led index")
        RR, GG, BB = (format(R, "08b"), format(G, "08b"), format(B, "08b"))
        self._Bytesto3Bytes(led_num * 3, GG)
        self._Bytesto3Bytes(led_num * 3 + 1, RR)
        self._Bytesto3Bytes(led_num * 3 + 2, BB)

    def LED_OFF_ALL(self):
        self.X = "100" * (self.led_count * 8 * 3)
        self.LED_show()


class LEDWorker(QThread):
    """
    Dual WS2812 strips driven over SPI0 and SPI1.

    Modes:
      - 'standby'      : rainbow
      - 'green'        : solid green
      - 'yellow_flash' : continuous yellow flashing until another mode overrides
      - 'pink_flash'   : continuous pink flashing (completion) until reset_for_next_usb()
    """

    to_standby = pyqtSignal()
    to_green = pyqtSignal()
    to_yellow_pulse = pyqtSignal()  # triggers yellow_flash
    to_pink_flash = pyqtSignal()

    def __init__(self, num_leds=5, parent=None):
        super().__init__(parent)
        self.strip0 = SPItoWS(num_leds, bus=0, device=0)
        self.strip1 = SPItoWS(num_leds, bus=1, device=0)

        # internal mode state
        self._mode = "standby"
        self._steady_mode = "standby"
        self._completion_active = False
        self._stop = False

        # connect signals
        self.to_standby.connect(lambda: self._set_steady("standby"))
        self.to_green.connect(lambda: self._set_steady("green"))
        self.to_yellow_pulse.connect(self._enter_yellow)
        self.to_pink_flash.connect(self._start_pink)

    def reset_for_next_usb(self):
        # called when returning to welcome for a new trailer
        self._completion_active = False
        self._steady_mode = "standby"
        self._mode = "standby"

    def _set_steady(self, m):
        # If completion (pink) started, do not change steady mode
        if self._completion_active:
            return
        self._steady_mode = m
        self._mode = m

    def _enter_yellow(self):
        # do not override completion pink
        if self._completion_active:
            return
        self._mode = "yellow_flash"

    def _start_pink(self):
        # once we enter completion, lock until reset_for_next_usb()
        self._completion_active = True
        self._mode = "pink_flash"

    def stop(self):
        self._stop = True

    def _hue_to_rgb(self, h):
        h = h % 360
        x = (1 - abs((h / 60) % 2 - 1)) * 255
        if h < 60:
            return (255, int(x), 0)
        if h < 120:
            return (int(x), 255, 0)
        if h < 180:
            return (0, 255, int(x))
        if h < 240:
            return (0, int(x), 255)
        if h < 300:
            return (int(x), 0, 255)
        return (255, 0, int(x))

    def _set_all(self, r, g, b):
        for i in range(self.strip0.led_count):
            self.strip0.RGBto3Bytes(i, r, g, b)
            self.strip1.RGBto3Bytes(i, r, g, b)
        self.strip0.LED_show()
        self.strip1.LED_show()

    def run(self):
        idx = 0
        while not self._stop:
            try:
                mode = self._mode

                if mode == "standby":
                    # rainbow rotate
                    for i in range(self.strip0.led_count):
                        h = (idx + i * 40) % 360
                        r, g, b = self._hue_to_rgb(h)
                        self.strip0.RGBto3Bytes(i, r, g, b)
                        self.strip1.RGBto3Bytes(i, r, g, b)
                    self.strip0.LED_show()
                    self.strip1.LED_show()
                    self.msleep(50)
                    idx = (idx + 8) % 360

                elif mode == "green":
                    self._set_all(0, 150, 0)
                    self.msleep(120)

                elif mode == "yellow_flash":
                    self._set_all(255, 160, 0)
                    self.msleep(120)
                    self.strip0.LED_OFF_ALL()
                    self.strip1.LED_OFF_ALL()
                    self.msleep(120)

                elif mode == "pink_flash":
                    self._set_all(255, 0, 120)
                    self.msleep(120)
                    self.strip0.LED_OFF_ALL()
                    self.strip1.LED_OFF_ALL()
                    self.msleep(120)

                else:
                    self.msleep(60)

            except Exception:
                self.msleep(200)

        # on stop, ensure LEDs are turned off
        try:
            self.strip0.LED_OFF_ALL()
            self.strip1.LED_OFF_ALL()
        except Exception:
            pass


# ----------------------------------------------------------------------
#  DualPingWorker (from pingScreenv005, with distanceUpdated)
# ----------------------------------------------------------------------

class DualPingWorker(QThread):
    """
    Dual MB1040 worker.

    Signals:
      - ready(avg_distance_in, "either"): when distance <= TRIGGER_IN
      - log(str): text logs
      - distanceUpdated(float): continuous distance updates for radar
    """

    ready = pyqtSignal(float, str)      # avg_distance_in, "either"
    log = pyqtSignal(str)               # text log
    distanceUpdated = pyqtSignal(float) # continuous distance updates

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import Jetson.GPIO as GPIO
        except Exception as e:
            self.log.emit(f"ping error: Jetson.GPIO not available: {e}")
            return

        import time as _time

        SENSOR1_PIN = 15
        SENSOR2_PIN = 32
        HARD_MIN_IN = 6.0
        MAX_IN = 254.0
        TRIGGER_IN = 13.0

        def measure_pulse(pin, timeout=0.05):
            if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
                return None
            start_ns = _time.monotonic_ns()
            if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
                return None
            end_ns = _time.monotonic_ns()
            return (end_ns - start_ns) / 1000.0  # microseconds

        def read_distance(pin, label):
            width_us = measure_pulse(pin)
            if width_us is None:
                self.log.emit(f"{label} → no pulse detected")
                return None
            distance_in = width_us / 147.0
            if not (HARD_MIN_IN <= distance_in <= MAX_IN):
                self.log.emit(f"{label} → out of range ({distance_in:.2f} in)")
                return None
            distance_cm = distance_in * 2.54
            self.log.emit(f"{label} → {distance_in:.2f} in ({distance_cm:.2f} cm)")
            return distance_in

        try:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(SENSOR1_PIN, GPIO.IN)
            GPIO.setup(SENSOR2_PIN, GPIO.IN)

            self.log.emit("ping worker active (instantaneous dual mb1040)...")

            while not self._stop:
                d1 = read_distance(SENSOR1_PIN, "sensor 1")
                _time.sleep(0.1)
                d2 = read_distance(SENSOR2_PIN, "sensor 2")

                active_dist = None

                if d1 is not None and d2 is not None:
                    avg = (d1 + d2) / 2.0
                    diff = d1 - d2
                    self.log.emit(f"→ fused avg: {avg:.2f} in | offset: {diff:.2f} in")
                    active_dist = avg
                elif d1 is not None or d2 is not None:
                    active_dist = d1 if d1 is not None else d2
                    self.log.emit(f"→ single sensor active: {active_dist:.2f} in")
                else:
                    self.log.emit("→ both sensors out of range")

                if active_dist is not None:
                    self.distanceUpdated.emit(active_dist)
                    if active_dist <= TRIGGER_IN:
                        self.log.emit("distance < 13 in — ready to scan")
                        self.ready.emit(active_dist, "either")
                        break

                _time.sleep(0.25)

        except Exception as e:
            self.log.emit(f"ping error: {e}")
        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.log.emit("ping gpio cleaned up")


# ----------------------------------------------------------------------
#  Manifest matcher
# ----------------------------------------------------------------------

class SimpleManifestMatcher:
    """Case-insensitive exact matcher for manifest barcodes."""

    def __init__(self, codes):
        self.codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        self._lut = {c.lower(): c for c in self.codes}

    def match(self, code: str):
        if not code:
            return None, 0, "none"
        key = str(code).strip().lower()
        if key in self._lut:
            return self._lut[key], 100, "exact"
        return None, 0, "none"


# ----------------------------------------------------------------------
#  BarcodeReaderWorker (CSI + YOLO + pyzbar)
# ----------------------------------------------------------------------

class BarcodeReaderWorker(QThread):
    """
    CSI camera + YOLO + pyzbar barcode reader.

    Emits:
      - log(str)
      - decoded(str)
      - matched(str, int, str)
      - finished_all()
    """

    log = pyqtSignal(str)
    decoded = pyqtSignal(str)
    matched = pyqtSignal(str, int, str)
    finished_all = pyqtSignal()

    def __init__(
        self,
        model_path="my_model.pt",
        sensor_id=0,
        width=1920,
        height=1080,
        framerate=5,
        min_conf=0.25,
        iou=0.45,
        max_rois=6,
        decode_every=1,
        fallback_interval=15,
        manifest_codes=None,
    ):
        super().__init__()
        self.model_path = model_path
        self.sensor_id = sensor_id
        self.width = width
        self.height = height
        self.framerate = framerate
        self.min_conf = min_conf
        self.iou = iou
        self.max_rois = max_rois
        self.decode_every = decode_every
        self.fallback_interval = fallback_interval
        self._stop = False
        self._manifest_codes = list(manifest_codes or [])
        self._found = set()
        self.Gst = None  # filled in run()

    def stop(self):
        self._stop = True

    # --- helpers from original GUI ---

    def _unwarp_barcode(self, crop_img):
        try:
            import cv2
            import numpy as np
            from PIL import Image
        except Exception:
            return crop_img

        try:
            img = cv2.cvtColor(np.array(crop_img), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]
            if min(h, w) < 40:
                return crop_img

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            grad = cv2.morphologyEx(
                gray,
                cv2.MORPH_GRADIENT,
                cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
            )
            _, bw = cv2.threshold(
                grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
            )

            cnts, _ = cv2.findContours(
                bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not cnts:
                return crop_img
            c = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(c) < 100:
                return crop_img

            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) != 4:
                x, y, ww, hh = cv2.boundingRect(c)
                if ww <= 0 or hh <= 0:
                    return crop_img
                pad = int(max(2, min(10, 0.05 * max(ww, hh))))
                x0 = max(0, x - pad)
                y0 = max(0, y - pad)
                x1 = min(w, x + ww + pad)
                y1 = min(h, y + hh + pad)
                roi = img[y0:y1, x0:x1]
                try:
                    return Image.fromarray(
                        cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                    )
                except Exception:
                    return crop_img

            pts = approx.reshape(4, 2).astype("float32")

            def order_pts(pts_):
                rect = np.zeros((4, 2), dtype="float32")
                s = pts_.sum(axis=1)
                rect[0] = pts_[np.argmin(s)]
                rect[2] = pts_[np.argmax(s)]
                diff = np.diff(pts_, axis=1)
                rect[1] = pts_[np.argmin(diff)]
                rect[3] = pts_[np.argmax(diff)]
                return rect

            rect = order_pts(pts)
            (tl, tr, br, bl) = rect
            widthA = np.linalg.norm(br - bl)
            widthB = np.linalg.norm(tr - tl)
            maxWidth = max(int(widthA), int(widthB))
            heightA = np.linalg.norm(tr - br)
            heightB = np.linalg.norm(tl - bl)
            maxHeight = max(int(heightA), int(heightB))

            if maxWidth < 20 or maxHeight < 10:
                return crop_img

            dst = np.array(
                [
                    [0, 0],
                    [maxWidth - 1, 0],
                    [maxWidth - 1, maxHeight - 1],
                    [0, maxHeight - 1],
                ],
                dtype="float32",
            )
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))

            if warped.shape[1] < warped.shape[0]:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
        except Exception:
            return crop_img

    def _make_pipeline(self):
        return (
            f"nvarguscamerasrc sensor-id={self.sensor_id} ! "
            f"video/x-raw(memory:NVMM), width={self.width}, height={self.height}, framerate={self.framerate}/1 ! "
            "nvvidconv ! video/x-raw, format=BGRx ! "
            "videoconvert ! video/x-raw, format=BGR ! "
            "appsink name=sink emit-signals=false max-buffers=1 drop=true sync=false"
        )

    def _pull_frame(self, appsink):
        sample = appsink.emit("pull-sample")
        if sample is None:
            return None
        buf = sample.get_buffer()
        caps = sample.get_caps()
        width = caps.get_structure(0).get_value("width")
        height = caps.get_structure(0).get_value("height")
        ok, map_info = buf.map(self.Gst.MapFlags.READ)  # type: ignore
        if not ok:
            return None
        try:
            import numpy as np

            frame = (
                np.frombuffer(map_info.data, dtype=np.uint8)
                .reshape((height, width, 3))
            )
            return frame
        finally:
            buf.unmap(map_info)

    def _yolo_rois(self, model, img):
        res = model.predict(img, conf=self.min_conf, iou=self.iou, verbose=False)
        if not res or len(res) == 0 or res[0].boxes is None or res[0].boxes.xyxy is None:
            return []
        boxes = res[0].boxes
        import numpy as np

        xyxy = boxes.xyxy.cpu().numpy().astype(int)
        if xyxy.size == 0:
            return []
        confs = (
            boxes.conf.cpu().numpy()
            if boxes.conf is not None
            else np.ones((xyxy.shape[0],), dtype=float)
        )
        areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
        order = np.argsort(-(confs * (areas.clip(min=1))))
        xyxy = xyxy[order][: self.max_rois]
        out = [
            (int(x1), int(y1), int(x2), int(y2))
            for x1, y1, x2, y2 in xyxy
        ]
        return out

    def _decode_from_rois(self, img_rgb, rois):
        from PIL import ImageOps
        from pyzbar.pyzbar import decode as zbar_decode

        out = []
        for (x1, y1, x2, y2) in rois:
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(img_rgb.width, x2)
            y2 = min(img_rgb.height, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = img_rgb.crop((x1, y1, x2, y2))
            try:
                crop = self._unwarp_barcode(crop)
            except Exception:
                pass
            crop_gray = ImageOps.grayscale(crop)
            res = zbar_decode(crop_gray)
            for r in res:
                try:
                    val = r.data.decode("utf-8", errors="ignore")
                except Exception:
                    val = None
                if val and val not in out:
                    out.append(val)
        return out

    def run(self):
        try:
            from ultralytics import YOLO
            from PIL import Image
            import gi

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst

            self.Gst = Gst
        except Exception as e:
            self.log.emit(f"[error] imports failed: {e}")
            return

        pipeline = None
        try:
            matcher = SimpleManifestMatcher(self._manifest_codes)

            self.Gst.init(None)
            pipeline_str = self._make_pipeline()
            pipeline = self.Gst.parse_launch(pipeline_str)
            appsink = pipeline.get_by_name("sink")
            if appsink is None:
                self.log.emit("[error] appsink 'sink' not found")
                return
            pipeline.set_state(self.Gst.State.PLAYING)
            self.log.emit("[info] csi pipeline started")

            self.log.emit(f"[info] loading yolo: {self.model_path}")
            model = YOLO(self.model_path)

            frame_idx = 0
            expected_total = len(self._manifest_codes)
            if expected_total == 0:
                self.log.emit("[warn] no manifest barcodes loaded")
            else:
                self.log.emit(
                    f"[info] expecting {expected_total} barcodes from manifest"
                )

            while not self._stop:
                frame_bgr = self._pull_frame(appsink)
                if frame_bgr is None:
                    time.sleep(0.2)
                    self.log.emit("no barcodes read")
                    continue

                frame_idx += 1
                if self.decode_every > 1 and (frame_idx % self.decode_every != 0):
                    time.sleep(0.2)
                    self.log.emit("no barcodes read")
                    continue

                img_rgb = Image.fromarray(frame_bgr[:, :, ::-1], mode="RGB")

                rois = self._yolo_rois(model, img_rgb)
                decoded = self._decode_from_rois(img_rgb, rois)

                if not decoded and self.fallback_interval > 0 and (
                    frame_idx % self.fallback_interval == 0
                ):
                    from PIL import ImageOps
                    from pyzbar.pyzbar import decode as zbar_decode

                    ff_gray = ImageOps.grayscale(img_rgb)
                    for r in zbar_decode(ff_gray):
                        try:
                            val = r.data.decode("utf-8", errors="ignore")
                        except Exception:
                            val = None
                        if val and val not in decoded:
                            decoded.append(val)

                if decoded:
                    for val in decoded:
                        self.decoded.emit(val)
                        rec, score, method = matcher.match(val)
                        if rec:
                            self.matched.emit(rec, score, method)
                            self._found.add(rec.strip())
                            self.log.emit(f"{val} is loaded")
                        else:
                            self.log.emit(f"{val} is not part of shipment")

                    if expected_total and len(self._found) >= expected_total:
                        self.log.emit("all barcodes found — scanning complete")
                        self.finished_all.emit()
                        break
                else:
                    self.log.emit("no barcodes read")

                time.sleep(0.2)

        except Exception as e:
            self.log.emit(f"[error] barcode reader crashed: {e}")
        finally:
            try:
                if pipeline is not None:
                    pipeline.set_state(self.Gst.State.NULL)
            except Exception:
                pass


# ----------------------------------------------------------------------
#  Generic GlitchTitle widget (no LEDs; screens can reuse)
# ----------------------------------------------------------------------

class GlitchTitle(QWidget):
    """
    Generic centered glitch title, no LED integration.

    Usage:
        title = GlitchTitle("SHIPMENT IN PROGRESS", font_size=40)
    """

    def __init__(self, text="TITLE", font_size=40, parent=None):
        from PyQt5.QtWidgets import QWidget as _QW  # avoid circular import at top
        # Can't inherit after dynamic import; do it directly here instead.
        # To keep this simple, we just define GlitchTitle as a QWidget subclass above.
        # NOTE: This comment is kept for context; actual class is already QWidget subclass.
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.font = QFont("Arial", font_size, QFont.Bold)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

    def update_glitch(self):
        import random, string
        if random.random() < 0.35:
            self.glitch_strength = random.randint(3, 10)
            chars = list(self.text)
            for i in range(len(chars)):
                if random.random() < 0.15:
                    chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
            self.scrambled = "".join(chars)
        else:
            self.scrambled = self.text
            self.glitch_strength = 0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        rect = p.boundingRect(self.rect(), Qt.AlignCenter, self.scrambled)
        fm = self.fontMetrics()
        baseline = rect.y() + rect.height() - fm.descent()

        x = rect.x()
        y = baseline

        # base white
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        if self.glitch_strength > 0:
            shift = self.glitch_strength

            p.setPen(QColor(255, 0, 0, 180))      # red left
            p.drawText(x - shift, y, self.scrambled)

            p.setPen(QColor(0, 255, 255, 180))    # cyan right
            p.drawText(x + shift, y, self.scrambled)

            import random
            if random.random() < 0.35:
                jitter_x = x + random.randint(-10, 10)
                jitter_y = y + random.randint(-15, 15)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()
