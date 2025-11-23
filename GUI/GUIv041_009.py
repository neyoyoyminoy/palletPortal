'''
guiv21.py
verified spi-based ws2812 integration for 5 leds on pin 19 (spi0_mosi)
based on https://github.com/seitomatsubara/Jetson-nano-WS2812-LED-/blob/master/W2812.py
'''

import os, re, sys, time
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QStackedWidget, QTextEdit, QListWidget, QListWidgetItem
import spidev
import sys

#---gpio availability check---
try:
    import Jetson.GPIO as _GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

BARCODE_FILENAME_CANDIDATES = ["barcodes.txt"]

def guess_mount_roots():
    roots=set()
    user=os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    for base in ["/media","/mnt","/run/media"]:
        roots.add(base)
        if user: roots.add(os.path.join(base,user))
    roots.add("/media/jetson")
    try:
        with open("/proc/mounts","r",encoding="utf-8",errors="ignore") as f:
            for line in f:
                p=line.split()
                if len(p)>=3:
                    mnt=p[1]; fstype=p[2].lower()
                    if any(fs in fstype for fs in("vfat","exfat","ntfs","fuseblk")):
                        roots.add(mnt)
    except: pass
    return [r for r in sorted(roots) if os.path.exists(r)]
DEFAULT_MOUNT_ROOTS=guess_mount_roots()

#--------------------shipment list parsing--------------------
class ShipmentList:
    #this just carries the list of barcodes from the text file
    def __init__(self,barcodes): self.barcodes=barcodes
    @staticmethod
    def parse(text:str):
        if text and text[0]=="\ufeff": text=text[1:]
        parts=[t.strip() for t in re.split(r"[\s,]+",text) if t.strip()]
        seen=set(); uniq=[]
        for p in parts:
            if p not in seen: seen.add(p); uniq.append(p)
        return ShipmentList(uniq) if uniq else None

# -------------------- USBWatcher (updated) --------------------
import os
from pathlib import Path
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

