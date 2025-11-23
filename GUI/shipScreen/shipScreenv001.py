"""
this is shipScreenv001.py

goals:
- standalone ship screen to test layout + theme
- title "SHIPMENT IN PROGRESS" with glitch effect (like welcome screen)
- black background + glitch color palette (white/cyan/magenta/red)
- show "1234 scanned" only when a barcode is actually scanned
- keep "SCANNED BARCODES" subtitle in all caps
- wired with helper methods so main gui can plug real barcode workers later
- includes 4-button exit combo (ctrl + c + v + enter/return) for fullscreen tests
"""

import sys  #for argv + exit
import random  #for demo fake scans
from PyQt5.QtCore import Qt, QTimer  #qt core
from PyQt5.QtGui import QPainter, QColor, QFont  #drawing + fonts
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)  #basic widgets


#-------------------- glitch title widget --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text  #base text
        self.font = QFont("Arial", 42, QFont.Bold)  #title font
        self.glitch_strength = 0  #horizontal shift for rgb layers
        self.scramble_chance = 0.08  #small random twitch
        self._timer = QTimer(self)  #animation timer
        self._timer.timeout.connect(self._tick)  #hook to tick
        self._timer.start(70)  #~14 fps

    def _tick(self):
        #simple low-key glitch motion
        import string, random as _r  #inline so file stays light

        if _r.random() < 0.30:
            self.glitch_strength = _r.randint(1, 6)  #small offset
        else:
            self.glitch_strength = 0

        #occasionally scramble a couple chars just for flavor
        chars = list(self.text)
        for i in range(len(chars)):
            if _r.random() < self.scramble_chance:
                chars[i] = _r.choice(string.ascii_uppercase + string.digits)
        self._scrambled = "".join(chars)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)  #painter
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        fm = self.fontMetrics()
        txt = getattr(self, "_scrambled", self.text)
        text_w = fm.horizontalAdvance(txt)
        text_h = fm.height()

        x = (self.width() - text_w) // 2
        y = (self.height() + text_h) // 2 - fm.descent()

        shift = self.glitch_strength

        #base white layer
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, txt)

        #cyan layer offset right
        p.setPen(QColor(0, 255, 255))
        p.drawText(x + shift, y, txt)

        #magenta layer offset left
        p.setPen(QColor(255, 0, 255))
        p.drawText(x - shift, y, txt)

        p.end()


#-------------------- ship screen ui --------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")  #black bg theme
        self.setFocusPolicy(Qt.StrongFocus)  #needed for key combo
        self._pressed = set()  #track keys for secret exit

        self._expected_codes = []  #manifest codes
        self._found = set()  #matched codes
        self._barcode_items = {}  #code -> list item

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        #glitch title at top
        self.title = GlitchTitle("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(100)
        layout.addWidget(self.title)

        #status label shows only meaningful events
        self.status = QLabel("")  #blank until first scan
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:#ffffff;")
        self.status.setFont(QFont("Beausite Classic", 22))
        layout.addWidget(self.status)

        #subtitle
        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#00ffff;")  #cyan accent
        subtitle.setFont(QFont("Beausite Classic", 18))
        layout.addWidget(subtitle)

        #list of manifest barcodes
        self.scanned_list = QListWidget()
        self.scanned_list.setSelectionMode(QListWidget.NoSelection)
        self.scanned_list.setStyleSheet(
            """
            QListWidget {
                background-color:#050505;
                color:#ffffff;
                border:1px solid #ff00ff;
            }
            QListWidget::item {
                padding:6px;
            }
            QListWidget::item:selected {
                background-color:#202020;
            }
            """
        )
        layout.addWidget(self.scanned_list, stretch=1)

    #--------------- manifest wiring ---------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])  #copy list
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            item.setForeground(QColor(255, 255, 255))
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

        self.status.setText("")  #reset status text

    #this is intended to be connected to your barcode worker's 'matched' signal
    #signature compatible with your existing _on_match(val, score, method)
    def on_barcode_matched(self, val, score=None, method=None):
        if val in self._found:
            return  #already counted

        self._found.add(val)
        self.status.setText(f"{val} scanned")  #only show on actual scans

        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(160, 160, 160))  #fade to gray
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

    #--------------- exit combo handling ---------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        #ctrl + c + v + enter/return exits
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


#-------------------- standalone demo --------------------
#this lets you test the screen on the jetson without cameras
class _DemoDriver:
    def __init__(self, screen: ShipScreen):
        self.screen = screen  #ship screen ref
        #fake manifest codes for demo
        demo_codes = [
            "1234567890",
            "2468135790",
            "ABC123XYZ",
            "PALLET-001",
            "PALLET-002",
        ]
        self.screen.set_manifest_codes(demo_codes)
        self._remaining = list(demo_codes)

        self.timer = QTimer()
        self.timer.timeout.connect(self._fake_scan)
        self.timer.start(1500)  #scan every 1.5s

    def _fake_scan(self):
        if not self._remaining:
            self.timer.stop()
            return
        code = self._remaining.pop(0)
        #simulate a real matched barcode event
        self.screen.on_barcode_matched(code, score=100, method="demo")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()  #fullscreen on 1024x600 display

    #demo driver for testing without cameras
    demo = _DemoDriver(w)

    sys.exit(app.exec_())
