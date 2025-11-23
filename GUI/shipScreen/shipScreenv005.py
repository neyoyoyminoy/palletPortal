"""
shipScreenv005.py

updates from v004:
- left bubble now fully rounded to match right panel
- bubble top aligned visually with right white panel (not the subtitle)
- progress bar + percent moved to just below halfway down the screen
- replaces qprogressbar with a custom pill-style floating bar
  similar to the video reference (thick outline, inner white track,
  soft rounded fill) with a subtle pulse animation
- keeps the same glitch title class as the welcome screen
- keeps 4-key exit combo (ctrl + c + v + enter/return)
"""

import sys, random, string, math
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QFont,
    QFontMetrics,
    QPixmap,
    QLinearGradient,
    QBrush,
)
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"


#-------------------- glitch text widget (exact welcome version, smaller font) --------------------
class GlitchText(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", led_driver=None):
        super().__init__()
        self.text = text  #base text
        self.scrambled = text  #current scrambled text
        self.glitch_strength = 0  #how strong the current glitch frame is
        self.led = led_driver  #placeholder for leds (not used here)

        self.font = QFont("Arial", 56, QFont.Bold)  #slightly smaller so it fits on 1024 width
        self.setStyleSheet("background-color: black;")  #black background

        self.timer = QTimer(self)  #timer for driving glitch frames
        self.timer.timeout.connect(self.update_glitch)  #hook to update method
        self.timer.start(60)  #about ~16 fps

    def set_led_color(self, rgb):
        if not self.led:
            return  #no leds provided

    def update_glitch(self):
        if random.random() < 0.35:  #random chance to enter glitch mode
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
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)  #back to string

    def paintEvent(self, e):
        p = QPainter(self)  #qt painter
        p.setRenderHint(QPainter.TextAntialiasing)  #smooth text edges
        p.setFont(self.font)  #apply font

        widget_rect = self.rect()  #full area of this widget
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)  #qt-centered rect

        fm = QFontMetrics(self.font)  #font metrics for baseline fix
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()  #baseline inside rect

        x = text_rect.x()  #left edge for centered text
        y = baseline_y  #baseline y

        # base white layer
        p.setPen(QColor(255, 255, 255))  #white text
        p.drawText(x, y, self.scrambled)  #draw main text

        # glitch overlays
        if self.glitch_strength > 0:
            shift = self.glitch_strength  #horizontal displacement

            # red channel shift (left)
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan channel shift (right)
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter slice (random vertical offset)
            if random.random() < 0.4:
                jitter_y = y + random.randint(-20, 20)  #small vertical jump
                jitter_x = x + random.randint(-10, 10)  #small horizontal jitter
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