class USBWatcher(QObject):
    """
    Scans mount_roots for known manifest filenames, parses them with
    ShipmentList.parse(txt) and emits validListFound(parsed, mount_dir, usb_serial).

    - mount_roots: list of top-level mount roots to scan (default ['/media'])
    - filename_candidates: list of filenames to look for (lowercased)
    - poll_ms: polling interval in ms
    - approved_mounts: optional set/list of exact mount dirs to accept (e.g. ['/media/design25/KINGSTON'])
                       If provided, only these mounts will be considered valid.
    """
    # emitted when a valid manifest is found: (parsed_shipment, mount_dir, usb_serial)
    validListFound = pyqtSignal(object, str, str)
    # text status updates for UI
    status = pyqtSignal(str)

    def __init__(self, mount_roots=None, filename_candidates=None, poll_ms=1000, approved_mounts=None, parent=None):
        super().__init__(parent)
        self.mount_roots = mount_roots or ["/media"]
        self.filename_candidates = [c.lower() for c in (filename_candidates or ["barcode.txt", "barcodes.txt", "manifest.txt"])]
        self.timer = QTimer(self)
        self.timer.setInterval(poll_ms)
        self.timer.timeout.connect(self.scan_once)

        # optional filter: only accept manifests found under these exact mount dirs
        # e.g. ['/media/design25/KINGSTON', '/media/design25/USB321FD', '/media/design25/ESD-USB']
        self.approved_mounts = set(os.path.normpath(m) for m in (approved_mounts or []))

    def start(self):
        # run one immediate scan then start timer
        self.scan_once()
        self.timer.start()

    def stop(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    def _mount_dir_to_serial(self, mount_dir):
        """
        Extract the final path component as the USB 'serial' / label.
        e.g. '/media/design25/KINGSTON' -> 'KINGSTON'
        """
        try:
            return os.path.basename(os.path.normpath(mount_dir))
        except Exception:
            return mount_dir

    def scan_once(self):
        any_found = False
        for root in self.mount_roots:
            if not os.path.exists(root):
                continue

            # walk top-level mounts under root
            for dirpath, dirnames, filenames in os.walk(root):
                # limit depth to avoid scanning deep system paths (keep similar to original)
                depth = dirpath.strip(os.sep).count(os.sep) - root.strip(os.sep).count(os.sep)
                if depth > 3:
                    dirnames[:] = []
                    continue

                # skip pseudo-filesystems if they appear
                if any(p in dirpath for p in ("/proc", "/sys", "/dev", "/run/lock")):
                    continue

                lower_files = {fn.lower(): fn for fn in filenames}
                for cand_lower in self.filename_candidates:
                    if cand_lower in lower_files:
                        any_found = True
                        found = lower_files[cand_lower]
                        full = os.path.join(dirpath, found)
                        try:
                            txt = Path(full).read_text(encoding="utf-8", errors="ignore")
                        except Exception as e:
                            self.status.emit(f"found {found} at {dirpath}, but couldn't read: {e}")
                            continue

                        # parse using your project's ShipmentList parser
                        try:
                            parsed = ShipmentList.parse(txt)
                        except Exception as e:
                            parsed = None
                            self.status.emit(f"error parsing {full}: {e}")

                        if parsed:
                            norm_dir = os.path.normpath(dirpath)
                            usb_serial = self._mount_dir_to_serial(norm_dir)

                            # if approved_mounts provided, enforce it
                            if self.approved_mounts:
                                if norm_dir not in self.approved_mounts:
                                    self.status.emit(f"Ignored valid manifest at {norm_dir} (not in approved mounts)")
                                    # continue scanning other locations
                                    continue

                            self.status.emit(f"valid list found at: {full}")
                            # emit parsed object, the directory where it was found, and the usb "serial"/label
                            self.validListFound.emit(parsed, norm_dir, usb_serial)
                            return
                        else:
                            self.status.emit(f"{found} at {dirpath} did not contain any readable barcodes")

        if not any_found:
            self.status.emit("scanning for usb + barcodes file...")

# --------------------welcome & menu screens--------------------
class WelcomeScreen(QWidget):
    proceed=pyqtSignal(ShipmentList,str)
    def __init__(self):
        super().__init__()
        lay=QVBoxLayout(self)
        t=QLabel("Welcome"); t.setAlignment(Qt.AlignCenter)
        t.setFont(QFont("Beausite Classic",40))
        t.setStyleSheet("color:#0c2340;background-color:#f15a22;font-weight:bold;")
        lay.addWidget(t)
        sub=QLabel("Insert flash drive with barcodes file to begin")
        sub.setAlignment(Qt.AlignCenter); sub.setWordWrap(True); lay.addWidget(sub)
        self.status=QLabel("Waiting for USB..."); self.status.setAlignment(Qt.AlignCenter); lay.addWidget(self.status)
        self.debug=QTextEdit(); self.debug.setReadOnly(True); self.debug.setVisible(True); lay.addWidget(self.debug)
        hint=QLabel("Press 'R' to force rescan. Looking under: "+", ".join(DEFAULT_MOUNT_ROOTS))
        hint.setWordWrap(True); hint.setAlignment(Qt.AlignCenter); lay.addWidget(hint)
        self.watcher=USBWatcher(); self.watcher.status.connect(self._on_status); self.watcher.validListFound.connect(self._on_valid)
        self.watcher.start()
    def keyPressEvent(self,e):
        if e.key()==Qt.Key_R:
            self._on_status("manual rescan requested."); self.watcher.scan_once(); e.accept(); return
        super().keyPressEvent(e)
    def _on_status(self,msg): self.status.setText(msg); self.debug.append(msg)
    def _on_valid(self,shipment,root): self.watcher.stop(); self.proceed.emit(shipment,root)

class MenuScreen(QWidget):
    shipSelected=pyqtSignal(); viewOrderSelected=pyqtSignal()
    def __init__(self):
        super().__init__(); self.setFocusPolicy(Qt.StrongFocus)
        self.opts=["Ship","View Order"]; self.idx=0
        lay=QVBoxLayout(self)
        t=QLabel("Menu"); t.setAlignment(Qt.AlignCenter); t.setFont(QFont("Beausite Classic",36))
        t.setStyleSheet("color:#0c2340;background-color:#f15a22;font-weight:bold;"); lay.addWidget(t)
        self.top=QLabel(self.opts[0]); self.bot=QLabel(self.opts[1])
        for l in(self.top,self.bot): l.setAlignment(Qt.AlignCenter); l.setFont(QFont("Beausite Classic",32)); l.setMargin(12); lay.addWidget(l)
        self._refresh()
    def _refresh(self):
        sel="border:4px solid #0c2340;border-radius:16px;"; norm="border:none;"
        self.top.setStyleSheet(sel if self.idx==0 else norm)
        self.bot.setStyleSheet(sel if self.idx==1 else norm)
    def keyPressEvent(self,e):
        k=e.key()
        if k in(Qt.Key_Return,Qt.Key_Enter): self.idx=(self.idx-1)%2; self._refresh(); e.accept(); return
        if k==Qt.Key_Control: self.idx=(self.idx+1)%2; self._refresh(); e.accept(); return
        if k==Qt.Key_V:
            (self.shipSelected if self.idx==0 else self.viewOrderSelected).emit(); e.accept(); return
        super().keyPressEvent(e)

#-------------------- ws2812 led strip (multi-SPI support) --------------------
# based on https://github.com/seitomatsubara/Jetson-nano-WS2812-LED-/blob/master/W2812.py
# note: enable spi0 and spi1 via jetson-io; pin19=spi0_mosi, pin37=spi1_mosi.
# use a 330 Ω resistor in series with DIN and a 1000 µF cap across 5 V and GND.
import spidev
from PyQt5.QtCore import QThread, pyqtSignal


class SPItoWS:
    def __init__(self, ledc=5, bus=0, device=0):
        self.led_count = ledc
        self.bus = bus
        self.device = device
        # one bit-pattern string for all LEDs
        self.X = "100" * (self.led_count * 8 * 3)
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)           # 0 or 1 depending on strip
        self.spi.max_speed_hz = 2400000
        self.LED_OFF_ALL()

    def __del__(self):
        try:
            self.spi.close()
        except Exception:
            pass

    def _Bytesto3Bytes(self, num, RGB):
        """
        Internal: encode one 8-bit color channel into WS2812-style timing
        using the '100' / '110' pattern trick.
        """
        base = num * 24
        for i in range(8):
            pat = '100' if RGB[i] == '0' else '110'
            self.X = self.X[:base + i * 3] + pat + self.X[base + i * 3 + 3:]

    def LED_show(self):
        """
        Push the bit-pattern X out over SPI to the strip.
        """
        Y = []
        for i in range(self.led_count * 9):
            Y.append(int(self.X[i * 8:(i + 1) * 8], 2))
        self.spi.xfer3(Y, 2400000, 0, 8)

    def RGBto3Bytes(self, led_num, R, G, B):
        """
        Set one LED's RGB value in X (not shown until LED_show is called).
        """
        if any(v > 255 or v < 0 for v in (R, G, B)):
            raise ValueError("invalid rgb value")
        if led_num > self.led_count - 1 or led_num < 0:
            raise ValueError("invalid led index")
        RR, GG, BB = (format(R, '08b'), format(G, '08b'), format(B, '08b'))
        self._Bytesto3Bytes(led_num * 3, GG)
        self._Bytesto3Bytes(led_num * 3 + 1, RR)
        self._Bytesto3Bytes(led_num * 3 + 2, BB)

    def LED_OFF_ALL(self):
        """
        Turn all LEDs off.
        """
        self.X = "100" * (self.led_count * 8 * 3)
        self.LED_show()


