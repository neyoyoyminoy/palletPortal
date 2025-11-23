"""
shipScreenv007.py

layout:
- top: "SHIPMENT IN PROGRESS" glitch title (same effect family as welcome screen)
- left mid: white rounded bubble "<code> was scanned"
- left lower mid: pill-style progress bar + percent label under it
- right: subtitle "SCANNED BARCODES" + rounded white panel with all manifest codes
- bottom-left: cyan logo

notes:
- themed for black background + cyan/magenta/red highlights
- includes 4-button exit combo for fullscreen testing (ctrl + c + v + enter/return)
- demo driver at bottom fakes scans so you can test layout without cameras
"""

import sys  #for argv + exit
import random  #for glitch scrambling
import string  #for glitch scrambling
from PyQt5.QtCore import Qt, QTimer, QEasingCurve  #qt core + timers + easing
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QFont,
    QPainterPath,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFrame,
)

CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"  #cyan logo path


#-------------------- glitch title widget (welcome-style, resized) --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text  #base text
        self.scrambled = text  #current scrambled text
        self.glitch_strength = 0  #horizontal shift amount
        self.font = QFont("Arial", 48, QFont.Bold)  #slightly smaller so it never clips

        self.timer = QTimer(self)  #timer for driving glitch frames
        self.timer.timeout.connect(self.update_glitch)  #hook to update method
        self.timer.start(60)  #about ~16 fps

    def update_glitch(self):
        #this mirrors the welcome screen feel but toned a bit for title usage
        if random.random() < 0.35:  #random chance to enter glitch mode
            self.glitch_strength = random.randint(3, 8)  #slightly smaller shift to avoid clipping
            self.scramble()  #scramble characters a bit
        else:
            self.scrambled = self.text  #go back to clean text
            self.glitch_strength = 0  #no shift

        self.update()  #ask qt to repaint

    def scramble(self):
        chars = list(self.text)  #turn string into list for editing
        for i in range(len(chars)):
            if random.random() < 0.20:  #scramble some chars
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)  #back to string

    def paintEvent(self, e):
        p = QPainter(self)  #qt painter
        p.setRenderHint(QPainter.TextAntialiasing)  #smooth text edges
        p.setFont(self.font)  #apply font

        widget_rect = self.rect()  #full widget rect
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)  #centered rect

        fm = self.fontMetrics()  #font metrics
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()  #baseline inside rect

        x = text_rect.x()  #left edge
        y = baseline_y  #baseline y

        # base white layer
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

        # glitch overlays only when active
        if self.glitch_strength > 0:
            shift = self.glitch_strength

            # red channel shift (left)
            p.setPen(QColor(255, 0, 0, 180))
            p.drawText(x - shift, y, self.scrambled)

            # cyan channel shift (right)
            p.setPen(QColor(0, 255, 255, 180))
            p.drawText(x + shift, y, self.scrambled)

            # magenta jitter slice
            if random.random() < 0.4:
                jitter_y = y + random.randint(-12, 12)
                jitter_x = x + random.randint(-8, 8)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


#-------------------- pill progress bar (drawn manually) --------------------
class PillProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0  #0.0 to 1.0 logical value
        self._anim_value = 0.0  #smoothed value
        self._anim_timer = QTimer(self)  #timer for lerp style easing
        self._anim_timer.timeout.connect(self._step_anim)  #drive step
        self._anim_timer.start(16)  #~60 fps
        self._easing = QEasingCurve.InOutCubic  #soft ease

    def set_fraction(self, frac):
        #clamp and store target value
        frac = max(0.0, min(1.0, float(frac)))
        self._value = frac  #target value

    def _step_anim(self):
        #simple eased interpolation toward target
        target = self._value
        current = self._anim_value

        #no heavy easing math; just move a fraction each frame
        delta = target - current
        if abs(delta) < 0.001:
            self._anim_value = target
            self.update()
            return

        self._anim_value += delta * 0.15  #move 15% toward target each frame
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(4, 4, -4, -4)  #outer pill margin
        radius = rect.height() / 2.0

        #outer border (dark)
        p.setPen(QColor(0, 0, 0))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRoundedRect(rect, radius, radius)

        #inner track (light)
        inner = rect.adjusted(4, 4, -4, -4)
        inner_radius = inner.height() / 2.0
        p.setPen(QColor(220, 255, 250))
        p.setBrush(QColor(220, 255, 250))
        p.drawRoundedRect(inner, inner_radius, inner_radius)

        #fill based on animated value
        frac = max(0.0, min(1.0, self._anim_value))
        if frac > 0.0:
            fill_width = inner.width() * frac
            fill_rect = inner.adjusted(0, 0, -(inner.width() - fill_width), 0)
            fill_radius = fill_rect.height() / 2.0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 255, 170))  #bright cyan/green fill
            p.drawRoundedRect(fill_rect, fill_radius, fill_radius)

        p.end()


