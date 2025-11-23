"""
this is shipScreenv001.py

goals:
- layout matches qt design studio mockup
- title "SHIPMENT IN PROGRESS" with the same centered glitch effect as the welcome screen
- left: white bubble showing "<code> was scanned"
- center: green progress bar showing percentage complete
- right: rounded white panel listing manifest barcodes (strike-through when scanned)
- theme: black bg with white/cyan/magenta/red accents
- no "no barcodes scanned" spam; status only updates on real scans
- includes 4-button exit combo (ctrl + c + v + enter/return) for fullscreen tests
"""

import sys  #for argv + exit
from PyQt5.QtCore import Qt, QTimer  #qt core + timers
from PyQt5.QtGui import QPainter, QColor, QFont, QPainterPath, QPixmap  #drawing + fonts + images
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


CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"  #path to cyan logo png


#-------------------- glitch title widget (same centering as welcome) --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text  #base text
        self.font = QFont("Arial", 46, QFont.Bold)  #big bold title
        self.glitch_strength = 0  #horizontal pixel shift
        self._scrambled = text  #current frame text
        self._tick_count = 0  #slow down glitch pacing

        self._timer = QTimer(self)  #animation timer
        self._timer.timeout.connect(self._tick)  #hook tick
        self._timer.start(90)  #slower than welcome to feel calmer

    def _tick(self):
        import random, string  #local import so top stays clean

        self._tick_count += 1

        #only do a real glitch every few ticks so it doesn't feel too chaotic
        if self._tick_count % 4 == 0:
            if random.random() < 0.35:
                self.glitch_strength = random.randint(2, 6)  #small rgb offset
            else:
                self.glitch_strength = 0

            chars = list(self.text)
            for i in range(len(chars)):
                if random.random() < 0.05:  #low scramble rate
                    chars[i] = random.choice(string.ascii_uppercase + string.digits)
            self._scrambled = "".join(chars)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)  #painter for title
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        txt = self._scrambled

        #use painterpath to get precise bounding box for centering
        path = QPainterPath()
        path.addText(0, 0, self.font, txt)
        rect = path.boundingRect()

        x = (self.width() - rect.width()) / 2 - rect.left()
        y = (self.height() - rect.height()) / 2 - rect.top()

        shift = self.glitch_strength

        #base white text
        p.setPen(QColor(255, 255, 255))
        p.drawText(int(x), int(y + rect.height()), txt)

        #cyan shifted right
        p.setPen(QColor(0, 255, 255))
        p.drawText(int(x + shift), int(y + rect.height()), txt)

        #magenta shifted left
        p.setPen(QColor(255, 0, 255))
        p.drawText(int(x - shift), int(y + rect.height()), txt)

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

        #glitch title at top
        self.title = GlitchTitle("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(100)
        root.addWidget(self.title)

        #middle row = left column + right column
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        #===== left column: bubble + progress bar =====
        left_col = QVBoxLayout()
        left_col.setSpacing(24)
        middle.addLayout(left_col, stretch=3)

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

        #progress bar label
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
        #fake "scale 2.2" by stretching horizontally via minimum width
        self.progress.setMinimumWidth(360)
        left_col.addWidget(self.progress)

        #stretch so logo hugs bottom
        left_col.addStretch(1)

        #cyan logo bottom-left
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(96, 96)
        self.logo_label.setStyleSheet("background:transparent;")
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo_label.setPixmap(pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