class LEDWorker(QThread):
    """
    Dual WS2812 strips driven over SPI0 and SPI1.

    Modes:
      - standby      : rainbow
      - green        : solid green
      - yellow_pulse : two yellow flashes, then return to previous mode
      - pink_flash   : flashing pink after order complete
    """

    to_standby = pyqtSignal()
    to_green = pyqtSignal()
    to_yellow_pulse = pyqtSignal()
    to_pink_flash = pyqtSignal()

    def __init__(self, num_leds=5, parent=None):
        super().__init__(parent)

        self.strip0 = SPItoWS(num_leds, bus=0, device=0)
        self.strip1 = SPItoWS(num_leds, bus=1, device=0)

        self._mode = "standby"
        self._previous_mode = "standby"
        self._stop = False

        self.to_standby.connect(lambda: self._force_mode("standby"))
        self.to_green.connect(lambda: self._force_mode("green"))
        self.to_yellow_pulse.connect(self._enter_yellow)
        self.to_pink_flash.connect(lambda: self._force_mode("pink_flash"))

    # ----------------------------------------------
    # MODE HELPERS
    # ----------------------------------------------

    def _force_mode(self, m):
        """Set mode directly, saving state."""
        self._previous_mode = m
        self._mode = m

    def _enter_yellow(self):
        """Enter yellow pulse without losing previous mode."""
        if self._mode != "pink_flash":       # pink flash takes top priority
            self._previous_mode = self._mode
            self._mode = "yellow_pulse"

    # ----------------------------------------------

    def stop(self):
        self._stop = True

    # Rainbow helper
    def _hue_to_rgb(self, h):
        h = h % 360
        x = (1 - abs((h/60)%2 - 1)) * 255
        if h < 60:   return (255,int(x),0)
        if h < 120:  return (int(x),255,0)
        if h < 180:  return (0,255,int(x))
        if h < 240:  return (0,int(x),255)
        if h < 300:  return (int(x),0,255)
        return (255,0,int(x))

    def _set_all(self, r, g, b):
        for i in range(self.strip0.led_count):
            self.strip0.RGBto3Bytes(i,r,g,b)
            self.strip1.RGBto3Bytes(i,r,g,b)
        self.strip0.LED_show()
        self.strip1.LED_show()

    # ----------------------------------------------
    # THREAD LOOP
    # ----------------------------------------------

    def run(self):
        idx = 0
        while not self._stop:
            try:
                mode = self._mode

                # -----------------------------
                # STANDBY → rainbow
                # -----------------------------
                if mode == "standby":
                    for i in range(self.strip0.led_count):
                        h = (idx + i*40) % 360
                        r,g,b = self._hue_to_rgb(h)
                        self.strip0.RGBto3Bytes(i,r,g,b)
                        self.strip1.RGBto3Bytes(i,r,g,b)
                    self.strip0.LED_show()
                    self.strip1.LED_show()
                    self.msleep(50)
                    idx = (idx + 8) % 360

                # -----------------------------
                # GREEN → solid
                # -----------------------------
                elif mode == "green":
                    self._set_all(0,150,0)
                    self.msleep(120)

                # -----------------------------
                # YELLOW PULSE (fixed)
                # -----------------------------
                elif mode == "yellow_pulse":
                    for _ in range(2):
                        self._set_all(255,160,0)
                        self.msleep(100)
                        self.strip0.LED_OFF_ALL()
                        self.strip1.LED_OFF_ALL()
                        self.msleep(100)

                    # IMPORTANT:
                    # return to the stored previous mode
                    self._mode = self._previous_mode

                # -----------------------------
                # PINK FLASH
                # -----------------------------
                elif mode == "pink_flash":
                    self._set_all(255,0,120)
                    self.msleep(120)
                    self.strip0.LED_OFF_ALL()
                    self.strip1.LED_OFF_ALL()
                    self.msleep(120)

                else:
                    self.msleep(60)

            except Exception:
                self.msleep(200)

        # Cleanup on exit
        try:
            self.strip0.LED_OFF_ALL()
            self.strip1.LED_OFF_ALL()
        except:
            pass


