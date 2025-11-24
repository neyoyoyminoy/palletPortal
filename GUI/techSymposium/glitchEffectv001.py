"""
glitchEffectv001.py

this module provides a reusable glitch text widget for the pallet portal gui.
it is designed to match the welcome screen glitch behavior and can be reused
for titles like "WELCOME", "SHIPMENT IN PROGRESS", or "VIEW ORDERS".

if you pass in an led driver (like DualStripDriver from ledWorkerv001.py)
it will optionally sync the ws2812 strips to the glitch colors.
"""

import random  #for glitch randomness
import string  #for scramble characters

from PyQt5.QtCore import Qt, QTimer  #qt core + timers
from PyQt5.QtGui import QPainter, QColor, QFont  #drawing + fonts
from PyQt5.QtWidgets import QWidget, QApplication, QVBoxLayout  #basic widgets


class GlitchText(QWidget):
    def __init__(self, text="WELCOME", led_driver=None, font_size=72, parent=None):
        super().__init__(parent)
        self.text = text  #base text
        self.scrambled = text  #current scrambled text
        self.glitch_strength = 0  #how strong the current glitch frame is
        self.led = led_driver  #optional led driver (can be None)

        self.font = QFont("Arial", font_size, QFont.Bold)  #big bold font

        self.timer = QTimer(self)  #timer for driving glitch frames
        self.timer.timeout.connect(self.update_glitch)  #hook to update method
        self.timer.start(60)  #about ~16 fps

    def set_led_color(self, rgb):
        if not self.led:
            return  #no leds provided
        try:
            #expect something like DualStripDriver with set_all(rgb)
            self.led.set_all(rgb)
        except Exception:
            pass  #fail quietly so gui never crashes on led error

    def update_glitch(self):
        #random chance to enter or keep a glitch frame
        if random.random() < 0.35:  #glitch about 35% of frames
            self.glitch_strength = random.randint(3, 12)  #horizontal shift in px
            self.scramble()  #scramble characters a bit
        else:
            self.scrambled = self.text  #go back to clean text
            self.glitch_strength = 0  #no shift

        self.update()  #ask qt to repaint

    def scramble(self):
        chars = list(self.text)  #turn string into list for editing
        for i in range(len(chars)):
            if random.random() < 0.25:  #25% of chars get replaced
                chars[i] = random.choice(
                    string.ascii_uppercase + string.digits + "!@#$%*"
                )
        self.scrambled = "".join(chars)  #back to string

    def paintEvent(self, e):
        p = QPainter(self)  #qt painter
        p.setRenderHint(QPainter.TextAntialiasing)  #smooth text edges
        p.setFont(self.font)  #apply font

        #let qt decide the centered rect for the text inside the full widget
        widget_rect = self.rect()  #full area of this widget
        text_rect = p.boundingRect(
            widget_rect, Qt.AlignCenter, self.scrambled
        )  #qt-centered rect

        fm = self.fontMetrics()  #font metrics for baseline fix
        baseline_y = (
            text_rect.y() + text_rect.height() - fm.descent()
        )  #baseline inside rect

        x = text_rect.x()  #left edge for centered text
        y = baseline_y  #baseline y

        # base white layer
        p.setPen(QColor(255, 255, 255))  #white text
        p.drawText(x, y, self.scrambled)  #draw main text
        self.set_led_color((255, 255, 255))  #leds match base color

        # glitch overlays
        if self.glitch_strength > 0:
            shift = self.glitch_strength  #horizontal displacement

            # red channel shift (left)
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)
            self.set_led_color((255, 0, 0))  #leds flash red with this frame

            # cyan channel shift (right)
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)
            self.set_led_color((0, 255, 255))  #leds flash cyan

            # magenta jitter slice (random vertical offset)
            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)  #small vertical jump
                jitter_x = x + random.randint(-10, 10)  #small horizontal jitter
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)
                self.set_led_color((255, 0, 255))  #leds flash magenta

        p.end()


# -------------------- self-test harness --------------------
#this section lets you run this file standalone to preview the glitch
class _DemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("glitchEffectv001 demo")  #window title
        self.setStyleSheet("background-color: black;")  #black background
        self._pressed = set()  #tracks keys for exit combo

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.glitch = GlitchText("SHIPMENT IN PROGRESS", led_driver=None, font_size=48)
        layout.addWidget(self.glitch)

        self.setLayout(layout)

    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        #secret exit combo: hold ctrl + c + v, then press enter/return
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


if __name__ == "__main__":
    app = QApplication(sys.argv)  #start qt app
    w = _DemoWindow()
    w.showFullScreen()  #fullscreen test like on the jetson display
    sys.exit(app.exec_())  #run event loop
