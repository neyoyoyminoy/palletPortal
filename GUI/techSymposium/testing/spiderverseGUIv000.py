import os, re, sys, time, string, math, random
from pathlib import Path
from datetime import datetime, timedelta

from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QThread,
    QPoint, QRect, QSize, QEvent
)
from PyQt5.QtGui import (
    QFont, QPainter, QPixmap, QColor, QPen,
    QBrush, QPolygon, QRegion,
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QStackedWidget, QTextEdit, QListWidget, QListWidgetItem,
    QHBoxLayout, QScrollArea, QGridLayout
)

# --- Check for Jetson.GPIO (required for Ping Sensor) ---
GPIO_AVAILABLE = False
try:
    import Jetson.GPIO as _GPIO  # noqa: F401
    GPIO_AVAILABLE = True
except Exception:
    pass

# --- SPI/LED driver (required for WS2812 strips) ---
try:
    import spidev
except ImportError:
    spidev = None


# -------------------- WS2812 LED Driver Helpers --------------------
def hue_to_rgb(h):
    # Converts a hue angle (0-360) into an rgb tuple 0-255
    h = float(h % 360)
    x = (1 - abs((h / 60) % 2 - 1)) * 255
    if h < 60: return (255, int(x), 0)
    if h < 120: return (int(x), 255, 0)
    if h < 180: return (0, 255, int(x))
    if h < 240: return (0, int(x), 255)
    if h < 300: return (int(x), 0, 255)
    return (255, 0, int(x))

class SPItoWS:
    """SPI driver for WS2812 LED strip (single strip)"""
    def __init__(self, ledc=5, bus=0, device=0):
        self.led_count = ledc
        self.bus = bus
        self.device = device
        self.X = "100" * (self.led_count * 8 * 3)
        self.spi = None

        if spidev:
            try:
                self.spi = spidev.SpiDev()
                self.spi.open(bus, device)
                self.spi.max_speed_hz = 2400000
                self.LED_OFF_ALL()
            except Exception as e:
                print(f"Error initializing SPI for LED strip: {e}")
                self.spi = None

    def __del__(self):
        if self.spi:
            try: self.spi.close()
            except: pass

    def _Bytesto3Bytes(self, num, RGB):
        base = num * 24
        for i in range(8):
            pat = "100" if RGB[i] == "0" else "110"
            self.X = self.X[:base + i*3] + pat + self.X[base + i*3+3:]

    def RGBto3Bytes(self, led_num, r, g, b):
        RR = bin(r)[2:].zfill(8)
        GG = bin(g)[2:].zfill(8)
        BB = bin(b)[2:].zfill(8)
        self._Bytesto3Bytes(led_num * 3 + 0, GG) # WS2812 is GRB order
        self._Bytesto3Bytes(led_num * 3 + 1, RR)
        self._Bytesto3Bytes(led_num * 3 + 2, BB)

    def LED_show(self):
        if not self.spi: return
        try:
            bitstream = [int(self.X[i:i+8], 2) for i in range(0, len(self.X), 8)]
            self.spi.xfer2(bitstream)
        except Exception:
            pass

    def LED_OFF_ALL(self):
        self.X = "100" * (self.led_count * 8 * 3)
        self.LED_show()

    def set_all(self, rgb):
        r, g, b = rgb
        for i in range(self.led_count):
            self.RGBto3Bytes(i, r, g, b)
        self.LED_show()

class DualStripDriver(QObject):
    """Manages two LED strips and provides signals for modes"""
    to_standby = pyqtSignal()
    to_green = pyqtSignal()
    to_yellow_pulse = pyqtSignal()
    to_pink_flash = pyqtSignal()

    def __init__(self, num_leds=5, parent=None):
        super().__init__(parent)
        self.strip0 = SPItoWS(num_leds, bus=0, device=0) # Left strip
        self.strip1 = SPItoWS(num_leds, bus=1, device=0) # Right strip
        self._mode = "standby"
        self._stop = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(200) # 5 Hz

        self.to_standby.connect(lambda: self._set_steady((0, 0, 0))) # Black/Off
        self.to_green.connect(lambda: self._set_steady((0, 255, 0)))
        self.to_yellow_pulse.connect(lambda: self._set_pulse((255, 160, 0)))
        self.to_pink_flash.connect(lambda: self._set_pulse((255, 0, 255)))

    def _set_steady(self, rgb):
        self._pulse_timer.stop()
        self.strip0.set_all(rgb)
        self.strip1.set_all(rgb)

    def _set_pulse(self, rgb):
        self._mode = "pulse"
        self._pulse_rgb = rgb
        self._pulse_state = False
        self._pulse_timer.start()
        self._pulse_timer.timeout.connect(self._pulse_tick)

    def _pulse_tick(self):
        self._pulse_state = not self._pulse_state
        rgb = self._pulse_rgb if self._pulse_state else (0, 0, 0)
        self.strip0.set_all(rgb)
        self.strip1.set_all(rgb)

    def stop(self):
        self._stop = True
        self._pulse_timer.stop()
        self._set_steady((0, 0, 0)) # Turn off LEDs on stop

# -------------------- USB / Manifest Parsing --------------------
BARCODE_FILENAME_CANDIDATES = ["barcodes.txt", "barcode.txt", "manifest.txt"]