# ==================== dual ping worker (based on dual mb1040 script) ====================
#this handles both mb1040 sensors alternating safely with smoothing
#based on dual mb1040 script adapted from crosstalk_filteringv2
# ==================== dual ping worker (simplified instantaneous readings) ====================
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

        import time

        # --- Pin assignments (BOARD numbering) ---
        SENSOR1_PIN = 15
        SENSOR2_PIN = 32

        # --- Sensor limits ---
        HARD_MIN_IN = 6.0
        MAX_IN = 254.0
        TRIGGER_IN = 13.0  # start CSI when either ≤ 13 in

        def measure_pulse(pin, timeout=0.05):
            """Measure one PWM pulse width (µs) with timeout."""
            if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
                return None
            start_ns = time.monotonic_ns()
            if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
                return None
            end_ns = time.monotonic_ns()
            return (end_ns - start_ns) / 1000.0

        def read_distance(pin, label):
            """Read one instantaneous pulse and return distance in inches."""
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
                time.sleep(0.1)  # crosstalk protection
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

                time.sleep(3.0)

        except Exception as e:
            self.log.emit(f"ping error: {e}")
        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.log.emit("ping gpio cleaned up")


#------------------ embedded: simple manifest matcher --------------------
#this wraps the usb-loaded barcodes into a simple matcher for exact checks
#based on manifest_matcher.py ideas (load and case-insensitive lookup)
class SimpleManifestMatcher:
    #this keeps a set and a dict for quick exact matches
    def __init__(self, codes):
        self.codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        # lower for lookup, keep original for echo
        self._lut = {c.lower(): c for c in self.codes}  #based on manifest_matcher.py lookup map

    def match(self, code: str):
        if not code:
            return None, 0, "none"
        key = str(code).strip().lower()
        if key in self._lut:
            # exact match like teammate script prints
            return self._lut[key], 100, "exact"  #based on manifest_matcher.py match()
        return None, 0, "none"

