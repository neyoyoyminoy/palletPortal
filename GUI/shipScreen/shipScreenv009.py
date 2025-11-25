"""
this is shipScreenv008.py

layout goals:
- centered glitch title "SHIPMENT IN PROGRESS" (same behavior as welcome screen)
- left: rounded white bubble "<code> was scanned"
- left middle: pill-style progress bar with percent label underneath
- right: "SCANNED BARCODES" title + rounded white panel with list
- theme: black bg, white text, cyan accent
- includes 4-button exit combo (ctrl + c + v + enter/return)
"""

import sys  #for argv + exit
import random  #for glitch randomness
import string  #for glitch scrambling

from PyQt5.QtCore import Qt, QTimer, QRect, QSize  #qt core + timers + rect + size
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap  #drawing + fonts + images
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)  #basic widgets


CYAN_LOGO_PATH = "/mnt/ssd/PalletPortal/transparentCyanLogo.png"  #cyan logo path on jetson


# -------------------- glitch title widget --------------------
class GlitchTitle(QWidget):
    def __init__(self, text="SHIPMENT IN PROGRESS", parent=None):
        super().__init__(parent)
        self.text = text  #base text
        self.scrambled = text  #current scrambled text
        self.glitch_strength = 0  #how strong the current glitch frame is

        #slightly smaller so it never clips on 1024x600
        self.font = QFont("Arial", 36, QFont.Bold)

        self.timer = QTimer(self)  #timer for driving glitch frames
        self.timer.timeout.connect(self.update_glitch)  #hook to update method
        self.timer.start(60)  #about ~16 fps

    def update_glitch(self):
        if random.random() < 0.35:  #random chance to enter glitch mode
            self.glitch_strength = random.randint(3, 10)  #horizontal shift in px
            self.scramble()  #scramble characters a bit
        else:
            self.scrambled = self.text  #go back to clean text
            self.glitch_strength = 0  #no shift

        self.update()  #ask qt to repaint

    def scramble(self):
        chars = list(self.text)  #turn string into list for editing
        for i in range(len(chars)):
            if random.random() < 0.15:  #lower scramble rate for calmer look
                chars[i] = random.choice(string.ascii_uppercase + string.digits + "!@#$%*")
        self.scrambled = "".join(chars)  #back to string

    def paintEvent(self, e):
        p = QPainter(self)  #qt painter
        p.setRenderHint(QPainter.TextAntialiasing)  #smooth text edges
        p.setFont(self.font)  #apply font

        widget_rect = self.rect()  #full area of this widget
        text_rect = p.boundingRect(widget_rect, Qt.AlignCenter, self.scrambled)  #centered rect

        fm = self.fontMetrics()
        baseline_y = text_rect.y() + text_rect.height() - fm.descent()  #baseline inside rect

        x = text_rect.x()
        y = baseline_y

        # base white layer
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y, self.scrambled)

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
                jitter_y = y + random.randint(-20, 20)
                jitter_x = x + random.randint(-10, 10)
                p.setPen(QColor(255, 0, 255, 200))
                p.drawText(jitter_x, jitter_y, self.scrambled)

        p.end()


# -------------------- rounded bubble widgets --------------------
class ScanBubble(QWidget):
    """white rounded bubble for '<code> was scanned'"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.radius = 40

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 18, 40, 18)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color:#000000;")
        self.label.setFont(QFont("Arial", 20))
        layout.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(rect, self.radius, self.radius)
        p.end()
        super().paintEvent(e)


class RoundedPanel(QWidget):
    """white rounded panel for the scanned barcode list"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.radius = 40

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(rect, self.radius, self.radius)
        p.end()
        super().paintEvent(e)