#-------------------- custom pill-style progress bar --------------------
class PillProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0  #0-100
        self._phase = 0.0  #pulse phase

        self.setMinimumHeight(34)  #tall enough to show the pill
        self.setMaximumHeight(40)

        self._timer = QTimer(self)  #small animation timer
        self._timer.timeout.connect(self._tick)  #drive pulse
        self._timer.start(40)  #about 25 fps

    def setValue(self, v):
        v = max(0, min(100, int(v)))  #clamp 0-100
        if v != self._value:
            self._value = v
            self.update()  #redraw

    def value(self):
        return self._value

    def _tick(self):
        self._phase = (self._phase + 0.04) % (2 * math.pi)  #spin phase
        if self._value > 0:  #only bother animating when something is filled
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        outer_rect = QRectF(2, 2, w - 4, h - 4)
        radius = outer_rect.height() / 2.0

        # outer black border with white interior track
        p.setPen(QColor(0, 0, 0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(outer_rect, radius, radius)

        inner_rect = outer_rect.adjusted(4, 4, -4, -4)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(240, 240, 240))
        p.drawRoundedRect(inner_rect, radius - 4, radius - 4)

        # filled portion
        if self._value > 0:
            fill_width = inner_rect.width() * (self._value / 100.0)
            # keep the pill end nice when small
            min_width = inner_rect.height()
            fill_width = max(fill_width, min_width)
            fill_rect = QRectF(inner_rect.left(), inner_rect.top(),
                               min(fill_width, inner_rect.width()), inner_rect.height())

            # base gradient
            grad = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            base = QColor(0, 190, 140)
            end = QColor(0, 230, 170)
            grad.setColorAt(0.0, base)
            grad.setColorAt(1.0, end)

            p.setBrush(QBrush(grad))
            p.drawRoundedRect(fill_rect, radius - 5, radius - 5)

            # soft glow/pulse band in center
            pulse = 0.35 * (1.0 + math.sin(self._phase))  #0..0.7
            glow_color = QColor(255, 255, 255, int(80 * pulse))
            glow_rect = fill_rect.adjusted(4, 4, -4, -4)
            p.setBrush(glow_color)
            p.drawRoundedRect(glow_rect, radius - 8, radius - 8)

        p.end()


#-------------------- main ship screen --------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()  #tracks key combo

        self._expected_codes = []  #manifest list
        self._found = set()  #matched codes
        self._barcode_items = {}  #code -> list item

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(10)

        #--- glitch title at top ---
        self.title = GlitchText("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(90)
        root.addWidget(self.title)

        #--- middle row ---
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        #==================== left column ====================
        left = QVBoxLayout()
        left.setSpacing(20)
        middle.addLayout(left, stretch=3)

        #small spacer so bubble top lines up visually with right panel top
        left.addSpacing(40)

        # bubble container
        self.bubble = QWidget()
        self.bubble.setStyleSheet(
            """
            QWidget {
                background-color:#ffffff;
                border-radius:40px;
            }
            """
        )
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(32, 20, 32, 20)

        self.scan_msg = QLabel("")
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setFont(QFont("Arial", 24))
        bubble_layout.addWidget(self.scan_msg)

        left.addWidget(self.bubble)

        #spacer between bubble and progress area to land around mid-screen
        left.addSpacing(60)

        # custom pill progress bar
        self.progress = PillProgress()
        left.addWidget(self.progress)

        # percent label underneath
        self.percent_lbl = QLabel("0%")
        self.percent_lbl.setAlignment(Qt.AlignCenter)
        self.percent_lbl.setFont(QFont("Arial", 20, QFont.Bold))
        self.percent_lbl.setStyleSheet("color:#ffffff;")
        left.addWidget(self.percent_lbl)

        left.addStretch(1)

        #cyan logo bottom-left
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(96, 96)
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo_label.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        left.addWidget(self.logo_label, alignment=Qt.AlignLeft | Qt.AlignBottom)

        #==================== right column ====================
        right = QVBoxLayout()
        right.setSpacing(12)
        middle.addLayout(right, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Arial", 28, QFont.Bold))
        subtitle.setStyleSheet("color:#eaeaea;")
        right.addWidget(subtitle)

        panel = QWidget()
        panel.setStyleSheet(
            """
            QWidget {
                background-color:#ffffff;
                border-radius:40px;
            }
            """
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)

        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        self.scanned_list.setStyleSheet(
            """
            QListWidget {
                background-color:#ffffff;
                border:0px;
                color:#000000;
            }
            QListWidget::item {
                padding:6px;
            }
            """
        )
        panel_layout.addWidget(self.scanned_list)
        right.addWidget(panel)

    #-------------------- manifest setup --------------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.scan_msg.setText("")
        self.progress.setValue(0)
        self.percent_lbl.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(16)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    #hook this to barcode worker's matched signal
    def on_barcode_matched(self, val, score=None, method=None):
        if val in self._found:
            return

        self._found.add(val)
        self.scan_msg.setText(f"{val} was scanned")

        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        total = len(self._expected_codes)
        if total > 0:
            pct = int(round(len(self._found) * 100.0 / total))
            self.progress.setValue(pct)
            self.percent_lbl.setText(f"{pct}%")

    #-------------------- 4-button exit combo --------------------
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


#-------------------- demo driver for standalone testing --------------------
class _DemoDriver:
    def __init__(self, screen: ShipScreen):
        self.screen = screen
        demo_codes = [
            "1234567891",
            "9876543210",
            "2085692649",
            "9340754051",
            "2799407451",
        ]
        self.screen.set_manifest_codes(demo_codes)
        self._remaining = list(demo_codes)

        self.timer = QTimer()
        self.timer.timeout.connect(self._fake_scan)
        self.timer.start(1700)  #fake scan every 1.7 s

    def _fake_scan(self):
        if not self._remaining:
            self.timer.stop()
            return
        code = self._remaining.pop(0)
        self.screen.on_barcode_matched(code, score=100, method="demo")


#-------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()  #target 1024x600 screen
    demo = _DemoDriver(w)  #remove when wiring in real barcode workers
    sys.exit(app.exec_())