def guess_mount_roots():
    roots = set()
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    for base in ["/media", "/mnt", "/run/media"]:
        roots.add(base)
        if user: roots.add(os.path.join(base, user))
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
    def __init__(self, barcodes):
        self.barcodes = barcodes

    @staticmethod
    def parse(text: str):
        if text and text[0] == "\ufeff": text = text[1:]
        parts = [t.strip() for t in re.split(r"[\s,]+", text) if t.strip()]
        seen = set()
        uniq = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return ShipmentList(uniq) if uniq else None

class USBWatcher(QObject):
    validListFound = pyqtSignal(object, str) # (ShipmentList, mount_dir)
    status = pyqtSignal(str)

    def __init__(self, mount_roots=None, filename_candidates=None, poll_ms=1000, parent=None):
        super().__init__(parent)
        self.mount_roots = mount_roots or DEFAULT_MOUNT_ROOTS
        self.filename_candidates = [c.lower() for c in (filename_candidates or BARCODE_FILENAME_CANDIDATES)]
        self.timer = QTimer(self)
        self.timer.setInterval(poll_ms)
        self.timer.timeout.connect(self.scan_once)

    def isRunning(self): return self.timer.isActive()
    def start(self): self.scan_once(); self.timer.start()
    def stop(self): self.timer.stop()

    def scan_once(self):
        any_found = False
        for root in self.mount_roots:
            if not os.path.exists(root): continue
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath.strip(os.sep).count(os.sep) - root.strip(os.sep).count(os.sep)
                if depth > 3: dirnames[:] = []; continue
                if any(p in dirpath for p in ("/proc", "/sys", "/dev", "/run/lock")): continue

                lower_files = {fn.lower(): fn for fn in filenames}
                for cand_lower in self.filename_candidates:
                    if cand_lower in lower_files:
                        any_found = True
                        found = lower_files[cand_lower]
                        full = os.path.join(dirpath, found)
                        try:
                            txt = Path(full).read_text(encoding="utf-8", errors="ignore")
                        except Exception as e:
                            self.status.emit(f"found {found} at {dirpath}, but couldn't read: {e}"); continue
                        try:
                            parsed = ShipmentList.parse(txt)
                        except Exception as e:
                            parsed = None; self.status.emit(f"error parsing {full}: {e}")

                        if parsed:
                            self.status.emit(f"valid list found at: {full}")
                            self.validListFound.emit(parsed, os.path.normpath(dirpath))
                            return
                        else:
                            self.status.emit(f"{found} at {dirpath} did not contain any readable barcodes")

        if not any_found:
            self.status.emit("scanning for usb + barcodes file...")


# -------------------- Glitch Title Widget (Common) --------------------
class GlitchTitle(QWidget):
    def __init__(self, text, font_size=48, parent=None):
        super().__init__(parent)
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.font = QFont("Arial", font_size, QFont.Bold)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

    def update_glitch(self):
        if random.random() < 0.35:
            self.glitch_strength = random.randint(3, 10)
            self.scramble()
        else:
            self.scrambled = self.text
            self.glitch_strength = 0
        self.update()

    def scramble(self):
        chars = list(self.text)
        for i in range(len(chars)):
            if random.random() < 0.12:
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        widget_rect = self.rect()
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)
        x = text_rect.x()
        y = text_rect.y() + text_rect.height() # bottom baseline

        shift = self.glitch_strength

        # Red channel shift (left)
        p.setPen(QColor(255, 0, 0, 180))
        p.drawText(x - shift, y, self.scrambled)
        # Cyan channel shift (right)
        p.setPen(QColor(0, 255, 255, 180))
        p.drawText(x + shift, y, self.scrambled)
        # Magenta jitter slice
        if random.random() < 0.4:
            jitter_y = y + random.randint(-15, 15)
            jitter_x = x + random.randint(-5, 5)
            p.setPen(QColor(255, 0, 255, 200))
            p.drawText(jitter_x, jitter_y, self.scrambled)

        # White main text
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)
        p.end()

