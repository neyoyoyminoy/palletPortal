"""
wait.py
Pallet Portal – Bouncing Logo Idle Screen (DVD style)

Features:
- Black background
- Bouncing logo with color cycling (white → cyan → red → magenta)
- LED strip synced with current logo color (via injected led_driver)
- Corner hits trigger rainbow “celebration” LED chase
- Secret exit combo: hold CTRL + C + V, then press ENTER/RETURN
"""

import random
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QWidget


# --------------------------------------------------------
# Utility: convert hue angle → RGB triple (0-255)
# --------------------------------------------------------
def hue_to_rgb(h):
    h = float(h % 360)
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


# --------------------------------------------------------
# File paths for logos & LED colors (theme colors)
# --------------------------------------------------------
LOGO_PATHS = [
    "/mnt/ssd/PalletPortal/transparentWhiteLogo.png",
    "/mnt/ssd/PalletPortal/transparentCyanLogo.png",
    "/mnt/ssd/PalletPortal/transparentRedLogo.png",
    "/mnt/ssd/PalletPortal/transparentMagentaLogo.png",
]

LED_COLORS = [
    (255, 255, 255),  # white
    (0, 255, 255),    # cyan
    (255, 0, 0),      # red
    (255, 0, 255),    # magenta
]


# --------------------------------------------------------
# Bouncing Logo Screen
# --------------------------------------------------------
class WaitScreen(QWidget):
    def __init__(self, led_driver=None):
        super().__init__()

        self.leds = led_driver

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background-color: black;")

        # load + scale logo frames
        self.logo_size = 180
        self.logos = []
        for path in LOGO_PATHS:
            pm = QPixmap(path)
            if not pm.isNull():
                self.logos.append(
                    pm.scaled(
                        self.logo_size,
                        self.logo_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )

        # safety fallback
        if not self.logos:
            self.logos.append(QPixmap(self.logo_size, self.logo_size))

        # initial logo + LED color
        self.color_index = 0
        self.current_logo = self.logos[self.color_index]
        if self.leds:
            self.leds.set_all(LED_COLORS[self.color_index])

        # initial position + random motion
        self.x = 50
        self.y = 50
        speed_min, speed_max = 2.0, 3.0
        self.dx = random.choice([-1, 1]) * random.uniform(speed_min, speed_max)
        self.dy = random.choice([-1, 1]) * random.uniform(speed_min, speed_max)

        # edge spacing
        self.margin = 0

        # rainbow celebration → LED chase
        self.celebrating = False
        self.celebrate_step = 0
        self.celebrate_timer = QTimer(self)
        self.celebrate_timer.timeout.connect(self._celebrate_frame)

        # exit combo
        self._pressed = set()

        # main animation loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(16)  # ~60fps redraw

    # ----------------------------------------------------
    # LED celebration animation (corner hit)
    # ----------------------------------------------------
    def _celebrate_frame(self):
        order = [0, 1, 2, 3, 4, 9, 8, 7, 6, 5]  # 10-LED CCW chase
        hue = (self.celebrate_step * 25) % 360
        r, g, b = hue_to_rgb(hue)

        if self.leds:
            # build pattern for 10 LEDs
            active = order[self.celebrate_step % len(order)]
            pattern = [(0, 0, 0)] * 10
            pattern[active] = (r, g, b)

            # map 10 → two strips of 5
            for i in range(5):
                self.leds.strip0.RGBto3Bytes(i, *pattern[i])
                self.leds.strip1.RGBto3Bytes(i, *pattern[5 + i])

            self.leds.strip0.LED_show()
            self.leds.strip1.LED_show()

        self.celebrate_step += 1

        # stop after ~40 frames
        if self.celebrate_step >= 40:
            self.celebrate_timer.stop()
            self.celebrating = False

    # ----------------------------------------------------
    # Normal LED/logo color cycle
    # ----------------------------------------------------
    def _switch_color(self):
        self.color_index = (self.color_index + 1) % len(self.logos)
        self.current_logo = self.logos[self.color_index]

        if self.leds:
            self.leds.set_all(LED_COLORS[self.color_index])

    # ----------------------------------------------------
    # Main animation update
    # ----------------------------------------------------
    def update_frame(self):
        w, h = self.width(), self.height()
        lw, lh = self.current_logo.width(), self.current_logo.height()

        # move
        self.x += self.dx
        self.y += self.dy

        # hit checks
        hit_left = (self.x <= self.margin)
        hit_right = (self.x + lw >= w - self.margin)
        hit_top = (self.y <= self.margin)
        hit_bottom = (self.y + lh >= h - self.margin)

        # bounce
        hit_edge = False
        if hit_left:
            self.x = self.margin
            self.dx *= -1
            hit_edge = True
        elif hit_right:
            self.x = w - lw - self.margin
            self.dx *= -1
            hit_edge = True

        if hit_top:
            self.y = self.margin
            self.dy *= -1
            hit_edge = True
        elif hit_bottom:
            self.y = h - lh - self.margin
            self.dy *= -1
            hit_edge = True

        # corner detection
        corner = (
            (hit_left and hit_top)
            or (hit_left and hit_bottom)
            or (hit_right and hit_top)
            or (hit_right and hit_bottom)
        )

        if corner:
            self.celebrating = True
            self.celebrate_step = 0
            self.celebrate_timer.start(50)
        elif hit_edge and not self.celebrating:
            self._switch_color()

        self.update()

    # ----------------------------------------------------
    # Drawing
    # ----------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        p.drawPixmap(int(self.x), int(self.y), self.current_logo)
        p.end()

    # ----------------------------------------------------
    # Exit combo: CTRL + C + V + ENTER
    # ----------------------------------------------------
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
            self.close()  # caller handles navigation
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)