# -------------------- pill-style progress bar --------------------
class PillProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0  #logical percent 0..100
        self._visual = 0.0  #animated fraction 0..1

        self._anim_timer = QTimer(self)  #timer to animate towards target
        self._anim_timer.timeout.connect(self._step_anim)
        self._anim_timer.start(30)  #smooth-ish animation

    def setValue(self, v):
        v = max(0, min(100, int(v)))
        self._value = v

    def _step_anim(self):
        target = self._value / 100.0
        if abs(self._visual - target) < 0.005:
            self._visual = target
        else:
            #simple easing towards target
            self._visual += (target - self._visual) * 0.12
        self.update()

    def minimumSizeHint(self):
        #fixed sensible pill size; QSize fixes previous tuple error
        return QSize(360, 40)

    def sizeHint(self):
        return self.minimumSizeHint()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 4 or h <= 4:
            p.end()
            return

        margin = 6  #outer margin around pill
        outer = QRect(margin, margin, w - 2 * margin, h - 2 * margin)
        if outer.width() <= 0 or outer.height() <= 0:
            p.end()
            return

        radius = outer.height() / 2

        # drop shadow
        shadow = outer.translated(0, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawRoundedRect(shadow, radius, radius)

        # outer pill (white track border)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QColor(0, 0, 0))
        p.drawRoundedRect(outer, radius, radius)

        # inner track
        track_margin = 4
        track = outer.adjusted(track_margin, track_margin, -track_margin, -track_margin)
        track_radius = track.height() / 2
        p.setBrush(QColor(210, 255, 250))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(track, track_radius, track_radius)

        # fill amount
        frac = max(0.0, min(1.0, float(self._visual)))
        fill_width = int(track.width() * frac)

        if fill_width > 0:
            fill = QRect(track.left(), track.top(), fill_width, track.height())
            p.setBrush(QColor(0, 255, 180))
            p.drawRoundedRect(fill, track_radius, track_radius)

        p.end()


# -------------------- main ship screen --------------------
class ShipScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")  #black bg
        self.setFocusPolicy(Qt.StrongFocus)  #needed for key combo
        self._pressed = set()  #keys that are currently down

        self._expected_codes = []  #manifest codes
        self._found = set()  #codes that have been scanned
        self._barcode_items = {}  #code -> listwidgetitem

        # ----- root layout -----
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(10)

        # glitch title at top
        self.title = GlitchTitle("SHIPMENT IN PROGRESS")
        self.title.setMinimumHeight(80)
        root.addWidget(self.title)

        # little gap between title and content
        root.addSpacing(30)

        # middle row = left column + right column
        middle = QHBoxLayout()
        middle.setSpacing(40)
        root.addLayout(middle, stretch=1)

        # =========== right column (built first so we can roughly align left bubble) ===========
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        middle.addLayout(right_col, stretch=4)

        subtitle = QLabel("SCANNED BARCODES")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#eaeaea;")
        subtitle.setFont(QFont("Arial", 26, QFont.Bold))
        right_col.addWidget(subtitle)

        self.panel = RoundedPanel()
        panel_layout = QVBoxLayout(self.panel)
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
        right_col.addWidget(self.panel)

        # =========== left column ===========
        left_col = QVBoxLayout()
        left_col.setSpacing(24)
        middle.insertLayout(0, left_col, stretch=3)

        # spacer to roughly align bubble top with panel top (subtitle + spacing height)
        left_col.addSpacing(52)

        # rounded bubble for "was scanned"
        self.bubble = ScanBubble()
        left_col.addWidget(self.bubble)

        # move progress bar further down toward middle of screen
        left_col.addSpacing(60)

        # custom pill progress bar
        self.progress = PillProgressBar()
        self.progress.setFixedHeight(40)
        left_col.addWidget(self.progress)

        # percent label
        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.percent_label.setStyleSheet("color:#ffffff;")
        self.percent_label.setFont(QFont("Arial", 18))
        left_col.addWidget(self.percent_label)

        # stretch so logo hugs bottom
        left_col.addStretch(1)

        # cyan logo bottom-left
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(96, 96)
        self.logo_label.setStyleSheet("background:transparent;")
        pm = QPixmap(CYAN_LOGO_PATH)
        if not pm.isNull():
            self.logo_label.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        left_col.addWidget(self.logo_label, alignment=Qt.AlignLeft | Qt.AlignBottom)

        root.addStretch(0)

    # --------------- manifest wiring ---------------
    def set_manifest_codes(self, codes):
        self._expected_codes = list(codes or [])
        self._found.clear()
        self._barcode_items.clear()
        self.scanned_list.clear()
        self.bubble.setText("")
        self.progress.setValue(0)
        self.percent_label.setText("0%")

        for code in self._expected_codes:
            item = QListWidgetItem(code)
            f = item.font()
            f.setPointSize(14)
            item.setFont(f)
            item.setForeground(QColor(0, 0, 0))
            self.scanned_list.addItem(item)
            self._barcode_items[code] = item

    # hook this to your barcode worker's matched signal: (val, score, method)
    def on_barcode_matched(self, val, score=None, method=None):
        if val in self._found:
            return  #already counted

        self._found.add(val)

        # update bubble text
        self.bubble.setText(f"{val} was scanned")

        # style item as completed
        item = self._barcode_items.get(val)
        if item:
            item.setForeground(QColor(150, 150, 150))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)

        # update progress bar percent
        total = len(self._expected_codes)
        if total > 0:
            pct = int(round(len(self._found) * 100.0 / total))
            self.progress.setValue(pct)
            self.percent_label.setText(f"{pct}%")

    # --------------- 4-button exit combo ---------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # hold ctrl + c + v and press enter/return to quit
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


# -------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShipScreen()
    w.showFullScreen()  #for the 1024x600 jetson display
    sys.exit(app.exec_())