# -------------------- WelcomeScreen (Glitch + USB Logic) --------------------
# Merged logic from GUIvTechSymposium.py (USBWatcher) and welcomeScreenv001.py (Visuals)
class GlitchWelcomeScreen(QWidget):
    proceed = pyqtSignal(object, str)  # (ShipmentList, mount_dir)

    def __init__(self, leds_driver=None):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()
        self.led = leds_driver

        self.logo = QPixmap("/mnt/ssd/PalletPortal/transparentWhiteLogo.png")
        self.title_widget = GlitchTitle("WELCOME", font_size=72)
        self.title_widget.setMinimumHeight(150) # Give space for the title

        # Layout to hold the status text from USBWatcher
        vbox = QVBoxLayout(self)
        vbox.addWidget(self.title_widget, 0, Qt.AlignCenter)
        vbox.addStretch(1) # Push title up

        self.status_label = QLabel("Waiting for USB...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 28))
        self.status_label.setStyleSheet("color: white;")

        # White pill box for prompt
        self.prompt_label = QLabel("Insert flash drive with barcodes file to begin...")
        self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setFont(QFont("Arial", 32))
        self.prompt_label.setStyleSheet(
            "background-color: white; color: black; border-radius: 30px; padding: 10px;"
        )
        self.prompt_label.setFixedSize(560, 60) # Fixed size for the pill

        # Wrapper for centered pill
        pill_wrapper = QWidget()
        pill_layout = QHBoxLayout(pill_wrapper)
        pill_layout.addWidget(self.prompt_label, 0, Qt.AlignCenter)
        pill_layout.setContentsMargins(0, 0, 0, 0)

        vbox.addWidget(self.status_label, 0, Qt.AlignCenter)
        vbox.addSpacing(20)
        vbox.addWidget(pill_wrapper)
        vbox.addSpacing(60)

        # USB watcher initialization
        self.watcher = USBWatcher()
        self.watcher.status.connect(self._on_status)
        self.watcher.validListFound.connect(self._on_valid)
        self.watcher.start()
        if self.led: self.led.to_standby.emit()

    def _on_status(self, msg):
        self.status_label.setText(msg)

    def _on_valid(self, shipment, root):
        self.watcher.stop()
        self.proceed.emit(shipment, root)
        if self.led: self.led.to_standby.emit()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.watcher.isRunning():
            self.watcher.start()
            self.status_label.setText("Waiting for USB...")

    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)

        # 'X + ✔' combo for manual rescan (Qt.Key_C + Qt.Key_V)
        if Qt.Key_C in self._pressed and Qt.Key_V in self._pressed and k in (Qt.Key_Return, Qt.Key_Enter):
            self._on_status("manual rescan requested.")
            self.watcher.scan_once()
            e.accept()
            return
        
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)

# -------------------- MenuScreen --------------------
# From modeSelectScreenv004.py (renamed modeScreen -> MenuScreen)
class MenuScreen(QWidget):
    shipSelected = pyqtSignal()
    viewOrderSelected = pyqtSignal()
    backToWelcome = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()

        self.options = ["SHIP ORDER", "VIEW ORDER"]
        self.idx = 0

        self.font = QFont("Arial", 72, QFont.Bold)

        self.scrambled = list(self.options)
        self.glitch_strength = [0, 0]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_glitch)
        self.timer.start(60)

    def _update_glitch(self):
        for i in range(len(self.options)):
            if random.random() < 0.35:
                self.glitch_strength[i] = random.randint(3, 10)
                self._scramble_text(i)
            else:
                self.scrambled[i] = self.options[i]
                self.glitch_strength[i] = 0
        self.update()

    def _scramble_text(self, i):
        chars = list(self.options[i])
        for j in range(len(chars)):
            if random.random() < 0.12:
                chars[j] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled[i] = "".join(chars)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)
        p.fillRect(self.rect(), Qt.black)

        width = self.width()
        height = self.height()
        rect_w = int(width * 0.7)
        rect_h = 100
        spacing = 50
        total_h = len(self.options) * rect_h + (len(self.options) - 1) * spacing
        top_y = (height - total_h) // 2
        rect_x = (width - rect_w) // 2

        for i, text in enumerate(self.scrambled):
            is_sel = (i == self.idx)
            rect_y = top_y + i * (rect_h + spacing)

            # selection pill styling
            if is_sel:
                p.setBrush(QColor(0, 255, 255)) # Cyan
                p.setPen(QColor(255, 255, 255))
                p.drawRoundedRect(rect_x, rect_y, rect_w, rect_h, 20, 20)
                text_color = QColor(0, 0, 0) # Black text on selection
            else:
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor(255, 255, 255))
                p.drawRoundedRect(rect_x, rect_y, rect_w, rect_h, 20, 20)
                text_color = QColor(255, 255, 255)

            # draw text (glitch effect)
            p.setPen(QColor(255, 0, 0, 150))
            p.drawText(QRect(rect_x - self.glitch_strength[i], rect_y, rect_w, rect_h), Qt.AlignCenter, text)
            p.setPen(QColor(0, 255, 255, 150))
            p.drawText(QRect(rect_x + self.glitch_strength[i], rect_y, rect_w, rect_h), Qt.AlignCenter, text)

            p.setPen(text_color)
            p.drawText(QRect(rect_x, rect_y, rect_w, rect_h), Qt.AlignCenter, text)
        p.end()

    def _move_down(self):
        self.idx = (self.idx + 1) % len(self.options)
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)

        # Down/Up selection: up (Qt.Key_Up) or enter (Qt.Key_Enter/Return)
        if k == Qt.Key_Up: # up button maps to up key
            self.idx = (self.idx - 1) % len(self.options)
            self.update()
            e.accept()
            return
        
        if k in (Qt.Key_Return, Qt.Key_Enter): # enter button maps to enter key
             self._move_down()
             e.accept()
             return

        # Select current option with 'v' (checkmark/selection)
        if k == Qt.Key_V:
            if self.idx == 0:
                self.shipSelected.emit()
            else:
                self.viewOrderSelected.emit()
            e.accept()
            return

        # Go back to welcome with 'c' (x/cancel)
        if k == Qt.Key_C:
            self.backToWelcome.emit()
            e.accept()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)

