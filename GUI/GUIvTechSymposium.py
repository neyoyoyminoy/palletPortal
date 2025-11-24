"""
GUIvTechSymposium.py

Pallet Portal GUI:
- USB-gated welcome screen
- Menu (Ship / View Order)
- Dual ping sensors to start scanning
- Dual CSI cameras with YOLO + pyzbar manifest matching
- SPI-based WS2812 LED strips on SPI0_MOSI (pin 19) and SPI1_MOSI (pin 37)
"""

"""
This codes works the most consistent. it is able to go through three manifests of 10 barcodes.
THIS ONE WORKS

"""

import os, re, sys, time
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QStackedWidget,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
)

import spidev

# --- gpio availability check ---
try:
    import Jetson.GPIO as _GPIO  # noqa: F401
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False


BARCODE_FILENAME_CANDIDATES = ["barcodes.txt"]


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


# -------------------- shipment list parsing --------------------
class ShipmentList:
    # this just carries the list of barcodes from the text file
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


# -------------------- USBWatcher --------------------
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
            for c in (filename_candidates or ["barcode.txt", "barcodes.txt", "manifest.txt"])
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


# -------------------- welcome & menu screens --------------------
# -------------------- WelcomeScreen (updated) --------------------
class WelcomeScreen(QWidget):
    proceed = pyqtSignal(object, str)  # (ShipmentList, mount_dir)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        t = QLabel("Welcome")
        t.setAlignment(Qt.AlignCenter)
        t.setFont(QFont("Beausite Classic", 40))
        t.setStyleSheet("color:#0c2340;background-color:#f15a22;font-weight:bold;")
        lay.addWidget(t)

        sub = QLabel("Insert flash drive with barcodes file to begin")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.status = QLabel("Waiting for USB...")
        self.status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status)

        self.debug = QTextEdit()
        self.debug.setReadOnly(True)
        self.debug.setVisible(True)
        lay.addWidget(self.debug)

        hint = QLabel(
            "Press 'X + ✔' to force rescan. Looking under: "
            + ", ".join(DEFAULT_MOUNT_ROOTS)
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        # USB watcher
        self.watcher = USBWatcher()
        self.watcher.status.connect(self._on_status)
        self.watcher.validListFound.connect(self._on_valid)
        self.watcher.start()

    def showEvent(self, event):
        """Ensure scanning resumes whenever screen becomes active"""
        super().showEvent(event)
        if not self.watcher.isRunning():
            self.watcher.start()
            self.status.setText("Waiting for USB...")

    def keyPressEvent(self, e):
        k = e.key()

        # Detect C then V (sequential)
        if k == Qt.Key_C:
            self._last_key = "C"
            e.accept()
            return

        if k == Qt.Key_V and getattr(self, "_last_key", None) == "C":
            self._on_status("manual rescan requested.")
            self.watcher.scan_once()
            self._last_key = None
            e.accept()
            return

        # Anything else resets the sequence
        self._last_key = None
        super().keyPressEvent(e)

    def _on_status(self, msg):
        self.status.setText(msg)
        self.debug.append(msg)

    def _on_valid(self, shipment, root):
        """Stop scanning and proceed to next screen"""
        self.watcher.stop()
        self.proceed.emit(shipment, root)

class MenuScreen(QWidget):
    shipSelected = pyqtSignal()
    viewOrderSelected = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.opts = ["Ship", "View Order"]
        self.idx = 0

        lay = QVBoxLayout(self)
        t = QLabel("Menu")
        t.setAlignment(Qt.AlignCenter)
        t.setFont(QFont("Beausite Classic", 36))
        t.setStyleSheet(
            "color:#0c2340;background-color:#f15a22;font-weight:bold;"
        )
        lay.addWidget(t)

        self.top = QLabel(self.opts[0])
        self.bot = QLabel(self.opts[1])
        for l in (self.top, self.bot):
            l.setAlignment(Qt.AlignCenter)
            l.setFont(QFont("Beausite Classic", 32))
            l.setMargin(12)
            lay.addWidget(l)

        self._refresh()

    def _refresh(self):
        sel = "border:4px solid #0c2340;border-radius:16px;"
        norm = "border:none;"
        self.top.setStyleSheet(sel if self.idx == 0 else norm)
        self.bot.setStyleSheet(sel if self.idx == 1 else norm)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.idx = (self.idx - 1) % 2
            self._refresh()
            e.accept()
            return
        if k == Qt.Key_Control:
            self.idx = (self.idx + 1) % 2
            self._refresh()
            e.accept()
            return
        if k == Qt.Key_V:
            if self.idx == 0:
                self.shipSelected.emit()
            else:
                self.viewOrderSelected.emit()
            e.accept()
            return
        super().keyPressEvent(e)

# -------------------- ws2812 led strip (multi-SPI support) --------------------
# based on https://github.com/seitomatsubara/Jetson-nano-WS2812-LED-/blob/master/W2812.py
# note: enable spi0 and spi1 via jetson-io; pin19=spi0_mosi, pin37=spi1_mosi.

class SPItoWS:
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

# LED worker that helps dislpay correct led colors for different portions of the code.
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
    to_yellow_pulse = pyqtSignal()  # kept name for compatibility; triggers yellow_flash
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
        self.to_yellow_pulse.connect(self._enter_yellow)  # still called by external code
        self.to_pink_flash.connect(self._start_pink)

    def reset_for_next_usb(self):
        # called when returning to welcome for a new trailer
        self._completion_active = False
        self._steady_mode = "standby"
        self._mode = "standby"

    # --- mode helpers ---
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
        # switch to continuous yellow flashing mode
        self._mode = "yellow_flash"

    def _start_pink(self):
        # once we enter completion, lock until reset_for_next_usb()
        self._completion_active = True
        self._mode = "pink_flash"

    def stop(self):
        # graceful stop flag for the run loop
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
                    # steady green
                    self._set_all(0, 150, 0)
                    self.msleep(120)

                elif mode == "yellow_flash":
                    # continuous yellow flashing until another mode overrides
                    self._set_all(255, 160, 0)
                    self.msleep(120)
                    self.strip0.LED_OFF_ALL()
                    self.strip1.LED_OFF_ALL()
                    self.msleep(120)

                elif mode == "pink_flash":
                    # continuous pink flashing until reset_for_next_usb()
                    self._set_all(255, 0, 120)
                    self.msleep(120)
                    self.strip0.LED_OFF_ALL()
                    self.strip1.LED_OFF_ALL()
                    self.msleep(120)

                else:
                    # unknown mode — idle briefly
                    self.msleep(60)

            except Exception:
                # if something goes wrong, back off a bit to avoid tight exception loops
                self.msleep(200)

        # on stop, ensure LEDs are turned off
        try:
            self.strip0.LED_OFF_ALL()
            self.strip1.LED_OFF_ALL()
        except Exception:
            pass

# -------------------- DualPingWorker --------------------
class DualPingWorker(QThread):
    ready = pyqtSignal(float, str)  # (avg_distance_in, "either")
    log = pyqtSignal(str)

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
            return (end_ns - start_ns) / 1000.0

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

            self.log.emit("alternating MB1040 readings every 3 s (instantaneous mode)...")
            while not self._stop:
                d1 = read_distance(SENSOR1_PIN, "sensor 1")
                _time.sleep(0.1)
                d2 = read_distance(SENSOR2_PIN, "sensor 2")

                if d1 is not None and d2 is not None:
                    avg = (d1 + d2) / 2.0
                    diff = d1 - d2
                    self.log.emit(f"→ Fused Avg: {avg:.2f} in | Offset: {diff:.2f} in")
                    if (d1 <= TRIGGER_IN) or (d2 <= TRIGGER_IN):
                        self.log.emit("one sensor < 13 in — ready to scan")
                        self.ready.emit(avg, "either")
                        break
                elif d1 is not None or d2 is not None:
                    active = d1 if d1 is not None else d2
                    self.log.emit(f"→ Single Sensor Active: {active:.2f} in")
                    if active <= TRIGGER_IN:
                        self.log.emit("single sensor < 13 in — ready to scan")
                        self.ready.emit(active, "either")
                        break
                else:
                    self.log.emit("→ both sensors out of range")

                _time.sleep(3.0)

        except Exception as e:
            self.log.emit(f"ping error: {e}")
        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.log.emit("ping gpio cleaned up")


# ------------------ simple manifest matcher --------------------
class SimpleManifestMatcher:
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


# --------------- BarcodeReaderWorker -------------------
class BarcodeReaderWorker(QThread):
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

    def stop(self):
        self._stop = True

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

# -------------------- ShipScreen (updated with order recording) --------------------
# -------------------- ShipScreen (updated with normalization + order recording) --------------------
class ShipScreen(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("Ship")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Beausite Classic", 36))
        title.setStyleSheet("color: #0c2340; background-color: #f15a22; font-weight:bold;")
        layout.addWidget(title)

        self._leds = None

        self.status = QLabel("Waiting for ping sensor...")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        layout.addWidget(QLabel("Scanned Barcodes:"))
        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.scanned_list)
        self._barcode_items = {}

        self._expected_codes = []
        self._found = set()
        self._all_done_fired = False
        self._barcode_worker = None
        self._barcode_worker2 = None
        self.worker = None
        self._current_usb_path = None
        self._start_time = None

    # Normalizes any scanned value or expected manifest value
    def _normalize(self, s: str) -> str:
        if not s:
            return ""
        s = s.strip().replace("\r", "").replace("\n", "")
        s = s.upper()
        return s

    # ---------------------------------------------------------------------

    def set_manifest_codes(self, codes):
        clean = [self._normalize(c) for c in codes]
        self._expected_codes = clean
        self._found.clear()
        self._all_done_fired = False
        self.scanned_list.clear()
        self._barcode_items.clear()

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            item.setForeground(Qt.black)
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    def set_current_usb_path(self, path):
        self._current_usb_path = path
        self._start_time = datetime.now()
        self._log(f"Started scanning USB: {path} at {self._start_time.strftime('%H:%M:%S')}")

    def _log(self, msg):
        self.log.append(msg)

    def on_attach(self, main_window):
        self._leds = getattr(main_window, "leds", None)

    # ----- ping ready -----
    def _on_ready(self, dist_in, label):
        self.status.setText("CSI cameras are starting up...")
        if self._leds:
            self._leds.to_green.emit()

        self._log(f"sensor ready (~{dist_in:.2f} in avg) -> starting csi")
        self._all_done_fired = False

        # Start 2 CSI workers
        for idx in range(2):
            attr = "_barcode_worker" if idx == 0 else "_barcode_worker2"
            if getattr(self, attr) is None:
                worker = BarcodeReaderWorker(
                    model_path="my_model.pt",
                    sensor_id=idx,
                    width=1920,
                    height=1080,
                    framerate=5,
                    min_conf=0.25,
                    iou=0.45,
                    max_rois=6,
                    decode_every=1,
                    fallback_interval=15,
                    manifest_codes=self._expected_codes,
                )
                worker.log.connect(self._log)
                worker.matched.connect(self._on_match)
                worker.finished_all.connect(self._on_all_done)
                setattr(self, attr, worker)
                worker.start()

        # flash yellow after first decode
        def _first_decode(_):
            if self._leds:
                self._leds.to_yellow_pulse.emit()
            for w in (self._barcode_worker, self._barcode_worker2):
                if w:
                    try: w.decoded.disconnect(_first_decode)
                    except: pass

        for w in (self._barcode_worker, self._barcode_worker2):
            if w:
                try: w.decoded.connect(_first_decode)
                except: pass

    # ---------------------------------------------------------------------
    # MATCH HANDLER with NORMALIZATION
    # ---------------------------------------------------------------------
    def _on_match(self, val, score=None, method=None):
        clean = self._normalize(val)

        if clean in self._found:
            return

        # confirm it matches manifest
        if clean not in self._expected_codes:
            self._log(f"Ignored non-manifest scan: {val}")
            return

        self._found.add(clean)
        self._log(f"{clean} matched")

        item = self._barcode_items.get(clean)
        if item:
            item.setForeground(Qt.gray)
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

    # ---------------------------------------------------------------------

    def _on_all_done(self):
        if self._all_done_fired:
            return
        self._all_done_fired = True

        for w in (self._barcode_worker, self._barcode_worker2):
            if w:
                try: w.finished_all.disconnect(self._on_all_done)
                except: pass

        self.status.setText("Manifest complete! Please remove USB drive.")
        self._log("All barcodes found — manifest complete.")

        try: self.stop_ping()
        except: pass

        for attr in ("_barcode_worker", "_barcode_worker2"):
            w = getattr(self, attr)
            if w and w.isRunning():
                w.stop()
                w.wait(2000)
            setattr(self, attr, None)

        if self._leds:
            self._leds.to_pink_flash.emit()

        self._wait_for_usb_removal()

    # ---------------------------------------------------------------------

    def _wait_for_usb_removal(self):
        mount_root = "/media"
        usb_present = False

        if os.path.isdir(mount_root):
            for user in os.listdir(mount_root):
                full = os.path.join(mount_root, user)
                if os.path.isdir(full) and os.listdir(full):
                    usb_present = True
                    break

        if not usb_present:
            self._return_to_welcome()
        else:
            QTimer.singleShot(500, self._wait_for_usb_removal)

    # ---------------------------------------------------------------------

    def _return_to_welcome(self):
        mw = self.window()
        if not mw:
            return

        if getattr(self, "_current_usb_path", None):
            mw.completed_usb_paths.add(self._current_usb_path)
            self._log(f"Recorded completed USB path: {self._current_usb_path}")

            # Add to ViewOrderScreen
            end_time = datetime.now()
            scanned_count = len(self._found)
            trailer_number = os.path.basename(self._current_usb_path)
            if hasattr(mw, "view"):
                mw.view.add_order(
                    start_time=self._start_time,
                    end_time=end_time,
                    scanned_count=scanned_count,
                    trailer_number=trailer_number
                )

            self._current_usb_path = None
            self._start_time = None
            self._found.clear()
            self.scanned_list.clear()

        completed = len(mw.completed_usb_paths)
        self._log(f"Completed USB count: {completed}/3")

        if self._leds:
            try:
                self._leds.reset_for_next_usb()
                self._leds.to_standby.emit()
            except:
                pass

        if completed >= 3:
            try: mw.setCurrentIndex(3)
            except: pass
            return

        try:
            mw.welcome.watcher.start()
            mw.welcome.status.setText("Waiting for USB...")
        except:
            pass

        mw.setCurrentIndex(0)

    # ---------------------------------------------------------------------

    def start_ping(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            self.worker = DualPingWorker()
            self.worker.log.connect(self._log)
            self.worker.ready.connect(self._on_ready)
            self._log("ping worker starting…")
            self.worker.start()
        except Exception as e:
            self._log(f"failed to start ping worker: {e}")
            self.worker = None

    def stop_ping(self):
        if not self.worker:
            return
        try:
            if self.worker.isRunning():
                self._log("stopping ping worker…")
                self.worker.stop()
                self.worker.wait(800)
        except Exception as e:
            self._log(f"error stopping ping worker: {e}")
        finally:
            self.worker = None

    def showEvent(self, e):
        super().showEvent(e)
        self.start_ping()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_ping()

    def closeEvent(self, e):
        try: self.stop_ping()
        except: pass
        super().closeEvent(e)

# -------------------- ViewOrderScreen (column style) --------------------
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSignal
from datetime import datetime

class ViewOrderScreen(QWidget):
    return_to_welcome = pyqtSignal()  # emit when X/C is pressed

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("View Orders")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Beausite Classic", 36))
        title.setStyleSheet(
            "color: #0c2340; background-color: #f15a22; font-weight: bold;"
        )
        layout.addWidget(title)

        # Scrollable area for orders
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        self.container = QWidget()
        self.scroll_area.setWidget(self.container)

        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_layout.setHorizontalSpacing(20)
        self.grid_layout.setVerticalSpacing(5)

        # Column headers
        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 12, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, col)

        self._next_row = 1  # track next row for new orders

        # Internal storage
        self.orders = []

        # Status label for messages
        self.status = QLabel("Press X to return to Welcome Screen")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(self.status)

    def add_order(self, start_time, end_time, scanned_count, trailer_number):
        """Add a completed order record in column style"""
        duration = end_time - start_time
        archway = "Archway 1"  # placeholder, update if needed

        order = {
            "start": start_time,
            "end": end_time,
            "duration": duration,
            "scanned_count": scanned_count,
            "archway": archway,
            "trailer": trailer_number,
        }
        self.orders.append(order)

        # Convert to display strings
        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
        duration_str = str(duration).split(".")[0]  # hh:mm:ss

        values = [trailer_number, archway, start_str, end_str, duration_str, str(scanned_count)]

        # Add to grid
        for col, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setFont(QFont("Arial", 11))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, self._next_row, col)

        self._next_row += 1

        # Keep status minimal at bottom
        self.status.setText("Press X to return to Welcome Screen")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_X, Qt.Key_C):
            import os, sys
            # Remove OpenCV's broken Qt plugin path environmental vars
            for k in list(os.environ.keys()):
                if "QT_QPA_PLATFORM_PLUGIN_PATH" in k or "QT_PLUGIN_PATH" in k:
                    os.environ.pop(k, None)

            python = sys.executable
            os.execv(python, [python] + sys.argv)

    def clear_orders(self):
        """Clear all orders from grid"""
        # Remove all widgets except header row
        for row in reversed(range(1, self._next_row)):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)
        self.orders.clear()
        self._next_row = 1
        self.status.setText("Press X to return to Welcome Screen")


