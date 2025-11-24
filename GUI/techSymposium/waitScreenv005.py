"""
waitScreenv005.py

dvd-style bouncing pallet portal logo
- cycles through white, cyan, red, magenta logos as it hits walls
- optional link to ledWorkerv001.DualStripDriver (if provided) so leds match logo color
- 4-button exit combo (ctrl + c + v + enter/return)
- standalone demo just runs full screen until combo is pressed
"""

import sys  #for argv + exit
import random  #for initial direction
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap, QColor
from PyQt5.QtWidgets import QApplication, QWidget

#update these paths to match your palletportal folder if needed
LOGO_PATHS = [
    "/mnt/ssd/PalletPortal/transparentWhiteLogo.png",
    "/mnt/ssd/PalletPortal/transparentCyanLogo.png",
    "/mnt/ssd/PalletPortal/transparentRedLogo.png",
    "/mnt/ssd/PalletPortal/transparentMagentaLogo.png",
]


class WaitScreen(QWidget):
    def __init__(self, led_driver=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("pallet portal wait screen")
        self.setStyleSheet("background-color:black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()

        self.led = led_driver

        self.logo_size = 180
        self.logos = []
        for path in LOGO_PATHS:
            pm = QPixmap(path)
            if not pm.isNull():
                self.logos.append(
                    pm.scaled(self.logo_size, self.logo_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        if not self.logos:
            self.logos.append(QPixmap(self.logo_size, self.logo_size))

        self.color_index = 0
        self.current_logo = self.logos[self.color_index]

        self.x = 50
        self.y = 50

        speed_min = 1.5
        speed_max = 3.0
        self.dx = random.choice([-1, 1]) * random.uniform(speed_min, speed_max)
        self.dy = random.choice([-1, 1]) * random.uniform(speed_min, speed_max)

        self.margin = 0
        self._corner_hit = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(16)

        self._apply_led_color()

    def _apply_led_color(self):
        if not self.led:
            return
        idx = self.color_index % 4
        if idx == 0:
            c = (255, 255, 255)
        elif idx == 1:
            c = (0, 255, 255)
        elif idx == 2:
            c = (255, 0, 0)
        else:
            c = (255, 0, 255)
        try:
            self.led.set_all(c)
        except Exception:
            pass

    def _next_color(self):
        self.color_index = (self.color_index + 1) % len(self.logos)
        self.current_logo = self.logos[self.color_index]
        self._apply_led_color()

    def update_frame(self):
        w = self.width()
        h = self.height()

        lw = self.current_logo.width()
        lh = self.current_logo.height()

        self.x += self.dx
        self.y += self.dy

        hit_x = False
        hit_y = False

        if self.x <= self.margin:
            self.x = self.margin
            self.dx *= -1
            hit_x = True
        elif self.x + lw >= w - self.margin:
            self.x = w - self.margin - lw
            self.dx *= -1
            hit_x = True

        if self.y <= self.margin:
            self.y = self.margin
            self.dy *= -1
            hit_y = True
        elif self.y + lh >= h - self.margin:
            self.y = h - self.margin - lh
            self.dy *= -1
            hit_y = True

        if hit_x or hit_y:
            self._next_color()

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        p.drawPixmap(int(self.x), int(self.y), self.current_logo)
        p.end()

    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            QApplication.quit()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


# -------------------- standalone demo --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = WaitScreen(led_driver=None)
    w.showFullScreen()
    sys.exit(app.exec_())