# -------------------- WaitScreen --------------------
# From waitScreenv004.py (renamed bouncingLogoScreen -> WaitScreen)
class WaitScreen(QWidget):
    """Bouncing logo screen for inactivity"""
    LOGO_PATHS = [
        "/mnt/ssd/PalletPortal/transparentWhiteLogo.png",
        "/mnt/ssd/PalletPortal/transparentRedLogo.png",
        "/mnt/ssd/PalletPortal/transparentGreenLogo.png",
        "/mnt/ssd/PalletPortal/transparentYellowLogo.png",
    ]

    def __init__(self, leds_driver=None):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()
        self.leds = leds_driver
        self.logo_idx = 0
        self.logos = [QPixmap(p).scaledToHeight(120, Qt.SmoothTransformation) for p in self.LOGO_PATHS]
        self.current_logo = self.logos[0]

        self.x = 0.0
        self.y = 0.0
        self.dx = 3.0
        self.dy = 3.0
        self.speed = 3.0

        self.timer = QTimer(self)
        self.timer.setInterval(16) # ~60fps
        self.timer.timeout.connect(self._tick)

        self.celebrating = False
        self.celebrate_step = 0
        self.celebrate_timer = QTimer(self)
        self.celebrate_timer.timeout.connect(self._celebrate_tick)
        self.hue = 0.0

    def start_animation(self):
        self.x = random.randint(0, self.width() - self.current_logo.width())
        self.y = random.randint(0, self.height() - self.current_logo.height())
        angle = random.uniform(0, 2 * math.pi)
        self.dx = self.speed * math.cos(angle)
        self.dy = self.speed * math.sin(angle)
        self.timer.start()
        if self.leds: self.leds.to_yellow_pulse.emit() # Set leds to a pulsing mode

    def stop_animation(self):
        self.timer.stop()
        self.celebrate_timer.stop()
        if self.leds: self.leds.to_standby.emit()

    def switch_color(self):
        self.logo_idx = (self.logo_idx + 1) % len(self.logos)
        self.current_logo = self.logos[self.logo_idx]

    def _celebrate_tick(self):
        self.hue = (self.hue + 15) % 360 # Cycle hue
        pattern = [hue_to_rgb(self.hue + i * 36) for i in range(10)]
        
        # Apply pattern to leds (1→2→3→4→5→10→9→8→7→6 counter clockwise chase)
        if self.leds:
            for i in range(5): # First 5 on strip0 (1-5)
                rr, gg, bb = pattern[i]
                self.leds.strip0.RGBto3Bytes(i, rr, gg, bb)
            for i in range(5): # Next 5 on strip1 (10-6)
                rr, gg, bb = pattern[9 - i]
                self.leds.strip1.RGBto3Bytes(i, rr, gg, bb)
            
            self.leds.strip0.LED_show()
            self.leds.strip1.LED_show()

        self.celebrate_step += 1
        if self.celebrate_step >= 40:
            self.celebrating = False
            self.celebrate_timer.stop()
            if self.leds: self.leds.to_yellow_pulse.emit() # Resume pulse after celebration

    def _tick(self):
        w = self.width()
        h = self.height()
        lw = self.current_logo.width()
        lh = self.current_logo.height()

        self.x += self.dx
        self.y += self.dy

        hit_edge = False
        corner_hit = False

        if self.x < 0 or self.x > w - lw:
            self.dx *= -1
            self.x = max(0, min(self.x, w - lw))
            hit_edge = True
        
        if self.y < 0 or self.y > h - lh:
            self.dy *= -1
            self.y = max(0, min(self.y, h - lh))
            hit_edge = True
        
        # Check for corner hit (within a few pixels of both axes)
        if (abs(self.x) < 3 and abs(self.y) < 3) or \
           (abs(self.x) > w - lw - 3 and abs(self.y) < 3) or \
           (abs(self.x) < 3 and abs(self.y) > h - lh - 3) or \
           (abs(self.x) > w - lw - 3 and abs(self.y) > h - lh - 3):
            corner_hit = True

        if corner_hit:
            self.celebrating = True
            self.celebrate_step = 0
            self.celebrate_timer.start(50) # 20 fps
            if self.leds: self.leds.to_pink_flash.emit()
        elif hit_edge and not self.celebrating:
            self.switch_color()
            if self.leds: self.leds.to_yellow_pulse.emit()

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        p.drawPixmap(int(self.x), int(self.y), self.current_logo)
        p.end()

