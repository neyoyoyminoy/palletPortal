"""
this is shipScreenv003.py

goals:
- same layout as your qt design studio mockup
- title "SHIPMENT IN PROGRESS" using the exact glitch class from the welcome screen
- left middle: "<code> was scanned" bubble + progress bar stacked and vertically centered
- right: rounded white panel with scanned barcodes
- theme: black bg + white/cyan/magenta/red accents
- only shows "<code> was scanned" on real scans (no spam)
- keeps 4-button exit combo (ctrl + c + v + enter/return)
"""

import sys  #for argv + exit
import random  #for glitch + demo scans
import string  #for glitch scramble
from PyQt5.QtCore import Qt, QTimer  #qt core + timers
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap  #drawing + fonts + images
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
)  #basic widgets


CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"  #cyan logo path


#-------------------- glitch text widget (copied from welcome, leds disabled) --------------------
class GlitchText(QWidget):
    def __init__(self, text="WELCOME", led_driver=None):
        super().__init__()
        self.text = text  #base text
        self.scrambled = text  #current scrambled text
        self.glitch_strength = 0  #how strong the current glitch frame is
        self.led = led_driver  #led driver (unused here, left for api match)

        self.font = QFont("Arial", 60, QFont.Bold)  #big bold font (slightly smaller for long title)
        self.setStyleSheet("background-color: black;")  #black background

        self.timer = QTimer(self)  #timer for driving glitch frames
        self.timer.timeout.connect(self.update_glitch)  #hook to update method
        self.timer.start(60)  #about ~16 fps

    def set_led_color(self, rgb):
        if not self.led:
            return  #no leds provided
        self.led.set_all(rgb)  #push color to both strips

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

        #let qt decide the centered rect for the text inside the full widget
        widget_rect = self.rect()  #full area of this widget
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)  #qt-centered rect

        fm = self.fontMetrics()  #font metrics for baseline fix
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()  #baseline inside rect

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


#-------------------- main ship screen --------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")  #black bg
        self.setFocusPolicy(Qt.StrongFocus)  #needed for key combo
        self._pressed = set()  #keys that are currently down

        self._expected_codes = []  #manifest codes
        self._found = set()  #codes that have been scanned
        self._barcode_items = {}  #code -> listwidgetitem

        #----- layout skeleton -----
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)

        #glitch title at top (same widget as welcome screen, different text)
        self.title = GlitchText("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(120)  #extra height so it never clips
        root.addWidget(self.title)

        #middle row = left column + right column
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        #===== left column: bubble + progress bar centered + logo bottom =====
        left_col = QVBoxLayout()
        left_col.setSpacing(24)
        middle.addLayout(left_col, stretch=3)

        #top stretch so center block ends up in the middle
        left_col.addStretch(1)

        #bubble wrapper
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
        bubble_layout.setContentsMargins(40, 18, 40, 18)

        self.scan_msg = QLabel("")  #shows "<code> was scanned"
        self.scan_msg.setAlignment(Qt.AlignCenter)
        self.scan_msg.setStyleSheet("color:#000000;")  #black text on white bubble
        self.scan_msg.setFont(QFont("Arial", 20))
        bubble_layout.addWidget(self.scan_msg)

        left_col.addWidget(self.bubble)

        #gap between bubble and progress bar
        left_col.addSpacing(18)

        #progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")  #show percent
        self.progress.setFixedHeight(26)
        self.progress.setStyleSheet(
            """
            QProgressBar {
                background-color:#202020;
                border-radius:4px;
                color:#ffffff;
                text-align:center;
            }
            QProgressBar::chunk {
                background-color:#00ff7f;
                border-radius:4px;
            }
            """
        )
        self.progress.setMinimumWidth(360)
        left_col.addWidget(self.progress)

        #bottom stretch so bubble+bar block is vertically centered
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

        #===== right column: subtitle + white rounded panel with list =====
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        middle.addLayout(right_col, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        subtitle.setStyleSheet("color:#eaeaea;")
        subtitle.setFont(QFont("Arial", 24, QFont.Bold))
        right_col.addWidget(subtitle)

        #white panel wrapper
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
                padding:4px;
            }
            """
        )
        panel_layout.addWidget(self.scanned_list)
        right_col.addWidget(panel)

        #small spacer under everything
        root.addStretch(0)

    #--------------- manifest wiring ---------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])  #copy list
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.scan_msg.setText("")  #clear last message
        self.progress.setValue(0)

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))  #black text
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    #hook this to your barcode worker's matched signal: (val, score, method)
    def on_barcode_matched(self, val, score=None, method=None):
        if val in self._found:
            return  #already counted

        self._found.add(val)

        #update bubble text
        self.scan_msg.setText(f"{val} was scanned")

        #style item as completed
        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(150, 150, 150))  #gray
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        #update progress bar percent
        total = len(self._expected_codes)
        if total > 0:
            pct = int(round(len(self._found) * 100.0 / total))
            self.progress.setValue(pct)

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
#this is just to test layout + behavior without cameras plugged in
class _DemoDriver:
    def __init__(self, screen: ShipScreen):
        self.screen = screen  #ship screen ref
        demo_codes = [
            "1234567891",
            "9876543210",
            "PALLET-001",
            "PALLET-002",
            "PALLET-003",
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
        self.screen.on_barcode_matched(code, score=100, method="demo")  #simulate match


#-------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()  #for the 1024x600 jetson display
    demo = _DemoDriver(w)  #remove this when wiring to real barcode workers
    sys.exit(app.exec_())