#-------------------- main ship screen --------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._pressed = set()  #tracks keys for exit combo

        self._expected_codes = []
        self._found = set()
        self._barcode_items = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(24)

        #----- glitch title at top -----
        self.title = GlitchTitle("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(90)
        root.addWidget(self.title)

        #----- middle row (left + right) -----
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        #========== left column ==========
        left_col = QVBoxLayout()
        left_col.setSpacing(28)
        middle.addLayout(left_col, stretch=3)

        #rounded white bubble (same radius style as right panel)
        self.bubble = QFrame()
        self.bubble.setObjectName("scanBubble")
        self.bubble.setAttribute(Qt.WA_StyledBackground, True)  #force stylesheet painting
        self.bubble.setStyleSheet(
            """
            QFrame#scanBubble {
                background-color:#ffffff;
                border-radius:40px;
            }
            """
        )
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(40, 20, 40, 20)

        self.scan_msg = QLabel("")
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setStyleSheet("color:#000000;")
        self.scan_msg.setFont(QFont("Arial", 20))
        bubble_layout.addWidget(self.scan_msg)

        left_col.addWidget(self.bubble)

        #progress pill
        self.progress_pill = PillProgressBar()
        self.progress_pill.setFixedHeight(30)
        self.progress_pill.setMinimumWidth(420)
        left_col.addWidget(self.progress_pill)

        #percent label under pill
        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignCenter)
        self.percent_label.setStyleSheet("color:#ffffff;")
        self.percent_label.setFont(QFont("Arial", 20))
        left_col.addWidget(self.percent_label)

        #stretch so logo hugs bottom
        left_col.addStretch(1)

        #cyan logo bottom-left
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(96, 96)
        self.logo_label.setStyleSheet("background:transparent;")
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo_label.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        left_col.addWidget(self.logo_label, alignment=Qt.AlignLeft | Qt.AlignBottom)

        #========== right column ==========
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        middle.addLayout(right_col, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        subtitle.setStyleSheet("color:#eaeaea;")
        subtitle.setFont(QFont("Arial", 26, QFont.Bold))
        right_col.addWidget(subtitle)

        #white rounded panel for list
        panel = QFrame()
        panel.setObjectName("scanPanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setStyleSheet(
            """
            QFrame#scanPanel {
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
                padding:4px;
            }
            """
        )
        panel_layout.addWidget(self.scanned_list)
        right_col.addWidget(panel)

        root.addStretch(0)

    #--------------- manifest wiring ---------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.scan_msg.setText("")
        self.progress_pill.set_fraction(0.0)
        self.percent_label.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    #this is what you hook to BarcodeReaderWorker.matched
    def on_barcode_matched(self, val, score=None, method=None):
        if val in self._found:
            return

        self._found.add(val)

        #bubble text
        self.scan_msg.setText(f"{val} was scanned")

        #gray + strike-through the item
        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        #update percent + pill
        total = len(self._expected_codes)
        if total > 0:
            frac = len(self._found) / float(total)
            pct = int(round(frac * 100.0))
            self.progress_pill.set_fraction(frac)
            self.percent_label.setText(f"{pct}%")

    #--------------- 4-button exit combo ---------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        #hold ctrl + c + v and press enter/return to quit
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


#-------------------- standalone demo driver --------------------
class _DemoDriver:
    #this just fakes scans over time so you can test the ui in isolation
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
        self.timer.start(1600)  #fake scan every 1.6 s

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
    w.showFullScreen()  #fullscreen on 1024x600 jetson display

    #demo driver for standalone testing
    demo = _DemoDriver(w)

    sys.exit(app.exec_())