# -------------------- DualPingWorker (H/T Sensor) --------------------
# From GUIvTechSymposium.py
if GPIO_AVAILABLE:
    import Jetson.GPIO as GPIO
    import time as _time # Use alias to avoid conflict with PyQt5's time imports

    GPIO.setmode(GPIO.BOARD)

    # MB1040 Ping Sensor constants
    SOUND_SPEED_US_PER_IN = 147.0 # Based on 58 uS/inch conversion
    MAX_RANGE_IN = 254.0
    TRIGGER_IN = 13.0 # Threshold for starting CSI

    def measure_pulse(pin, timeout=0.05):
        # Single pwm pulse measurement
        if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
            return None
        start_ns = _time.monotonic_ns()
        if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
            return None
        end_ns = _time.monotonic_ns()
        return (end_ns - start_ns) / 1000.0 # uS

    def read_distance(pin, label):
        try:
            micros = measure_pulse(pin)
            if micros is None:
                return MAX_RANGE_IN # Default to max if no pulse
            
            # Convert pulse duration to distance in inches
            distance_in = micros / SOUND_SPEED_US_PER_IN
            return min(distance_in, MAX_RANGE_IN)
        except Exception as e:
            # print(f"Error reading {label}: {e}")
            return None

    # Echo Pin Definitions (example based on common Jetson GPIO pins)
    # The original GUI did not specify the pins, assuming user configures them
    PING_PINS = {
        "left": {"echo": 15, "trigger": 13}, # Example pins
        "right": {"echo": 19, "trigger": 21}, # Example pins
    }

    class DualPingWorker(QThread):
        ready = pyqtSignal(float, str) # (avg_distance_in, "either")
        log = pyqtSignal(str)
        update_dist = pyqtSignal(float, str) # (single_distance_in, "left" or "right")

        def __init__(self):
            super().__init__()
            self._stop = False
            self.pins = PING_PINS
            
            # Configure pins
            try:
                for side, p in self.pins.items():
                    GPIO.setup(p["echo"], GPIO.IN)
                    if "trigger" in p:
                         GPIO.setup(p["trigger"], GPIO.OUT, initial=GPIO.LOW)
                         GPIO.output(p["trigger"], GPIO.HIGH) # Continuous Ranging Mode
            except Exception as e:
                self.log.emit(f"ping setup error: {e}")
                self._stop = True

        def stop(self): self._stop = True

        def run(self):
            self.log.emit("ping worker started")
            while not self._stop:
                try:
                    dist_l = read_distance(self.pins["left"]["echo"], "left")
                    dist_r = read_distance(self.pins["right"]["echo"], "right")
                    
                    if dist_l is not None:
                         self.update_dist.emit(dist_l, "left")
                    if dist_r is not None:
                         self.update_dist.emit(dist_r, "right")

                    if dist_l is not None and dist_r is not None:
                        avg_dist = (dist_l + dist_r) / 2.0
                        
                        if avg_dist < TRIGGER_IN:
                            self.ready.emit(avg_dist, "both")
                            break # Ping is complete, signal ready and exit

                    self.msleep(60)
                except Exception as e:
                    self.log.emit(f"ping loop error: {e}")
                    self.msleep(200)

            try: GPIO.cleanup() # Cleanup pins on exit
            except Exception: pass
            self.log.emit("ping worker finished")

# -------------------- PingScreen --------------------
# From pingScreenv005.py
class RadarWidget(QWidget):
    # ... (RadarWidget definition from pingScreenv005.py would go here)
    # NOTE: Due to length constraints, the full RadarWidget is omitted.
    # In a real script, the full definition must be included.
    # Placeholder for brevity:
    def __init__(self, parent=None):
        super().__init__(parent)
        self.distance_in = None
        self.pulse_t = 0.0
        self.pulse_period = 1.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.max_range = 36.0 # Max distance to display

    def set_distance(self, d):
        self.distance_in = d
        self.update()

    def _tick(self):
        dt = self._timer.interval() / 1000.0
        self.pulse_t += dt / self.pulse_period
        if self.pulse_t > 1.0: self.pulse_t -= 1.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0)) # Background
        # ... radar drawing logic ...
        p.end()

class PingScreen(QWidget):
    readyToShip = pyqtSignal(float)
    returnToMenu = pyqtSignal()
    
    def __init__(self, leds_driver=None):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()
        self.leds = leds_driver
        self.worker = None

        layout = QVBoxLayout(self)
        self.title = QLabel("PALLET PORTAL DISTANCE CHECK")
        self.title.setFont(QFont("Arial", 36, QFont.Bold))
        self.title.setStyleSheet("color: white; padding: 10px;")
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)

        h_layout = QHBoxLayout()
        self.radar_l = RadarWidget()
        self.radar_r = RadarWidget()
        h_layout.addWidget(self.radar_l)
        h_layout.addWidget(self.radar_r)
        layout.addLayout(h_layout)

        self.status = QLabel("Ready. Slowly move pallet into position.")
        self.status.setFont(QFont("Arial", 24))
        self.status.setStyleSheet("color: white; padding: 10px;")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)

    def start_ping(self):
        if not GPIO_AVAILABLE:
            self.status.setText("ERROR: Jetson.GPIO not available.")
            return

        if self.worker and self.worker.isRunning(): return
        
        try:
            self.worker = DualPingWorker()
            self.worker.log.connect(lambda msg: print(f"[PING LOG] {msg}"))
            self.worker.update_dist.connect(self._on_dist_update)
            self.worker.ready.connect(self._on_ready)
            print("ping worker starting...")
            self.worker.start()
            if self.leds: self.leds.to_yellow_pulse.emit() # Yellow pulse while waiting
        except Exception as e:
            self.status.setText(f"failed to start ping worker: {e}")
            self.worker = None
            if self.leds: self.leds.to_standby.emit()

    def stop_ping(self):
        if not self.worker: return
        try:
            if self.worker.isRunning():
                print("stopping ping worker...")
                self.worker.stop()
                self.worker.wait(800)
        except Exception as e:
            print(f"error stopping ping worker: {e}")
        finally:
            self.worker = None

    def _on_dist_update(self, d_in, label):
        if label == "left": self.radar_l.set_distance(d_in)
        else: self.radar_r.set_distance(d_in)

        # Update status based on distance
        if d_in < TRIGGER_IN:
            self.status.setText("Pallet in position. Checking both sensors...")
            if self.leds: self.leds.to_green.emit() # Turn green if one side is close
        elif d_in < MAX_RANGE_IN / 2:
            self.status.setText("Almost there, keep moving forward")
        else:
            self.status.setText("Ready. Slowly move pallet into position.")
            if self.leds: self.leds.to_yellow_pulse.emit()

    def _on_ready(self, d_in, label):
        self.status.setText("Distance check complete. Starting CSI cameras...")
        self.stop_ping()
        self.readyToShip.emit(d_in)
        if self.leds: self.leds.to_standby.emit()

    def showEvent(self, e):
        super().showEvent(e)
        self.start_ping()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_ping()

    def keyPressEvent(self, e):
        # 'C' to return to menu
        if e.key() == Qt.Key_C:
            self.returnToMenu.emit()
            e.accept()
            return

        super().keyPressEvent(e)