# -------------------- MainWindow --------------------
# -------------------- MainWindow (updated) --------------------
class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "Pallet Portal GUI (USB-gated + Menu + Dual Ping + CSI)"
        )
        self.setMinimumSize(960, 540)

        self.completed_usb_paths = set()

        # LED worker
        self.leds = LEDWorker(num_leds=5)
        self.leds.start()
        self.leds.to_standby.emit()

        # Screens
        self.welcome = WelcomeScreen()
        self.menu = MenuScreen()
        self.ship = ShipScreen()
        self.ship.on_attach(self)
        self.view = ViewOrderScreen()

        # Add screens to stacked widget
        self.addWidget(self.welcome)
        self.addWidget(self.menu)
        self.addWidget(self.ship)
        self.addWidget(self.view)

        # Start at WelcomeScreen
        self.setCurrentIndex(0)

        # Connect signals
        self.welcome.proceed.connect(self._unlock_to_menu)
        self.menu.shipSelected.connect(lambda: self.setCurrentIndex(2))
        self.menu.viewOrderSelected.connect(self._goto_view_orders)
        self.view.return_to_welcome.connect(self._return_to_welcome)

    def _unlock_to_menu(self, shipment, source):
        self.expected_barcodes = shipment.barcodes
        self.ship.set_manifest_codes(self.expected_barcodes)
        self.ship.set_current_usb_path(source)
        self.setCurrentIndex(1)
        self.menu.setFocus()

    def _goto_view_orders(self):
        if self.leds:
            self.leds.to_standby.emit()
        self.setCurrentIndex(3)

    def _return_to_welcome(self):
        """Return from ViewOrderScreen to WelcomeScreen and resume USB scanning"""
        self.setCurrentIndex(0)
        # Ensure WelcomeScreen is fully reset for scanning
        if not self.welcome.watcher.isRunning():
            self.welcome.watcher.start()
            self.welcome.status.setText("Waiting for USB...")

    def closeEvent(self, e):
        try:
            if hasattr(self, "leds") and self.leds.isRunning():
                self.leds.stop()
                self.leds.wait(800)
        except Exception:
            pass
        super().closeEvent(e)

# -------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
