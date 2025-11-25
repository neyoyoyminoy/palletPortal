"""
welcome.py
Glitch welcome screen for Pallet Portal.
- Uses glitch effect identical to your original welcome screen
- Syncs LEDs through injected LED driver
- Displays project logo top-left
- Shows bottom pill prompt
- 30-second idle timeout → WaitScreen
- Ctrl + C + V + Enter forces exit
"""

import sys
import random
import string
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication


# ---------------------------------------------------------
#  Glitch Text (identical to your working welcome screen)
# ---------------------------------------------------------
class GlitchText(QWidget):
    def __init__(self, text="WELCOME", led_driver=None):
        super().__init__()
        self.text = text
        self.scrambled = text
        self.glitch_strength = 0
        self.led = led_driver

        self.font = QFont("Arial", 72, QFont.Bold)
        self.setStyleSheet("background-color: black;")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)

    def set_led_color(self, rgb):
        if self.led:
            self.led.set_all(rgb)

    def update_glitch(self):
        if random.random() < 0.35:
            self.glitch_strength = random.randint(3, 12)
            self.scramble()
        else:
            self.scrambled = self.text
            self.glitch_strength = 0

        self.update()

    def scramble(self):
        chars = list(self.text)
        for i in range(len(chars)):
            if random.random() < 0.25:
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)

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
        self.set_led_color((255, 255, 255))

        if self.glitch_strength:
            s = self.glitch_strength

            # red left
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - s, y, self.scrambled)
            self.set_led_color((255, 0, 0))

            # cyan right
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + s, y, self.scrambled)
            self.set_led_color((0, 255, 255))

            # magenta jitter
            if random.random() < 0.4:
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(x + random.randint(-10, 10),
                           y + random.randint(-20, 20),
                           self.scrambled)
                self.set_led_color((255, 0, 255))

        p.end()


# ---------------------------------------------------------
#  Welcome Screen
# ---------------------------------------------------------
class WelcomeScreen(QWidget):

    usbReady = pyqtSignal(object, str)      # (ShipmentList, mount_dir)
    timeoutToWait = pyqtSignal()            # 30s inactivity triggers wait screen

    def __init__(self, led_driver=None):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()
        self.usbWatcher = None
        self.led = led_driver

        # idle timeout timer
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(30_000)  # 30 seconds
        self.idle_timer.timeout.connect(self._timeout_trigger)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.glitch = GlitchText("WELCOME", led_driver)
        layout.addWidget(self.glitch)

        self.setLayout(layout)

        # load logo
        self.logo = QPixmap("/mnt/ssd/PalletPortal/transparentWhiteLogo.png")

    # USB watcher injected by palletPortal.py
    def inject_usb_watcher(self, watcher):
        self.usbWatcher = watcher
        watcher.validListFound.connect(self.usbReady)

    # -------------------
    # Idle Timeout Handler
    # -------------------
    def _timeout_trigger(self):
        self.timeoutToWait.emit()

    def reset_idle(self):
        self.idle_timer.stop()
        self.idle_timer.start()

    # -------------------
    # Event Overrides
    # -------------------
    def showEvent(self, e):
        super().showEvent(e)
        self.reset_idle()
        if self.usbWatcher:
            self.usbWatcher.start()

    def keyPressEvent(self, e):
        self.reset_idle()  # Reset idle timer on ANY key

        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # Exit combo
        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            QApplication.quit()
            return

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())

    # -------------------
    # Paint (logo + pill)
    # -------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        # draw top-left logo
        if not self.logo.isNull():
            pm = self.logo.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(20, 20, pm)

        # draw bottom pill
        pill_w = 524
        pill_h = 56
        pill_x = (self.width() - pill_w) // 2
        pill_y = self.height() - 140

        p.setPen(QColor(234, 234, 234))
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 30, 30)

        p.setFont(QFont("Arial", 32))
        p.setPen(QColor(0, 0, 0))
        text = "Insert flashdrive to begin..."

        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        tx = pill_x + (pill_w - tw) // 2
        ty = pill_y + (pill_h + th) // 2 - fm.descent()

        p.drawText(tx, ty, text)

        p.end()


# -------------------
# Standalone test
# -------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = WelcomeScreen()
    w.showFullScreen()
    sys.exit(app.exec_())