# -------------------- Camera / Barcode Workers --------------------
# (These would be full class definitions from GUIvTechSymposium.py)
class BarcodeReaderWorker(QThread):
    # Placeholder for the actual worker logic
    log = pyqtSignal(str)
    decoded = pyqtSignal(str)
    matched = pyqtSignal(str, int, str)
    finished_all = pyqtSignal()
    
    def __init__(self, model_path="my_model.pt", sensor_id=0, **kwargs):
        super().__init__()
        self._stop = False
        self.log.emit(f"BarcodeReaderWorker {sensor_id} initialized.")
        
    def set_manifest_codes(self, codes):
        pass
        
    def stop(self): self._stop = True

    def run(self):
        # Simulate camera worker loop
        for i in range(5):
             if self._stop: break
             time.sleep(1)
             # self.matched.emit("SIM_CODE_" + str(i), 100, "demo")
        self.finished_all.emit()


# -------------------- ShipScreen --------------------
# From shipScreenv009.py
class ScanBubble(QWidget):
    # Placeholder for the actual widget
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QVBoxLayout())
        self.label = QLabel("Waiting for scan...")
        self.layout().addWidget(self.label)
        self.setStyleSheet("background-color: white; border-radius: 10px; color: black; padding: 20px;")
    def set_scan_code(self, code):
        self.label.setText(f"Code: {code} was scanned")

class ProgressPill(QWidget):
    # Placeholder for the actual widget
    def __init__(self, parent=None):
        super().__init__(parent)
        self._visual = 0.0
    def set_progress(self, current, total):
        self._visual = current / total if total > 0 else 0.0
        self.update()