#--------------- embedded: csi camera barcode reader worker -------------------
#this uses pillow + yolo + pyzbar + gstreamer to read barcodes from the csi cam
#based on yolo_pillow_manifest.py functions and loop
class BarcodeReaderWorker(QThread):
    log = pyqtSignal(str)          #this shows in the ship screen debug box
    decoded = pyqtSignal(str)      #this fires for every decoded barcode
    matched = pyqtSignal(str, int, str)  #value, score, method
    finished_all = pyqtSignal()    #this fires when all manifest barcodes are found

    def __init__(self, model_path="my_model.pt", sensor_id=0, width=1920, height=1080, framerate=5,
                 min_conf=0.25, iou=0.45, max_rois=6, decode_every=1, fallback_interval=15,
                 manifest_codes=None):
        super().__init__()
        self.model_path = model_path
        self.sensor_id = sensor_id
        self.width = width
        self.height = height
        self.framerate = framerate  #now 5 fps
        self.min_conf = min_conf
        self.iou = iou
        self.max_rois = max_rois
        self.decode_every = decode_every
        self.fallback_interval = fallback_interval
        self._stop = False
        self._manifest_codes = list(manifest_codes or [])
        # this tracks matched codes until we hit all (per your request to stop when all found)
        self._found = set()

    def stop(self):
        self._stop = True

    # --- perspective unwarp helper (applies to ROI crops) ---
    def _unwarp_barcode(self, crop_img):
        """Attempt to detect a 4-corner barcode region inside the crop and return an unwarped PIL image.
        If detection fails, returns the original crop_img.
        This helper uses OpenCV but imports locally so it doesn't break GUI on dev machines without cv2.
        """
        try:
            import cv2
            import numpy as np
            from PIL import Image
        except Exception:
            # OpenCV not available — just return original
            return crop_img

        try:
            # convert PIL image to OpenCV BGR
            img = cv2.cvtColor(np.array(crop_img), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]

            # If the crop is very small, skip unwarping to save time
            if min(h, w) < 40:
                return crop_img

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # use morphological gradient + threshold to emphasize barcode bars
            grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3,3)))
            _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

            # find contours
            cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                return crop_img

            # take largest contour by area
            c = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(c) < 100:  # too small
                return crop_img

            # approximate to polygon and expect 4 corners
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) != 4:
                # fallback: try bounding rect of largest contour
                x,y,ww,hh = cv2.boundingRect(c)
                if ww <= 0 or hh <= 0:
                    return crop_img
                # expand slightly and crop
                pad = int(max(2, min(10, 0.05 * max(ww, hh))))
                x0 = max(0, x-pad); y0 = max(0, y-pad); x1 = min(w, x+ww+pad); y1 = min(h, y+hh+pad)
                roi = img[y0:y1, x0:x1]
                try:
                    return Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
                except Exception:
                    return crop_img

            pts = approx.reshape(4,2).astype('float32')

            # order points: tl,tr,br,bl
            def order_pts(pts):
                rect = np.zeros((4,2), dtype='float32')
                s = pts.sum(axis=1)
                rect[0] = pts[np.argmin(s)]
                rect[2] = pts[np.argmax(s)]
                diff = np.diff(pts, axis=1)
                rect[1] = pts[np.argmin(diff)]
                rect[3] = pts[np.argmax(diff)]
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

            dst = np.array([[0,0],[maxWidth-1,0],[maxWidth-1,maxHeight-1],[0,maxHeight-1]], dtype='float32')
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))

            # optionally rotate if the barcode appears vertical (make width > height)
            if warped.shape[1] < warped.shape[0]:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))

        except Exception:
            return crop_img

    def _make_pipeline(self):
        #this builds the gstreamer string for nvargus
        #based on yolo_pillow_manifest.py make_pipeline()
        return (
            f"nvarguscamerasrc sensor-id={self.sensor_id} ! "
            f"video/x-raw(memory:NVMM), width={self.width}, height={self.height}, framerate={self.framerate}/1 ! "
            f"nvvidconv ! video/x-raw, format=BGRx ! "
            f"videoconvert ! video/x-raw, format=BGR ! "
            f"appsink name=sink emit-signals=false max-buffers=1 drop=true sync=false"
        )

    def _pull_frame(self, appsink):
        #based on yolo_pillow_manifest.py pull_frame()
        sample = appsink.emit("pull-sample")
        if sample is None:
            return None
        buf = sample.get_buffer()
        caps = sample.get_caps()
        width = caps.get_structure(0).get_value("width")
        height = caps.get_structure(0).get_value("height")
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            import numpy as np
            frame = np.frombuffer(map_info.data, dtype=np.uint8).reshape((height, width, 3))
            return frame
        finally:
            buf.unmap(map_info)

    def _yolo_rois(self, model, img):
        #based on yolo_pillow_manifest.py yolo_rois()
        res = model.predict(img, conf=self.min_conf, iou=self.iou, verbose=False)
        if not res or len(res) == 0 or res[0].boxes is None or res[0].boxes.xyxy is None:
            return []
        boxes = res[0].boxes
        import numpy as np
        xyxy = boxes.xyxy.cpu().numpy().astype(int)
        if xyxy.size == 0:
            return []
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones((xyxy.shape[0],), dtype=float)
        areas = (xyxy[:,2]-xyxy[:,0]) * (xyxy[:,3]-xyxy[:,1])
        order = np.argsort(-(confs * (areas.clip(min=1))))
        xyxy = xyxy[order][:self.max_rois]
        out = [(int(x1), int(y1), int(x2), int(y2)) for x1, y1, x2, y2 in xyxy]
        return out

    def _decode_from_rois(self, img_rgb, rois):
        #based on yolo_pillow_manifest.py decode_from_rois()
        from PIL import ImageOps
        from pyzbar.pyzbar import decode as zbar_decode
        out = []
        for (x1, y1, x2, y2) in rois:
            x1 = max(0, x1); y1 = max(0, y1); x2 = min(img_rgb.width, x2); y2 = min(img_rgb.height, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = img_rgb.crop((x1, y1, x2, y2))

            # NEW: attempt to unwarp the crop to correct perspective/skew before decoding
            try:
                crop = self._unwarp_barcode(crop)
            except Exception:
                pass

            crop_gray = ImageOps.grayscale(crop)
            res = zbar_decode(crop_gray)
            for r in res:
                try:
                    val = r.data.decode('utf-8', errors='ignore')
                except Exception:
                    val = None
                if val and val not in out:
                    out.append(val)
        return out

    def run(self):
        #lazy imports so the rest of the gui can still load on dev machines
        #this mirrors teammate script pattern
        try:
            from ultralytics import YOLO  #based on yolo_pillow_manifest.py import
            from PIL import Image         #we convert frames to pillow
            import gi                     #gstreamer introspection
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            globals()['Gst'] = Gst  #stash for helpers
        except Exception as e:
            self.log.emit(f"[error] imports failed: {e} #based on yolo_pillow_manifest.py imports")
            return

        pipeline = None
        try:
            matcher = SimpleManifestMatcher(self._manifest_codes)  #this uses our usb-loaded list instead of auto
            #start camera pipeline (based on yolo_pillow_manifest.py main() gst section)
            Gst.init(None)
            pipeline_str = self._make_pipeline()
            pipeline = Gst.parse_launch(pipeline_str)
            appsink = pipeline.get_by_name("sink")
            if appsink is None:
                self.log.emit("[error] appsink 'sink' not found #based on yolo_pillow_manifest.py")
                return
            pipeline.set_state(Gst.State.PLAYING)
            self.log.emit("[info] csi pipeline started #based on yolo_pillow_manifest.py")

            #load model (based on yolo_pillow_manifest.py model load)
            self.log.emit(f"[info] loading yolo: {self.model_path}")
            model = YOLO(self.model_path)

            frame_idx = 0
            expected_total = len(self._manifest_codes)
            if expected_total == 0:
                self.log.emit("[warn] no manifest barcodes loaded")
            else:
                self.log.emit(f"[info] expecting {expected_total} barcodes from manifest")

            while not self._stop:
                frame_bgr = self._pull_frame(appsink)
                if frame_bgr is None:
                    # still keep loop moving at ~5 fps
                    time.sleep(0.2)
                    self.log.emit("no barcodes read")
                    continue

                frame_idx += 1
                if self.decode_every > 1 and (frame_idx % self.decode_every != 0):
                    time.sleep(0.2)
                    self.log.emit("no barcodes read")
                    continue

                #convert bgr to pillow rgb (based on yolo_pillow_manifest.py Image.fromarray usage)
                img_rgb = Image.fromarray(frame_bgr[:, :, ::-1], mode="RGB")  #this converts bgr to rgb for pillow

                rois = self._yolo_rois(model, img_rgb)
                decoded = self._decode_from_rois(img_rgb, rois)

                #full frame fallback occasionally (based on yolo_pillow_manifest.py fallback_interval)
                if not decoded and self.fallback_interval > 0 and (frame_idx % self.fallback_interval == 0):
                    from PIL import ImageOps
                    from pyzbar.pyzbar import decode as zbar_decode
                    ff_gray = ImageOps.grayscale(img_rgb)
                    for r in zbar_decode(ff_gray):
                        try:
                            val = r.data.decode('utf-8', errors='ignore')
                        except Exception:
                            val = None
                        if val and val not in decoded:
                            decoded.append(val)

                if decoded:
                    #report detections in requested phrasing
                    for val in decoded:
                        self.decoded.emit(val)
                        rec, score, method = matcher.match(val)
                        if rec:
                            self.matched.emit(rec, score, method)
                            self._found.add(rec.strip())
                            self.log.emit(f"{val} is loaded") #barcode decoded and IS on shipping manifest
                        else:
                            self.log.emit(f"{val} is not part of shipment") #barcode decoded but IS NOT on shipping manifest

                    #check completion
                    if expected_total and len(self._found) >= expected_total:
                        self.log.emit("all barcodes found — scanning complete")
                        self.finished_all.emit()
                        break
                else:
                    #no decodes this pass → say it
                    self.log.emit("no barcodes read") #keeps an active feed for testing and visualization purposes

                #enforce ~5 fps pacing
                time.sleep(0.2)

        except Exception as e:
            self.log.emit(f"[error] barcode reader crashed: {e}")

        finally:
            #stop pipeline when done
            try:
                if pipeline is not None:
                    pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass

#--------------------ship screen (patched ping start/stop + scanned indicator)--------------------
#--------------------ship screen (patched for repeated runs)--------------------
# -------------------- ShipScreen (FULL UPDATED) --------------------
class ShipScreen(QWidget):
    VALID_USB_PATHS = {
        "/media/design25/KINGSTON",
        "/media/design25/USB321FD",
        "/media/design25/ESD-USB"
    }

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("Ship")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Beausite Classic", 36))
        title.setStyleSheet("color: #0c2340; background-color: #f15a22; font-weight: bold;")
        layout.addWidget(title)

        self._leds = None

        self.status = QLabel("Waiting for ping sensor...")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(QLabel("Scanned Barcodes:"))
        layout.addWidget(self.scanned_list)
        self._barcode_items = {}

        # internal state
        self._expected_codes = []
        self._found = set()
        self._all_done_fired = False
        self._barcode_worker = None
        self._barcode_worker2 = None
        self.worker = None

        # track current manifest USB path
        self._current_usb_path = None

    # ---------------- MANIFEST SETUP ----------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])

        # FULL RESET when a new manifest appears
        self._found.clear()
        self._all_done_fired = False
        self.scanned_list.clear()
        self._barcode_items.clear()

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            item.setForeground(Qt.black)
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    # ---------------- LOG HELPER ----------------
    def _log(self, msg):
        self.log.append(msg)

    # ---------------- USB arrival from USBWatcher ----------------
    def load_manifest(self, shipment_list, usb_path):
        """Called when a valid BARCODE.TXT is detected on a USB."""

        # --- FILTER: Only allow 3 specific USB drives ---
        if usb_path not in self.VALID_USB_PATHS:
            self._log(f"Ignoring unauthorized USB: {usb_path}")
            return

        mw = self.window()
        if not mw:
            return

        # Stop the watcher while manifest is being processed
        try:
            if hasattr(mw, "welcome") and getattr(mw.welcome, "watcher", None):
                mw.welcome.watcher.stop()
        except Exception:
            pass

        self._current_usb_path = usb_path

        # Setup codes
        codes = getattr(shipment_list, "codes", None)
        if codes is None and hasattr(shipment_list, "items"):
            codes = shipment_list.items

        self.set_manifest_codes(codes or [])

        # LED: standby (rainbow)
        if self._leds:
            self._leds.to_standby.emit()

        self.status.setText("USB detected — waiting for forklift/pallet...")
        self._log(f"Manifest loaded from: {usb_path}")

        # Switch to ship screen (index 2)
        try:
            mw.setCurrentIndex(2)
        except Exception:
            pass

    # ---------------- READY FROM PING ----------------
    def _on_ready(self, dist_in, label):
        self.status.setText("CSI cameras are starting up...")

        if self._leds:
            self._leds.to_green.emit()

        self._log(f"sensor ready (~{dist_in:.2f} in avg) -> starting csi")
        self._all_done_fired = False

        # Start 2 barcode workers
        for idx in range(2):
            attr = "_barcode_worker" if idx == 0 else "_barcode_worker2"
            if getattr(self, attr) is None:
                worker = BarcodeReaderWorker(
                    model_path="my_model.pt",
                    sensor_id=idx,
                    width=1920, height=1080, framerate=5,
                    min_conf=0.25, iou=0.45, max_rois=6,
                    decode_every=1, fallback_interval=15,
                    manifest_codes=self._expected_codes
                )
                worker.log.connect(self._log)
                worker.matched.connect(self._on_match)
                worker.decoded.connect(self._on_match)
                worker.finished_all.connect(self._on_all_done)
                setattr(self, attr, worker)
                worker.start()

        # first decode pulse
        def _first_decode(_):
            if self._leds:
                self._leds.to_yellow_pulse.emit()
            for w in (self._barcode_worker, self._barcode_worker2):
                if w:
                    try:
                        w.decoded.disconnect(_first_decode)
                    except Exception:
                        pass

        for w in (self._barcode_worker, self._barcode_worker2):
            if w:
                try:
                    w.decoded.connect(_first_decode)
                except Exception:
                    pass

    # ---------------- MATCH HANDLER ----------------
    def _on_match(self, val):
        if val in self._found:
            return

        self._log(f"{val} matched")
        self._found.add(val)

        item = self._barcode_items.get(val)
        if item:
            item.setForeground(Qt.gray)
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

    # ---------------- ALL DONE ----------------
    def _on_all_done(self):
        if self._all_done_fired:
            return
        self._all_done_fired = True

        self.status.setText("Manifest complete! Please remove USB drive.")
        self._log("All barcodes found — manifest complete.")

        # Stop workers
        try:
            self.stop_ping()
        except Exception:
            pass

        for worker in (self._barcode_worker, self._barcode_worker2):
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(800)

        if self._leds:
            self._leds.to_pink_flash.emit()

        self._barcode_worker = None
        self._barcode_worker2 = None

        self._wait_for_usb_removal()

    # ---------------- USB REMOVAL ----------------
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

    # ---------------- RETURN ----------------
    def _return_to_welcome(self):
        mw = self.window()
        if not mw:
            return

        # Mark USB as completed
        if getattr(self, "_current_usb_path", None):
            mw.completed_usb_paths.add(self._current_usb_path)
            self._log(f"Recorded completed USB path: {self._current_usb_path}")
            self._current_usb_path = None

        completed = len(mw.completed_usb_paths)
        self._log(f"Completed USB count: {completed}/3")

        # After 3 → go to View Orders screen (index 3)
        if completed >= 3:
            try:
                if self._leds:
                    self._leds.reset_for_next_usb()
                    self._leds.to_standby.emit()
            except Exception:
                pass

            try:
                mw.setCurrentIndex(3)
            except Exception:
                pass
            return

        # Otherwise return to welcome
        try:
            if self._leds:
                self._leds.reset_for_next_usb()
                self._leds.to_standby.emit()
        except Exception:
            pass

        try:
            mw.welcome.watcher.start()
            mw.welcome.status.setText("Waiting for USB...")
        except Exception:
            pass

        mw.setCurrentIndex(0)

    # ---------------- PING WORKERS ----------------
    def on_attach(self, main_window):
        self._leds = getattr(main_window, "leds", None)

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
        try:
            self.stop_ping()
        except Exception:
            pass
        super().closeEvent(e)

#--------------------view order screen--------------------
class ViewOrderScreen(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("View Order")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Beausite Classic", 36))
        title.setStyleSheet("color: #0c2340; background-color: #f15a22; font-weight: bold;")
        layout.addWidget(title)

#--------------------main window--------------------
class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pallet Portal GUI (USB-gated + Menu + Dual Ping + CSI)")
        self.setMinimumSize(900, 600)

        # Track completed USB paths
        self.completed_usb_paths = set()

        # --- initialize LED worker first ---
        self.leds = LEDWorker(num_leds=5)  # spi0.0 uses pin 19 (spi0_mosi); enable via jetson-io
        self.leds.start()
        self.leds.to_standby.emit()  # rainbow on startup

        # --- now create screens ---
        self.welcome = WelcomeScreen()
        self.menu = MenuScreen()
        self.ship = ShipScreen()
        self.ship.on_attach(self)  # LEDs exist before this call
        self.view = ViewOrderScreen()

        # --- screen navigation ---
        self.menu.viewOrderSelected.connect(lambda: self.leds.to_standby.emit())
        self.menu.shipSelected.connect(lambda: None)  # ship will set its own LED mode

        self.addWidget(self.welcome)
        self.addWidget(self.menu)
        self.addWidget(self.ship)
        self.addWidget(self.view)

        self.setCurrentIndex(0)

        # --- connections ---
        self.welcome.proceed.connect(self._unlock_to_menu)
        self.menu.shipSelected.connect(lambda: self.setCurrentIndex(2))   # Ship screen
        self.menu.viewOrderSelected.connect(lambda: self.setCurrentIndex(3))  # View Order screen

    def _unlock_to_menu(self, shipment, source):
        """Pass manifest to ship screen and unlock menu."""
        self.expected_barcodes = shipment.barcodes
        self.ship_source = source
        try:
            self.ship.set_manifest_codes(self.expected_barcodes)  # hands manifest to ship screen
        except Exception:
            pass
        self.setCurrentIndex(1)
        self.menu.setFocus()

    def closeEvent(self, e):
        """Ensure LEDWorker stops cleanly."""
        try:
            if hasattr(self, "leds") and self.leds.isRunning():
                self.leds.stop()
                self.leds.wait(800)
        except Exception:
            pass
        super().closeEvent(e)

#--------------------entry point--------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)  #starts the qt app
    w = MainWindow()  #creates the main window
    w.show()  #shows the window
    sys.exit(app.exec_())  #keeps the app running until closed