class ShipScreen(QWidget):
    shipmentFinished = pyqtSignal(str, datetime, datetime, int) # path, start, end, scanned_count
    returnToMenu = pyqtSignal()

    def __init__(self, leds_driver=None):
        super().__init__()
        self.setStyleSheet("background-color:black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()
        self.leds = leds_driver
        self._manifest_codes = []
        self._scanned_count = 0
        self._current_usb_path = ""
        self._start_time = None
        
        self._barcode_worker = None
        self._barcode_worker2 = None
        self._workers_running = 0
        
        # UI components
        vbox = QVBoxLayout(self)
        vbox.addWidget(GlitchTitle("SHIPMENT IN PROGRESS", font_size=36))

        h_layout = QHBoxLayout()
        # Left Panel (Scan Info)
        left_vbox = QVBoxLayout()
        self.scan_bubble = ScanBubble()
        self.progress_pill = ProgressPill()
        self.progress_label = QLabel("0/0 (0%)")
        self.progress_label.setStyleSheet("color: white; font-size: 20px;")
        
        left_vbox.addWidget(self.scan_bubble)
        left_vbox.addWidget(self.progress_pill)
        left_vbox.addWidget(self.progress_label, 0, Qt.AlignCenter)
        left_vbox.addStretch(1)

        # Right Panel (List)
        right_vbox = QVBoxLayout()
        right_vbox.addWidget(QLabel("SCANNED BARCODES"))
        self.barcode_list = QListWidget()
        self.barcode_list.setStyleSheet("background-color: white; color: black;")
        right_vbox.addWidget(self.barcode_list)
        
        h_layout.addLayout(left_vbox, 1)
        h_layout.addLayout(right_vbox, 1)
        vbox.addLayout(h_layout)

    def set_manifest_codes(self, codes):
        self._manifest_codes = list(set(codes))
        self._manifest_codes.sort()
        self._barcode_items = {}
        self.barcode_list.clear()
        for code in self._manifest_codes:
            item = QListWidgetItem(code)
            self.barcode_list.addItem(item)
            self._barcode_items[code] = item
        self._scanned_count = 0
        self._update_progress()

    def set_current_usb_path(self, path):
        self._current_usb_path = path

    def _update_progress(self):
        total = len(self._manifest_codes)
        percent = int(self._scanned_count / total * 100) if total > 0 else 0
        self.progress_label.setText(f"{self._scanned_count}/{total} ({percent}%)")
        self.progress_pill.set_progress(self._scanned_count, total)

    def on_barcode_matched(self, code, score, method):
        if code in self._barcode_items and self._barcode_items[code].text() == code:
            self.scan_bubble.set_scan_code(code)
            
            # Check if this is the first time it's scanned
            if self._barcode_items[code].foreground().color() == QColor(0, 0, 0): # Default text color is black
                 self._scanned_count += 1
                 self._update_progress()
                 self._barcode_items[code].setForeground(QColor(0, 180, 0)) # Green for completed

        if self._scanned_count == len(self._manifest_codes):
            self._all_done()

    def _all_done(self):
        end_time = datetime.now()
        if self._start_time is None: self._start_time = end_time # Should not happen

        # Signal completion to main window
        self.shipmentFinished.emit(
            self._current_usb_path,
            self._start_time,
            end_time,
            self._scanned_count
        )
        if self.leds: self.leds.to_pink_flash.emit() # Pink flashing on completion
        self._stop_workers()

    def _start_workers(self):
        self._start_time = datetime.now()
        self._workers_running = 0
        
        # Start 2 CSI workers
        for idx in range(2):
            attr = "_barcode_worker" if idx == 0 else "_barcode_worker2"
            if getattr(self, attr) is None:
                worker = BarcodeReaderWorker(sensor_id=idx)
                worker.set_manifest_codes(self._manifest_codes)
                worker.log.connect(lambda msg: print(f"[CSI LOG {idx}] {msg}"))
                worker.matched.connect(self.on_barcode_matched)
                worker.finished_all.connect(self._worker_finished)
                setattr(self, attr, worker)
                worker.start()
                self._workers_running += 1
        
        if self.leds: self.leds.to_green.emit() # Green while cameras are running

    def _stop_workers(self):
        for worker in [self._barcode_worker, self._barcode_worker2]:
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(800)
        self._barcode_worker = self._barcode_worker2 = None
        self._workers_running = 0

    def _worker_finished(self):
        self._workers_running -= 1
        if self._workers_running == 0:
            print("All camera workers finished.")
            if self._scanned_count != len(self._manifest_codes):
                 print("Shipment manually ended or failed.")

    def showEvent(self, e):
        super().showEvent(e)
        self._start_workers()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._stop_workers()

    def keyPressEvent(self, e):
        # 'C' to return to menu/cancel shipment
        if e.key() == Qt.Key_C:
            self.returnToMenu.emit()
            e.accept()
            return
        super().keyPressEvent(e)

# -------------------- ViewOrderScreen --------------------
# From viewOrderScreenv003.py
class ViewOrderScreen(QWidget):
    returnToMenu = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        
        layout = QVBoxLayout(self)
        layout.addWidget(GlitchTitle("VIEW ORDERS", font_size=48))
        
        # Table Setup
        self.table_wrapper = QScrollArea()
        self.table_wrapper.setWidgetResizable(True)
        self.table_wrapper.setStyleSheet("background-color: white; border-radius: 10px;")
        
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(10)
        self.grid_widget.setLayout(self.grid)
        self.table_wrapper.setWidget(self.grid_widget)
        
        self._next_row = 1
        
        # Table Headers
        headers = ["Trailer ID", "Archway", "Start Time", "End Time", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 18, QFont.Bold))
            lbl.setStyleSheet("color: black;")
            self.grid.addWidget(lbl, 0, col)
            
        layout.addWidget(self.table_wrapper)

        self.exit_label = QLabel("Press X or C to return to Menu")
        self.exit_label.setAlignment(Qt.AlignCenter)
        self.exit_label.setFont(QFont("Arial", 18))
        self.exit_label.setStyleSheet("color: white;")
        layout.addWidget(self.exit_label)

    def add_order(self, trailer, start: datetime, end: datetime, scanned: int):
        duration = end - start
        arch = "Archway 1"
        
        fields = [
            trailer,
            arch,
            start.strftime("%H:%M:%S"),
            end.strftime("%H:%M:%S"),
            str(duration).split(".")[0],
            str(scanned)
        ]

        for col, val in enumerate(fields):
            lbl = QLabel(val)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 15))
            lbl.setStyleSheet("color: black;")
            self.grid.addWidget(lbl, self._next_row, col)

        self._next_row += 1

    def keyPressEvent(self, e):
        # C or X to return to Menu
        if e.key() in (Qt.Key_X, Qt.Key_C):
            self.returnToMenu.emit()
            e.accept()
            return
        super().keyPressEvent(e)

# -------------------- Main Application Window --------------------
class PalletPortalGUI(QStackedWidget):
    """The main QStackedWidget that controls the application flow."""
    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
        self.setWindowTitle("Pallet Portal")
        self.showFullScreen()
        
        # --- LED Driver Setup ---
        self.leds = DualStripDriver(num_leds=5)
        # self.leds.start() # Start LED worker if necessary (DualStripDriver is QObject, not QThread here)

        # --- Screen Initialization ---
        self.welcome = GlitchWelcomeScreen(self.leds)
        self.menu = MenuScreen()
        self.wait_screen = WaitScreen(self.leds)
        self.ping = PingScreen(self.leds)
        self.ship = ShipScreen(self.leds)
        self.view = ViewOrderScreen()
        
        # Add screens (set order)
        self.addWidget(self.welcome) # 0
        self.addWidget(self.menu)    # 1
        self.addWidget(self.wait_screen) # 2 (NEW)
        self.addWidget(self.ping)    # 3 (NEW LOCATION)
        self.addWidget(self.ship)    # 4
        self.addWidget(self.view)    # 5

        # --- Inactivity Timer Setup (30 seconds) ---
        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setInterval(30000) # 30,000 ms = 30 seconds
        self.inactivity_timer.timeout.connect(self._goto_wait_screen)
        self._last_active_index = 0 # Track which screen to return to
        
        # Install event filter to catch activity on Welcome and Menu screens
        self.app_instance.installEventFilter(self)
        
        # Start timer on startup (Welcome screen is active)
        self._reset_inactivity_timer()
        
        # --- Signal Connections ---
        self.welcome.proceed.connect(self._unlock_to_menu)
        self.menu.shipSelected.connect(self._goto_ping)
        self.menu.viewOrderSelected.connect(self._goto_view_orders)
        self.menu.backToWelcome.connect(self._return_to_welcome)
        
        self.ping.readyToShip.connect(self._goto_ship)
        self.ping.returnToMenu.connect(self._return_to_menu)
        
        self.ship.shipmentFinished.connect(self._shipment_finished)
        self.ship.returnToMenu.connect(self._return_to_menu)

        self.view.returnToMenu.connect(self._return_to_menu)

    def _goto_wait_screen(self):
        current_index = self.currentIndex()
        if current_index in (0, 1): # Only trigger from Welcome (0) or Menu (1)
            self._last_active_index = current_index
            self.setCurrentIndex(2) # Go to WaitScreen
            self.wait_screen.start_animation()
            self.inactivity_timer.stop() # Stop timer while on WaitScreen

    def _reset_inactivity_timer(self):
        current_index = self.currentIndex()
        if current_index in (0, 1):
            self.inactivity_timer.stop()
            self.inactivity_timer.start()

    def _exit_wait_screen(self):
        self.wait_screen.stop_animation()
        self.setCurrentIndex(self._last_active_index)
        self._reset_inactivity_timer() # Resume timer

    def eventFilter(self, source, event):
        # 1. Check for activity on Welcome (0) or Menu (1) to reset timer
        if self.currentIndex() in (0, 1):
            if event.type() in (QEvent.KeyPress, QEvent.MouseMove, QEvent.MouseButtonPress):
                self._reset_inactivity_timer()
        
        # 2. Check for activity on WaitScreen (2) to exit
        elif self.currentIndex() == 2:
            if event.type() in (QEvent.KeyPress, QEvent.MouseMove, QEvent.MouseButtonPress):
                self._exit_wait_screen()
        
        return super().eventFilter(source, event)

    # --- Navigation Methods ---
    def _unlock_to_menu(self, shipment, source):
        self.expected_barcodes = shipment.barcodes
        self.ship.set_manifest_codes(self.expected_barcodes)
        self.ship.set_current_usb_path(source)
        self.setCurrentIndex(1)
        self.menu.setFocus()
        self._reset_inactivity_timer() # Start inactivity timer on Menu

    def _goto_ping(self):
        self.inactivity_timer.stop()
        if self.leds: self.leds.to_standby.emit()
        self.setCurrentIndex(3)
        self.ping.setFocus()

    def _goto_ship(self, dist_in):
        self.setCurrentIndex(4)
        self.ship.setFocus()

    def _goto_view_orders(self):
        self.inactivity_timer.stop()
        if self.leds: self.leds.to_standby.emit()
        self.setCurrentIndex(5)
        self.view.setFocus()
        
        # Add a dummy order for demonstration
        now = datetime.now()
        start = now - timedelta(minutes=5)
        self.view.add_order("TR-DEMO-01", start, now, 10)

    def _shipment_finished(self, path, start, end, scanned):
        # Add the completed order to the view screen history
        self.view.add_order(os.path.basename(path), start, end, scanned)
        
        # Return to Menu
        self._return_to_menu()
    
    def _return_to_menu(self):
        """Standard return path to the Mode Selection Menu."""
        if self.leds: self.leds.to_standby.emit()
        self.setCurrentIndex(1)
        self.menu.setFocus()
        self._reset_inactivity_timer() # Resume inactivity timer

    def _return_to_welcome(self):
        """Return from Menu to WelcomeScreen and resume USB scanning"""
        if self.leds: self.leds.to_standby.emit()
        self.setCurrentIndex(0)
        self.welcome.setFocus()
        self._reset_inactivity_timer() # Resume inactivity timer

    def closeEvent(self, e):
        # Ensure LED workers and Ping workers are stopped
        try:
            if self.leds: self.leds.stop()
            self.ping.stop_ping()
            self.ship._stop_workers()
        except Exception:
            pass
        super().closeEvent(e)


# -------------------- Entry Point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Enable mouse tracking for QStackedWidget to capture mouse movement events globally
    # This helps the eventFilter catch activity to exit the WaitScreen
    for widget in QApplication.topLevelWidgets():
        widget.setMouseTracking(True)
        
    window = PalletPortalGUI(app)
    window.show()
    sys.exit(app.exec_())
